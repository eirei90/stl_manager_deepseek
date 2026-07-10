"""
Фоновые потоки для длительных операций.
Поддерживает остановку, использует существующие изображения.
"""

import threading
import logging
from pathlib import Path
from typing import Callable, Optional
import os

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

            if not is_valid or file_path.startswith("[ARCHIVE]"):
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            stl_path = Path(file_path)
            if not stl_path.exists():
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # Создаём директорию .thumbs
            thumb_dir = stl_path.parent / ".thumbs"
            thumb_dir.mkdir(exist_ok=True, parents=True)
            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"

            used_existing = False

            # Проверяем существующее изображение
            existing_img = self.renderer.find_existing_image(str(stl_path))
            if existing_img:
                logger.info(f"[{idx}/{total}] Использую существующее: {Path(existing_img).name}")
                if self.renderer.copy_existing_image(existing_img, str(thumb_path)):
                    self.db.update_thumbnail_status(file_id, str(thumb_path), is_existing=1)
                    rendered += 1
                    from_existing += 1
                    used_existing = True

            # Если нет существующего — рендерим
            if not used_existing:
                logger.info(f"[{idx}/{total}] Рендеринг: {file_name}")
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
