"""
Фоновые потоки для выполнения длительных операций без зависания GUI.
Поддерживает остановку операций.
"""

import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CancellationToken:
    """Токен для безопасной остановки фоновых операций."""

    def __init__(self):
        self._cancelled = False
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        """Проверяет, отменена ли операция."""
        with self._lock:
            return self._cancelled

    def cancel(self):
        """Отменяет операцию."""
        with self._lock:
            self._cancelled = True
            logger.info("Операция отменена пользователем")

    def reset(self):
        """Сбрасывает токен для повторного использования."""
        with self._lock:
            self._cancelled = False


class BackgroundTask(threading.Thread):
    """
    Базовый класс для фоновой задачи с поддержкой отмены.
    """

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
        self._cancelled = False

        # Используем переданный токен или создаём новый
        self.cancellation_token = cancellation_token or CancellationToken()

    def run(self):
        """Выполняет задачу с проверкой отмены."""
        try:
            # Передаём токен и колбэк прогресса в целевую функцию
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
        """Безопасно сообщает о прогрессе в главный поток."""
        if self._on_progress and not self.cancellation_token.is_cancelled:
            self._on_progress(current, total)

    def cancel(self):
        """Запрашивает отмену операции."""
        self.cancellation_token.cancel()
        logger.info("Запрошена отмена операции")

    @property
    def result(self):
        return self._result

    @property
    def error(self):
        return self._error


class ScanWorker(BackgroundTask):
    """Поток для сканирования директории с поддержкой отмены."""

    def __init__(self, scanner, root_path: str, **kwargs):
        self.scanner = scanner
        self.root_path = root_path

        def scan_target(progress_cb, cancel_token):
            return scanner.scan_directory(root_path, progress_cb, cancel_token)

        super().__init__(target=scan_target, **kwargs)


class RenderWorker(BackgroundTask):
    """Поток для пакетного рендеринга превью с поддержкой отмены."""

    def __init__(self, renderer, db, project_id: int, **kwargs):
        self.renderer = renderer
        self.db = db
        self.project_id = project_id

        def render_target(progress_cb, cancel_token):
            return self._batch_render(progress_cb, cancel_token)

        super().__init__(target=render_target, **kwargs)

    def _batch_render(self, progress_cb, cancel_token) -> int:
        """Рендерит превью для всех файлов проекта с проверкой отмены."""
        from pathlib import Path

        files = self.db.get_files_for_project(self.project_id)
        total = len(files)
        rendered = 0

        for idx, file_record in enumerate(files, 1):
            # Проверяем отмену
            if cancel_token.is_cancelled:
                logger.info(f"Рендеринг прерван пользователем. Обработано: {rendered}/{total}")
                break

            file_id = file_record[0]
            file_path = file_record[2]

            # Пропускаем файлы из архивов (у них путь начинается с [ARCHIVE])
            if file_path.startswith("[ARCHIVE]"):
                if progress_cb:
                    progress_cb(idx, total)
                continue

            stl_path = Path(file_path)
            if not stl_path.exists():
                logger.warning(f"Файл не найден: {file_path}")
                if progress_cb:
                    progress_cb(idx, total)
                continue

            thumb_dir = stl_path.parent / ".thumbs"
            thumb_dir.mkdir(exist_ok=True)
            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"

            # Рендерим
            success = self.renderer.render_to_jpeg(
                str(stl_path),
                str(thumb_path)
            )

            if not success:
                self.renderer.create_error_placeholder(str(thumb_path))
            
            # Сохраняем информацию о превью в БД
            self.db.update_thumbnail_status(file_id, str(thumb_path))
            
            rendered += 1
            if progress_cb:
                progress_cb(idx, total)
        
        return rendered