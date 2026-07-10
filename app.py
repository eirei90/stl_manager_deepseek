#!/usr/bin/env python3
"""STL Manager - точка входа."""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Подавляем предупреждения
warnings.filterwarnings("ignore", category=UserWarning)
import os
os.environ['PYVISTA_OFF_SCREEN'] = 'true'

from models.database import Database
from services.scanner import STLScanner
from services.renderer import STLRenderer
from ui.main_window import STLManagerApp
from utils.logger import logger


def main():
    try:
        logger.info("=" * 50)
        logger.info("STL Manager - запуск")

        db = Database("stl_catalog.db")
        scanner = STLScanner(db)
        renderer = STLRenderer()

        app = STLManagerApp(db, scanner, renderer)
        app.mainloop()

    except KeyboardInterrupt:
        logger.info("Остановлено")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
