"""
Модуль headless-рендеринга STL файлов в JPEG.
Использует vedo с VTK-бэкендом или matplotlib как запасной вариант.
"""

import os
import logging
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

# Пробуем импортировать vedo
try:
    import vedo
    vedo.settings.default_backend = 'vtk'

    try:
        vedo.settings.interactive = False
    except AttributeError:
        try:
            vedo.settings.allow_interaction = False
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

        # Пробуем vedo
        if VEDO_AVAILABLE:
            try:
                import vtk
                self.vtk_available = True
                self.method = "vedo"
                logger.info("Используется рендерер: vedo + VTK")
            except ImportError:
                logger.warning("VTK не установлен")

        # Пробуем matplotlib
        if not self.method:
            try:
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt
                self.method = "matplotlib"
                logger.info("Используется рендерер: matplotlib")
            except ImportError:
                pass

        # Запасной вариант - PIL
        if not self.method:
            try:
                from PIL import Image
                self.method = "pil"
                logger.info("Используется рендерер: PIL (заглушки)")
            except ImportError:
                pass

        if not self.method:
            raise RuntimeError("Не удалось инициализировать рендерер")

    def _get_mesh_points(self, mesh) -> int:
        """Получает количество точек в меше (совместимость с разными версиями vedo)."""
        try:
            return mesh.NPoints()
        except AttributeError:
            return mesh.npoints

    def _get_mesh_cells(self, mesh) -> int:
        """Получает количество граней в меше (совместимость с разными версиями vedo)."""
        try:
            return mesh.NCells()
        except AttributeError:
            return mesh.ncells

    def _get_mesh_bounds(self, mesh):
        """Получает границы меша (совместимость с разными версиями vedo)."""
        try:
            return mesh.bounds()
        except (AttributeError, TypeError):
            # В новых версиях bounds может быть свойством
            if hasattr(mesh, 'bounds'):
                b = mesh.bounds
                if callable(b):
                    return b()
                return b
        return [-1, 1, -1, 1, -1, 1]

    def _get_mesh_center(self, mesh):
        """Получает центр меша (совместимость с разными версиями vedo)."""
        try:
            return mesh.center_of_mass()
        except (AttributeError, TypeError):
            try:
                return mesh.centerOfMass()
            except:
                bounds = self._get_mesh_bounds(mesh)
                return [
                    (bounds[0] + bounds[1]) / 2,
                    (bounds[2] + bounds[3]) / 2,
                    (bounds[4] + bounds[5]) / 2,
                ]

    def _clone_mesh(self, mesh):
        """Клонирует меш (совместимость с разными версиями vedo)."""
        try:
            return mesh.clone()
        except AttributeError:
            # В новых версиях может быть copy()
            return mesh.copy()

    def render_to_jpeg(
        self,
        stl_path: str,
        output_path: str,
        resolution: tuple = DEFAULT_RESOLUTION
    ) -> bool:
        """
        Рендерит STL-файл в JPEG.
        """
        if not os.path.exists(stl_path):
            logger.error(f"Файл не найден: {stl_path}")
            return False

        logger.info(f"Рендеринг: {os.path.basename(stl_path)} (метод: {self.method})")

        # Безопасно создаём директорию для выходного файла
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                logger.error(f"Не удалось создать директорию {output_dir}: {e}")
                return False

        if self.method == "vedo":
            return self._render_vedo(stl_path, output_path, resolution)
        elif self.method == "matplotlib":
            return self._render_matplotlib(stl_path, output_path, resolution)
        elif self.method == "pil":
            return self._render_pil(stl_path, output_path, resolution)
        else:
            logger.error("Нет доступного метода рендеринга")
            return False

    def _render_vedo(self, stl_path: str, output_path: str, resolution: tuple) -> bool:
        """Рендеринг через vedo."""
        plotter = None
        try:
            import vedo

            # Загружаем меш
            logger.debug(f"Загрузка STL: {stl_path}")

            try:
                mesh = vedo.Mesh(stl_path)
            except Exception as e:
                logger.error(f"Ошибка загрузки меша: {e}")
                return False

            # Проверяем меш (используем новые методы)
            n_points = self._get_mesh_points(mesh)
            n_cells = self._get_mesh_cells(mesh)

            if n_points == 0:
                logger.error(f"Пустой меш: {stl_path}")
                return False

            logger.debug(f"Меш: {n_points} точек, {n_cells} граней")

            # Центр и размеры
            bounds = self._get_mesh_bounds(mesh)
            center = self._get_mesh_center(mesh)

            # Позиция камеры
            dx = max((bounds[1] - bounds[0]) * 1.5, 1.0)
            dy = max((bounds[3] - bounds[2]) * 1.5, 1.0)
            dz = max((bounds[5] - bounds[4]) * 1.5, 1.0)

            camera_pos = (
                center[0] + dx,
                center[1] + dy,
                center[2] + dz
            )

            # Создаём plotter
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

            # Полупрозрачная поверхность
            try:
                surf = self._clone_mesh(mesh)
                surf.color((0.7, 0.85, 1.0)).alpha(0.5)

                try:
                    surf.lighting(ambient=0.3, diffuse=0.6, specular=0.2, specular_power=10)
                except Exception:
                    pass  # Может не поддерживаться

                plotter.add(surf)
            except Exception as e:
                logger.warning(f"Не удалось добавить поверхность: {e}")
                mesh.alpha(0.5).color((0.7, 0.85, 1.0))
                plotter.add(mesh)

            # Wireframe
            try:
                wire = self._clone_mesh(mesh).wireframe().color((0.1, 0.1, 0.1)).linewidth(0.5)
                try:
                    wire.lighting(ambient=1.0, diffuse=0.0, specular=0.0)
                except:
                    pass
                plotter.add(wire)
            except Exception as e:
                logger.debug(f"Wireframe пропущен: {e}")

            # Освещение
            try:
                plotter.add_light(pos=(1, 1, 1), intensity=0.7)
                plotter.add_light(pos=(-0.5, 0.5, -0.5), intensity=0.4)
            except Exception:
                pass

            # Камера
            try:
                plotter.camera.SetPosition(camera_pos)
                plotter.camera.SetFocalPoint(center)
                plotter.camera.SetViewUp(0, 0, 1)
                plotter.camera.Zoom(1.3)
            except Exception as e:
                logger.debug(f"Ошибка камеры: {e}")

            # Сохраняем результат
            logger.debug(f"Сохранение в: {output_path}")

            try:
                plotter.screenshot(output_path, scale=1)
            except Exception as e:
                logger.error(f"Ошибка screenshot: {e}")
                return False

            # Закрываем
            try:
                plotter.close()
            except:
                pass
            plotter = None

            # Проверяем результат
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size > 0:
                    logger.info(f"✅ Превью создано: {os.path.basename(output_path)} ({file_size} байт)")
                    return True
                else:
                    logger.error(f"Файл превью пуст: {output_path}")
                    return False
            else:
                logger.error(f"Файл превью не создан: {output_path}")
                return False

        except Exception as e:
            logger.error(f"Ошибка vedo рендеринга: {e}", exc_info=True)
            return False
        finally:
            if plotter is not None:
                try:
                    plotter.close()
                except:
                    pass

    def _render_matplotlib(self, stl_path: str, output_path: str, resolution: tuple) -> bool:
        """Рендеринг через matplotlib."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            try:
                import trimesh
                mesh = trimesh.load(stl_path, file_type='stl')
                if mesh is None or len(mesh.faces) == 0:
                    return False
                vertices = mesh.vertices
                faces = mesh.faces
            except ImportError:
                logger.error("trimesh не установлен")
                return False

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
                output_path,
                format='jpg',
                dpi=dpi,
                facecolor='gray',
                bbox_inches='tight',
                pad_inches=0.1
            )
            plt.close(fig)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"✅ Превью (matplotlib): {os.path.basename(output_path)}")
                return True
            return False

        except Exception as e:
            logger.error(f"Ошибка matplotlib: {e}", exc_info=True)
            return False

    def _render_pil(self, stl_path: str, output_path: str, resolution: tuple) -> bool:
        """Создаёт информативную заглушку через PIL."""
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
                    info_lines.append(f"Размер: {extent[0]:.1f} x {extent[1]:.1f} x {extent[2]:.1f} мм")
            except:
                pass

            info_lines.append("")
            info_lines.append("3D превью недоступно")
            info_lines.append("Установите: pip install vedo vtk")

            img = Image.new('RGB', resolution, color=(50, 50, 55))
            draw = ImageDraw.Draw(img)

            draw.rectangle([8, 8, resolution[0]-8, resolution[1]-8], outline=(80, 80, 90), width=2)

            y = 25
            for line in info_lines:
                try:
                    draw.text((20, y), line, fill=(200, 200, 210))
                except:
                    pass
                y += 28

            img.save(output_path, 'JPEG', quality=90)
            logger.info(f"✅ Заглушка (PIL): {os.path.basename(output_path)}")
            return True

        except Exception as e:
            logger.error(f"Ошибка PIL: {e}")
            return False

    def create_error_placeholder(self, output_path: str, resolution: tuple = DEFAULT_RESOLUTION):
        """Создаёт заглушку для битых файлов."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            output_dir = os.path.dirname(os.path.abspath(output_path))
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            img = Image.new('RGB', resolution, color=(50, 50, 50))
            draw = ImageDraw.Draw(img)

            m = 30
            draw.line((m, m, resolution[0]-m, resolution[1]-m), fill=(220, 50, 50), width=5)
            draw.line((resolution[0]-m, m, m, resolution[1]-m), fill=(220, 50, 50), width=5)

            text = "ОШИБКА STL"
            try:
                font_paths = [
                    "/usr/share/fonts/TTF/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ]
                font = None
                for fp in font_paths:
                    if os.path.exists(fp):
                        font = ImageFont.truetype(fp, 22)
                        break
                if font is None:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_x = (resolution[0] - text_w) // 2

            draw.text((text_x, resolution[1]//2 + 20), text, fill=(255, 255, 255), font=font)

            img.save(output_path, 'JPEG', quality=85)
            logger.info(f"Placeholder: {output_path}")

        except Exception as e:
            logger.error(f"Ошибка placeholder: {e}")