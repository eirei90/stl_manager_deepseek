"""
Виджет карточки STL-файла для отображения в списке.
Содержит миниатюру, метаданные и кнопку открытия.
Показывает источник файла: обычный STL или из архива.
"""

import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

THUMB_SIZE = (200, 200)


class FileCard(ctk.CTkFrame):
    """Карточка одного STL-файла с поддержкой кириллицы."""

    def __init__(self, master, file_data: tuple, on_open=None,
                 font_family="Arial", font_size=12, **kwargs):
        # Проверяем, что master — это виджет, а не строка
        if not isinstance(master, (ctk.CTkFrame, ctk.CTkScrollableFrame, ctk.CTk)):
            raise TypeError(f"master должен быть виджетом, получен {type(master)}: {master}")

        super().__init__(master, corner_radius=10, **kwargs)

        self.file_data = file_data
        self.on_open = on_open
        self.font_family = font_family
        self.font_size = font_size

        # Создаём шрифты
        self.title_font = ctk.CTkFont(family=font_family, size=font_size, weight="bold")
        self.normal_font = ctk.CTkFont(family=font_family, size=font_size - 1)
        self.small_font = ctk.CTkFont(family=font_family, size=font_size - 2)
        self.button_font = ctk.CTkFont(family=font_family, size=font_size - 1)
        self.badge_font = ctk.CTkFont(family=font_family, size=font_size - 3, weight="bold")

        # Распаковываем данные с проверкой
        try:
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
        except (ValueError, TypeError) as e:
            logger.error(f"Неверный формат данных файла: {e}")
            # Значения по умолчанию
            self.file_id = 0
            self.file_name = "Ошибка данных"
            self.file_path = ""
            self.file_size = 0
            self.modified_date = ""
            self.face_count = 0
            self.bbox_x = self.bbox_y = self.bbox_z = 0.0
            self.volume = 0.0
            self.surface_area = 0.0
            self.is_valid = 0
            self.has_thumbnail = 0
            self.thumbnail_path = None

        # Определяем источник файла
        self.is_from_archive = str(self.file_path).startswith("[ARCHIVE]") if self.file_path else False

        self._photo = None
        self._create_widgets()

    def _create_widgets(self):
        """Создаёт элементы карточки."""

        # === Рамка с цветом ===
        if self.is_from_archive:
            border_color = "#FF9800"
        elif self.is_valid:
            border_color = "#4CAF50"
        else:
            border_color = "#F44336"

        self.configure(border_width=2, border_color=border_color)

        # === Миниатюра ===
        self.thumb_label = ctk.CTkLabel(
            self,
            text="",  # Пустая строка — это нормально для CTkLabel
            width=200,
            height=200,
            font=self.normal_font,
            fg_color="gray20",
            corner_radius=8
        )
        self.thumb_label.pack(padx=10, pady=(10, 5))

        # Загружаем изображение
        self._load_thumbnail()

        # === Бейдж источника ===
        badge_frame = ctk.CTkFrame(self, fg_color="transparent")
        badge_frame.pack(fill="x", padx=10, pady=(0, 5))

        if self.is_from_archive:
            archive_badge = ctk.CTkFrame(
                badge_frame,
                fg_color="#FF9800",
                corner_radius=4
            )
            archive_badge.pack(side="left", padx=(0, 5))

            ctk.CTkLabel(
                archive_badge,
                text="📦 Архив",
                font=self.badge_font,
                text_color="white"
            ).pack(padx=6, pady=2)
        else:
            stl_badge = ctk.CTkFrame(
                badge_frame,
                fg_color="#4CAF50",
                corner_radius=4
            )
            stl_badge.pack(side="left", padx=(0, 5))

            ctk.CTkLabel(
                stl_badge,
                text="🔷 STL",
                font=self.badge_font,
                text_color="white"
            ).pack(padx=6, pady=2)

        # === Имя файла ===
        name = str(self.file_name) if self.file_name else "Без имени"
        if len(name) > 25:
            name = name[:22] + "..."

        self.lbl_name = ctk.CTkLabel(
            self,
            text=name,
            font=self.title_font,
            anchor="w",
            wraplength=180
        )
        self.lbl_name.pack(padx=10, pady=(0, 5), fill="x")

        # === Информация ===
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(padx=10, pady=5, fill="x")

        # Полигоны
        if self.face_count:
            face_text = f"🔺 {self.face_count:,}"
        else:
            face_text = "🔺 Н/Д"

        ctk.CTkLabel(info_frame, text=face_text, font=self.normal_font, anchor="w").pack(fill="x")

        # Размеры
        if self.bbox_x and self.bbox_y and self.bbox_z:
            bbox_text = f"📐 {self.bbox_x:.1f}×{self.bbox_y:.1f}×{self.bbox_z:.1f} мм"
        else:
            bbox_text = "📐 Н/Д"

        ctk.CTkLabel(info_frame, text=bbox_text, font=self.small_font, text_color="gray", anchor="w").pack(fill="x")

        # Размер файла
        if self.file_size:
            size_kb = self.file_size / 1024
            if size_kb < 1024:
                size_text = f"💾 {size_kb:.1f} КБ"
            else:
                size_text = f"💾 {size_kb/1024:.1f} МБ"
        else:
            size_text = "💾 Н/Д"

        ctk.CTkLabel(info_frame, text=size_text, font=self.small_font, text_color="gray", anchor="w").pack(fill="x")

        # === Статус ===
        if not self.is_valid:
            status_text = "⚠ Файл повреждён"
            status_color = "#FF6B6B"
        elif self.has_thumbnail:
            status_text = "✓ Превью готово"
            status_color = "#51CF66"
        else:
            status_text = "○ Без превью"
            status_color = "#FFD43B"

        ctk.CTkLabel(
            self, text=status_text,
            font=self.small_font, text_color=status_color, anchor="w"
        ).pack(padx=10, pady=(2, 5), fill="x")

        # === Кнопка ===
        btn_text = "📦 Архив" if self.is_from_archive else "📂 Открыть папку"

        self.btn_open = ctk.CTkButton(
            self,
            text=btn_text,
            command=self._open_file,
            width=180,
            height=30,
            font=self.button_font,
            fg_color="transparent",
            border_width=1,
            border_color="gray"
        )
        self.btn_open.pack(padx=10, pady=(0, 10))

        # Фиксируем размер
        self.configure(width=240, height=400)

    def _load_thumbnail(self):
        """Загружает миниатюру."""
        try:
            if self.thumbnail_path and Path(str(self.thumbnail_path)).exists():
                img = Image.open(str(self.thumbnail_path))
                self._photo = CTkImage(light_image=img, dark_image=img, size=THUMB_SIZE)
                self.thumb_label.configure(image=self._photo, text="")
            else:
                self._show_placeholder()
        except Exception as e:
            logger.warning(f"Не удалось загрузить превью: {e}")
            self._show_placeholder()

    def _show_placeholder(self):
        """Показывает заглушку."""
        # Создаём CTkLabel вместо простого текста
        if self.is_from_archive:
            text = "📦\nПревью из\nархива"
        else:
            text = "🔷\nНет\nпревью"

        self.thumb_label.configure(
            text=text,
            image=None,
            fg_color="gray20"
        )

    def _open_file(self):
        """Открывает расположение файла."""
        if self.on_open and self.file_path:
            try:
                self.on_open(str(self.file_path))
            except Exception as e:
                logger.error(f"Ошибка при открытии: {e}")