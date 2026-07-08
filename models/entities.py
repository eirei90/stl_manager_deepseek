"""
Классы-сущности для представления данных из БД.
Можно использовать для типобезопасной передачи данных между слоями.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FileRecord:
    """Запись о STL-файле."""
    id: int
    project_id: int
    file_name: str
    file_path: str
    file_size: int
    modified_date: str
    format_type: Optional[str]
    is_valid: bool
    face_count: Optional[int]
    bbox_x: Optional[float]
    bbox_y: Optional[float]
    bbox_z: Optional[float]
    volume: Optional[float]
    surface_area: Optional[float]
    has_thumbnail: bool
    thumbnail_path: Optional[str] = None


@dataclass
class ProjectRecord:
    """Запись о проекте (корневой папке)."""
    id: int
    root_path: str
    scan_date: str
    total_files: int
    total_size: int