"""
Модуль headless-рендеринга STL файлов в JPEG.
Поддерживает vedo+VTK, matplotlib, PIL.
"""

import os
import logging
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# Принудительно отключаем OpenGL перед импортом VTK
os.environ.setdefault('VTK_OPENGL_HAS_EGL', '1')
os.environ.setdefault('VTK_USE_EGL', '1')
os.environ.setdefault('PYVISTA_OFF_SCREEN', 'true')
os.environ.setdefault('PYVISTA_USE_PANEL', 'false')
os.environ.setdefault('DISPLAY', ':0')

# Пробуем импортировать vedo
try:
    import vedo
    vedo.settings.default_backend = 'vtk'

    try:
        vedo.settings.interactive = False
    except AttributeError:
        pass

    VEDO_AVAILABLE = True
    logger.info(f"vedo импортирован (версия: {vedo.__version__})")
except ImportError:
    VEDO_AVAILABLE = False
    logger.warning("vedo не установлен")


class STLRenderer:
    """Генератор JPEG-превью для STL-файлов."""

    DEFAULT_RESOLUTION = (512, 512)

    def __init__(self):
        """Инициализация рендерера."""
        self.method = None

        # Сначала пробуем matplotlib (более надёжный)
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            self.method = "matplotlib"
            logger.info("Используется рендерер: matplotlib")
            return
        except ImportError:
            pass

        # Пробуем vedo
        if VEDO_AVAILABLE:
            try:
                import vtk
                self.vtk_available = True
                self.method = "vedo"
                logger.info("Используется рендерер: vedo + VTK")
                return
            except ImportError:
                logger.warning("VTK не установлен")

        # Запасной вариант - PIL
        try:
            from PIL import Image
            self.method = "pil"
            logger.info("Используется рендерер: PIL (заглушки)")
            return
        except ImportError:
            pass

        raise RuntimeError("Не удалось инициализировать рендерер")

    def render_to_jpeg(self, stl_path: str, output_path: str, resolution=DEFAULT_RESOLUTION) -> bool:
        """Рендерит STL-файл в JPEG."""
        if not os.path.exists(stl_path):
            logger.error(f"Файл не найден: {stl_path}")
            return False

        logger.info(f"Рендеринг: {os.path.basename(stl_path)} (метод: {self.method})")

        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if self.method == "matplotlib":
            return self._render_matplotlib(stl_path, output_path, resolution)
        elif self.method == "vedo":
            return self._render_vedo(stl_path, output_path, resolution)
        elif self.method == "pil":
            return self._render_pil(stl_path, output_path, resolution)
        else:
            return False

    def _render_matplotlib(self, stl_path: str, output_path: str, resolution: tuple) -> bool:
        """Рендеринг через matplotlib (без OpenGL)."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import trimesh

            mesh = trimesh.load(stl_path, file_type='stl')
            if mesh is None or len(mesh.faces) == 0:
                logger.error(f"Не удалось загрузить меш: {stl_path}")
                return False

            vertices = mesh.vertices
            faces = mesh.faces

            dpi = 100
            figsize = (resolution[0]/dpi, resolution[1]/dpi)
            fig = plt.figure(figsize=figsize, dpi=dpi)
            ax = fig.add_subplot(111, projection='3d')

            ax.plot_trisurf(
                vertices[:, 0], vertices[:, 1], vertices[:, 2],
                triangles=faces,
                alpha=0.7,
                color='lightblue',
                edgecolor='darkgray',
                linewidth=0.3,
                shade=True
            )

            ax.view_init(elev=25, azim=45)
            ax.set_axis_off()

            plt.tight_layout(pad=0)
            plt.savefig(
                output_path, format='jpg', dpi=dpi,
                facecolor='gray', bbox_inches='tight', pad_inches=0.1
            )
            plt.close(fig)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"✅ Превью (matplotlib): {os.path.basename(output_path)}")
                return True
            return False

        except Exception as e:
            logger.error(f"Ошибка matplotlib: {e}", exc_info=True)
            return False

    def _render_vedo(self, stl_path: str, output_path: str, resolution: tuple) -> bool:
        """Рендеринг через vedo (может падать без OpenGL)."""
        plotter = None
        try:
            import vedo

            mesh = vedo.Mesh(stl_path)

            # Проверяем меш
            try:
                n_points = mesh.npoints
            except:
                n_points = mesh.NPoints() if hasattr(mesh, 'NPoints') else 0

            if n_points == 0:
                logger.error(f"Пустой меш: {stl_path}")
                return False

            # Пробуем EGL backend
            try:
                plotter = vedo.Plotter(
                    offscreen=True,
                    size=resolution,
                    bg=(0.6, 0.6, 0.6),
                    bg2=(0.3, 0.3, 0.3)
                )
            except TypeError:
                plotter = vedo.Plotter(
                    offscreen=True,
                    size=resolution,
                    bg=(0.5, 0.5, 0.5)
                )

            # Упрощённый рендер
            mesh.color((0.7, 0.85, 1.0)).alpha(0.5)
            plotter.add(mesh)

            try:
                wire = mesh.clone().wireframe().color((0.1, 0.1, 0.1)).linewidth(0.5)
                plotter.add(wire)
            except:
                pass

            plotter.screenshot(output_path, scale=1)

            try:
                plotter.close()
            except:
                pass
            plotter = None

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"✅ Превью (vedo): {os.path.basename(output_path)}")
                return True
            return False

        except Exception as e:
            logger.error(f"Ошибка vedo: {e}")
            return False
        finally:
            if plotter is not None:
                try:
                    plotter.close()
                except:
                    pass

    def _render_pil(self, stl_path: str, output_path: str, resolution: tuple) -> bool:
        """Заглушка через PIL."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            info_lines = [f"Файл: {os.path.basename(stl_path)}"]

            try:
                import trimesh
                mesh = trimesh.load(stl_path, file_type='stl')
                if mesh is not None:
                    info_lines.append(f"Граней: {len(mesh.faces):,}")
                    bounds = mesh.bounds
                    extent = bounds[1] - bounds[0]
                    info_lines.append(f"Размер: {extent[0]:.1f} x {extent[1]:.1f} x {extent[2]:.1f}")
            except:
                pass

            img = Image.new('RGB', resolution, color=(50, 50, 55))
            draw = ImageDraw.Draw(img)

            y = 25
            for line in info_lines:
                draw.text((20, y), line, fill=(200, 200, 210))
                y += 28

            img.save(output_path, 'JPEG', quality=90)
            return True

        except Exception as e:
            logger.error(f"Ошибка PIL: {e}")
            return False

    def create_error_placeholder(self, output_path: str, resolution=DEFAULT_RESOLUTION):
        """Создаёт заглушку для битых файлов."""
        try:
            from PIL import Image, ImageDraw

            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            img = Image.new('RGB', resolution, color=(50, 50, 50))
            draw = ImageDraw.Draw(img)

            m = 30
            draw.line((m, m, resolution[0]-m, resolution[1]-m), fill=(220, 50, 50), width=5)
            draw.line((resolution[0]-m, m, m, resolution[1]-m), fill=(220, 50, 50), width=5)

            img.save(output_path, 'JPEG', quality=85)

        except Exception as e:
            logger.error(f"Ошибка placeholder: {e}")