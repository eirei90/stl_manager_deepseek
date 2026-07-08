"""
Утилиты для работы с архивами 7z и RAR.
Извлечение STL-файлов во временную директорию для анализа и рендеринга.
"""

import os
import tempfile
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Generator
import zipfile

logger = logging.getLogger(__name__)

# Проверка доступности библиотек
try:
    import py7zr
    PY7ZR_AVAILABLE = True
except ImportError:
    PY7ZR_AVAILABLE = False
    logger.warning("py7zr не установлен. Поддержка 7z будет отключена.")

try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False
    logger.warning("rarfile не установлен. Поддержка RAR будет отключена.")


class ArchiveExtractor:
    """
    Извлекает STL-файлы из архивов во временную директорию.
    Поддерживает форматы: 7z, rar, zip.
    """
    
    # Расширения файлов, которые мы ищем в архивах
    TARGET_EXTENSIONS = {'.stl'}
    
    # Поддерживаемые расширения архивов
    ARCHIVE_EXTENSIONS = {'.7z', '.rar', '.zip'}
    
    def __init__(self, temp_dir: Optional[str] = None):
        """
        Инициализация экстрактора.
        
        Args:
            temp_dir: Директория для временных файлов. Если None — используется системная.
        """
        self.temp_dir = temp_dir or tempfile.mkdtemp(prefix="stl_manager_")
        os.makedirs(self.temp_dir, exist_ok=True)
        logger.info(f"Временная директория для архивов: {self.temp_dir}")
    
    def is_archive(self, file_path: str) -> bool:
        """Проверяет, является ли файл поддерживаемым архивом."""
        ext = Path(file_path).suffix.lower()
        return ext in self.ARCHIVE_EXTENSIONS
    
    def list_stl_files(self, archive_path: str) -> List[str]:
        """
        Возвращает список STL-файлов внутри архива без извлечения.
        
        Args:
            archive_path: Путь к архиву
            
        Returns:
            Список путей к STL-файлам внутри архива
        """
        ext = Path(archive_path).suffix.lower()
        
        try:
            if ext == '.7z' and PY7ZR_AVAILABLE:
                return self._list_7z(archive_path)
            elif ext == '.rar' and RARFILE_AVAILABLE:
                return self._list_rar(archive_path)
            elif ext == '.zip':
                return self._list_zip(archive_path)
            else:
                logger.warning(f"Неподдерживаемый формат архива: {ext}")
                return []
        except Exception as e:
            logger.error(f"Ошибка чтения архива {archive_path}: {e}")
            return []
    
    def extract_stl_files(self, archive_path: str) -> Generator[str, None, None]:
        """
        Извлекает STL-файлы из архива во временную директорию.
        Генератор: возвращает путь к каждому извлечённому файлу.
        
        Args:
            archive_path: Путь к архиву
            
        Yields:
            Путь к извлечённому STL-файлу
        """
        ext = Path(archive_path).suffix.lower()
        archive_name = Path(archive_path).stem
        
        # Создаём поддиректорию для этого архива
        extract_dir = os.path.join(self.temp_dir, archive_name)
        os.makedirs(extract_dir, exist_ok=True)
        
        try:
            if ext == '.7z' and PY7ZR_AVAILABLE:
                yield from self._extract_7z(archive_path, extract_dir)
            elif ext == '.rar' and RARFILE_AVAILABLE:
                yield from self._extract_rar(archive_path, extract_dir)
            elif ext == '.zip':
                yield from self._extract_zip(archive_path, extract_dir)
        except Exception as e:
            logger.error(f"Ошибка извлечения из архива {archive_path}: {e}")
    
    def _list_7z(self, archive_path: str) -> List[str]:
        """Список STL-файлов в 7z архиве."""
        stl_files = []
        with py7zr.SevenZipFile(archive_path, mode='r') as archive:
            for name in archive.getnames():
                if Path(name).suffix.lower() in self.TARGET_EXTENSIONS:
                    stl_files.append(name)
        return stl_files
    
    def _list_rar(self, archive_path: str) -> List[str]:
        """Список STL-файлов в RAR архиве."""
        stl_files = []
        with rarfile.RarFile(archive_path) as archive:
            for info in archive.infolist():
                if not info.isdir():
                    if Path(info.filename).suffix.lower() in self.TARGET_EXTENSIONS:
                        stl_files.append(info.filename)
        return stl_files
    
    def _list_zip(self, archive_path: str) -> List[str]:
        """Список STL-файлов в ZIP архиве."""
        stl_files = []
        with zipfile.ZipFile(archive_path, 'r') as archive:
            for name in archive.namelist():
                if Path(name).suffix.lower() in self.TARGET_EXTENSIONS:
                    stl_files.append(name)
        return stl_files
    
    def _extract_7z(self, archive_path: str, extract_dir: str) -> Generator[str, None, None]:
        """Извлекает STL из 7z."""
        with py7zr.SevenZipFile(archive_path, mode='r') as archive:
            # Получаем список целевых файлов
            target_files = [
                name for name in archive.getnames()
                if Path(name).suffix.lower() in self.TARGET_EXTENSIONS
            ]
            
            if target_files:
                archive.extract(extract_dir, targets=target_files)
                for name in target_files:
                    extracted_path = os.path.join(extract_dir, name)
                    if os.path.exists(extracted_path):
                        yield extracted_path
    
    def _extract_rar(self, archive_path: str, extract_dir: str) -> Generator[str, None, None]:
        """Извлекает STL из RAR."""
        with rarfile.RarFile(archive_path) as archive:
            for info in archive.infolist():
                if not info.isdir() and Path(info.filename).suffix.lower() in self.TARGET_EXTENSIONS:
                    archive.extract(info, extract_dir)
                    extracted_path = os.path.join(extract_dir, info.filename)
                    if os.path.exists(extracted_path):
                        yield extracted_path
    
    def _extract_zip(self, archive_path: str, extract_dir: str) -> Generator[str, None, None]:
        """Извлекает STL из ZIP."""
        with zipfile.ZipFile(archive_path, 'r') as archive:
            for name in archive.namelist():
                if Path(name).suffix.lower() in self.TARGET_EXTENSIONS:
                    archive.extract(name, extract_dir)
                    extracted_path = os.path.join(extract_dir, name)
                    if os.path.exists(extracted_path):
                        yield extracted_path
    
    def cleanup(self):
        """Удаляет все временные файлы."""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Временная директория удалена: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Не удалось удалить временную директорию: {e}")
    
    def __del__(self):
        """Деструктор — пытается очистить временные файлы."""
        self.cleanup()