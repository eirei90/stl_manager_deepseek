"""
Виджет карточки STL-файла для отображения в списке.
Содержит миниатюру, метаданные и кнопку открытия.
Показывает источник файла: обычный STL или из архива.
"""

import customtkinter as ctk
from PIL import Image, ImageTk
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)

THUMB_SIZE = (200, 200)


class FileCard(ctk.CTkFrame):
    """Карточка одного STL-файла с поддержкой кириллицы."""

    def __init__(self, master, file_data: tuple, on_open=None,
                 font_family="Arial", font_size=12, **kwargs):
        if not isinstance(master, (ctk.CTkFrame, ctk.CTkScrollableFrame, ctk.CTk)):
            raise TypeError(f"master должен быть виджетом CustomTkinter, получен {type(master)}")

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

        # Распаковываем данные
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
        except ValueError as e:
            logger.error(f"Неверный формат данных: {e}")
            self.file_id = 0
            self.file_name = "Ошибка"
            self.file_path = ""
            self.file_size = 0
            self.modified_date = ""
            self.face_count = 0
            self.bbox_x = self.bbox_y = self.bbox_z = 0
            self.volume = 0
            self.surface_area = 0
            self.is_valid = 0
            self.has_thumbnail = 0
            self.thumbnail_path = None

        # Определяем источник файла
        self.is_from_archive = self.file_path.startswith("[ARCHIVE]")

        self._photo = None
        self._create_widgets()

    def _create_widgets(self):
        """Создаёт элементы карточки."""

        # === Рамка с цветом в зависимости от источника ===
        if self.is_from_archive:
            border_color = "#FF9800"  # Оранжевый для архивов
        elif self.is_valid:
            border_color = "#4CAF50"  # Зелёный для обычных STL
        else:
            border_color = "#F44336"  # Красный для битых

        self.configure(border_width=2, border_color=border_color)

        # === Миниатюра ===
        self.thumb_label = ctk.CTkLabel(
            self,
            text="",
            width=200,
            height=200,
            font=self.normal_font,
            fg_color="gray20",
            corner_radius=8
        )
        self.thumb_label.pack(padx=10, pady=(10, 5))
        self.thumb_label.pack_propagate(False)

        # Загружаем изображение
        self._load_thumbnail()

        # === Бейдж источника файла ===
        badge_frame = ctk.CTkFrame(self, fg_color="transparent")
        badge_frame.pack(fill="x", padx=10, pady=(0, 5))

        if self.is_from_archive:
            # Метка "АРХИВ"
            archive_badge = ctk.CTkFrame(
                badge_frame,
                fg_color="#FF9800",
                corner_radius=4,
                width=60,
                height=20
            )
            archive_badge.pack(side="left", padx=(0, 5))
            archive_badge.pack_propagate(False)

            ctk.CTkLabel(
                archive_badge,
                text="📦 Архив",
                font=self.badge_font,
                text_color="white"
            ).pack(padx=4, pady=1)

            # Имя архива
            archive_name = self.file_path.replace("[ARCHIVE] ", "").split("/")[0]
            if len(archive_name) > 20:
                archive_name = archive_name[:17] + "..."

            ctk.CTkLabel(
                badge_frame,
                text=f"📁 {archive_name}",
                font=self.small_font,
                text_color="#FF9800"
            ).pack(side="left")
        else:
            # Метка "STL"
            stl_badge = ctk.CTkFrame(
                badge_frame,
                fg_color="#4CAF50",
                corner_radius=4,
                width=50,
                height=20
            )
            stl_badge.pack(side="left", padx=(0, 5))
            stl_badge.pack_propagate(False)

            ctk.CTkLabel(
                stl_badge,
                text="🔷 STL",
                font=self.badge_font,
                text_color="white"
            ).pack(padx=4, pady=1)

            # Путь к файлу (сокращённый)
            try:
                parent_name = Path(self.file_path).parent.name
                if len(parent_name) > 20:
                    parent_name = parent_name[:17] + "..."
                ctk.CTkLabel(
                    badge_frame,
                    text=f"📁 {parent_name}",
                    font=self.small_font,
                    text_color="gray"
                ).pack(side="left")
            except:
                pass

        # === Имя файла ===
        if len(self.file_name) > 25:
            name_display = self.file_name[:22] + "..."
        else:
            name_display = self.file_name

        self.lbl_name = ctk.CTkLabel(
            self,
            text=name_display or "Без имени",
            font=self.title_font,
            anchor="w",
            wraplength=180
        )
        self.lbl_name.pack(padx=10, pady=(0, 5), fill="x")

        # === Информация о файле ===
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(padx=10, pady=5, fill="x")

        # Количество полигонов
        if self.face_count:
            face_text = f"🔺 {self.face_count:,}"
        else:
            face_text = "🔺 Н/Д"

        ctk.CTkLabel(
            info_frame,
            text=face_text,
            font=self.normal_font,
            anchor="w"
        ).pack(fill="x")

        # Размеры
        if self.bbox_x and self.bbox_y and self.bbox_z:
            bbox_text = f"📐 {self.bbox_x:.1f}×{self.bbox_y:.1f}×{self.bbox_z:.1f} мм"
        else:
            bbox_text = "📐 Н/Д"

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
                size_text = f"💾 {size_kb:.1f} КБ"
            else:
                size_text = f"💾 {size_kb/1024:.1f} МБ"
        else:
            size_text = "💾 Н/Д"

        ctk.CTkLabel(
            info_frame,
            text=size_text,
            font=self.small_font,
            text_color="gray",
            anchor="w"
        ).pack(fill="x")

        # === Статус ===
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(padx=10, pady=(5, 0), fill="x")

        if not self.is_valid:
            status_text = "⚠ Файл повреждён"
            status_color = "#FF6B6B"
        elif self.has_thumbnail:
            if self.is_from_archive:
                status_text = "✓ Превью (из архива)"
            else:
                status_text = "✓ Превью готово"
            status_color = "#51CF66"
        else:
            status_text = "○ Без превью"
            status_color = "#FFD43B"

        ctk.CTkLabel(
            status_frame,
            text=status_text,
            font=self.small_font,
            text_color=status_color,
            anchor="w"
        ).pack(fill="x", pady=(2, 0))

        # === Кнопка открытия ===
        if self.is_from_archive:
            btn_text = "📦 Открыть архив"
        else:
            btn_text = "📂 Открыть папку"

        self.btn_open = ctk.CTkButton(
            self,
            text=btn_text,
            command=self._open_file,
            width=180,
            height=30,
            font=self.button_font,
            fg_color="transparent",
            border_width=1,
            border_color="gray" if not self.is_from_archive else "#FF9800"
        )
        self.btn_open.pack(padx=10, pady=(5, 10))

        # Фиксированные размеры карточки
        self.configure(width=240, height=420)
        self.pack_propagate(False)

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
            logger.warning(f"Не удалось загрузить превью: {e}")
            self._show_placeholder()

    def _show_placeholder(self):
        """Показывает заглушку если нет превью."""
        if self.is_from_archive:
            text = "📦\nПревью из\nархива"
        else:
            text = "🔷\nНет\nпревью"

        self.thumb_label.configure(
            text=text,
            font=self.normal_font,
            fg_color="gray20"
        )

    def _open_file(self):
        """Открывает расположение файла."""
        if self.on_open and self.file_path:
            try:
                self.on_open(self.file_path)
            except Exception as e:
                logger.error(f"Ошибка при открытии файла: {e}")