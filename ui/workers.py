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
        files = self.db.get_files_for_project(self.project_id)
        dirs = set()
        for record in files:
            path = record[2]
            if not path.startswith("[ARCHIVE]"):
                parent = str(Path(path).parent)
                dirs.add(parent)
                dirs.add(str(Path(parent).parent))

        for dir_path in dirs:
            if not os.path.exists(dir_path):
                continue
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

            # Файлы из архивов
            if file_path.startswith("[ARCHIVE]"):
                original_name = file_path.replace("[ARCHIVE] ", "")
                logger.info(f"[{idx}/{total}] Архив: {original_name}")

                archive_path = self._find_archive(original_name)
                if archive_path:
                    extracted = self._extract_from_archive(archive_path, original_name)
                    if extracted and os.path.exists(extracted):
                        archive_dir = Path(archive_path).parent
                        thumb_dir = archive_dir / ".thumbs"
                        thumb_dir.mkdir(exist_ok=True)
                        thumb_path = thumb_dir / f"{Path(archive_path).stem}__{Path(original_name).stem}.jpg"

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
                                errors += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

                if progress_cb:
                    progress_cb(idx, total)
                continue

            # Обычные файлы
            stl_path = Path(file_path)
            if not stl_path.exists():
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            thumb_dir = stl_path.parent / ".thumbs"
            thumb_dir.mkdir(exist_ok=True, parents=True)
            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"

            existing_img = self.renderer.find_existing_image(str(stl_path))
            if existing_img:
                if self.renderer.copy_existing_image(existing_img, str(thumb_path)):
                    self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                    rendered += 1
                    from_existing += 1
            else:
                success = self.renderer.render_to_jpeg(str(stl_path), str(thumb_path))
                if success and thumb_path.exists():
                    self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=0)
                    rendered += 1
                else:
                    errors += 1

            if progress_cb:
                progress_cb(idx, total)

        logger.info(f"Готово: {rendered} (из существующих: {from_existing}), пропущено: {skipped}, ошибок: {errors}")
        return rendered
