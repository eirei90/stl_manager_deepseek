"""
Пакет пользовательского интерфейса STL Manager.

Содержит:
- main_window.py — главное окно приложения (CustomTkinter)
- cards.py — виджет карточки STL-файла
- workers.py — фоновые потоки для длительных операций
"""

from ui.main_window import STLManagerApp

__all__ = ['STLManagerApp']