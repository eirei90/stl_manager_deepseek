"""
Модуль работы с базой данных SQLite.
Реализует CRUD-операции для проектов, файлов и миниатюр.
"""

import sqlite3
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


class Database:
    """Менеджер базы данных STL Catalog."""
    
    def __init__(self, db_path: str = "stl_catalog.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._create_tables()
        logger.info(f"База данных инициализирована: {self.db_path.absolute()}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Получает соединение с БД (создаёт при необходимости)."""
        if self.conn is None:
            self.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False  # Для работы из разных потоков
            )
            self.conn.execute("PRAGMA journal_mode=WAL")  # Ускорение записи
            self.conn.execute("PRAGMA foreign_keys=ON")
        return self.conn
    
    def _create_tables(self):
        """Создаёт таблицы, если их нет."""
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
                file_size INTEGER,
                modified_date TIMESTAMP,
                format_type TEXT,
                is_valid INTEGER DEFAULT 1,
                face_count INTEGER,
                bbox_x REAL, bbox_y REAL, bbox_z REAL,
                volume REAL,
                surface_area REAL,
                has_thumbnail INTEGER DEFAULT 0,
                scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS thumbnails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL UNIQUE,
                thumbnail_path TEXT,
                generation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id);
            CREATE INDEX IF NOT EXISTS idx_files_name ON files(file_name);
            CREATE INDEX IF NOT EXISTS idx_files_faces ON files(face_count);
        """)
        conn.commit()
    
    # === Операции с проектами ===
    
    def add_project(self, root_path: str) -> int:
        """Добавляет новый проект или возвращает ID существующего."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO projects (root_path) VALUES (?)",
            (str(Path(root_path).resolve()),)
        )
        conn.commit()
        cursor.execute(
            "SELECT id FROM projects WHERE root_path = ?",
            (str(Path(root_path).resolve()),)
        )
        return cursor.fetchone()[0]
    
    def update_project_stats(self, project_id: int):
        """Обновляет статистику проекта после сканирования."""
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
    
    # === Операции с файлами ===

    def insert_file(self, project_id: int, file_data: dict) -> int:
        """Вставляет или обновляет запись о файле. Возвращает file_id."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO files (
                    project_id, file_name, file_path, file_size, modified_date,
                    format_type, is_valid, face_count,
                    bbox_x, bbox_y, bbox_z, volume, surface_area
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    project_id = excluded.project_id,
                    file_name = excluded.file_name,
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
                file_data['file_size'],
                file_data['modified_date'],
                file_data['format_type'],
                file_data['is_valid'],
                file_data['face_count'],
                file_data['bbox_x'],
                file_data['bbox_y'],
                file_data['bbox_z'],
                file_data['volume'],
                file_data['surface_area']
            ))
            conn.commit()

            # Получаем ID вставленной/обновлённой записи
            cursor.execute("SELECT id FROM files WHERE file_path = ?", (file_data['file_path'],))
            result = cursor.fetchone()

            if result:
                return result[0]
            else:
                logger.error(f"Не удалось получить ID для {file_data['file_path']}")
                return 0

        except Exception as e:
            logger.error(f"Ошибка вставки в БД: {e}")
            conn.rollback()
            return 0
    
    def update_thumbnail_status(self, file_id: int, thumbnail_path: str):
        """Обновляет статус превью для файла."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Обновляем флаг в таблице files
        cursor.execute(
            "UPDATE files SET has_thumbnail = 1 WHERE id = ?",
            (file_id,)
        )
        
        # Вставляем/обновляем запись в thumbnails
        cursor.execute("""
            INSERT INTO thumbnails (file_id, thumbnail_path, generation_date)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_id) DO UPDATE SET
                thumbnail_path = excluded.thumbnail_path,
                generation_date = CURRENT_TIMESTAMP
        """, (file_id, str(thumbnail_path)))
        
        conn.commit()

    def get_files_for_project(self, project_id: int,
                              name_filter: str = None,
                              min_faces: int = None,
                              max_faces: int = None) -> List[Tuple]:
        """Получает список файлов проекта с фильтрацией."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT f.id, f.file_name, f.file_path, f.file_size, f.modified_date,
                   f.face_count, f.bbox_x, f.bbox_y, f.bbox_z,
                   f.volume, f.surface_area, f.is_valid, f.has_thumbnail,
                   t.thumbnail_path
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

        query += " ORDER BY f.file_name"

        logger.debug(f"SQL: {query}")
        logger.debug(f"Params: {params}")

        cursor.execute(query, params)
        result = cursor.fetchall()

        logger.info(f"Запрос вернул {len(result)} записей для project_id={project_id}")

        return result
    
    def close(self):
        """Закрывает соединение с БД."""
        if self.conn:
            self.conn.close()
            self.conn = None