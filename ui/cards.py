"""
Виджет карточки STL-файла для отображения в списке.
Содержит миниатюру, метаданные и кнопку открытия.
"""

import customtkinter as ctk
from PIL import Image, ImageTk
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

# Размер миниатюры в карточке
THUMB_SIZE = (200, 200)


class FileCard(ctk.CTkFrame):
    """Карточка одного STL-файла с поддержкой кириллицы."""
    
    def __init__(self, master, file_data: tuple, on_open=None, 
                 font_family="Arial", font_size=12, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)
        
        self.file_data = file_data
        self.on_open = on_open
        self.font_family = font_family
        self.font_size = font_size
        
        # Создаём шрифты для карточки
        self.title_font = ctk.CTkFont(family=font_family, size=font_size, weight="bold")
        self.normal_font = ctk.CTkFont(family=font_family, size=font_size - 1)
        self.small_font = ctk.CTkFont(family=font_family, size=font_size - 2)
        self.button_font = ctk.CTkFont(family=font_family, size=font_size - 1)
        
        # Распаковываем данные
        (
            self.file_id,
            self.file_name,
            self.file_path,
            self.file_size,
            self.modified_date,
            self.face_count,
            self.bbox_x, self.bbox_y, self.bbox_z,
            self.volume,
            self.surface_area,
            self.is_valid,
            self.has_thumbnail,
            self.thumbnail_path
        ) = file_data
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Создаёт элементы карточки с правильными шрифтами."""
        # === Миниатюра ===
        self.thumb_label = ctk.CTkLabel(
            self, 
            text="",
            width=200, 
            height=200,
            font=self.normal_font
        )
        self.thumb_label.pack(padx=10, pady=(10, 5))
        
        # Загружаем изображение
        self._load_thumbnail()
        
        # === Имя файла ===
        # Ограничиваем длину имени для отображения
        if len(self.file_name) > 25:
            name_display = self.file_name[:22] + "..."
        else:
            name_display = self.file_name
            
        self.lbl_name = ctk.CTkLabel(
            self,
            text=name_display,
            font=self.title_font,
            anchor="w",
            wraplength=180
        )
        self.lbl_name.pack(padx=10, pady=(0, 5), fill="x")
        
        # === Информация ===
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(padx=10, pady=5, fill="x")
        
        # Количество полигонов
        if self.face_count:
            face_text = f"Полигонов: {self.face_count:,}"
        else:
            face_text = "Полигонов: Н/Д"
            
        ctk.CTkLabel(
            info_frame,
            text=face_text,
            font=self.normal_font,
            anchor="w"
        ).pack(fill="x")
        
        # Размеры (только если есть данные)
        if self.bbox_x and self.bbox_y and self.bbox_z:
            bbox_text = f"Размер: {self.bbox_x:.1f}×{self.bbox_y:.1f}×{self.bbox_z:.1f} мм"
        else:
            bbox_text = "Размер: Н/Д"
            
        ctk.CTkLabel(
            info_frame,
            text=bbox_text,
            font=self.small_font,
            text_color="gray",
            anchor="w"
        ).pack(fill="x")
        
        # Размер файла
        if self.file_size:
            size_kb = self.file_size / 1024
            if size_kb < 1024:
                size_text = f"Размер: {size_kb:.1f} КБ"
            else:
                size_text = f"Размер: {size_kb/1024:.1f} МБ"
        else:
            size_text = "Размер: Н/Д"
            
        ctk.CTkLabel(
            info_frame,
            text=size_text,
            font=self.small_font,
            text_color="gray",
            anchor="w"
        ).pack(fill="x")
        
        # Статус
        if not self.is_valid:
            status_text = "⚠ Файл повреждён"
            status_color = "#FF6B6B"  # Красный
        elif self.has_thumbnail:
            status_text = "✓ Превью готово"
            status_color = "#51CF66"  # Зелёный
        else:
            status_text = "○ Без превью"
            status_color = "#FFD43B"  # Оранжевый
        
        ctk.CTkLabel(
            info_frame,
            text=status_text,
            font=self.small_font,
            text_color=status_color,
            anchor="w"
        ).pack(fill="x", pady=(5, 0))
        
        # === Кнопка открытия ===
        self.btn_open = ctk.CTkButton(
            self,
            text="📂 Открыть папку",
            command=self._open_file,
            width=180,
            height=30,
            font=self.button_font,
            fg_color="transparent",
            border_width=1,
            border_color="gray"
        )
        self.btn_open.pack(padx=10, pady=(5, 10))
        
        # Фиксированная ширина карточки
        self.configure(width=220)
    
    def _load_thumbnail(self):
        """Загружает миниатюру в карточку."""
        try:
            if self.thumbnail_path and Path(self.thumbnail_path).exists():
                img = Image.open(self.thumbnail_path)
                img = img.resize(THUMB_SIZE, Image.Resampling.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                self.thumb_label.configure(image=self._photo, text="")
            else:
                self._show_placeholder()
        except Exception as e:
            logger.warning(f"Не удалось загрузить превью {self.thumbnail_path}: {e}")
            self._show_placeholder()
    
    def _show_placeholder(self):
        """Показывает заглушку если нет превью."""
        self.thumb_label.configure(
            text="Нет превью",
            font=self.normal_font,
            width=200,
            height=200,
            fg_color="gray20"
        )
    
    def _open_file(self):
        """Открывает расположение файла."""
        if self.on_open:
            self.on_open(self.file_path)