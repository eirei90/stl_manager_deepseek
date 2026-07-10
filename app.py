"""STL Manager - точка входа."""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

import os
os.environ['PYVISTA_OFF_SCREEN'] = 'true'

# ============================================================
# ПАТЧ: исправление бага скролла в CustomTkinter
# ============================================================
import customtkinter as ctk

_original_check = ctk.CTkScrollableFrame._check_if_valid_scroll
_patch_enabled = True  # Флаг для временного отключения патча

def _patched_check(self, widget):
    """Безопасная проверка с возможностью отключения."""
    global _patch_enabled

    # Если патч отключен — используем оригинал
    if not _patch_enabled:
        return _original_check(self, widget)

    # Если widget — не виджет, игнорируем
    if not hasattr(widget, 'master'):
        return False

    try:
        while widget is not None:
            if widget is self:
                return True
            if not hasattr(widget, 'master'):
                return False
            widget = widget.master
        return False
    except Exception:
        return False

ctk.CTkScrollableFrame._check_if_valid_scroll = _patched_check

# Функции для управления патчем
def disable_scroll_patch():
    global _patch_enabled
    _patch_enabled = False

def enable_scroll_patch():
    global _patch_enabled
    _patch_enabled = True
# ============================================================

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
