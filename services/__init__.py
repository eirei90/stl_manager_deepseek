"""
Пакет бизнес-логики STL Manager.

Содержит:
- scanner.py — рекурсивный обход директорий, поиск в архивах, парсинг STL
- renderer.py — headless-рендеринг STL в JPEG (vedo/matplotlib/PIL)
- archive_utils.py — работа с архивами 7z, RAR, ZIP
"""

from services.scanner import STLScanner
from services.renderer import STLRenderer

__all__ = ['STLScanner', 'STLRenderer']