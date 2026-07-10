python3 -c "
from services.scanner import STLScanner
from models.database import Database

db = Database('stl_catalog.db')
scanner = STLScanner(db)

# Тестовый поиск файлов
files = scanner._find_stl_files('/home/eirei/3D/Korgi')
print(f'Найдено файлов: {len(files)}')
for f in files[:10]:
    print(f'  {f}')
"