"""
Пакет бизнес-логики STL Manager.

Содержит:
- scanner.py — рекурсивный обход директорий, парсинг STL, извлечение метаданных
- renderer.py — headless-рендеринг STL в JPEG (vedo + VTK)
"""

from services.scanner import STLScanner
from services.renderer import STLRenderer

__all__ = ['STLScanner', 'STLRenderer']