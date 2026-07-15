"""
Модуль сканирования STL/OBJ-файлов.
Оптимизированная версия: один проход os.walk для всего.
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
    """Сканер STL/OBJ-файлов."""

    def __init__(self, db):
        self.db = db
        self.archive_extractor = ArchiveExtractor()

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
        """Быстрый сбор метаданных без trimesh для скорости."""
        if not os.path.exists(file_path):
            return None

        stat = os.stat(file_path)
        root = os.path.abspath(root_path)
        full = os.path.abspath(file_path)
        relative = os.path.relpath(full, root)
        relative_dir = os.path.dirname(relative)
        if relative_dir == '.':
            relative_dir = ''

        # Быстрый подсчёт граней для бинарных STL
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

        metadata = {
            'file_name': os.path.basename(file_path),
            'file_path': full,
            'relative_path': relative_dir,
            'file_size': stat.st_size,
            'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'format_type': format_type,
            'is_valid': 1,
            'face_count': face_count,
            'bbox_x': 0.0, 'bbox_y': 0.0, 'bbox_z': 0.0,
            'volume': 0.0, 'surface_area': 0.0
        }

        # trimesh оставлен для совместимости, но не обязателен при сканировании
        if TRIMESH_AVAILABLE and face_count == 0:
            try:
                mesh = trimesh.load(file_path, file_type='stl')
                if mesh and hasattr(mesh, 'faces') and len(mesh.faces) > 0:
                    metadata['face_count'] = len(mesh.faces)
            except:
                pass

        return metadata

    def scan_directory(self, root_path: str, progress_callback=None, cancel_token=None) -> int:
        """Однопроходное сканирование: ищет STL/OBJ и архивы одновременно."""
        root_path = os.path.abspath(root_path)
        logger.info(f"Сканирование: {root_path}")

        project_id = self.db.add_project(root_path)

        stl_files = []          # обычные файлы
        archive_entries = []    # информация об архивах

        # ОДИН обход файловой системы
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
                    archive_entries.append((fname, full_path, rel_dir))

        total = len(stl_files) + len(archive_entries)
        processed = 0

        # Обработка обычных файлов
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

        # Обработка архивов
        for fname, archive_path, rel_dir in archive_entries:
            if cancel_token and cancel_token.is_cancelled:
                break
            try:
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

        self.db.update_project_stats(project_id)
        self.archive_extractor.cleanup()
        logger.info(f"Готово: {processed}/{total}")
        return project_id
