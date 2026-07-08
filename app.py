#!/usr/bin/env python3
"""
STL Manager - Приложение для управления коллекцией STL-файлов.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models.database import Database
from services.scanner import STLScanner
from services.renderer import STLRenderer
from ui.main_window import STLManagerApp
from utils.logger import logger


def main():
    """Главная функция запуска приложения."""
    try:
        print("=" * 60)
        print("  STL Manager - запуск")
        print("=" * 60)

        # База данных
        print("Инициализация БД...")
        db = Database("stl_catalog.db")
        print("✅ БД готова")

        # Сканер
        print("Инициализация сканера...")
        scanner = STLScanner(db)
        print("✅ Сканер готов")

        # Рендерер
        print("Инициализация рендерера...")
        renderer = None
        try:
            renderer = STLRenderer()
            print(f"✅ Рендерер готов (метод: {renderer.method})")
        except Exception as e:
            print(f"⚠️ Рендерер недоступен: {e}")
            print("  Превью не будут создаваться")
            renderer = None

        # GUI
        print("Запуск интерфейса...")
        app = STLManagerApp(db, scanner, renderer)
        app.protocol("WM_DELETE_WINDOW", app.on_closing)

        print("✅ Приложение запущено\n")
        app.mainloop()

    except KeyboardInterrupt:
        print("\n⏹ Остановлено")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()