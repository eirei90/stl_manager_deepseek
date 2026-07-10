"""
Модуль сканирования STL-файлов.
Рекурсивный обход, поиск в архивах, извлечение метаданных.
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
    """Сканер STL-файлов."""

    def __init__(self, db):
        self.db = db
        self.archive_extractor = ArchiveExtractor()
        self._temp_files = []

    def detect_stl_format(self, file_path: str) -> Optional[str]:
        """
        Определяет формат STL-файла: бинарный или ASCII.
        Корректно обрабатывает спецсимволы в пути.
        """
        try:
            # Используем bytes для открытия, чтобы избежать проблем с кодировкой
            with open(file_path, 'rb') as f:
                # Читаем первые 5 байт
                header = f.read(5)

                # Проверяем, начинается ли с "solid" (бинарный или ASCII)
                if header.lower().startswith(b'solid'):
                    # Пропускаем заголовок (80 байт)
                    f.seek(80)
                    triangle_count_bytes = f.read(4)

                    if len(triangle_count_bytes) == 4:
                        triangle_count = struct.unpack('<I', triangle_count_bytes)[0]
                        f.seek(0, os.SEEK_END)
                        file_size = f.tell()

                        # Вычисляем ожидаемый размер бинарного STL
                        expected_size = 84 + triangle_count * 50

                        # Проверяем, совпадает ли размер
                        if abs(file_size - expected_size) <= 10:
                            return 'binary'

                    # Если размер не совпадает — это ASCII
                    return 'ascii'
                else:
                    # Не начинается с "solid" — точно бинарный
                    return 'binary'

        except FileNotFoundError:
            logger.warning(f"Файл не найден: {file_path}")
            return None
        except PermissionError:
            logger.warning(f"Нет доступа к файлу: {file_path}")
            return None
        except OSError as e:
            logger.warning(f"Ошибка ОС при чтении {file_path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Неизвестная ошибка определения формата {file_path}: {e}")
            return None

    def parse_stl_metadata(self, file_path: str, root_path: str) -> Optional[Dict]:
        """Извлекает метаданные STL-файла."""
        path = Path(file_path)

        # Проверяем существование через os.path (надёжнее с Unicode)
        if not os.path.exists(file_path):
            logger.warning(f"Файл не существует: {file_path}")
            return None

        try:
            stat = os.stat(file_path)  # Используем os.stat вместо Path.stat()
        except OSError as e:
            logger.error(f"Ошибка доступа к файлу {file_path}: {e}")
            return None

        # Относительный путь
        try:
            root = os.path.abspath(root_path)
            full = os.path.abspath(file_path)
            relative = os.path.relpath(full, root)
            relative_dir = os.path.dirname(relative)
            if relative_dir == '.':
                relative_dir = ''
        except (ValueError, OSError) as e:
            logger.debug(f"Ошибка вычисления относительного пути: {e}")
            relative_dir = ''

        metadata = {
            'file_name': os.path.basename(file_path),  # Используем os.path
            'file_path': os.path.abspath(file_path),
            'relative_path': relative_dir,
            'file_size': stat.st_size,
            'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'format_type': self.detect_stl_format(file_path),
            'is_valid': 1,
            'face_count': 0,
            'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
            'volume': 0.0, 'surface_area': 0.0
        }

        # Геометрия через trimesh
        if TRIMESH_AVAILABLE and metadata['is_valid']:
            try:
                # Передаём путь как строку (trimesh сам обработает кодировку)
                mesh = trimesh.load(file_path, file_type='stl')
                if mesh is not None and hasattr(mesh, 'faces') and len(mesh.faces) > 0:
                    metadata['face_count'] = len(mesh.faces)
                    extent = mesh.bounds[1] - mesh.bounds[0]
                    metadata['bbox_x'] = round(float(extent[0]), 4)
                    metadata['bbox_y'] = round(float(extent[1]), 4)
                    metadata['bbox_z'] = round(float(extent[2]), 4)
                    if hasattr(mesh, 'is_watertight') and mesh.is_watertight:
                        metadata['volume'] = round(float(mesh.volume), 4)
                    metadata['surface_area'] = round(float(mesh.area), 4)
                else:
                    metadata['is_valid'] = 0
            except Exception as e:
                logger.warning(f"Ошибка trimesh для {os.path.basename(file_path)}: {e}")
                metadata['is_valid'] = 0

        return metadata

    def _find_stl_files(self, root_path: str) -> List[str]:
        """Находит все STL-файлы, исключая дубликаты из архивов."""
        stl_files = []
        self._temp_files = []

        # Сначала собираем все обычные STL
        regular_stl = set()

        for dirpath, _, filenames in os.walk(root_path):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                ext = Path(fname).suffix.lower()

                if ext == '.stl':
                    stl_files.append(full_path)
                    regular_stl.add(fname)  # Запоминаем имя файла

        # Теперь ищем архивы
        for dirpath, _, filenames in os.walk(root_path):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                ext = Path(fname).suffix.lower()

                if self.archive_extractor.is_archive(full_path):
                    logger.info(f"Найден архив: {fname}")

                    # Проверяем, какие файлы из архива уже есть в папке
                    stl_in_archive = self.archive_extractor.list_stl_files(full_path)

                    # Извлекаем только те файлы, которых нет в папке
                    for extracted in self.archive_extractor.extract_stl_files(full_path):
                        if extracted and os.path.exists(extracted):
                            extracted_name = Path(extracted).name

                            # Проверяем, есть ли уже такой файл в папке
                            if extracted_name not in regular_stl:
                                stl_files.append(extracted)
                                self._temp_files.append(extracted)
                                logger.debug(f"  + {extracted_name} (из архива)")
                            else:
                                logger.debug(f"  - {extracted_name} (уже есть в папке, пропущен)")

        logger.info(f"Найдено STL: {len(stl_files)} (из архивов: {len(self._temp_files)})")
        return stl_files

    def scan_directory(self, root_path: str, progress_callback=None, cancel_token=None) -> int:
        root_path = str(Path(root_path).resolve())
        logger.info(f"Сканирование: {root_path}")

        project_id = self.db.add_project(root_path)
        stl_files = self._find_stl_files(root_path)
        total = len(stl_files)

        # ... existing code ...

        # После обработки всех STL — добавляем записи о самих архивах
        self._add_archive_entries(root_path, project_id)

        self.db.update_project_stats(project_id)
        self.archive_extractor.cleanup()
        self._temp_files = []

        return project_id

    def _add_archive_entries(self, root_path: str, project_id: int):
        """Добавляет записи о найденных архивах как отдельные файлы."""
        added = 0
        for dirpath, _, filenames in os.walk(root_path):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                if self.archive_extractor.is_archive(full_path):
                    try:
                        archive_metadata = {
                            'file_name': fname,
                            'file_path': f"[ARCHIVE] {fname}",
                            'relative_path': '',
                            'file_size': os.path.getsize(full_path),
                            'modified_date': datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat(),
                            'format_type': 'archive',
                            'is_valid': 1,
                            'face_count': 0,
                            'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
                            'volume': 0.0,
                            'surface_area': 0.0
                        }
                        self.db.insert_file(project_id, archive_metadata)
                        added += 1
                        logger.info(f"Добавлен архив: {fname}")
                    except Exception as e:
                        logger.error(f"Ошибка добавления архива {fname}: {e}")

        if added > 0:
            logger.info(f"Добавлено архивов: {added}")
