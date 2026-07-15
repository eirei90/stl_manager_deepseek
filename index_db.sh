cd /home/eirei/PycharmProjects/stl_manager
python3 -c "
from models.database import Database
db = Database('stl_catalog.db')
conn = db._get_connection()
cursor = conn.cursor()
cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_project_path ON files(project_id, relative_path)')
cursor.execute('CREATE INDEX IF NOT EXISTS idx_files_format ON files(format_type)')
conn.commit()
print('Индексы созданы')
db.close()
"