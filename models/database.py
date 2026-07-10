"""
Модуль работы с базой данных SQLite.
Реализует CRUD-операции для проектов, файлов и миниатюр.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


class Database:
    """Менеджер базы данных STL Catalog."""

    def __init__(self, db_path: str = "stl_catalog.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._create_tables()
        logger.info(f"БД инициализирована: {self.db_path.absolute()}")

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn

    def _create_tables(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_path TEXT NOT NULL UNIQUE,
                scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_files INTEGER DEFAULT 0,
                total_size INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                relative_path TEXT,
                file_size INTEGER,
                modified_date TIMESTAMP,
                format_type TEXT,
                is_valid INTEGER DEFAULT 1,
                face_count INTEGER,
                bbox_x REAL, bbox_y REAL, bbox_z REAL,
                volume REAL,
                surface_area REAL,
                has_thumbnail INTEGER DEFAULT 0,
                thumbnail_source TEXT DEFAULT 'none',
                scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS thumbnails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL UNIQUE,
                thumbnail_path TEXT,
                is_existing INTEGER DEFAULT 0,
                generation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id);
            CREATE INDEX IF NOT EXISTS idx_files_name ON files(file_name);
            CREATE INDEX IF NOT EXISTS idx_files_relative ON files(relative_path);
        """)
        conn.commit()

    def add_project(self, root_path: str) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        resolved = str(Path(root_path).resolve())
        cursor.execute("INSERT OR IGNORE INTO projects (root_path) VALUES (?)", (resolved,))
        conn.commit()
        cursor.execute("SELECT id FROM projects WHERE root_path = ?", (resolved,))
        return cursor.fetchone()[0]

    def update_project_stats(self, project_id: int):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE projects SET
                total_files = (SELECT COUNT(*) FROM files WHERE project_id = ?),
                total_size = (SELECT COALESCE(SUM(file_size), 0) FROM files WHERE project_id = ?),
                scan_date = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (project_id, project_id, project_id))
        conn.commit()

    def insert_file(self, project_id: int, file_data: dict) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO files (
                project_id, file_name, file_path, relative_path, file_size, modified_date,
                format_type, is_valid, face_count,
                bbox_x, bbox_y, bbox_z, volume, surface_area
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_name = excluded.file_name,
                relative_path = excluded.relative_path,
                file_size = excluded.file_size,
                modified_date = excluded.modified_date,
                format_type = excluded.format_type,
                is_valid = excluded.is_valid,
                face_count = excluded.face_count,
                bbox_x = excluded.bbox_x,
                bbox_y = excluded.bbox_y,
                bbox_z = excluded.bbox_z,
                volume = excluded.volume,
                surface_area = excluded.surface_area,
                scan_time = CURRENT_TIMESTAMP
        """, (
            project_id,
            file_data['file_name'],
            file_data['file_path'],
            file_data.get('relative_path', ''),
            file_data['file_size'],
            file_data['modified_date'],
            file_data['format_type'],
            file_data['is_valid'],
            file_data['face_count'],
            file_data['bbox_x'], file_data['bbox_y'], file_data['bbox_z'],
            file_data['volume'], file_data['surface_area']
        ))
        conn.commit()
        cursor.execute("SELECT id FROM files WHERE file_path = ?", (file_data['file_path'],))
        result = cursor.fetchone()
        return result[0] if result else 0

    def update_thumbnail_status(self, file_id: int, thumbnail_path: str, is_existing: int = 0):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE files SET has_thumbnail = 1, thumbnail_source = ? WHERE id = ?",
                      ('existing' if is_existing else 'generated', file_id))
        cursor.execute("""
            INSERT INTO thumbnails (file_id, thumbnail_path, is_existing, generation_date)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_id) DO UPDATE SET
                thumbnail_path = excluded.thumbnail_path,
                is_existing = excluded.is_existing,
                generation_date = CURRENT_TIMESTAMP
        """, (file_id, str(thumbnail_path), is_existing))
        conn.commit()

    def get_files_for_project(self, project_id: int,
                               name_filter: str = None,
                               min_faces: int = None,
                               max_faces: int = None,
                               relative_path: str = None) -> List[Tuple]:
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT f.id, f.file_name, f.file_path, f.file_size, f.modified_date,
                   f.face_count, f.bbox_x, f.bbox_y, f.bbox_z,
                   f.volume, f.surface_area, f.is_valid, f.has_thumbnail,
                   t.thumbnail_path, f.relative_path, f.thumbnail_source
            FROM files f
            LEFT JOIN thumbnails t ON f.id = t.file_id
            WHERE f.project_id = ?
        """
        params = [project_id]

        if name_filter:
            query += " AND f.file_name LIKE ?"
            params.append(f"%{name_filter}%")
        if min_faces is not None:
            query += " AND f.face_count >= ?"
            params.append(min_faces)
        if max_faces is not None:
            query += " AND f.face_count <= ?"
            params.append(max_faces)
        if relative_path:
            query += " AND f.relative_path LIKE ?"
            params.append(f"{relative_path}%")

        query += " ORDER BY f.relative_path, f.file_name"

        cursor.execute(query, params)
        return cursor.fetchall()

    def get_directory_tree(self, project_id: int):
        """Возвращает структуру папок и файлов для дерева."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT root_path FROM projects WHERE id = ?", (project_id,))
        root = cursor.fetchone()
        root_path = root[0] if root else ""
        root_name = Path(root_path).name if root_path else "Проект"

        cursor.execute("""
            SELECT file_name, relative_path, is_valid,
                   CASE WHEN format_type = 'archive' THEN 2
                        WHEN file_path LIKE '[ARCHIVE]%' THEN 1
                        ELSE 0 END as file_type
            FROM files WHERE project_id = ?
            ORDER BY file_type DESC, relative_path, file_name
        """, (project_id,))
        files = cursor.fetchall()

        if not files:
            return []

        tree = {}
        for file_name, rel_path, is_valid, file_type in files:
            # Определяем части пути
            if rel_path and rel_path != '.':
                parts = Path(rel_path).parts
            else:
                parts = []  # <-- ВОТ ЭТО БЫЛО ПРОПУЩЕНО

            current = tree
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]

            if '__files' not in current:
                current['__files'] = []

            # Префикс в зависимости от типа
            if file_type == 2:
                prefix = "📦 "  # Архив
            elif file_type == 1:
                prefix = "📄 "  # Файл из архива
            else:
                prefix = "📄 "  # Обычный файл

            if not is_valid:
                prefix = "⚠ "

            current['__files'].append({
                'name': file_name,
                'full_name': f"{prefix}{file_name}",
                'file_type': file_type,
                'is_valid': bool(is_valid)
            })

        def build_tree(node, path=''):
            result = []
            for name, children in sorted(node.items()):
                if name == '__files':
                    continue
                full = f"{path}/{name}" if path else name

                def count(n):
                    c = len(n.get('__files', []))
                    for k, v in n.items():
                        if k != '__files':
                            c += count(v)
                    return c

                result.append({
                    'name': name, 'path': full, 'is_dir': True,
                    'file_count': count(children),
                    'children': build_tree(children, full)
                })
            for f in sorted(node.get('__files', []), key=lambda x: x['name']):
                result.append({
                    'name': f['full_name'],
                    'path': f"{path}/{f['name']}" if path else f['name'],
                    'is_dir': False,
                    'file_type': f.get('file_type', 0),
                    'is_valid': f['is_valid'],
                    'children': []
                })
            return result

        tree_list = build_tree(tree, '')

        return [{
            'name': f"📂 {root_name}",
            'path': root_name,
            'is_dir': True,
            'file_count': len(files),
            'children': tree_list
        }]

        logger.info(f"Дерево построено: корень '{root_name}', файлов: {len(files)}")
        return [root]
