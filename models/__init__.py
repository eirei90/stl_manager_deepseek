"""
Пакет моделей данных STL Manager.

Содержит:
- database.py — менеджер базы данных SQLite (схема, CRUD-операции)
- entities.py — классы-сущности (заготовка для будущего расширения)
"""

from models.database import Database

__all__ = ['Database']