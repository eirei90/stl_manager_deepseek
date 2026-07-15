"""
Модуль рендеринга STL/OBJ файлов в JPEG.
Использует matplotlib с переиспользованием фигуры (без GUI).
"""

import os
import logging
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import trimesh
import numpy as np

logger = logging.getLogger(__name__)


class STLRenderer:
    """Генератор превью для STL/OBJ-файлов."""

    DEFAULT_RESOLUTION = (512, 512)
    EXISTING_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

    def __init__(self):
        """Инициализация рендерера с переиспользуемой фигурой."""
        self.method = "matplotlib"
        # Создаём фигуру и оси один раз
        dpi = 100
        self.fig = plt.figure(
            figsize=(self.DEFAULT_RESOLUTION[0]/dpi, self.DEFAULT_RESOLUTION[1]/dpi),
            dpi=dpi,
            facecolor='#555555'
        )
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.ax.set_facecolor('#666666')
        # Кэш для загрузки мешей (опционально, ограничен 50 последними)
        self._mesh_cache = {}
        self._max_cache_size = 50

        logger.info("Рендерер готов: matplotlib + trimesh (оптимизированный)")

    def find_existing_image(self, stl_path: str) -> Optional[str]:
        """Ищет существующее изображение с тем же именем, что и STL/OBJ."""
        stl_file = Path(stl_path)
        stl_dir = stl_file.parent
        stl_stem = stl_file.stem

        for ext in self.EXISTING_EXTENSIONS:
            candidate = stl_dir / f"{stl_stem}{ext}"
            if candidate.exists():
                logger.info(f"Найдено существующее изображение: {candidate.name}")
                return str(candidate)
            candidate = stl_dir / ".thumbs" / f"{stl_stem}{ext}"
            if candidate.exists():
                logger.info(f"Найдено изображение в .thumbs: {candidate.name}")
                return str(candidate)
        return None

    def copy_existing_image(self, source_path: str, output_path: str) -> bool:
        """Копирует/конвертирует существующее изображение как превью."""
        try:
            from PIL import Image
            img = Image.open(source_path)
            if img.mode in ('RGBA', 'P'):
                background = Image.new('RGB', img.size, (128, 128, 128))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            img = img.resize(self.DEFAULT_RESOLUTION, Image.Resampling.LANCZOS)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, 'JPEG', quality=90)
            return True
        except Exception as e:
            logger.error(f"Ошибка копирования изображения: {e}")
            return False

    def render_to_jpeg(self, stl_path: str, output_path: str,
                       resolution=DEFAULT_RESOLUTION) -> bool:
        """Рендерит STL/OBJ в JPEG с переиспользованием фигуры."""
        if not os.path.exists(stl_path):
            logger.error(f"Файл не найден: {stl_path}")
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        try:
            # Загрузка меша с кэшированием
            if stl_path in self._mesh_cache:
                mesh = self._mesh_cache[stl_path]
            else:
                loaded = trimesh.load(stl_path)
                if isinstance(loaded, trimesh.Scene):
                    meshes = [geom for geom in loaded.geometry.values()
                             if hasattr(geom, 'faces') and len(geom.faces) > 0]
                    if not meshes:
                        logger.error(f"Нет мешей в сцене: {stl_path}")
                        return False
                    mesh = trimesh.util.concatenate(meshes)
                else:
                    mesh = loaded
                # Кэшируем
                if len(self._mesh_cache) >= self._max_cache_size:
                    self._mesh_cache.clear()  # Простая очистка, можно LRU
                self._mesh_cache[stl_path] = mesh

            if mesh is None or not hasattr(mesh, 'faces') or len(mesh.faces) == 0:
                logger.error(f"Не удалось загрузить меш: {stl_path}")
                return False

            vertices = mesh.vertices
            faces = mesh.faces

            # Подгоняем размер фигуры под текущее разрешение
            dpi = self.fig.get_dpi()
            need_resize = (resolution != self.DEFAULT_RESOLUTION)
            if need_resize:
                self.fig.set_size_inches(resolution[0]/dpi, resolution[1]/dpi)

            # Очищаем оси от предыдущего графика
            self.ax.clear()
            self.ax.set_facecolor('#666666')

            # Рендерим (отключаем shade для скорости)
            self.ax.plot_trisurf(
                vertices[:, 0], vertices[:, 1], vertices[:, 2],
                triangles=faces,
                alpha=0.75,
                color='#7EB8DA',
                edgecolor='#333333',
                linewidth=0.4,
                shade=False,          # Быстрее без расчёта освещения
                antialiased=True
            )

            self.ax.view_init(elev=25, azim=45)
            self.ax.set_axis_off()

            # Сохраняем
            self.fig.savefig(
                output_path, format='jpg', dpi=dpi,
                facecolor=self.fig.get_facecolor(),
                bbox_inches='tight', pad_inches=0.1
            )

            # Если меняли размер, возвращаем обратно
            if need_resize:
                self.fig.set_size_inches(
                    self.DEFAULT_RESOLUTION[0]/dpi,
                    self.DEFAULT_RESOLUTION[1]/dpi
                )

            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                logger.info(f"✅ Превью: {os.path.basename(output_path)}")
                return True
            return False

        except Exception as e:
            logger.error(f"Ошибка рендеринга {stl_path}: {e}")
            return False

    def create_error_placeholder(self, output_path: str, resolution=DEFAULT_RESOLUTION):
        """Создаёт заглушку для битых файлов."""
        try:
            from PIL import Image, ImageDraw
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            img = Image.new('RGB', resolution, color=(50, 50, 50))
            draw = ImageDraw.Draw(img)
            m = 30
            draw.line((m, m, resolution[0]-m, resolution[1]-m), fill=(220, 60, 60), width=5)
            draw.line((resolution[0]-m, m, m, resolution[1]-m), fill=(220, 60, 60), width=5)
            img.save(output_path, 'JPEG', quality=85)
        except Exception as e:
            logger.error(f"Ошибка placeholder: {e}")
