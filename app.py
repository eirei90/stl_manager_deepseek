#!/usr/bin/env python3
"""
STL Manager - Приложение для управления коллекцией STL-файлов.
Точка входа в программу.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models import Database
from services.scanner import STLScanner
from services.renderer import STLRenderer, SimpleRenderer
from ui import STLManagerApp
from utils import logger


def main():
    """Главная функция запуска приложения."""
    try:
        logger.info("=" * 50)
        logger.info("Запуск STL Manager")
        logger.info("=" * 50)
        
        # Инициализация слоя данных
        db = Database("stl_catalog.db")
        
        # Инициализация сервисов
        scanner = STLScanner(db)
        
        # Инициализация рендерера с fallback
        renderer = None
        try:
            renderer = STLRenderer()
            logger.info("Рендерер (vedo+VTK) успешно инициализирован")
        except (RuntimeError, Exception) as e:
            logger.warning(f"Не удалось инициализировать основной рендерер: {e}")
            logger.info("Пробуем упрощённый рендерер (matplotlib)...")
            try:
                renderer = SimpleRenderer()
                logger.info("Упрощённый рендерер инициализирован")
                print("⚠️  Используется упрощённый рендерер (качество превью будет ниже)")
            except Exception as e2:
                logger.error(f"Не удалось инициализировать даже упрощённый рендерер: {e2}")
                print("❌ Рендеринг недоступен. Установите одно из: vtk, matplotlib+trimesh")
        
        # Запуск GUI
        app = STLManagerApp(db, scanner, renderer)
        
        # Обработка закрытия окна
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        
        logger.info("Главное окно запущено")
        app.mainloop()
        
    except KeyboardInterrupt:
        logger.info("Приложение остановлено пользователем")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        print(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()