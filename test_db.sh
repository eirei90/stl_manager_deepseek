cd /home/eirei/PycharmProjects/stl_manager
python3 -c "
from models.database import Database

db = Database('stl_catalog.db')
conn = db._get_connection()
cursor = conn.cursor()

# Проверяем проекты
cursor.execute('SELECT * FROM projects')
projects = cursor.fetchall()
print('=== ПРОЕКТЫ ===')
for p in projects:
    print(f'  ID: {p[0]}, Путь: {p[1]}, Файлов: {p[3]}, Дата: {p[2]}')

print()

# Проверяем общее количество файлов
cursor.execute('SELECT COUNT(*) FROM files')
total = cursor.fetchone()[0]
print(f'Всего файлов в БД: {total}')

# Проверяем распределение по проектам
cursor.execute('SELECT project_id, COUNT(*) FROM files GROUP BY project_id')
print('\nРаспределение файлов по проектам:')
for row in cursor.fetchall():
    print(f'  project_id={row[0]}: {row[1]} файлов')

# Проверяем файлы для проекта 12
cursor.execute('SELECT * FROM files WHERE project_id = 12 LIMIT 3')
files = cursor.fetchall()
print(f'\nФайлы проекта 12: {len(files)}')
for f in files:
    print(f'  {f[1]} -> {f[2]}')

db.close()
"