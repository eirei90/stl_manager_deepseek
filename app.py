#!/usr/bin/env python3
"""
STL Manager - Приложение для управления коллекцией STL-файлов.
Точка входа в программу.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from models.database import Database
from services.scanner import STLScanner
from services.renderer import STLRenderer
from ui.main_window import STLManagerApp
from utils.logger import logger


def main():
    """Главная функция запуска приложения."""
    try:
        logger.info("=" * 60)
        logger.info("  STL Manager - запуск приложения")
        logger.info("=" * 60)

        # Инициализация базы данных
        logger.info("Инициализация базы данных...")
        db = Database("stl_catalog.db")
        logger.info("База данных готова")

        # Инициализация сканера
        logger.info("Инициализация сканера...")
        scanner = STLScanner(db)
        logger.info("Сканер готов")

        # Инициализация рендерера
        logger.info("Инициализация рендерера...")
        renderer = None

        try:
            renderer = STLRenderer()
            logger.info(f"Рендерер готов (метод: {renderer.method})")
        except RuntimeError as e:
            logger.error(f"Ошибка инициализации рендерера: {e}")
            print(f"\n❌ Ошибка: {e}")
            print("\nДля рендеринга STL в изображения установите один из вариантов:")
            print("  1. vedo + vtk (рекомендуется):")
            print("     pip install vedo vtk")
            print("  2. matplotlib + trimesh (запасной):")
            print("     pip install matplotlib trimesh")
            print("  3. Только Pillow (будут создаваться заглушки):")
            print("     pip install Pillow trimesh")
            print("\nПриложение будет запущено без возможности рендеринга.")
            print("Вы сможете сканировать и каталогизировать файлы, но без превью.\n")

            # Пробуем запустить без рендерера
            renderer = None
        except Exception as e:
            logger.error(f"Неожиданная ошибка рендерера: {e}")
            print(f"\n⚠️ Предупреждение: {e}")
            print("Рендеринг может быть недоступен.\n")
            renderer = None

        # Запуск GUI
        logger.info("Запуск графического интерфейса...")
        app = STLManagerApp(db, scanner, renderer)

        # Обработка закрытия окна
        app.protocol("WM_DELETE_WINDOW", app.on_closing)

        logger.info("Главное окно открыто")
        print("✅ Приложение запущено. Закройте окно для выхода.")

        # Запуск главного цикла
        app.mainloop()

    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем (Ctrl+C)")
        print("\n⏹ Приложение остановлено.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        print(f"\n❌ Критическая ошибка: {e}")
        print("Проверьте лог-файл stl_manager.log для подробностей.")
        sys.exit(1)


if __name__ == "__main__":
    main()