"""
Виджет карточки STL-файла.
Показывает миниатюру, метаданные, источник.
"""

import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

THUMB_SIZE = (200, 200)


class FileCard(ctk.CTkFrame):
    """Карточка одного STL-файла."""

    def __init__(self, master, file_data, on_open=None, on_preview=None,
                 font_family="Arial", font_size=12, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)

        self.file_data = file_data
        self.on_open = on_open
        self.on_preview = on_preview

        self.title_font = ctk.CTkFont(family=font_family, size=font_size, weight="bold")
        self.normal_font = ctk.CTkFont(family=font_family, size=font_size - 1)
        self.small_font = ctk.CTkFont(family=font_family, size=font_size - 2)
        self.badge_font = ctk.CTkFont(family=font_family, size=font_size - 3, weight="bold")

        self.file_id = file_data[0]
        self.file_name = file_data[1] or "Без имени"
        self.file_path = file_data[2] or ""
        self.file_size = file_data[3] or 0
        self.face_count = file_data[5] if len(file_data) > 5 else 0
        self.bbox_x = file_data[6] if len(file_data) > 6 else 0
        self.bbox_y = file_data[7] if len(file_data) > 7 else 0
        self.bbox_z = file_data[8] if len(file_data) > 8 else 0
        self.is_valid = file_data[11] if len(file_data) > 11 else 1
        self.has_thumbnail = file_data[12] if len(file_data) > 12 else 0
        self.thumbnail_path = file_data[13] if len(file_data) > 13 else None
        self.thumb_source = file_data[15] if len(file_data) > 15 else 'none'

        self.is_from_archive = str(self.file_path).startswith("[ARCHIVE]")

        self._photo = None
        self._create_widgets()

    def _create_widgets(self):
        border = "#FF9800" if self.is_from_archive else ("#4CAF50" if self.is_valid else "#F44336")
        self.configure(border_width=2, border_color=border)

        self.thumb_btn = ctk.CTkButton(
            self, text="", width=200, height=200,
            fg_color="gray20", hover_color="gray30",
            corner_radius=8, command=self._on_thumb_click
        )
        self.thumb_btn.pack(padx=10, pady=(10, 5))
        self._load_thumbnail()

        badge_frame = ctk.CTkFrame(self, fg_color="transparent")
        badge_frame.pack(fill="x", padx=10, pady=(0, 5))

        if self.is_from_archive:
            color, text = "#FF9800", "📦 Архив"
        elif self.thumb_source == 'existing':
            color, text = "#2196F3", "🖼 Готовое"
        else:
            color, text = "#4CAF50", "🔷 STL"

        badge = ctk.CTkFrame(badge_frame, fg_color=color, corner_radius=4)
        badge.pack(side="left")
        ctk.CTkLabel(badge, text=text, font=self.badge_font, text_color="white").pack(padx=6, pady=2)

        name = str(self.file_name)[:28] + "..." if len(str(self.file_name)) > 28 else str(self.file_name)
        ctk.CTkLabel(self, text=name, font=self.title_font, anchor="w", wraplength=200).pack(
            padx=10, pady=(0, 5), fill="x")

        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(padx=10, pady=5, fill="x")

        face_txt = f"🔺 {self.face_count:,}" if self.face_count else "🔺 Архив"
        ctk.CTkLabel(info, text=face_txt, font=self.normal_font, anchor="w").pack(fill="x")

        if self.bbox_x:
            ctk.CTkLabel(info, text=f"📐 {self.bbox_x:.1f}×{self.bbox_y:.1f}×{self.bbox_z:.1f}",
                        font=self.small_font, text_color="gray", anchor="w").pack(fill="x")

        if not self.is_valid:
            st, sc = "⚠ Повреждён", "#FF6B6B"
        elif self.has_thumbnail:
            st, sc = "✓ Превью", "#51CF66"
        else:
            st, sc = "○ Без превью", "#FFD43B"

        ctk.CTkLabel(self, text=st, font=self.small_font, text_color=sc, anchor="w").pack(
            padx=10, pady=(2, 5), fill="x")

        btn_text = "📂 Открыть папку" if not self.is_from_archive else "📦 Архив"
        ctk.CTkButton(self, text=btn_text, command=self._open_file,
                     font=self.small_font, fg_color="transparent",
                     border_width=1, height=28).pack(padx=10, pady=(0, 10))

        self.configure(width=240, height=400)

    def _load_thumbnail(self):
        """Загружает миниатюру."""
        try:
            if self.thumbnail_path and Path(str(self.thumbnail_path)).exists():
                img = Image.open(str(self.thumbnail_path))
                self._photo = CTkImage(light_image=img, dark_image=img, size=THUMB_SIZE)
                self.thumb_btn.configure(image=self._photo, text="", fg_color="transparent")
            else:
                self._show_placeholder()
        except Exception as e:
            logger.error(f"Ошибка загрузки превью: {e}")
            self._show_placeholder()

    def _show_placeholder(self):
        """Показывает заглушку если нет превью."""
        if self.is_from_archive:
            text = "📦\nАрхив"
        elif not self.is_valid:
            text = "⚠\nОшибка"
        else:
            text = "🔷\nНет\nпревью"

        self.thumb_btn.configure(
            text=text,
            image=None,
            fg_color="gray20"
        )

    def _on_thumb_click(self):
        """Открыть превью при клике."""
        if self.on_preview and self.thumbnail_path:
            self.on_preview(str(self.thumbnail_path))

    def _open_file(self):
        if self.on_open and self.file_path:
            self.on_open(str(self.file_path))
