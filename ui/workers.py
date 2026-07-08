"""
Фоновые потоки для выполнения длительных операций без зависания GUI.
Использует threading.Thread + queue для безопасного обновления UI.
"""

import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BackgroundTask(threading.Thread):
    """
    Базовый класс для фоновой задачи.
    Поддерживает callback для обновления прогресса и завершения.
    """
    
    def __init__(self, target: Callable, on_progress: Optional[Callable] = None,
                 on_complete: Optional[Callable] = None, on_error: Optional[Callable] = None):
        super().__init__(daemon=True)
        self._target = target
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error
        self._result = None
        self._error = None
    
    def run(self):
        try:
            self._result = self._target(self._report_progress)
            if self._on_complete:
                # Выполняем в главном потоке через after()
                self._on_complete(self._result)
        except Exception as e:
            logger.error(f"Ошибка в фоновом потоке: {e}", exc_info=True)
            self._error = e
            if self._on_error:
                self._on_error(str(e))
    
    def _report_progress(self, current: int, total: int):
        """Безопасно сообщает о прогрессе в главный поток."""
        if self._on_progress:
            # Вызываем напрямую, т.к. customtkinter thread-safe для update()
            self._on_progress(current, total)
    
    @property
    def result(self):
        return self._result
    
    @property
    def error(self):
        return self._error


class ScanWorker(BackgroundTask):
    """Поток для сканирования директории."""
    
    def __init__(self, scanner, root_path: str, **kwargs):
        def scan_target(progress_cb):
            return scanner.scan_directory(root_path, progress_cb)
        
        super().__init__(target=scan_target, **kwargs)


class RenderWorker(BackgroundTask):
    """Поток для пакетного рендеринга превью."""
    
    def __init__(self, renderer, db, project_id: int, **kwargs):
        self.renderer = renderer
        self.db = db
        self.project_id = project_id
        
        def render_target(progress_cb):
            return self._batch_render(progress_cb)
        
        super().__init__(target=render_target, **kwargs)
    
    def _batch_render(self, progress_cb) -> int:
        """Рендерит превью для всех файлов проекта."""
        from pathlib import Path
        
        files = self.db.get_files_for_project(self.project_id)
        total = len(files)
        rendered = 0
        
        for idx, file_record in enumerate(files, 1):
            file_id = file_record[0]
            file_path = file_record[2]
            
            # Определяем путь для превью
            stl_path = Path(file_path)
            thumb_dir = stl_path.parent / ".thumbs"
            thumb_dir.mkdir(exist_ok=True)
            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"
            
            # Рендерим
            success = self.renderer.render_to_jpeg(
                str(stl_path),
                str(thumb_path)
            )
            
            if not success:
                # Создаём заглушку для битых файлов
                self.renderer.create_error_placeholder(str(thumb_path))
            
            # Сохраняем информацию о превью в БД
            self.db.update_thumbnail_status(file_id, str(thumb_path))
            
            rendered += 1
            if progress_cb:
                progress_cb(idx, total)
        
        return rendered