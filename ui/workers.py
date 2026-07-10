"""
Фоновые потоки для выполнения длительных операций без зависания GUI.
Поддерживает остановку операций и рендеринг файлов из архивов.
"""

import threading
import logging
import tempfile
import shutil
from typing import Callable, Optional
from pathlib import Path
import os

logger = logging.getLogger(__name__)

# Импорт для работы с архивами
try:
    from services.archive_utils import ArchiveExtractor
    ARCHIVE_SUPPORT = True
except ImportError:
    ARCHIVE_SUPPORT = False
    logger.warning("archive_utils не найден, файлы из архивов будут пропущены")


class CancellationToken:
    """Токен для безопасной остановки фоновых операций."""

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
            logger.info("Операция отменена пользователем")

    def reset(self):
        with self._lock:
            self._cancelled = False


class BackgroundTask(threading.Thread):
    """Базовый класс для фоновой задачи с поддержкой отмены."""

    def __init__(
        self,
        target: Callable,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_cancelled: Optional[Callable] = None,
        cancellation_token: Optional[CancellationToken] = None
    ):
        super().__init__(daemon=True)
        self._target = target
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._on_cancelled = on_cancelled
        self._result = None
        self._error = None
        self.cancellation_token = cancellation_token or CancellationToken()

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
            if self.cancellation_token.is_cancelled:
                if self._on_cancelled:
                    self._on_cancelled()
            else:
                logger.error(f"Ошибка в фоновом потоке: {e}", exc_info=True)
                self._error = e
                if self._on_error:
                    self._on_error(str(e))

    def _report_progress(self, current: int, total: int):
        if self._on_progress and not self.cancellation_token.is_cancelled:
            self._on_progress(current, total)

    def cancel(self):
        self.cancellation_token.cancel()
        logger.info("Запрошена отмена операции")

    @property
    def result(self):
        return self._result

    @property
    def error(self):
        return self._error


class ScanWorker(BackgroundTask):
    """Поток для сканирования директории."""

    def __init__(self, scanner, root_path: str, **kwargs):
        self.scanner = scanner
        self.root_path = root_path

        def scan_target(progress_cb, cancel_token):
            return scanner.scan_directory(root_path, progress_cb, cancel_token)

        super().__init__(target=scan_target, **kwargs)


class RenderWorker(BackgroundTask):
    """Поток для пакетного рендеринга превью с поддержкой файлов из архивов."""

    def __init__(self, renderer, db, project_id: int, **kwargs):
        self.renderer = renderer
        self.db = db
        self.project_id = project_id

        # Временная директория для извлечения файлов из архивов
        self._temp_dir = tempfile.mkdtemp(prefix="stl_render_")

        def render_target(progress_cb, cancel_token):
            try:
                return self._batch_render(progress_cb, cancel_token)
            finally:
                # Очищаем временную директорию
                self._cleanup_temp()

        super().__init__(target=render_target, **kwargs)

    def _cleanup_temp(self):
        """Очищает временную директорию."""
        try:
            if os.path.exists(self._temp_dir):
                shutil.rmtree(self._temp_dir)
                logger.debug(f"Временная директория очищена: {self._temp_dir}")
        except Exception as e:
            logger.warning(f"Не удалось очистить временную директорию: {e}")

    def _extract_from_archive(self, archive_path: str, file_name: str) -> Optional[str]:
        """
        Извлекает конкретный файл из архива во временную директорию.
        """
        import zipfile

        try:
            archive_name = Path(archive_path).stem
            extract_dir = os.path.join(self._temp_dir, archive_name)
            os.makedirs(extract_dir, exist_ok=True)

            logger.debug(f"  Извлечение из {archive_path}")
            logger.debug(f"  Искомый файл: {file_name}")

            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    # Показываем содержимое архива для отладки
                    all_names = zf.namelist()
                    logger.debug(f"  Содержимое архива ({len(all_names)} файлов):")
                    for n in all_names[:5]:
                        logger.debug(f"    - {n}")

                    # Ищем файл
                    for name in all_names:
                        # Проверяем разные варианты совпадения
                        if (file_name in name or
                                name.endswith(file_name) or
                                Path(name).name == file_name):

                            zf.extract(name, extract_dir)
                            extracted_path = os.path.join(extract_dir, name)

                            # Создаём директории если нужно
                            os.makedirs(os.path.dirname(extracted_path), exist_ok=True)

                            if os.path.exists(extracted_path):
                                logger.info(f"  ✅ Извлечён: {name}")
                                return extracted_path

            elif archive_path.endswith('.7z'):
                try:
                    import py7zr
                    with py7zr.SevenZipFile(archive_path, 'r') as szf:
                        for name in szf.getnames():
                            if (file_name in name or
                                    name.endswith(file_name) or
                                    Path(name).name == file_name):

                                szf.extract(extract_dir, targets=[name])
                                extracted_path = os.path.join(extract_dir, name)
                                if os.path.exists(extracted_path):
                                    return extracted_path
                except ImportError:
                    logger.error("py7zr не установлен")

            elif archive_path.endswith('.rar'):
                try:
                    import rarfile
                    with rarfile.RarFile(archive_path) as rf:
                        for info in rf.infolist():
                            if (file_name in info.filename or
                                    info.filename.endswith(file_name) or
                                    Path(info.filename).name == file_name):

                                rf.extract(info, extract_dir)
                                extracted_path = os.path.join(extract_dir, info.filename)
                                if os.path.exists(extracted_path):
                                    return extracted_path
                except ImportError:
                    logger.error("rarfile не установлен")

            logger.warning(f"  Файл '{file_name}' не найден в архиве")
            return None

        except Exception as e:
            logger.error(f"  Ошибка извлечения: {e}")
            return None

    def _find_archive_for_file(self, file_name: str) -> Optional[str]:
        """
        Ищет архив, содержащий указанный файл.
        Ищет в директориях проекта и родительских директориях.
        """
        # Получаем все файлы проекта для поиска директорий
        files = self.db.get_files_for_project(self.project_id)

        # Собираем все уникальные директории + родительские
        dirs_to_search = set()

        for record in files:
            path = record[2]
            if not path.startswith("[ARCHIVE]"):
                parent = str(Path(path).parent)
                dirs_to_search.add(parent)
                # Добавляем также родительскую директорию
                grandparent = str(Path(parent).parent)
                dirs_to_search.add(grandparent)

        # Также получаем корневую папку проекта
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.project_id,))
        result = cursor.fetchone()
        if result:
            dirs_to_search.add(result[0])

        logger.debug(f"Поиск архива для '{file_name}' в {len(dirs_to_search)} директориях")

        # Ищем архивы во всех найденных директориях
        for dir_path in dirs_to_search:
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

                    # Проверяем, содержит ли архив нужный файл
                    try:
                        if ext == '.zip':
                            import zipfile
                            with zipfile.ZipFile(item_path, 'r') as zf:
                                for name in zf.namelist():
                                    # Проверяем: полное совпадение имени файла
                                    # или файл находится внутри архива
                                    if file_name in name or name.endswith(file_name):
                                        logger.info(f"  Найден архив: {item_path}")
                                        logger.info(f"    Содержит: {name}")
                                        return item_path

                        elif ext == '.7z':
                            try:
                                import py7zr
                                with py7zr.SevenZipFile(item_path, 'r') as szf:
                                    for name in szf.getnames():
                                        if file_name in name or name.endswith(file_name):
                                            logger.info(f"  Найден архив: {item_path}")
                                            return item_path
                            except ImportError:
                                pass

                        elif ext == '.rar':
                            try:
                                import rarfile
                                with rarfile.RarFile(item_path) as rf:
                                    for info in rf.infolist():
                                        if file_name in info.filename or info.filename.endswith(file_name):
                                            logger.info(f"  Найден архив: {item_path}")
                                            return item_path
                            except ImportError:
                                pass

                    except Exception as e:
                        logger.debug(f"  Ошибка чтения архива {item_path}: {e}")
                        continue

            except PermissionError:
                continue

        logger.warning(f"  Архив не найден для '{file_name}'")
        logger.debug(f"  Проверены директории: {list(dirs_to_search)[:5]}")
        return None

    def _batch_render(self, progress_cb, cancel_token) -> int:
        """Рендерит превью для всех файлов проекта."""
        files = self.db.get_files_for_project(self.project_id)
        total = len(files)
        rendered = 0
        skipped = {
            'not_valid': 0,
            'archive': 0,
            'not_found': 0,
            'already_has_thumb': 0
        }
        errors = 0

        logger.info(f"=" * 60)
        logger.info(f"НАЧАЛО РЕНДЕРИНГА")
        logger.info(f"  Проект ID: {self.project_id}")
        logger.info(f"  Всего файлов: {total}")
        logger.info(f"  Метод: {self.renderer.method}")
        logger.info(f"=" * 60)

        for idx, file_record in enumerate(files, 1):
            if cancel_token.is_cancelled:
                logger.info(f"⏹ Прервано. Обработано: {idx-1}/{total}")
                break

            file_id = file_record[0]
            file_name = file_record[1]
            file_path = file_record[2]
            is_valid = file_record[11] if len(file_record) > 11 else 1

            # Пропускаем невалидные
            if not is_valid:
                logger.debug(f"[{idx}/{total}] ПРОПУЩЕН (невалидный): {file_name}")
                skipped['not_valid'] += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # === Обработка файлов из архивов ===
            if file_path.startswith("[ARCHIVE]"):
                original_name = file_path.replace("[ARCHIVE] ", "")
                logger.info(f"[{idx}/{total}] Файл из архива: {original_name}")

                # Ищем архив
                archive_path = self._find_archive_for_file(original_name)

                if archive_path:
                    # Извлекаем файл
                    extracted_path = self._extract_from_archive(archive_path, original_name)

                    if extracted_path and os.path.exists(extracted_path):
                        # Рендерим извлечённый файл
                        stl_path = Path(extracted_path)

                        # Сохраняем превью в .thumbs рядом с архивом
                        archive_dir = Path(archive_path).parent
                        thumb_dir = archive_dir / ".thumbs"
                        thumb_dir.mkdir(exist_ok=True)

                        # Имя превью: archive_name__file_name.jpg
                        archive_stem = Path(archive_path).stem
                        safe_name = original_name.replace('/', '_').replace('\\', '_')
                        thumb_path = thumb_dir / f"{archive_stem}__{Path(safe_name).stem}.jpg"

                        try:
                            success = self.renderer.render_to_jpeg(
                                str(stl_path),
                                str(thumb_path)
                            )

                            if success and thumb_path.exists():
                                self.db.update_thumbnail_status(file_id, str(thumb_path))
                                rendered += 1
                                logger.info(f"  ✅ Превью из архива создано!")
                            else:
                                self.renderer.create_error_placeholder(str(thumb_path))
                                self.db.update_thumbnail_status(file_id, str(thumb_path))
                                errors += 1
                        except Exception as e:
                            logger.error(f"  ❌ Ошибка: {e}")
                            errors += 1
                    else:
                        logger.warning(f"  ❌ Не удалось извлечь файл из архива")
                        skipped['archive'] += 1
                else:
                    logger.warning(f"  ❌ Архив не найден для {original_name}")
                    skipped['archive'] += 1

                if progress_cb:
                    progress_cb(idx, total)
                continue

            # === Обработка обычных файлов ===
            stl_path = Path(file_path)

            if not stl_path.exists():
                logger.warning(f"[{idx}/{total}] ПРОПУЩЕН (не найден): {file_path}")
                skipped['not_found'] += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # Создаём .thumbs
            thumb_dir = stl_path.parent / ".thumbs"
            try:
                thumb_dir.mkdir(exist_ok=True, parents=True)
            except Exception:
                thumb_dir = stl_path.parent

            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"

            if idx % 5 == 0 or idx == 1:
                logger.info(f"[{idx}/{total}] Рендеринг: {file_name}")

            try:
                success = self.renderer.render_to_jpeg(
                    str(stl_path),
                    str(thumb_path)
                )

                if success and thumb_path.exists() and thumb_path.stat().st_size > 100:
                    self.db.update_thumbnail_status(file_id, str(thumb_path))
                    rendered += 1
                else:
                    self.renderer.create_error_placeholder(str(thumb_path))
                    self.db.update_thumbnail_status(file_id, str(thumb_path))
                    errors += 1
            except Exception as e:
                logger.error(f"  ❌ {e}")
                errors += 1

            if progress_cb:
                progress_cb(idx, total)

        # Итоги
        logger.info(f"=" * 60)
        logger.info(f"РЕНДЕРИНГ ЗАВЕРШЁН")
        logger.info(f"  ✅ Успешно: {rendered}")
        logger.info(f"  ⏭ Пропущено: невалидных={skipped['not_valid']}, "
                   f"из архивов={skipped['archive']}, не найдено={skipped['not_found']}")
        logger.info(f"  ❌ Ошибок: {errors}")
        logger.info(f"=" * 60)

        return rendered