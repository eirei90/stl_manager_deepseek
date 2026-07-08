#!/usr/bin/env python3
"""
Тестовый скрипт для диагностики проблем рендеринга.
Запускает рендеринг одного файла с подробным логированием.
"""

import sys
import os
import logging
from pathlib import Path

# Настройка подробного логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_render.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def test_vedo_import():
    """Проверка импорта vedo."""
    print("\n" + "="*60)
    print("1. Проверка vedo")
    print("="*60)
    
    try:
        import vedo
        print(f"✅ vedo импортирован")
        print(f"   Версия: {vedo.__version__}")
        print(f"   Путь: {vedo.__file__}")
        
        # Проверяем настройки
        print(f"   default_backend: {vedo.settings.default_backend}")
        
    except ImportError as e:
        print(f"❌ vedo не установлен: {e}")
        return False
    
    return True


def test_vtk_import():
    """Проверка импорта VTK."""
    print("\n" + "="*60)
    print("2. Проверка VTK")
    print("="*60)
    
    try:
        import vtk
        print(f"✅ VTK импортирован")
        print(f"   Версия: {vtk.vtkVersion.GetVTKVersion()}")
        
        # Проверяем, что VTK работает
        cone = vtk.vtkConeSource()
        cone.Update()
        print(f"   Тестовый объект создан успешно")
        
    except ImportError as e:
        print(f"❌ VTK не установлен: {e}")
        return False
    
    return True


def test_trimesh_import():
    """Проверка импорта trimesh."""
    print("\n" + "="*60)
    print("3. Проверка trimesh")
    print("="*60)
    
    try:
        import trimesh
        print(f"✅ trimesh импортирован")
        print(f"   Версия: {trimesh.__version__}")
    except ImportError as e:
        print(f"⚠️ trimesh не установлен: {e}")
        return False
    
    return True


def test_renderer_init():
    """Проверка инициализации рендерера."""
    print("\n" + "="*60)
    print("4. Инициализация рендерера")
    print("="*60)
    
    sys.path.insert(0, '.')
    
    try:
        from services.renderer import STLRenderer
        renderer = STLRenderer()
        print(f"✅ Рендерер создан")
        print(f"   Метод: {renderer.method}")
        return renderer
    except Exception as e:
        print(f"❌ Ошибка создания рендерера: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_test_stl():
    """Поиск тестового STL файла."""
    print("\n" + "="*60)
    print("5. Поиск тестового STL")
    print("="*60)
    
    # Проверяем файлы из БД
    try:
        from models.database import Database
        db = Database("stl_catalog.db")
        conn = db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT file_path FROM files 
            WHERE is_valid = 1 
            AND file_path NOT LIKE '[ARCHIVE]%'
            LIMIT 5
        """)
        
        files = cursor.fetchall()
        
        for (file_path,) in files:
            if os.path.exists(file_path):
                print(f"✅ Найден файл: {file_path}")
                db.close()
                return file_path
        
        db.close()
    except Exception as e:
        print(f"⚠️ Не удалось получить файлы из БД: {e}")
    
    # Поиск в домашней директории
    home = os.path.expanduser("~")
    for root, dirs, files in os.walk(home):
        for f in files:
            if f.endswith('.stl'):
                path = os.path.join(root, f)
                print(f"✅ Найден файл: {path}")
                return path
        if len(root.split(os.sep)) > 4:  # Ограничиваем глубину поиска
            break
    
    print("❌ STL файлы не найдены")
    return None


def test_render_file(renderer, stl_path):
    """Тестовый рендеринг файла."""
    print("\n" + "="*60)
    print("6. Тестовый рендеринг")
    print("="*60)
    
    if not renderer:
        print("❌ Рендерер недоступен")
        return False
    
    if not stl_path:
        print("❌ Нет файла для рендеринга")
        return False
    
    print(f"Файл: {stl_path}")
    print(f"Существует: {os.path.exists(stl_path)}")
    print(f"Размер: {os.path.getsize(stl_path)} байт")
    
    # Пробуем загрузить через trimesh для проверки
    try:
        import trimesh
        mesh = trimesh.load(stl_path, file_type='stl')
        if mesh is not None:
            print(f"Граней: {len(mesh.faces)}")
            print(f"Вершин: {len(mesh.vertices)}")
            print(f"Водонепроницаемый: {mesh.is_watertight}")
        else:
            print("⚠️ trimesh не смог загрузить файл")
    except Exception as e:
        print(f"⚠️ Ошибка trimesh: {e}")
    
    # Пробуем рендеринг
    output = "test_preview.jpg"
    
    print(f"\nЗапуск рендеринга...")
    print(f"Выходной файл: {output}")
    
    try:
        success = renderer.render_to_jpeg(stl_path, output)
        
        if success:
            if os.path.exists(output):
                size = os.path.getsize(output)
                print(f"✅ РЕНДЕРИНГ УСПЕШЕН!")
                print(f"   Файл: {output}")
                print(f"   Размер: {size} байт")
                return True
            else:
                print(f"❌ Файл не создан: {output}")
        else:
            print(f"❌ Рендеринг вернул False")
            
            # Проверяем, есть ли файл-заглушка
            if os.path.exists(output):
                print(f"   (создана заглушка: {os.path.getsize(output)} байт)")
            
    except Exception as e:
        print(f"❌ Исключение при рендеринге: {e}")
        import traceback
        traceback.print_exc()
    
    return False


def test_direct_vedo(stl_path):
    """Прямой тест vedo без рендерера."""
    print("\n" + "="*60)
    print("7. Прямой тест vedo")
    print("="*60)
    
    if not stl_path:
        print("Нет файла для теста")
        return
    
    try:
        import vedo
        
        print(f"Загрузка файла: {stl_path}")
        mesh = vedo.Mesh(stl_path)
        print(f"✅ Меш загружен")
        print(f"   Точек: {mesh.NPoints()}")
        print(f"   Граней: {mesh.NCells()}")
        
        # Пробуем минимальный рендеринг
        print("Создание плоттера...")
        
        plotter = vedo.Plotter(
            offscreen=True,
            size=(512, 512),
            bg=(0.5, 0.5, 0.5)
        )
        print("✅ Плоттер создан")
        
        print("Добавление меша...")
        plotter.add(mesh)
        print("✅ Меш добавлен")
        
        output = "test_vedo_direct.jpg"
        print(f"Сохранение в {output}...")
        
        plotter.screenshot(output, scale=1)
        plotter.close()
        
        if os.path.exists(output):
            size = os.path.getsize(output)
            print(f"✅ ПРЯМОЙ РЕНДЕРИНГ УСПЕШЕН!")
            print(f"   Размер: {size} байт")
            return True
        else:
            print("❌ Файл не создан")
            
    except Exception as e:
        print(f"❌ Ошибка прямого рендеринга: {e}")
        import traceback
        traceback.print_exc()
    
    return False


def main():
    """Главная функция."""
    print("="*60)
    print("  ДИАГНОСТИКА РЕНДЕРИНГА STL")
    print("="*60)
    
    # Проверяем импорты
    test_vedo_import()
    test_vtk_import()
    test_trimesh_import()
    
    # Создаём рендерер
    renderer = test_renderer_init()
    
    # Ищем тестовый файл
    stl_path = find_test_stl()
    
    # Тестовый рендеринг через рендерер
    if renderer and stl_path:
        test_render_file(renderer, stl_path)
    
    # Прямой тест vedo
    if stl_path:
        test_direct_vedo(stl_path)
    
    # Итоги
    print("\n" + "="*60)
    print("  ИТОГИ ДИАГНОСТИКИ")
    print("="*60)
    
    # Проверяем созданные файлы
    for test_file in ['test_preview.jpg', 'test_vedo_direct.jpg']:
        if os.path.exists(test_file):
            print(f"✅ {test_file} - {os.path.getsize(test_file)} байт")
        else:
            print(f"❌ {test_file} - не создан")
    
    print("\nПроверьте лог-файл: test_render.log")
    print("Отправьте вывод этого скрипта для дальнейшей диагностики.")


if __name__ == "__main__":
    main()