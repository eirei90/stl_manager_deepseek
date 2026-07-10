python3 -c "
from models.database import Database

db = Database('stl_catalog.db')
conn = db._get_connection()
cursor = conn.cursor()

# Находим проект с файлами
cursor.execute('''
    SELECT p.id, p.root_path, p.total_files
    FROM projects p
    WHERE p.total_files > 0
    ORDER BY p.scan_date DESC
    LIMIT 1
''')
project = cursor.fetchone()
if project:
    pid, path, total = project
    print(f'Проект: {path} (ID: {pid}, файлов: {total})')

    # Статистика по превью
    cursor.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN has_thumbnail = 1 THEN 1 ELSE 0 END) as with_thumb,
            SUM(CASE WHEN has_thumbnail = 0 AND is_valid = 1 AND file_path NOT LIKE \"[ARCHIVE]%\" THEN 1 ELSE 0 END) as need_thumb,
            SUM(CASE WHEN is_valid = 0 THEN 1 ELSE 0 END) as invalid,
            SUM(CASE WHEN file_path LIKE \"[ARCHIVE]%\" THEN 1 ELSE 0 END) as in_archive
        FROM files
        WHERE project_id = ?
    ''', (pid,))

    stats = cursor.fetchone()
    print(f'\nСтатистика:')
    print(f'  Всего файлов: {stats[0]}')
    print(f'  С превью: {stats[1]}')
    print(f'  Нужно превью: {stats[2]}')
    print(f'  Невалидных: {stats[3]}')
    print(f'  В архивах: {stats[4]}')

    # Показываем файлы без превью
    cursor.execute('''
        SELECT file_name, file_path, is_valid,
               CASE WHEN file_path LIKE \"[ARCHIVE]%\" THEN 1 ELSE 0 END as in_archive
        FROM files
        WHERE project_id = ? AND has_thumbnail = 0
        LIMIT 10
    ''', (pid,))

    print(f'\nФайлы без превью (первые 10):')
    for row in cursor.fetchall():
        print(f'  {row[0]}')
        print(f'    Путь: {row[1]}')
        print(f'    Валидный: {row[2]}, В архиве: {row[3]}')

db.close()
"