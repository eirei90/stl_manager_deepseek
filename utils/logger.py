"""
Настройка логирования для приложения.
Логи пишутся в файл stl_manager.log и выводятся в консоль.
Поддерживает кириллицу в логах.
"""

import logging
import sys
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "stl_manager.log"

# Настройка обработчика файла с поддержкой UTF-8
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))

# Настройка обработчика консоли с поддержкой UTF-8
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
))

# Настройка корневого логгера
root_logger = logging.getLogger("STLManager")
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = root_logger