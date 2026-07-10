cat > /home/eirei/PycharmProjects/stl_manager/services/archive_utils.py << 'ENDSCRIPT'
"""Работа с архивами."""

import os
import tempfile
import shutil
import logging
from pathlib import Path
from typing import List, Generator
import zipfile

logger = logging.getLogger(__name__)

try:
    import py7zr
    PY7ZR_AVAILABLE = True
except ImportError:
    PY7ZR_AVAILABLE = False

try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False


class ArchiveExtractor:

    TARGET = {'.stl'}
    ARCHIVES = {'.7z', '.rar', '.zip'}

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="stl_")
        os.makedirs(self.temp_dir, exist_ok=True)

    def is_archive(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.ARCHIVES

    def list_stl_files(self, archive_path: str) -> List[str]:
        ext = Path(archive_path).suffix.lower()
        result = []
        try:
            if ext == '.zip':
                with zipfile.ZipFile(archive_path) as zf:
                    result = [n for n in zf.namelist() if Path(n).suffix.lower() in self.TARGET]
            elif ext == '.7z' and PY7ZR_AVAILABLE:
                with py7zr.SevenZipFile(archive_path, 'r') as szf:
                    result = [n for n in szf.getnames() if Path(n).suffix.lower() in self.TARGET]
            elif ext == '.rar' and RARFILE_AVAILABLE:
                with rarfile.RarFile(archive_path) as rf:
                    result = [i.filename for i in rf.infolist() if not i.isdir() and Path(i.filename).suffix.lower() in self.TARGET]
        except Exception as e:
            logger.error(f"Error: {e}")
        return result

    def extract_stl_files(self, archive_path: str) -> Generator[str, None, None]:
        ext = Path(archive_path).suffix.lower()
        name = Path(archive_path).stem
        extract_dir = os.path.join(self.temp_dir, name)
        os.makedirs(extract_dir, exist_ok=True)

        try:
            if ext == '.zip':
                with zipfile.ZipFile(archive_path) as zf:
                    for n in zf.namelist():
                        if Path(n).suffix.lower() in self.TARGET:
                            zf.extract(n, extract_dir)
                            p = os.path.join(extract_dir, n)
                            if os.path.exists(p):
                                yield p
            elif ext == '.7z' and PY7ZR_AVAILABLE:
                with py7zr.SevenZipFile(archive_path, 'r') as szf:
                    targets = [n for n in szf.getnames() if Path(n).suffix.lower() in self.TARGET]
                    if targets:
                        szf.extract(extract_dir, targets=targets)
                        for n in targets:
                            p = os.path.join(extract_dir, n)
                            if os.path.exists(p):
                                yield p
        except Exception as e:
            logger.error(f"Extract error: {e}")

    def cleanup(self):
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
        except:
            pass
ENDSCRIPT
