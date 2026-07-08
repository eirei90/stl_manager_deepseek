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
import numpy as np

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

    def detect_stl_format(self, file_path: str) -> Optional[str]:
        """
        Определяет формат STL: бинарный или ASCII.
        Читает первые байты файла.
        """
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
        """
        Извлекает метаданные STL-файла.
        Использует trimesh для геометрии, если доступен.
        """
        path = Path(file_path)

        # Проверяем существование файла (может быть временным из архива)
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

        Args:
            root_path: Корневая директория

        Returns:
            Список путей к STL-файлам (включая временные из архивов)
        """
        stl_files = []
        temp_files = []  # Временные файлы из архивов (для очистки)

        for dirpath, _, filenames in os.walk(root_path):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                ext = Path(fname).suffix.lower()

                if ext == '.stl':
                    # Обычный STL-файл
                    stl_files.append(full_path)

                elif self.archive_extractor.is_archive(full_path):
                    # Архив — ищем STL внутри
                    logger.info(f"Обнаружен архив: {fname}")

                    # Сначала просто считаем количество STL в архиве
                    stl_in_archive = self.archive_extractor.list_stl_files(full_path)
                    logger.info(f"  Содержит {len(stl_in_archive)} STL-файлов")

                    # Извлекаем и добавляем в список
                    for extracted_path in self.archive_extractor.extract_stl_files(full_path):
                        stl_files.append(extracted_path)
                        temp_files.append(extracted_path)

        # Сохраняем список временных файлов для последующей очистки
        self._temp_files = temp_files

        return stl_files

    def scan_directory(self, root_path: str, progress_callback=None) -> int:
        """
        Рекурсивно сканирует директорию, включая архивы.

        Args:
            root_path: Корневая папка для сканирования
            progress_callback: Функция(current, total) для обновления прогресса

        Returns:
            project_id: ID проекта в БД
        """
        root_path = str(Path(root_path).resolve())
        project_id = self.db.add_project(root_path)

        # Собираем список всех STL-файлов (включая из архивов)
        logger.info(f"Начинаем сканирование: {root_path}")
        stl_files = self._find_stl_files(root_path)

        total = len(stl_files)
        logger.info(f"Найдено {total} STL-файлов (включая извлечённые из архивов)")

        # Обрабатываем каждый файл
        for idx, file_path in enumerate(stl_files, 1):
            try:
                metadata = self.parse_stl_metadata(file_path)

                # Проверяем, не является ли файл временным (из архива)
                is_temp = hasattr(self, '_temp_files') and file_path in self._temp_files

                if is_temp:
                    # Для файлов из архивов добавляем пометку в путь
                    original_name = Path(file_path).name
                    metadata['file_path'] = f"[ARCHIVE] {original_name}"
                    logger.debug(f"Обработан файл из архива: {original_name}")

                self.db.insert_file(project_id, metadata)

                if progress_callback:
                    progress_callback(idx, total)

                logger.debug(f"[{idx}/{total}] Обработан: {Path(file_path).name}")

            except Exception as e:
                logger.error(f"Критическая ошибка при обработке {file_path}: {e}")
                continue

        # Обновляем статистику проекта
        self.db.update_project_stats(project_id)

        # Очищаем временные файлы
        self.archive_extractor.cleanup()

        return project_id

    def cleanup(self):
        """Очистка временных ресурсов."""
        self.archive_extractor.cleanup()