"""
Модуль сканирования STL-файлов.
Рекурсивно обходит директории, парсит метаданные, сохраняет в БД.
"""

import os
import struct
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import numpy as np

# Попытка импорта trimesh для точного парсинга
try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

logger = logging.getLogger(__name__)


class STLScanner:
    """Сканер STL-файлов с извлечением метаданных."""
    
    def __init__(self, db):
        self.db = db
    
    def detect_stl_format(self, file_path: str) -> Optional[str]:
        """
        Определяет формат STL: бинарный или ASCII.
        Читает первые байты файла.
        """
        try:
            with open(file_path, 'rb') as f:
                # Читаем первые 5 байт
                header = f.read(5)
                
                # Если начинается с "solid" — вероятно ASCII
                if header.lower().startswith(b'solid'):
                    # Дополнительная проверка: бинарные STL тоже могут начинаться с solid
                    # Проверяем размер файла относительно заголовка (84 байта)
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
        
        # Пытаемся загрузить геометрию через trimesh
        if TRIMESH_AVAILABLE:
            try:
                mesh = trimesh.load(file_path, file_type='stl')
                
                if mesh is not None and len(mesh.faces) > 0:
                    metadata['face_count'] = len(mesh.faces)
                    
                    # Габаритные размеры
                    bounds = mesh.bounds  # [[xmin, ymin, zmin], [xmax, ymax, zmax]]
                    extent = bounds[1] - bounds[0]
                    metadata['bbox_x'] = round(float(extent[0]), 4)
                    metadata['bbox_y'] = round(float(extent[1]), 4)
                    metadata['bbox_z'] = round(float(extent[2]), 4)
                    
                    # Объём (если меш водонепроницаемый)
                    if mesh.is_watertight:
                        metadata['volume'] = round(float(mesh.volume), 4)
                    
                    # Площадь поверхности
                    metadata['surface_area'] = round(float(mesh.area), 4)
                else:
                    metadata['is_valid'] = 0
                    
            except Exception as e:
                logger.warning(f"Ошибка парсинга {file_path}: {e}")
                metadata['is_valid'] = 0
        
        return metadata
    
    def scan_directory(self, root_path: str, progress_callback=None) -> int:
        """
        Рекурсивно сканирует директорию, сохраняет метаданные в БД.
        
        Args:
            root_path: Корневая папка для сканирования
            progress_callback: Функция(current, total) для обновления прогресса
            
        Returns:
            project_id: ID проекта в БД
        """
        root_path = str(Path(root_path).resolve())
        project_id = self.db.add_project(root_path)
        
        # Собираем список всех STL-файлов
        stl_files = []
        for dirpath, _, filenames in os.walk(root_path):
            for fname in filenames:
                if fname.lower().endswith('.stl'):
                    stl_files.append(os.path.join(dirpath, fname))
        
        total = len(stl_files)
        logger.info(f"Найдено {total} STL-файлов в {root_path}")
        
        # Обрабатываем каждый файл
        for idx, file_path in enumerate(stl_files, 1):
            try:
                metadata = self.parse_stl_metadata(file_path)
                self.db.insert_file(project_id, metadata)
                
                if progress_callback:
                    progress_callback(idx, total)
                    
                logger.debug(f"[{idx}/{total}] Обработан: {Path(file_path).name}")
                
            except Exception as e:
                logger.error(f"Критическая ошибка при обработке {file_path}: {e}")
                continue
        
        # Обновляем статистику проекта
        self.db.update_project_stats(project_id)
        
        return project_id