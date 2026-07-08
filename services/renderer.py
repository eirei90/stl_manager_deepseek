"""
Модуль headless-рендеринга STL файлов в JPEG.
Использует vedo с VTK-бэкендом для создания превью с полупрозрачным материалом,
трёхточечным освещением и видимым wireframe.
"""

import os
import logging
from typing import Optional
import vedo

# Критически важно для работы без дисплея
vedo.settings.default_backend = 'vtk'
# В новых версиях vedo может не быть атрибута interactive
try:
    vedo.settings.interactive = False
except AttributeError:
    # В новых версиях используем allow_interaction
    try:
        vedo.settings.allow_interaction = False
    except AttributeError:
        pass
    logger = logging.getLogger(__name__)
    logger.warning("Не удалось установить interactive=False, может потребоваться ручная настройка")

# Отключаем использование блокнотов (если есть)
try:
    vedo.settings.notebook = False
except AttributeError:
    pass

logger = logging.getLogger(__name__)


class STLRenderer:
    """
    Генератор JPEG-превью для STL-файлов.
    
    Особенности рендера:
    - Полупрозрачный материал с видимым каркасом (wireframe)
    - Трёхточечное студийное освещение
    - Градиентный серый фон (белые модели не сливаются)
    - Размер выходного изображения 512x512
    """
    
    # Параметры выходного изображения
    DEFAULT_RESOLUTION = (512, 512)
    
    # Цвета для градиентного фона (светло-серый -> тёмно-серый)
    BACKGROUND_TOP = (0.75, 0.75, 0.75)
    BACKGROUND_BOTTOM = (0.35, 0.35, 0.35)
    
    # Параметры полупрозрачного материала
    MESH_COLOR = (0.6, 0.8, 1.0)   # Голубоватый оттенок
    MESH_ALPHA = 0.4                # Прозрачность
    WIRE_COLOR = (0.2, 0.2, 0.2)   # Тёмно-серый цвет рёбер
    WIRE_WIDTH = 0.5
    
    # Освещение: три источника (ключевой, заполняющий, контровой)
    LIGHTS = [
        {"position": (1, 1, 1), "intensity": 0.8},   # Key light
        {"position": (-0.5, 0.5, -0.5), "intensity": 0.4},  # Fill light
        {"position": (0, -1, 0), "intensity": 0.3},   # Rim/back light
    ]
    
    def __init__(self):
        """Инициализация рендерера. Проверяет доступность VTK."""
        try:
            import vtk
            self.vtk_available = True
            logger.info("VTK backend доступен для headless-рендеринга")
        except ImportError:
            self.vtk_available = False
            logger.error("VTK не установлен! Рендеринг невозможен.")
            raise RuntimeError(
                "Для рендеринга требуется VTK. Установите: pip install vtk"
            )
    
    def render_to_jpeg(
        self,
        stl_path: str,
        output_path: str,
        resolution: tuple = DEFAULT_RESOLUTION
    ) -> bool:
        """
        Рендерит STL-файл в JPEG.
        
        Args:
            stl_path: Путь к STL-файлу
            output_path: Путь для сохранения JPEG
            resolution: Кортеж (ширина, высота)
            
        Returns:
            bool: True в случае успеха, False при ошибке
        """
        plotter = None
        try:
            logger.debug(f"Рендеринг: {stl_path} -> {output_path}")
            
            # Загружаем меш
            mesh = vedo.Mesh(stl_path)
            
            # Вычисляем bounding box для автоматического кадрирования
            bounds = mesh.bounds()  # [xmin, xmax, ymin, ymax, zmin, zmax]
            center = mesh.center_of_mass()
            
            # Настройка камеры: изометрический вид
            camera_position = (
                center[0] + bounds[1] - bounds[0],
                center[1] + bounds[3] - bounds[2],
                center[2] + bounds[5] - bounds[4]
            )
            
            # Создаём plotter с явным указанием offscreen
            plotter = vedo.Plotter(
                offscreen=True,           # Без оконного вывода
                size=resolution,
                bg=self.BACKGROUND_TOP,   # Базовый цвет фона
                bg2=self.BACKGROUND_BOTTOM,  # Градиент
                title="STL Preview",
                interactive=False  # Явно отключаем интерактивность для этого плоттера
            )
            
            # === Материал и визуализация ===
            
            # Полупрозрачная поверхность
            mesh_surface = mesh.clone().color(self.MESH_COLOR).alpha(self.MESH_ALPHA)
            mesh_surface.lighting(
                ambient=0.2,
                diffuse=0.6,
                specular=0.3,
                specular_power=20,
                specular_color=(1, 1, 1)
            )
            plotter.add(mesh_surface)
            
            # Wireframe поверх (рёбра)
            wireframe = mesh.clone().wireframe()
            wireframe.color(self.WIRE_COLOR).linewidth(self.WIRE_WIDTH)
            wireframe.lighting(ambient=1.0, diffuse=0.0, specular=0.0)  # Без бликов
            plotter.add(wireframe)
            
            # === Освещение ===
            for light in self.LIGHTS:
                plotter.add_light(
                    pos=light["position"],
                    intensity=light["intensity"]
                )
            
            # Направляем камеру
            plotter.camera.SetPosition(camera_position)
            plotter.camera.SetFocalPoint(center)
            plotter.camera.SetViewUp(0, 0, 1)  # Ось Z вверх
            plotter.camera.Zoom(1.2)
            
            # Сохраняем результат
            plotter.screenshot(output_path, scale=1)
            logger.info(f"Превью сохранено: {output_path}")
            return True
            
        except vedo.exceptions.VedoException as e:
            logger.error(f"Ошибка vedo при рендеринге {stl_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка рендеринга {stl_path}: {e}", exc_info=True)
            return False
        finally:
            # Гарантированно освобождаем ресурсы VTK
            if plotter is not None:
                try:
                    plotter.close()
                except Exception:
                    pass
    
    def create_error_placeholder(self, output_path: str, resolution: tuple = DEFAULT_RESOLUTION):
        """
        Создаёт изображение-заглушку для битых файлов.
        
        Args:
            output_path: Путь для сохранения
            resolution: Размер изображения
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new('RGB', resolution, color=(60, 60, 60))
            draw = ImageDraw.Draw(img)
            
            # Красный крест
            draw.line((50, 50, resolution[0]-50, resolution[1]-50), fill=(200, 50, 50), width=5)
            draw.line((resolution[0]-50, 50, 50, resolution[1]-50), fill=(200, 50, 50), width=5)
            
            # Текст ошибки
            text = "BROKEN STL"
            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except IOError:
                font = ImageFont.load_default()
            
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_x = (resolution[0] - text_width) // 2
            text_y = resolution[1] // 2 + 30
            draw.text((text_x, text_y), text, fill=(255, 255, 255), font=font)
            
            img.save(output_path, 'JPEG', quality=85)
            logger.info(f"Placeholder создан: {output_path}")
            
        except Exception as e:
            logger.error(f"Ошибка создания placeholder: {e}")


# Альтернативная упрощённая версия рендерера без VTK (запасной вариант)
class SimpleRenderer:
    """
    Упрощённый рендерер без VTK.
    Использует matplotlib для создания простых превью.
    """
    
    def __init__(self):
        logger.info("Используется упрощённый рендерер (matplotlib)")
        
    def render_to_jpeg(self, stl_path: str, output_path: str, resolution=(512, 512)) -> bool:
        """
        Рендерит STL используя matplotlib (менее качественно, но без VTK).
        """
        try:
            import matplotlib
            matplotlib.use('Agg')  # Headless backend
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d import Axes3D
            import numpy as np
            
            # Пробуем загрузить STL через trimesh
            try:
                import trimesh
                mesh = trimesh.load(stl_path)
                if mesh is None or len(mesh.faces) == 0:
                    return False
                
                vertices = mesh.vertices
                faces = mesh.faces
                
                # Создаём 3D-график
                fig = plt.figure(figsize=(resolution[0]/100, resolution[1]/100), dpi=100)
                ax = fig.add_subplot(111, projection='3d')
                
                # Рендерим меш
                ax.plot_trisurf(
                    vertices[:, 0], vertices[:, 1], vertices[:, 2],
                    triangles=faces,
                    alpha=0.6,
                    color='lightblue',
                    edgecolor='darkgray',
                    linewidth=0.2
                )
                
                # Настройка вида
                ax.view_init(elev=30, azim=45)
                ax.set_axis_off()
                
                # Сохраняем
                plt.tight_layout()
                plt.savefig(output_path, format='jpg', dpi=100, 
                           facecolor='gray', bbox_inches='tight', pad_inches=0)
                plt.close(fig)
                
                logger.info(f"Превью создано (matplotlib): {output_path}")
                return True
                
            except ImportError:
                logger.error("trimesh не установлен для SimpleRenderer")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка SimpleRenderer: {e}")
            return False
    
    def create_error_placeholder(self, output_path: str, resolution=(512, 512)):
        """Создаёт заглушку (тот же метод, что у основного рендерера)."""
        # Используем тот же метод из PIL
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new('RGB', resolution, color=(60, 60, 60))
            draw = ImageDraw.Draw(img)
            
            draw.line((50, 50, resolution[0]-50, resolution[1]-50), fill=(200, 50, 50), width=5)
            draw.line((resolution[0]-50, 50, 50, resolution[1]-50), fill=(200, 50, 50), width=5)
            
            text = "BROKEN STL"
            try:
                font = ImageFont.truetype("arial.ttf", 24)
            except IOError:
                font = ImageFont.load_default()
            
            draw.text((resolution[0]//2 - 70, resolution[1]//2 + 20), text, 
                     fill=(255, 255, 255), font=font)
            
            img.save(output_path, 'JPEG', quality=85)
        except Exception as e:
            logger.error(f"Ошибка создания placeholder: {e}")