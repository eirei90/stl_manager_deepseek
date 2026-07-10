"""
Фоновые потоки для длительных операций.
Поддерживает остановку, использует существующие изображения.
"""

import threading
import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CancellationToken:
    def __init__(self):
        self._cancelled = False
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def cancel(self):
        with self._lock:
            self._cancelled = True


class BackgroundTask(threading.Thread):
    def __init__(self, target, on_progress=None, on_complete=None,
                 on_error=None, on_cancelled=None, cancellation_token=None):
        super().__init__(daemon=True)
        self._target = target
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._on_cancelled = on_cancelled
        self.cancellation_token = cancellation_token or CancellationToken()
        self._result = None
        self._error = None

    def run(self):
        try:
            self._result = self._target(self._report_progress, self.cancellation_token)
            if self.cancellation_token.is_cancelled:
                if self._on_cancelled:
                    self._on_cancelled()
            else:
                if self._on_complete:
                    self._on_complete(self._result)
        except Exception as e:
            if not self.cancellation_token.is_cancelled:
                logger.error(f"Ошибка потока: {e}", exc_info=True)
                self._error = e
                if self._on_error:
                    self._on_error(str(e))

    def _report_progress(self, current, total):
        if self._on_progress and not self.cancellation_token.is_cancelled:
            self._on_progress(current, total)

    def cancel(self):
        self.cancellation_token.cancel()


class ScanWorker(BackgroundTask):
    def __init__(self, scanner, root_path, **kwargs):
        def target(progress, token):
            return scanner.scan_directory(root_path, progress, token)
        super().__init__(target=target, **kwargs)


class RenderWorker(BackgroundTask):
    def __init__(self, renderer, db, project_id, **kwargs):
        self.renderer = renderer
        self.db = db
        self.project_id = project_id
        super().__init__(target=self._batch_render, **kwargs)

    def _find_archive(self, file_name: str) -> Optional[str]:
        """Ищет архив, содержащий указанный файл."""
        # Получаем корневую папку проекта
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.project_id,))
        root_result = cursor.fetchone()

        dirs = set()

        # Добавляем корневую папку проекта
        if root_result:
            root_path = root_result[0]
            if os.path.exists(root_path):
                dirs.add(root_path)

        # Собираем директории из файлов проекта
        files = self.db.get_files_for_project(self.project_id)
        for record in files:
            path = record[2]
            if not path.startswith("[ARCHIVE]") and os.path.exists(path):
                parent = str(Path(path).parent)
                dirs.add(parent)
                # Добавляем родительскую директорию
                grandparent = str(Path(parent).parent)
                if os.path.exists(grandparent):
                    dirs.add(grandparent)

        logger.debug(f"Поиск архива для '{file_name}' в {len(dirs)} директориях")

        # Ищем архив
        for dir_path in dirs:
            if not os.path.exists(dir_path):
                continue
            try:
                for item in os.listdir(dir_path):
                    item_path = os.path.join(dir_path, item)
                    if not os.path.isfile(item_path):
                        continue
                    ext = Path(item).suffix.lower()
                    if ext not in ('.zip', '.7z', '.rar'):
                        continue

                    try:
                        if ext == '.zip':
                            with zipfile.ZipFile(item_path) as zf:
                                for name in zf.namelist():
                                    if file_name in name or Path(name).name == file_name:
                                        logger.info(f"  Найден архив: {item_path}")
                                        return item_path
                    except Exception as e:
                        logger.debug(f"  Ошибка чтения {item}: {e}")
            except PermissionError:
                continue

        logger.warning(f"  Архив не найден для: {file_name}")
        return None

    def _extract_from_archive(self, archive_path: str, file_name: str) -> Optional[str]:
        """Извлекает файл из архива во временную директорию."""
        tmp = tempfile.mkdtemp(prefix="stl_thumb_")
        try:
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path) as zf:
                    for name in zf.namelist():
                        if file_name in name or Path(name).name == file_name:
                            zf.extract(name, tmp)
                            extracted = os.path.join(tmp, name)
                            if os.path.exists(extracted):
                                return extracted
        except Exception as e:
            logger.error(f"Ошибка извлечения: {e}")
        return None

    def _batch_render(self, progress_cb, cancel_token):
        files = self.db.get_files_for_project(self.project_id)
        total = len(files)
        rendered = 0
        from_existing = 0
        skipped = 0
        errors = 0

        logger.info(f"Рендеринг {total} файлов")

        for idx, record in enumerate(files, 1):
            if cancel_token.is_cancelled:
                break

            file_id = record[0]
            file_name = record[1]
            file_path = record[2]
            is_valid = record[11] if len(record) > 11 else 1

            if not is_valid:
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # ============================================
            # ФАЙЛЫ ИЗ АРХИВОВ
            # ============================================
            if file_path.startswith("[ARCHIVE]"):
                original_name = file_path.replace("[ARCHIVE] ", "")

                # Проверяем: это сам архив или файл внутри?
                is_archive_itself = original_name.endswith(('.zip', '.7z', '.rar'))

                # ========================================
                # САМ АРХИВ (не файл внутри)
                # ========================================
                if is_archive_itself:
                    archive_name = original_name
                    archive_path_on_disk = None

                    # Ищем архив на диске
                    conn = self.db._get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.project_id,))
                    root = cursor.fetchone()

                    if root and os.path.exists(root[0]):
                        # Рекурсивно ищем архив в корневой папке
                        for dirpath, _, filenames in os.walk(root[0]):
                            if archive_name in filenames:
                                archive_path_on_disk = os.path.join(dirpath, archive_name)
                                logger.info(f"  Найден архив: {archive_path_on_disk}")
                                break

                    if archive_path_on_disk:
                        archive_dir = Path(archive_path_on_disk).parent
                        thumb_dir = archive_dir / ".thumbs"
                        thumb_dir.mkdir(exist_ok=True)
                        archive_stem = Path(archive_name).stem
                        thumb_path = thumb_dir / f"{archive_stem}.jpg"

                        # 1. Готовое превью
                        if thumb_path.exists() and thumb_path.stat().st_size > 100:
                            logger.info(f"[{idx}/{total}] ✅ Превью архива уже есть")
                            self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                            rendered += 1
                            from_existing += 1
                            if progress_cb:
                                progress_cb(idx, total)
                            continue

                        # 2. Ищем изображение с именем архива
                        found_image = None
                        for ext in self.renderer.EXISTING_EXTENSIONS:
                            candidate = archive_dir / f"{archive_stem}{ext}"
                            if candidate.exists():
                                found_image = str(candidate)
                                logger.info(f"[{idx}/{total}] Найдено изображение: {candidate.name}")
                                break

                        if found_image:
                            if self.renderer.copy_existing_image(found_image, str(thumb_path)):
                                self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                                rendered += 1
                                from_existing += 1
                        else:
                            # Заглушка для архива
                            self.renderer.create_error_placeholder(str(thumb_path))
                            self.db.update_thumbnail_status(file_id, str(thumb_path))
                            logger.info(f"[{idx}/{total}] Создана заглушка для архива")
                            rendered += 1
                    else:
                        logger.warning(f"[{idx}/{total}] Архив не найден: {archive_name}")
                        skipped += 1

                    if progress_cb:
                        progress_cb(idx, total)
                    continue

                # ========================================
                # ФАЙЛ ВНУТРИ АРХИВА
                # ========================================
                file_name_only = Path(original_name).name
                logger.info(f"[{idx}/{total}] Архив: {file_name_only}")

                archive_path = self._find_archive(file_name_only)

                if archive_path:
                    archive_dir = Path(archive_path).parent
                    thumb_dir = archive_dir / ".thumbs"
                    thumb_dir.mkdir(exist_ok=True)
                    archive_stem = Path(archive_path).stem
                    file_stem = Path(file_name_only).stem
                    thumb_path = thumb_dir / f"{archive_stem}__{file_stem}.jpg"

                    # 1. Готовое превью
                    if thumb_path.exists() and thumb_path.stat().st_size > 100:
                        logger.info(f"  ✅ Превью уже существует")
                        self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                        rendered += 1
                        from_existing += 1
                        if progress_cb:
                            progress_cb(idx, total)
                        continue

                    # 2. Ищем изображение
                    found_image = None
                    for ext in self.renderer.EXISTING_EXTENSIONS:
                        candidate = archive_dir / f"{archive_stem}{ext}"
                        if candidate.exists():
                            found_image = str(candidate)
                            break
                        candidate = archive_dir / f"{file_stem}{ext}"
                        if candidate.exists():
                            found_image = str(candidate)
                            break

                    if found_image:
                        if self.renderer.copy_existing_image(found_image, str(thumb_path)):
                            self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                            rendered += 1
                            from_existing += 1
                            if progress_cb:
                                progress_cb(idx, total)
                            continue

                    # 3. Извлекаем и рендерим
                    extracted = self._extract_from_archive(archive_path, file_name_only)
                    if extracted and os.path.exists(extracted):
                        existing = self.renderer.find_existing_image(extracted)
                        if existing:
                            if self.renderer.copy_existing_image(existing, str(thumb_path)):
                                self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                                rendered += 1
                                from_existing += 1
                        else:
                            success = self.renderer.render_to_jpeg(extracted, str(thumb_path))
                            if success and thumb_path.exists():
                                self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=0)
                                rendered += 1
                            else:
                                self.renderer.create_error_placeholder(str(thumb_path))
                                self.db.update_thumbnail_status(file_id, str(thumb_path))
                                errors += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

                if progress_cb:
                    progress_cb(idx, total)
                continue

            # ============================================
            # ОБЫЧНЫЕ STL ФАЙЛЫ
            # ============================================
            stl_path = Path(file_path)
            if not stl_path.exists():
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            thumb_dir = stl_path.parent / ".thumbs"
            thumb_dir.mkdir(exist_ok=True, parents=True)
            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"

            # 1. Готовое превью
            if thumb_path.exists() and thumb_path.stat().st_size > 100:
                logger.info(f"[{idx}/{total}] ✅ Превью уже есть: {file_name}")
                self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                rendered += 1
                from_existing += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # 2. Ищем изображение рядом с STL
            existing_img = None
            for ext in self.renderer.EXISTING_EXTENSIONS:
                candidate = stl_path.parent / f"{stl_path.stem}{ext}"
                if candidate.exists():
                    existing_img = str(candidate)
                    logger.info(f"[{idx}/{total}] Найдено изображение: {candidate.name}")
                    break

            if not existing_img:
                existing_img = self.renderer.find_existing_image(str(stl_path))

            if existing_img:
                if self.renderer.copy_existing_image(existing_img, str(thumb_path)):
                    self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                    rendered += 1
                    from_existing += 1
                else:
                    errors += 1
            else:
                # 3. Рендерим
                success = self.renderer.render_to_jpeg(str(stl_path), str(thumb_path))
                if success and thumb_path.exists():
                    self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=0)
                    rendered += 1
                else:
                    self.renderer.create_error_placeholder(str(thumb_path))
                    self.db.update_thumbnail_status(file_id, str(thumb_path))
                    errors += 1

            if progress_cb:
                progress_cb(idx, total)

        logger.info(f"Готово: {rendered} (из существующих: {from_existing}), пропущено: {skipped}, ошибок: {errors}")
        return rendered
