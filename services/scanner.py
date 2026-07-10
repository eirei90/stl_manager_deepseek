"""
Модуль сканирования STL-файлов.
Рекурсивно обходит директории, заглядывает в архивы 7z/rar/zip,
парсит метаданные, сохраняет в БД.
"""

import os
import struct
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

from services.archive_utils import ArchiveExtractor

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

logger = logging.getLogger(__name__)


class STLScanner:
    """Сканер STL-файлов с извлечением метаданных и поддержкой архивов."""

    def __init__(self, db):
        self.db = db
        self.archive_extractor = ArchiveExtractor()
        self._temp_files = []

    def detect_stl_format(self, file_path: str) -> Optional[str]:
        """Определяет формат STL: бинарный или ASCII."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(5)

                if header.lower().startswith(b'solid'):
                    f.seek(80)
                    triangle_count_bytes = f.read(4)
                    if len(triangle_count_bytes) == 4:
                        triangle_count = struct.unpack('<I', triangle_count_bytes)[0]
                        f.seek(0, os.SEEK_END)
                        file_size = f.tell()
                        expected_size = 84 + triangle_count * 50
                        if abs(file_size - expected_size) < 10:
                            return 'binary'
                    return 'ascii'
                else:
                    return 'binary'
        except Exception:
            return None

    def parse_stl_metadata(self, file_path: str) -> Dict:
        """Извлекает метаданные STL-файла."""
        path = Path(file_path)

        if not path.exists():
            return {
                'file_name': path.name,
                'file_path': str(path.resolve()),
                'file_size': 0,
                'modified_date': datetime.now().isoformat(),
                'format_type': None,
                'is_valid': 0,
                'face_count': 0,
                'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
                'volume': 0.0,
                'surface_area': 0.0
            }

        stat = path.stat()

        metadata = {
            'file_name': path.name,
            'file_path': str(path.resolve()),
            'file_size': stat.st_size,
            'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'format_type': self.detect_stl_format(file_path),
            'is_valid': 1,
            'face_count': 0,
            'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
            'volume': 0.0,
            'surface_area': 0.0
        }

        if TRIMESH_AVAILABLE:
            try:
                mesh = trimesh.load(file_path, file_type='stl')

                if mesh is not None and len(mesh.faces) > 0:
                    metadata['face_count'] = len(mesh.faces)

                    bounds = mesh.bounds
                    extent = bounds[1] - bounds[0]
                    metadata['bbox_x'] = round(float(extent[0]), 4)
                    metadata['bbox_y'] = round(float(extent[1]), 4)
                    metadata['bbox_z'] = round(float(extent[2]), 4)

                    if mesh.is_watertight:
                        metadata['volume'] = round(float(mesh.volume), 4)

                    metadata['surface_area'] = round(float(mesh.area), 4)
                else:
                    metadata['is_valid'] = 0

            except Exception as e:
                logger.warning(f"Ошибка парсинга {file_path}: {e}")
                metadata['is_valid'] = 0

        return metadata

    def _find_stl_files(self, root_path: str) -> List[str]:
        """
        Находит все STL-файлы в директории и вложенных архивах.
        """
        stl_files = []
        temp_files = []

        root_path = str(Path(root_path).resolve())
        logger.info(f"Поиск STL в: {root_path}")

        # Счётчики для статистики
        stl_count = 0
        archive_count = 0
        stl_in_archives = 0

        for dirpath, _, filenames in os.walk(root_path):
            logger.debug(f"  Просмотр директории: {dirpath}")

            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                ext = Path(fname).suffix.lower()

                if ext == '.stl':
                    stl_files.append(full_path)
                    stl_count += 1
                    if stl_count <= 5:  # Логируем первые 5
                        logger.info(f"  Найден STL: {fname}")

                elif self.archive_extractor.is_archive(full_path):
                    archive_count += 1
                    logger.info(f"  Найден архив: {fname}")

                    # Получаем список STL в архиве
                    stl_in = self.archive_extractor.list_stl_files(full_path)
                    logger.info(f"    Содержит STL: {len(stl_in)}")

                    if len(stl_in) > 0:
                        # Извлекаем STL из архива
                        for extracted_path in self.archive_extractor.extract_stl_files(full_path):
                            stl_files.append(extracted_path)
                            temp_files.append(extracted_path)
                            stl_in_archives += 1

        logger.info(f"Итого найдено:")
        logger.info(f"  STL файлов: {stl_count}")
        logger.info(f"  Архивов: {archive_count}")
        logger.info(f"  STL в архивах: {stl_in_archives}")
        logger.info(f"  Всего для обработки: {len(stl_files)}")

        self._temp_files = temp_files
        return stl_files

    def scan_directory(self, root_path: str, progress_callback=None, cancel_token=None) -> int:
        """
        Рекурсивно сканирует директорию, включая архивы.
        """
        root_path = str(Path(root_path).resolve())
        logger.info(f"=" * 50)
        logger.info(f"НАЧАЛО СКАНИРОВАНИЯ: {root_path}")
        logger.info(f"=" * 50)

        # Проверяем существование директории
        if not os.path.exists(root_path):
            logger.error(f"Директория не существует: {root_path}")
            return 0

        if not os.path.isdir(root_path):
            logger.error(f"Это не директория: {root_path}")
            return 0

        # Выводим содержимое для отладки
        logger.info(f"Содержимое директории:")
        for item in os.listdir(root_path):
            item_path = os.path.join(root_path, item)
            if os.path.isfile(item_path):
                size = os.path.getsize(item_path)
                logger.info(f"  Файл: {item} ({size} байт)")
            elif os.path.isdir(item_path):
                logger.info(f"  Папка: {item}")

        project_id = self.db.add_project(root_path)
        logger.info(f"Project ID: {project_id}")

        # Собираем список всех STL-файлов
        stl_files = self._find_stl_files(root_path)
        total = len(stl_files)

        if total == 0:
            logger.warning(f"STL-файлы не найдены в {root_path}")
            # Обновляем статистику (0 файлов)
            self.db.update_project_stats(project_id)
            # Возвращаем project_id, чтобы UI мог показать "Файлов: 0"
            return project_id

        # Выводим все найденные файлы
        logger.info(f"Найдено {total} STL-файлов:")
        for i, f in enumerate(stl_files[:10]):
            logger.info(f"  [{i + 1}] {f}")
        if total > 10:
            logger.info(f"  ... и ещё {total - 10}")

        # Обрабатываем каждый файл
        processed = 0
        for idx, file_path in enumerate(stl_files, 1):
            # Проверяем отмену
            if cancel_token and cancel_token.is_cancelled:
                logger.info(f"Сканирование прервано. Обработано: {processed}/{total}")
                break

            try:
                logger.debug(f"[{idx}/{total}] Обработка: {Path(file_path).name}")

                metadata = self.parse_stl_metadata(file_path)

                # Проверяем, является ли файл временным (из архива)
                is_temp = file_path in self._temp_files

                if is_temp:
                    original_name = Path(file_path).name
                    metadata['file_path'] = f"[ARCHIVE] {original_name}"
                    logger.debug(f"  Это файл из архива: {original_name}")

                # Сохраняем в БД
                file_id = self.db.insert_file(project_id, metadata)
                processed += 1

                if progress_callback:
                    progress_callback(idx, total)

                if idx % 5 == 0 or idx == total:
                    logger.info(f"  Прогресс: {idx}/{total} (сохранено: {processed})")

            except Exception as e:
                logger.error(f"Ошибка обработки {file_path}: {e}", exc_info=True)
                continue

        # Обновляем статистику проекта
        self.db.update_project_stats(project_id)

        # Проверяем, что файлы сохранились
        check_files = self.db.get_files_for_project(project_id)
        logger.info(f"Проверка: в БД сохранено {len(check_files)} файлов для проекта {project_id}")

        # Очищаем временные файлы
        self.archive_extractor.cleanup()

        logger.info(f"=" * 50)
        logger.info(f"СКАНИРОВАНИЕ ЗАВЕРШЕНО")
        logger.info(f"  Проект ID: {project_id}")
        logger.info(f"  Обработано: {processed}/{total}")
        logger.info(f"  В БД: {len(check_files)} записей")
        logger.info(f"=" * 50)

        return project_id

    def cleanup(self):
        """Очистка временных ресурсов."""
        self.archive_extractor.cleanup()