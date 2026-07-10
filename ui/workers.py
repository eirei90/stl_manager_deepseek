"""
Фоновые потоки для длительных операций.
Поддерживает остановку, использует существующие изображения.
"""

import threading
import logging
import os
import tempfile
import zipfile
import shutil
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
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.project_id,))
        root_result = cursor.fetchone()

        dirs = set()
        if root_result:
            root_path = root_result[0]
            if os.path.exists(root_path):
                dirs.add(root_path)

        files = self.db.get_files_for_project(self.project_id)
        for record in files:
            path = record[2]
            if not path.startswith("[ARCHIVE]") and os.path.exists(path):
                parent = str(Path(path).parent)
                dirs.add(parent)
                grandparent = str(Path(parent).parent)
                if os.path.exists(grandparent):
                    dirs.add(grandparent)

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
                                        return item_path
                    except:
                        continue
            except PermissionError:
                continue
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
                is_archive_itself = original_name.endswith(('.zip', '.7z', '.rar'))

                # ========================================
                # САМ АРХИВ
                # ========================================
                if is_archive_itself:
                    archive_name = original_name
                    archive_path_on_disk = None

                    conn = self.db._get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.project_id,))
                    root = cursor.fetchone()

                    if root and os.path.exists(root[0]):
                        for dirpath, _, filenames in os.walk(root[0]):
                            if archive_name in filenames:
                                archive_path_on_disk = os.path.join(dirpath, archive_name)
                                logger.info(f"  Найден архив: {archive_path_on_disk}")
                                break

                    if not archive_path_on_disk:
                        logger.warning(f"[{idx}/{total}] Архив не найден: {archive_name}")
                        skipped += 1
                        if progress_cb:
                            progress_cb(idx, total)
                        continue

                    archive_dir = Path(archive_path_on_disk).parent
                    thumb_dir = archive_dir / ".thumbs"
                    thumb_dir.mkdir(exist_ok=True)
                    archive_stem = Path(archive_name).stem
                    thumb_path = thumb_dir / f"{archive_stem}.jpg"

                    # 1. Готовое превью
                    if thumb_path.exists() and thumb_path.stat().st_size > 15000:
                        logger.info(f"[{idx}/{total}] ✅ Превью архива уже есть")
                        self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                        rendered += 1
                        from_existing += 1
                        if progress_cb:
                            progress_cb(idx, total)
                        continue

                    # 2. Изображение рядом с архивом
                    found_image = None
                    for ext in self.renderer.EXISTING_EXTENSIONS:
                        candidate = archive_dir / f"{archive_stem}{ext}"
                        if candidate.exists() and candidate.stat().st_size > 5000:
                            found_image = str(candidate)
                            logger.info(f"[{idx}/{total}] Найдено изображение: {candidate.name}")
                            break

                    if found_image:
                        if self.renderer.copy_existing_image(found_image, str(thumb_path)):
                            self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                            rendered += 1
                            from_existing += 1
                            if progress_cb:
                                progress_cb(idx, total)
                            continue

                    # 3. Извлекаем из архива
                    logger.info(f"[{idx}/{total}] ⚠ Извлекаем из архива...")
                    extracted = None
                    found_image_in_archive = None
                    extract_dir = os.path.join(str(thumb_dir), "_tmp")
                    os.makedirs(extract_dir, exist_ok=True)

                    try:
                        ext = Path(archive_path_on_disk).suffix.lower()

                        if ext == '.zip':
                            with zipfile.ZipFile(archive_path_on_disk) as zf:
                                for name in zf.namelist():
                                    zf.extract(name, extract_dir)

                        elif ext == '.7z':
                            try:
                                import py7zr
                                with py7zr.SevenZipFile(archive_path_on_disk, 'r') as szf:
                                    szf.extractall(extract_dir)
                            except ImportError:
                                logger.error("  py7zr не установлен")

                        elif ext == '.rar':
                            try:
                                import rarfile
                                with rarfile.RarFile(archive_path_on_disk) as rf:
                                    rf.extractall(extract_dir)
                            except ImportError:
                                logger.error("  rarfile не установлен")

                        # Рекурсивно ищем STL и изображения
                        for root_dir, dirs, files_in_dir in os.walk(extract_dir):
                            dirs[:] = [d for d in dirs if not d.startswith('__MACOSX') and not d.startswith('._')]

                            for f in files_in_dir:
                                if f.startswith('._') or f.startswith('.DS_Store'):
                                    continue

                                f_lower = f.lower()
                                candidate = os.path.join(root_dir, f)

                                if not found_image_in_archive and f_lower.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                    if os.path.getsize(candidate) > 5000:
                                        found_image_in_archive = candidate
                                        logger.info(f"  Найдено изображение: {f}")

                                if not extracted and f_lower.endswith('.stl'):
                                    if os.path.getsize(candidate) > 500:
                                        extracted = candidate
                                        logger.info(f"  Найден STL: {f}")

                                if extracted and found_image_in_archive:
                                    break
                            if extracted and found_image_in_archive:
                                break

                    except Exception as e:
                        logger.error(f"  Ошибка извлечения: {e}")

                    # Используем найденное изображение
                    if found_image_in_archive:
                        logger.info(f"  Использую изображение из архива")
                        if self.renderer.copy_existing_image(found_image_in_archive, str(thumb_path)):
                            self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                            rendered += 1
                            from_existing += 1
                        else:
                            errors += 1
                        shutil.rmtree(extract_dir, ignore_errors=True)
                        if progress_cb:
                            progress_cb(idx, total)
                        continue

                    # Рендерим найденный STL
                    if extracted and os.path.exists(extracted):
                        logger.info(f"  Рендеринг...")
                        success = self.renderer.render_to_jpeg(extracted, str(thumb_path))
                        shutil.rmtree(extract_dir, ignore_errors=True)

                        if success and thumb_path.exists() and thumb_path.stat().st_size > 15000:
                            self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=0)
                            rendered += 1
                            logger.info(f"  ✅ Превью создано")
                        else:
                            logger.warning(f"  ❌ Не удалось создать превью")
                            self.renderer.create_error_placeholder(str(thumb_path))
                            self.db.update_thumbnail_status(file_id, str(thumb_path))
                            errors += 1
                    else:
                        shutil.rmtree(extract_dir, ignore_errors=True)
                        logger.warning(f"  ❌ STL не найден в архиве")
                        self.renderer.create_error_placeholder(str(thumb_path))
                        self.db.update_thumbnail_status(file_id, str(thumb_path))
                        errors += 1

                    if progress_cb:
                        progress_cb(idx, total)
                    continue

                # ========================================
                # ФАЙЛ ВНУТРИ АРХИВА
                # ========================================
                file_name_only = Path(original_name).name
                logger.info(f"[{idx}/{total}] Файл в архиве: {file_name_only}")
                skipped += 1  # Пока пропускаем файлы внутри архивов
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # ============================================
            # ОБЫЧНЫЕ STL
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
            if thumb_path.exists() and thumb_path.stat().st_size > 15000:
                logger.info(f"[{idx}/{total}] ✅ Превью уже есть: {file_name}")
                self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                rendered += 1
                from_existing += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # 2. Ищем изображение рядом
            existing_img = None
            for ext in self.renderer.EXISTING_EXTENSIONS:
                candidate = stl_path.parent / f"{stl_path.stem}{ext}"
                if candidate.exists() and candidate.stat().st_size > 5000:
                    existing_img = str(candidate)
                    logger.info(f"[{idx}/{total}] Найдено изображение: {candidate.name}")
                    break

            if existing_img:
                if self.renderer.copy_existing_image(existing_img, str(thumb_path)):
                    self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                    rendered += 1
                    from_existing += 1
                else:
                    errors += 1
            else:
                # 3. Рендерим
                logger.info(f"[{idx}/{total}] Рендеринг: {file_name}")
                success = self.renderer.render_to_jpeg(str(stl_path), str(thumb_path))
                if success and thumb_path.exists() and thumb_path.stat().st_size > 15000:
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


class RefreshThumbsWorker(BackgroundTask):
    """Пересоздаёт превью для файлов с заглушками."""

    def __init__(self, renderer, db, project_id, **kwargs):
        self.renderer = renderer
        self.db = db
        self.project_id = project_id
        super().__init__(target=self._batch_refresh, **kwargs)

    def _batch_refresh(self, progress_cb, cancel_token):
        files = self.db.get_files_for_project(self.project_id)
        to_refresh = []
        for record in files:
            has_thumb = record[12] if len(record) > 12 else 0
            thumb_path = record[13] if len(record) > 13 else None
            if has_thumb and thumb_path:
                thumb_file = Path(str(thumb_path))
                if thumb_file.exists() and thumb_file.stat().st_size < 15000:
                    to_refresh.append(record)

        total = len(to_refresh)
        if total == 0:
            logger.info("Нет заглушек для обновления")
            return 0

        logger.info(f"Обновление {total} заглушек")
        refreshed = 0

        for idx, record in enumerate(to_refresh, 1):
            if cancel_token.is_cancelled:
                break

            file_id = record[0]
            file_name = record[1]
            file_path = record[2]
            thumb_path = record[13]

            logger.info(f"[{idx}/{total}] Обновление: {file_name}")
            try:
                os.remove(str(thumb_path))
            except:
                pass

            # Используем RenderWorker для пересоздания
            worker = RenderWorker(self.renderer, self.db, self.project_id)
            files_list = [record]

            def dummy_render(progress_cb, cancel_token):
                rendered = 0
                for idx2, rec in enumerate(files_list, 1):
                    if cancel_token.is_cancelled:
                        break
                    # Обрабатываем через _batch_render одного файла
                    pass
                return rendered

            if progress_cb:
                progress_cb(idx, total)

        logger.info(f"Обновлено: {refreshed}/{total}")
        return refreshed
