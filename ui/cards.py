"""
Виджет карточки STL-файла.
Показывает миниатюру, метаданные, иконку типа файла.
"""

import customtkinter as ctk
from customtkinter import CTkImage
from PIL import Image
from pathlib import Path
import logging
import os
import tkinter as tk

logger = logging.getLogger(__name__)

THUMB_SIZE = (200, 200)


class FileCard(ctk.CTkFrame):
    """Карточка одного STL/OBJ-файла."""

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
        self.file_ext = os.path.splitext(self.file_name)[1].lower()

        self._photo = None
        self._create_widgets()

    # ------------------------------------------------------------
    def _get_db(self):
        widget = self.master
        while widget is not None:
            if hasattr(widget, 'db'):
                return widget.db
            widget = widget.master
        return None

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

        # Иконка типа файла
        badge_frame = ctk.CTkFrame(self, fg_color="transparent")
        badge_frame.pack(fill="x", padx=10, pady=(0, 5))

        if self.is_from_archive:
            color, letter = "#FF9800", "A"
        elif self.file_ext == '.obj':
            color, letter = "#9C27B0", "O"
        elif self.thumb_source == 'existing':
            color, letter = "#2196F3", "E"
        else:
            color, letter = "#4CAF50", "S"

        icon = ctk.CTkFrame(badge_frame, width=24, height=24, fg_color=color, corner_radius=12)
        icon.pack_propagate(False)
        icon.pack(side="left")
        ctk.CTkLabel(icon, text=letter, font=self.badge_font, text_color="white").pack(expand=True)

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

        self.bind("<Button-3>", self._show_context_menu)
        for child in self.winfo_children():
            child.bind("<Button-3>", self._show_context_menu)

    # ------------------------------------------------------------
    def _load_thumbnail(self):
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
        if self.is_from_archive:
            text = "📦\nАрхив"
        elif not self.is_valid:
            text = "⚠\nОшибка"
        else:
            text = "🔷\nНет\nпревью"
        self.thumb_btn.configure(text=text, image=None, fg_color="gray20")

    def _on_thumb_click(self):
        if self.on_preview and self.thumbnail_path:
            self.on_preview(str(self.thumbnail_path))

    def _open_file(self):
        if self.on_open and self.file_path:
            self.on_open(str(self.file_path))

    # ------------------------------------------------------------
    # контекстное меню
    def _show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white",
                       activebackground="#4a4a4a", activeforeground="white")
        menu.add_command(label="🗑 Удалить файл и превью", command=self._delete_file)
        menu.add_command(label="🖼 Удалить только превью", command=self._delete_thumbnail)
        menu.add_command(label="📂 Открыть папку", command=self._open_file)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_file(self):
        from tkinter import messagebox
        ftype = "архив" if self.is_from_archive else "файл"
        if not messagebox.askyesno("Подтверждение",
                                   f"Удалить {ftype} и превью?\n\n{self.file_name}\n\nЭто действие нельзя отменить!"):
            return

        db = self._get_db()
        # удаление превью
        if self.thumbnail_path:
            thumb = Path(str(self.thumbnail_path))
            if thumb.exists():
                try: thumb.unlink()
                except: pass

        # удаление файла/архива
        if not self.is_from_archive:
            fp = Path(str(self.file_path))
            if fp.exists():
                try: fp.unlink()
                except: pass

        # удаление из БД
        if db:
            try:
                conn = db._get_connection()
                c = conn.cursor()
                c.execute("DELETE FROM thumbnails WHERE file_id=?", (self.file_id,))
                c.execute("DELETE FROM files WHERE id=?", (self.file_id,))
                conn.commit()
            except Exception as e:
                logger.error(f"Ошибка удаления из БД: {e}")

        self.destroy()

    def _delete_thumbnail(self):
        from tkinter import messagebox
        if not messagebox.askyesno("Подтверждение", f"Удалить превью?\n\n{self.file_name}"):
            return

        db = self._get_db()
        if self.thumbnail_path:
            thumb = Path(str(self.thumbnail_path))
            if thumb.exists():
                try: thumb.unlink()
                except: pass

        if db:
            try:
                conn = db._get_connection()
                c = conn.cursor()
                c.execute("DELETE FROM thumbnails WHERE file_id=?", (self.file_id,))
                c.execute("UPDATE files SET has_thumbnail=0, thumbnail_source='none' WHERE id=?", (self.file_id,))
                conn.commit()
            except Exception as e:
                logger.error(f"Ошибка обновления БД: {e}")

        self.has_thumbnail = 0
        self.thumbnail_path = None
        self._show_placeholder()
