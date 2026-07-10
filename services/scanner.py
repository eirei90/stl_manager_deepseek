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
        path = Path(file_path)
        if not path.exists():
            return None
        
        stat = path.stat()
        
        try:
            relative = str(path.resolve().relative_to(Path(root_path).resolve()))
            relative_dir = str(Path(relative).parent)
        except ValueError:
            relative_dir = ''
        
        metadata = {
            'file_name': path.name,
            'file_path': str(path.resolve()),
            'relative_path': relative_dir,
            'file_size': stat.st_size,
            'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'format_type': self.detect_stl_format(file_path),
            'is_valid': 1,
            'face_count': 0,
            'bbox_x': 0.0,
            'bbox_y': 0.0,
            'bbox_z': 0.0,
            'volume': 0.0,
            'surface_area': 0.0
        }
        
        if TRIMESH_AVAILABLE:
            try:
                mesh = trimesh.load(file_path, file_type='stl')
                if mesh is not None and len(mesh.faces) > 0:
                    metadata['face_count'] = len(mesh.faces)
                    extent = mesh.bounds[1] - mesh.bounds[0]
                    metadata['bbox_x'] = round(float(extent[0]), 4)
                    metadata['bbox_y'] = round(float(extent[1]), 4)
                    metadata['bbox_z'] = round(float(extent[2]), 4)
                    if mesh.is_watertight:
                        metadata['volume'] = round(float(mesh.volume), 4)
                    metadata['surface_area'] = round(float(mesh.area), 4)
                else:
                    metadata['is_valid'] = 0
            except Exception as e:
                logger.warning(f"trimesh error: {e}")
                metadata['is_valid'] = 0
        
        return metadata
    
    def _find_stl_files(self, root_path: str) -> List[str]:
        stl_files = []
        self._temp_files = []
        
        for dirpath, _, filenames in os.walk(root_path):
            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                ext = Path(fname).suffix.lower()
                
                if ext == '.stl':
                    stl_files.append(full_path)
                elif self.archive_extractor.is_archive(full_path):
                    logger.info(f"Найден архив: {fname}")
                    for extracted in self.archive_extractor.extract_stl_files(full_path):
                        if extracted and os.path.exists(extracted):
                            stl_files.append(extracted)
                            self._temp_files.append(extracted)
        
        return stl_files
    
    def scan_directory(self, root_path: str, progress_callback=None, cancel_token=None) -> int:
        root_path = str(Path(root_path).resolve())
        logger.info(f"Сканирование: {root_path}")
        
        project_id = self.db.add_project(root_path)
        stl_files = self._find_stl_files(root_path)
        total = len(stl_files)
        
        if total == 0:
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
                    metadata['file_path'] = f"[ARCHIVE] {Path(file_path).name}"
                    metadata['relative_path'] = ''
                
                self.db.insert_file(project_id, metadata)
                processed += 1
                
                if progress_callback:
                    progress_callback(idx, total)
                    
            except Exception as e:
                logger.error(f"Ошибка: {e}")
        
        self.db.update_project_stats(project_id)
        self.archive_extractor.cleanup()
        self._temp_files = []
        
        logger.info(f"Готово: {processed}/{total}")
        return project_id
