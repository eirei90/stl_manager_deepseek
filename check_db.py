#!/usr/bin/env python3
"""Проверка базы данных и тестовый рендеринг."""

import sys
sys.path.insert(0, '.')

from models.database import Database
from services.renderer import STLRenderer
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Подключаемся к БД
    db = Database("stl_catalog.db")
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Проверяем таблицы
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"Таблицы в БД: {[t[0] for t in tables]}")
    
    # Проверяем структуру files
    cursor.execute("PRAGMA table_info(files)")
    columns = cursor.fetchall()
    print("\nСтруктура таблицы files:")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
    
    # Проверяем количество записей
    cursor.execute("SELECT COUNT(*) FROM files")
    count = cursor.fetchone()[0]
    print(f"\nВсего файлов в БД: {count}")
    
    # Проверяем записи с превью
    cursor.execute("SELECT COUNT(*) FROM files WHERE has_thumbnail = 1")
    with_thumb = cursor.fetchone()[0]
    print(f"Файлов с превью: {with_thumb}")
    
    # Показываем первые 5 файлов
    cursor.execute("""
        SELECT f.id, f.file_name, f.file_path, f.is_valid, f.has_thumbnail, t.thumbnail_path
        FROM files f
        LEFT JOIN thumbnails t ON f.id = t.file_id
        LIMIT 5
    """)
    
    print("\nПримеры файлов:")
    for row in cursor.fetchall():
        print(f"  ID: {row[0]}")
        print(f"  Имя: {row[1]}")
        print(f"  Путь: {row[2]}")
        print(f"  Валидный: {row[3]}")
        print(f"  Есть превью: {row[4]}")
        print(f"  Путь к превью: {row[5]}")
        print()
    
    # Проверяем существование файлов
    cursor.execute("SELECT file_path FROM files WHERE is_valid = 1 AND file_path NOT LIKE '[ARCHIVE]%' LIMIT 3")
    valid_files = cursor.fetchall()
    
    if valid_files:
        print("Тестовый рендеринг первого валидного файла...")
        test_file = valid_files[0][0]
        
        if Path(test_file).exists():
            print(f"  Файл существует: {test_file}")
            
            try:
                renderer = STLRenderer()
                test_output = "test_preview.jpg"
                success = renderer.render_to_jpeg(test_file, test_output)
                
                if success:
                    print(f"  ✅ Тестовый рендеринг успешен: {test_output}")
                    print(f"  Размер: {Path(test_output).stat().st_size} байт")
                else:
                    print(f"  ❌ Тестовый рендеринг не удался")
            except Exception as e:
                print(f"  ❌ Ошибка рендерера: {e}")
        else:
            print(f"  ❌ Файл не существует: {test_file}")
    else:
        print("Нет валидных файлов для тестового рендеринга")
    
    db.close()

if __name__ == "__main__":
    main()