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
        try:
            with open(file_path, 'rb') as f:
                header = f.read(5)
                if header.lower().startswith(b'solid'):
                    f.seek(80)
                    data = f.read(4)
                    if len(data) == 4:
                        count = struct.unpack('<I', data)[0]
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        if abs(size - (84 + count * 50)) < 10:
                            return 'binary'
                    return 'ascii'
                return 'binary'
        except:
            return None

    def parse_stl_metadata(self, file_path: str, root_path: str) -> Optional[Dict]:
        # ... определение relative_dir ...
        # Быстрый разбор бинарного STL для количества граней
        face_count = 0
        format_type = self.detect_stl_format(file_path)
        if format_type == 'binary':
            try:
                with open(file_path, 'rb') as f:
                    f.seek(80)
                    data = f.read(4)
                    if len(data) == 4:
                        face_count = struct.unpack('<I', data)[0]
            except:
                pass
        # Если не бинарный или не удалось, оставляем 0 (trimesh догрузит позже при необходимости)
        # Но можно загружать trimesh только если нужен bounding box/volume
        # Для скорости пропустим trimesh при сканировании
        metadata = {
            'file_name': os.path.basename(file_path),
            'file_path': os.path.abspath(file_path),
            'relative_path': relative_dir,
            'file_size': stat.st_size,
            'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'format_type': format_type,
            'is_valid': 1,
            'face_count': face_count,
            'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
            'volume': 0.0, 'surface_area': 0.0
        }
        # Опционально: включить trimesh для детальных метаданных (медленно)
        # if TRIMESH_AVAILABLE and metadata['is_valid']:
        #    ... (оставьте, если нужны размеры, иначе закомментируйте)
        return metadata

    def scan_directory(self, root_path: str, progress_callback=None, cancel_token=None) -> int:
        root_path = os.path.abspath(root_path)
        logger.info(f"Сканирование: {root_path}")
        project_id = self.db.add_project(root_path)

        stl_files = []
        self._temp_files = []
        archives = []  # (full_path, relative_dir)

        # Один обход директорий
        for dirpath, _, filenames in os.walk(root_path):
            if cancel_token and cancel_token.is_cancelled:
                break
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                ext = Path(fname).suffix.lower()
                if ext in ('.stl', '.obj'):
                    stl_files.append(full_path)
                elif self.archive_extractor.is_archive(full_path):
                    rel = os.path.relpath(full_path, root_path)
                    rel_dir = os.path.dirname(rel)
                    if rel_dir == '.':
                        rel_dir = ''
                    archives.append((full_path, rel_dir))

        total = len(stl_files) + len(archives)
        processed = 0

        # Обработка STL/OBJ
        for file_path in stl_files:
            if cancel_token and cancel_token.is_cancelled:
                break
            try:
                metadata = self.parse_stl_metadata(file_path, root_path)
                if metadata:
                    self.db.insert_file(project_id, metadata)
                    processed += 1
            except Exception as e:
                logger.error(f"Ошибка: {e}")
            if progress_callback:
                progress_callback(processed, total)

        # Обработка архивов (добавляем записи БД, извлекаем только метаданные, не файлы)
        for archive_path, rel_dir in archives:
            if cancel_token and cancel_token.is_cancelled:
                break
            try:
                fname = os.path.basename(archive_path)
                archive_metadata = {
                    'file_name': fname,
                    'file_path': f"[ARCHIVE] {fname}",
                    'relative_path': rel_dir,
                    'file_size': os.path.getsize(archive_path),
                    'modified_date': datetime.fromtimestamp(os.path.getmtime(archive_path)).isoformat(),
                    'format_type': 'archive',
                    'is_valid': 1,
                    'face_count': 0,
                    'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
                    'volume': 0.0, 'surface_area': 0.0
                }
                self.db.insert_file(project_id, archive_metadata)
                processed += 1
            except Exception as e:
                logger.error(f"Ошибка архива: {e}")
            if progress_callback:
                progress_callback(processed, total)

        # Извлекаем STL из архивов для каталогизации (но не сохраняем в БД как отдельные файлы)
        # если нужно только количество граней, можно пропустить для ускорения
        # Оставляем опционально: закомментировать для скорости
        # self._extract_and_catalog_archives(archives, root_path, project_id)

        self.db.update_project_stats(project_id)
        self.archive_extractor.cleanup()
        self._temp_files = []
        logger.info(f"Готово: {processed}/{total}")
        return project_id

    def scan_directory(self, root_path: str, progress_callback=None, cancel_token=None) -> int:
        root_path = os.path.abspath(root_path)
        logger.info(f"Сканирование: {root_path}")

        project_id = self.db.add_project(root_path)
        stl_files = self._find_stl_files(root_path)
        total = len(stl_files)

        if total == 0:
            self._add_archive_entries(root_path, project_id, progress_callback, cancel_token)
            self.db.update_project_stats(project_id)
            self.archive_extractor.cleanup()
            return project_id

        processed = 0
        for idx, file_path in enumerate(stl_files, 1):
            if cancel_token and cancel_token.is_cancelled:
                break
            try:
                if not os.path.exists(file_path):
                    continue
                metadata = self.parse_stl_metadata(file_path, root_path)
                if metadata is None:
                    continue
                if file_path in self._temp_files:
                    metadata['file_path'] = f"[ARCHIVE] {os.path.basename(file_path)}"
                    # Сохраняем relative_path из архива
                self.db.insert_file(project_id, metadata)
                processed += 1
                if progress_callback:
                    progress_callback(idx, total)
            except Exception as e:
                logger.error(f"Ошибка: {e}")

        self._add_archive_entries(root_path, project_id, progress_callback, cancel_token)
        self.db.update_project_stats(project_id)
        self.archive_extractor.cleanup()
        self._temp_files = []

        logger.info(f"Готово: {processed}/{total}")
        return project_id
