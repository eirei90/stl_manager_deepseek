"""
Фоновые потоки для выполнения длительных операций без зависания GUI.
Поддерживает остановку операций.
"""

import threading
import logging
from typing import Callable, Optional
from pathlib import Path
import os

logger = logging.getLogger(__name__)


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
    """Поток для пакетного рендеринга превью."""

    def __init__(self, renderer, db, project_id: int, **kwargs):
        self.renderer = renderer
        self.db = db
        self.project_id = project_id

        def render_target(progress_cb, cancel_token):
            return self._batch_render(progress_cb, cancel_token)

        super().__init__(target=render_target, **kwargs)

    def _batch_render(self, progress_cb, cancel_token) -> int:
        """Рендерит превью для всех файлов проекта."""
        files = self.db.get_files_for_project(self.project_id)
        total = len(files)
        rendered = 0
        skipped = 0
        errors = 0

        logger.info(f"=" * 50)
        logger.info(f"Начинаем рендеринг {total} файлов")
        logger.info(f"=" * 50)

        for idx, file_record in enumerate(files, 1):
            # Проверяем отмену
            if cancel_token.is_cancelled:
                logger.info(f"Рендеринг прерван. Обработано: {rendered}/{total}")
                break

            # Распаковываем данные файла
            # Индексы: 0:id, 1:file_name, 2:file_path, 3:file_size, 4:modified_date,
            #          5:face_count, 6:bbox_x, 7:bbox_y, 8:bbox_z, 9:volume,
            #          10:surface_area, 11:is_valid, 12:has_thumbnail, 13:thumbnail_path
            file_id = file_record[0]
            file_name = file_record[1]
            file_path = file_record[2]
            is_valid = file_record[11] if len(file_record) > 11 else 1

            # Пропускаем невалидные
            if not is_valid:
                logger.debug(f"[{idx}/{total}] Пропущен (невалидный): {file_name}")
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # Пропускаем файлы из архивов
            if file_path.startswith("[ARCHIVE]"):
                logger.debug(f"[{idx}/{total}] Пропущен (архив): {file_name}")
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # Проверяем существование файла
            stl_path = Path(file_path)
            if not stl_path.exists():
                logger.warning(f"[{idx}/{total}] Файл не найден: {file_path}")
                skipped += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            # Создаём директорию .thumbs рядом с файлом
            thumb_dir = stl_path.parent / ".thumbs"
            try:
                thumb_dir.mkdir(exist_ok=True, parents=True)
            except PermissionError:
                # Если нет прав на создание .thumbs, сохраняем рядом
                thumb_dir = stl_path.parent
                logger.warning(f"Нет прав на создание .thumbs, сохраняем рядом с файлом")
            except Exception as e:
                logger.error(f"Ошибка создания директории {thumb_dir}: {e}")
                errors += 1
                if progress_cb:
                    progress_cb(idx, total)
                continue

            thumb_path = thumb_dir / f"{stl_path.stem}.jpg"

            # Логируем
            logger.info(f"[{idx}/{total}] Рендеринг: {file_name}")
            logger.debug(f"  STL: {stl_path}")
            logger.debug(f"  JPG: {thumb_path}")

            # Рендерим
            try:
                success = self.renderer.render_to_jpeg(
                    str(stl_path),
                    str(thumb_path)
                )

                if success:
                    # Проверяем что файл создался
                    if thumb_path.exists() and thumb_path.stat().st_size > 100:
                        # Сохраняем в БД
                        self.db.update_thumbnail_status(file_id, str(thumb_path))
                        rendered += 1
                        logger.info(f"  ✅ Успешно! ({rendered} всего)")
                    else:
                        logger.warning(f"  ⚠ Файл превью слишком маленький")
                        self.renderer.create_error_placeholder(str(thumb_path))
                        self.db.update_thumbnail_status(file_id, str(thumb_path))
                        errors += 1
                else:
                    logger.warning(f"  ❌ Рендеринг вернул False")
                    # Создаём заглушку
                    self.renderer.create_error_placeholder(str(thumb_path))
                    self.db.update_thumbnail_status(file_id, str(thumb_path))
                    errors += 1

            except Exception as e:
                logger.error(f"  ❌ Исключение: {e}", exc_info=True)
                try:
                    self.renderer.create_error_placeholder(str(thumb_path))
                    self.db.update_thumbnail_status(file_id, str(thumb_path))
                except:
                    pass
                errors += 1

            # Обновляем прогресс
            if progress_cb:
                progress_cb(idx, total)

        # Итоги
        logger.info(f"=" * 50)
        logger.info(f"Рендеринг завершён:")
        logger.info(f"  ✅ Успешно: {rendered}")
        logger.info(f"  ⏭ Пропущено: {skipped}")
        logger.info(f"  ❌ Ошибок: {errors}")
        logger.info(f"=" * 50)

        return rendered