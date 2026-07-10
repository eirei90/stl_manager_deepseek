"""
Модуль рендеринга STL файлов в JPEG.
Использует matplotlib (без OpenGL) или ищет существующие изображения.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Настройка matplotlib без GUI
import matplotlib
matplotlib.use('Agg')

class STLRenderer:
    """Генератор превью для STL-файлов."""

    DEFAULT_RESOLUTION = (512, 512)
    EXISTING_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

    def __init__(self):
        """Инициализация рендерера."""
        self.method = "matplotlib"

        try:
            import matplotlib.pyplot as plt
            import trimesh
            logger.info("Рендерер готов: matplotlib + trimesh")
        except ImportError as e:
            logger.warning(f"Не все библиотеки доступны: {e}")

        logger.info("Также будет проверяться наличие существующих изображений")

    def find_existing_image(self, stl_path: str) -> Optional[str]:
        """
        Ищет существующее изображение с тем же именем, что и STL-файл.

        Returns:
            Путь к найденному изображению или None
        """
        stl_file = Path(stl_path)
        stl_dir = stl_file.parent
        stl_stem = stl_file.stem

        # Ищем файлы с тем же именем, но другим расширением
        for ext in self.EXISTING_EXTENSIONS:
            # Проверяем в той же папке
            candidate = stl_dir / f"{stl_stem}{ext}"
            if candidate.exists():
                logger.info(f"Найдено существующее изображение: {candidate.name}")
                return str(candidate)

            # Проверяем в .thumbs
            candidate = stl_dir / ".thumbs" / f"{stl_stem}{ext}"
            if candidate.exists():
                logger.info(f"Найдено изображение в .thumbs: {candidate.name}")
                return str(candidate)

        return None

    def copy_existing_image(self, source_path: str, output_path: str) -> bool:
        """
        Копирует существующее изображение как превью.
        Если формат не JPEG — конвертирует.
        """
        try:
            from PIL import Image

            img = Image.open(source_path)

            # Конвертируем RGBA/PNG в RGB для JPEG
            if img.mode in ('RGBA', 'P'):
                # Создаём серый фон
                background = Image.new('RGB', img.size, (128, 128, 128))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Изменяем размер
            img = img.resize(self.DEFAULT_RESOLUTION, Image.Resampling.LANCZOS)

            # Сохраняем как JPEG
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, 'JPEG', quality=90)

            logger.info(f"Изображение сохранено: {os.path.basename(output_path)}")
            return True

        except Exception as e:
            logger.error(f"Ошибка копирования изображения: {e}")
            return False

    def render_to_jpeg(self, stl_path: str, output_path: str,
                       resolution=DEFAULT_RESOLUTION) -> bool:
        """Рендерит STL в JPEG."""
        if not os.path.exists(stl_path):
            logger.error(f"Файл не найден: {stl_path}")
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        try:
            import matplotlib.pyplot as plt
            import trimesh
            import numpy as np

            mesh = trimesh.load(stl_path, file_type='stl')
            if mesh is None or len(mesh.faces) == 0:
                logger.error(f"Не удалось загрузить: {stl_path}")
                return False

            vertices = mesh.vertices
            faces = mesh.faces

            dpi = 100
            figsize = (resolution[0]/dpi, resolution[1]/dpi)
            fig = plt.figure(figsize=figsize, dpi=dpi, facecolor='#555555')
            ax = fig.add_subplot(111, projection='3d')
            ax.set_facecolor('#666666')

            # Основная поверхность
            ax.plot_trisurf(
                vertices[:, 0], vertices[:, 1], vertices[:, 2],
                triangles=faces,
                alpha=0.75,
                color='#7EB8DA',
                edgecolor='#333333',
                linewidth=0.4,
                shade=True,
                antialiased=True
            )

            # Изометрия
            ax.view_init(elev=25, azim=45)
            ax.set_axis_off()

            # Убираем отступы
            plt.subplots_adjust(0, 0, 1, 1)

            plt.savefig(output_path, format='jpg', dpi=dpi,
                       facecolor=fig.get_facecolor(),
                       bbox_inches='tight', pad_inches=0.1)
            plt.close(fig)

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
