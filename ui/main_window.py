"""
Главное окно приложения STL Manager.
Содержит панель инструментов, дерево каталога, карточки файлов с пагинацией,
горячие клавиши, хлебные крошки, прогресс-бар с детализацией, иконки типов,
возможность рендеринга одного файла или текущей страницы.
"""

import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
from pathlib import Path
import logging
import os
import platform
import subprocess
import re
from PIL import Image
from typing import Optional, Tuple
from ui.workers import BackgroundTask, RenderWorker, CancellationToken
import shutil
from ui.move_dialog import MoveFileDialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger(__name__)

# ---------- автоопределение шрифта ----------
def detect_best_font() -> Tuple[str, int]:
    system = platform.system()
    preferred = ["DejaVu Sans", "Liberation Sans", "Ubuntu", "Noto Sans",
                 "Arial", "Helvetica", "TkDefaultFont"]
    if system == "Windows":
        preferred = ["Segoe UI"] + preferred

    root = tk.Tk()
    root.withdraw()
    try:
        available = set(tkfont.families())
        for font in preferred:
            if font in available:
                return (font, 12)
        return ("TkDefaultFont", 12)
    finally:
        root.destroy()

FONT_FAMILY, FONT_SIZE = detect_best_font()
logger.info(f"Шрифт: {FONT_FAMILY}")

# ---------- окно предпросмотра ----------
class ImagePreviewWindow(ctk.CTkToplevel):
    def __init__(self, master, image_path):
        super().__init__(master)
        self.title("Превью")
        self.geometry("600x600")
        try:
            img = Image.open(image_path)
            w, h = img.size
            max_size = 550
            if w > max_size or h > max_size:
                ratio = min(max_size/w, max_size/h)
                w, h = int(w*ratio), int(h*ratio)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
            ctk.CTkLabel(self, image=ctk_img, text="").pack(padx=20, pady=20, expand=True)
        except Exception as e:
            ctk.CTkLabel(self, text=f"Ошибка: {e}").pack(padx=20, pady=20)
        self.after(100, self.lift)

# ---------- главное окно ----------
class STLManagerApp(ctk.CTk):
    def __init__(self, db, scanner, renderer):
        super().__init__()
        self.db = db
        self.scanner = scanner
        self.renderer = renderer

        self.current_project_id = None
        self.current_root_path = None
        self.current_worker = None
        self.selected_path = None
        self.selected_file_ids = set()
        self.selected_file_data = []  # Храним полные данные выделенных файлов
        self._last_clicked_card = None  # для Shift+Click

        # пагинация
        self.page_size = 50
        self.current_page = 0
        self.all_files = []

        self.title("STL Manager")
        self.geometry("1500x900")
        self.minsize(1100, 600)

        self._create_fonts()
        self._create_widgets()
        self._create_layout()
        self._bind_hotkeys()

        self.after(300, self._load_last_project)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        logger.info("Окно создано")

    def _create_fonts(self):
        self.title_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE+2, weight="bold")
        self.normal_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE)
        self.small_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE-2)
        self.btn_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold")

    def _create_widgets(self):
        # Тулбар
        self.toolbar = ctk.CTkFrame(self, height=45, corner_radius=0)
        self.btn_folder = ctk.CTkButton(self.toolbar, text="📁 Выбрать папку",
                                        command=self.select_folder, width=140, font=self.btn_font)
        self.btn_scan = ctk.CTkButton(self.toolbar, text="🔍 Сканировать",
                                      command=self.start_scan, state="disabled", width=140, font=self.btn_font)
        self.btn_render = ctk.CTkButton(self.toolbar, text="🖼 Всё превью",
                                        command=self.start_render, state="disabled", width=130, font=self.btn_font)
        self.btn_render_page = ctk.CTkButton(self.toolbar, text="📄 Превью страницы",
                                             command=self.start_render_page, state="disabled", width=150, font=self.btn_font)
        self.btn_refresh_thumbs = ctk.CTkButton(self.toolbar, text="🔄 Обновить",
                                                command=self.start_refresh_thumbs, state="disabled",
                                                width=120, font=self.btn_font, fg_color="#2196F3")
        self.btn_delete_missing = ctk.CTkButton(self.toolbar, text="🗑 Очистить",
                                                command=self.delete_missing_files, state="disabled",
                                                width=120, font=self.btn_font, fg_color="#D32F2F")
        self.btn_stop = ctk.CTkButton(self.toolbar, text="⏹ Стоп",
                                      command=self.stop_operation, state="disabled",
                                      width=100, font=self.btn_font, fg_color="#D32F2F")
        self.lbl_folder = ctk.CTkLabel(self.toolbar, text="Папка не выбрана",
                                       anchor="w", font=self.normal_font)

        # Хлебные крошки
        self.breadcrumb_frame = ctk.CTkFrame(self, height=22, fg_color="transparent")
        self.breadcrumb_frame.pack_propagate(False)
        self._update_breadcrumbs()

        # Прогресс
        self.progress_frame = ctk.CTkFrame(self, height=30)
        self.progress_frame.pack_propagate(False)
        self.progress = ctk.CTkProgressBar(self.progress_frame, height=10, width=300)
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self.progress_frame, text="Готов", font=self.small_font)
        self.lbl_progress_detail = ctk.CTkLabel(self.progress_frame, text="", font=self.small_font, text_color="gray")

        # Фильтры
        self.filter_frame = ctk.CTkFrame(self, height=35)
        ctk.CTkLabel(self.filter_frame, text="🔎", font=self.normal_font).pack(side="left", padx=5)
        self.search_var = ctk.StringVar()
        self.search_var.trace_add('write', lambda *a: self._reset_and_refresh())
        self.entry_search = ctk.CTkEntry(self.filter_frame, textvariable=self.search_var,
                                         width=180, placeholder_text="Поиск...", font=self.normal_font)
        self.entry_search.pack(side="left", padx=5)
        ctk.CTkLabel(self.filter_frame, text="Полигонов:", font=self.small_font).pack(side="left", padx=(20,5))
        self.min_faces = ctk.StringVar(value="0")
        self.max_faces = ctk.StringVar(value="9999999")
        ctk.CTkEntry(self.filter_frame, textvariable=self.min_faces, width=70, font=self.small_font).pack(side="left", padx=2)
        ctk.CTkLabel(self.filter_frame, text="-", font=self.small_font).pack(side="left")
        ctk.CTkEntry(self.filter_frame, textvariable=self.max_faces, width=70, font=self.small_font).pack(side="left", padx=2)
        ctk.CTkButton(self.filter_frame, text="Применить", command=self._reset_and_refresh,
                      width=80, font=self.small_font).pack(side="left", padx=10)

        # Пагинация с полем ввода
        self.page_frame = ctk.CTkFrame(self, height=30)
        self.page_frame.pack_propagate(False)
        self.btn_prev = ctk.CTkButton(self.page_frame, text="◀", command=self._prev_page,
                                      width=30, font=self.small_font, state="disabled")
        self.btn_prev.pack(side="left", padx=2)
        self.lbl_page = ctk.CTkLabel(self.page_frame, text="0 / 0", font=self.small_font, width=80)
        self.lbl_page.pack(side="left", padx=5)
        self.btn_next = ctk.CTkButton(self.page_frame, text="▶", command=self._next_page,
                                      width=30, font=self.small_font, state="disabled")
        self.btn_next.pack(side="left", padx=2)

        ctk.CTkLabel(self.page_frame, text="Страница", font=self.small_font).pack(side="left", padx=(15, 5))
        self.entry_page = ctk.CTkEntry(self.page_frame, width=50, font=self.small_font,
                                       placeholder_text="№")
        self.entry_page.pack(side="left", padx=5)
        ctk.CTkButton(self.page_frame, text="Перейти", command=self._goto_page,
                      width=60, font=self.small_font).pack(side="left", padx=5)

        # Основная область
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        from ui.tree_panel import TreePanel
        self.tree_panel = TreePanel(self.main_frame, on_select=self._on_tree_select,
                                    font_family=FONT_FAMILY, font_size=FONT_SIZE, width=250)
        self.cards_frame = ctk.CTkScrollableFrame(self.main_frame, label_text="Файлы",
                                                   label_font=self.title_font)
        # Статус
        self.status = ctk.CTkLabel(self, text="Готов", anchor="w", font=self.small_font, height=25)

    def _create_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # тулбар
        self.grid_rowconfigure(1, weight=0)  # хлебные крошки
        self.grid_rowconfigure(2, weight=0)  # прогресс
        self.grid_rowconfigure(3, weight=0)  # фильтры
        self.grid_rowconfigure(4, weight=0)  # пагинация
        self.grid_rowconfigure(5, weight=1)  # основной контент
        self.grid_rowconfigure(6, weight=0)  # статус

        self.toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.toolbar.grid_columnconfigure(7, weight=1)
        self.btn_folder.grid(row=0, column=0, padx=3)
        self.btn_scan.grid(row=0, column=1, padx=3)
        self.btn_render.grid(row=0, column=2, padx=3)
        self.btn_render_page.grid(row=0, column=3, padx=3)
        self.btn_refresh_thumbs.grid(row=0, column=4, padx=3)
        self.btn_delete_missing.grid(row=0, column=5, padx=3)
        self.btn_stop.grid(row=0, column=6, padx=3)
        self.lbl_folder.grid(row=0, column=7, padx=10, sticky="w")

        self.breadcrumb_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(0,2))

        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
        self.progress.pack(side="left", padx=(0,10))
        self.lbl_progress.pack(side="left")
        self.lbl_progress_detail.pack(side="left", padx=10)

        self.filter_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        self.page_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=2)

        self.main_frame.grid(row=5, column=0, sticky="nsew", padx=5, pady=2)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.tree_panel.grid(row=0, column=0, sticky="ns", padx=(0,5))
        self.cards_frame.grid(row=0, column=1, sticky="nsew")

        self.status.grid(row=6, column=0, sticky="ew", padx=5, pady=2)
        self.status.configure(height=25)

    # ---------- горячие клавиши ----------
    def _bind_hotkeys(self):
        self.bind_all("<Control-f>", lambda e: self.entry_search.focus_set())
        self.bind_all("<Control-o>", lambda e: self.select_folder())
        self.bind_all("<Control-Return>", lambda e: self._on_show_all())
        self.bind_all("<BackSpace>", self._on_backspace)
        self.bind_all("<F5>", lambda e: self.start_scan())

    def _on_backspace(self, event):
        if event.widget == self.entry_search:
            return
        self.tree_panel._navigate_up()

    def _on_show_all(self):
        self.tree_panel._show_all()

    # ---------- хлебные крошки ----------
    def _update_breadcrumbs(self, path=None):
        for widget in self.breadcrumb_frame.winfo_children():
            widget.destroy()

        if not self.current_project_id or not self.selected_path:
            ctk.CTkLabel(self.breadcrumb_frame, text="🏠 Корень",
                        font=self.small_font, text_color="gray").pack(side="left", padx=5)
            return

        parts = self.selected_path.split('/')
        ctk.CTkButton(self.breadcrumb_frame, text="🏠", command=self._go_to_root,
                      width=28, height=20, font=self.small_font,
                      fg_color="transparent", border_width=0).pack(side="left")
        for i, part in enumerate(parts):
            ctk.CTkLabel(self.breadcrumb_frame, text="›", font=self.small_font,
                        text_color="gray").pack(side="left")
            full = '/'.join(parts[:i+1])
            if i == len(parts)-1:
                ctk.CTkLabel(self.breadcrumb_frame, text=part[:25],
                            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE-2, weight="bold"),
                            text_color="white").pack(side="left")
            else:
                ctk.CTkButton(self.breadcrumb_frame, text=part[:25],
                             command=lambda p=full: self._on_breadcrumb_click(p),
                             width=len(part[:25])*8+10, height=20,
                             font=self.small_font, fg_color="transparent",
                             border_width=0, text_color="#4FC3F7").pack(side="left")

    def _go_to_root(self):
        self._on_tree_select(None)

    def _on_breadcrumb_click(self, path):
        self.tree_panel._navigate_to(path)
        self._on_tree_select(path)

    # ---------- прогресс-бар с детализацией ----------
    def _update_progress(self, current, total, text, detail=""):
        if total > 0:
            self.progress.set(current / total)
        self.lbl_progress.configure(text=f"{text}: {current}/{total}")
        self.lbl_progress_detail.configure(text=detail)

    # ---------- пагинация ----------
    def _reset_and_refresh(self):
        self.current_page = 0
        self.refresh_files()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._show_page()

    def _next_page(self):
        total_pages = max(1, (len(self.all_files) + self.page_size - 1) // self.page_size)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._show_page()

    def _goto_page(self):
        try:
            page_input = int(self.entry_page.get())
        except ValueError:
            messagebox.showwarning("Ошибка", "Введите число")
            return
        total_pages = max(1, (len(self.all_files) + self.page_size - 1) // self.page_size)
        if page_input < 1 or page_input > total_pages:
            messagebox.showwarning("Ошибка", f"Страница должна быть от 1 до {total_pages}")
            return
        self.current_page = page_input - 1
        self._show_page()

    def _update_pagination_controls(self):
        total_pages = max(1, (len(self.all_files) + self.page_size - 1) // self.page_size)
        self.lbl_page.configure(text=f"{self.current_page + 1} / {total_pages}")
        self.btn_prev.configure(state="normal" if self.current_page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self.current_page < total_pages - 1 else "disabled")
        self.entry_page.delete(0, "end")
        self.entry_page.insert(0, str(self.current_page + 1))

    def _show_page(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()

        start = self.current_page * self.page_size
        end = start + self.page_size
        page_files = self.all_files[start:end]

        from ui.cards import FileCard
        row, col, maxc = 0, 0, 3
        for i in range(maxc):
            self.cards_frame.grid_columnconfigure(i, weight=1, uniform="card")

        for fd in page_files:
            card = FileCard(
                self.cards_frame, fd,
                on_open=self._open_location,
                on_preview=self._open_preview,
                on_render_single=self._render_single_file,
                on_move=self._show_move_dialog,
                on_selection_changed=self._on_card_selection_changed,
                font_family=FONT_FAMILY, font_size=FONT_SIZE
            )
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            col += 1
            if col >= maxc:
                col = 0
                row += 1

        self._update_pagination_controls()
        total = len(self.all_files)
        thumbs = sum(1 for f in self.all_files if len(f) > 12 and f[12])
        archives = sum(1 for f in self.all_files if str(f[2]).startswith("[ARCHIVE]"))
        existing = sum(1 for f in self.all_files if len(f) > 15 and f[15] == 'existing')
        self.status.configure(
            text=f"Всего: {total} | STL: {total-archives} | Архив: {archives} | Превью: {thumbs} | Готовых: {existing}"
        )

        # ===== ИСПРАВЛЕНИЕ: Обновить скролл-регион Canvas'а =====
        self.cards_frame.update_idletasks()
        if hasattr(self.cards_frame, '_parent_canvas'):
            self.cards_frame._parent_canvas.configure(
                scrollregion=self.cards_frame._parent_canvas.bbox("all")
            )
            # Сброс скролла в начало при смене страницы/папки
            self.cards_frame._parent_canvas.yview_moveto(0)
        # =====================================================

    def _on_cards_frame_right_click(self, event):
        """Контекстное меню для выделенных файлов."""
        selected = self._get_selected_files()
        if not selected:
            return

        menu = tk.Menu(self, tearoff=0, bg="#2b2b2b", fg="white",
                       activebackground="#4a4a4a", activeforeground="white")

        if len(selected) == 1:
            menu.add_command(
                label=f"🖼 Создать превью",
                command=lambda: self._render_single_file(selected[0])
            )

        menu.add_command(
            label=f"📁 Переместить ({len(selected)})",
            command=lambda: self._show_move_dialog(selected)
        )
        menu.add_command(
            label=f"🗑 Удалить ({len(selected)})",
            command=lambda: self._delete_files(selected)
        )

        menu.post(event.x_root, event.y_root)

    def _delete_files(self, file_records):
        """Удаляет выбранные файлы."""
        if not file_records:
            return

        count = len(file_records)
        if not messagebox.askyesno(
            "Подтверждение",
            f"Удалить {count} файлов и их превью?\n\nЭто действие нельзя отменить!"
        ):
            return

        conn = self.db._get_connection()
        cursor = conn.cursor()
        deleted = 0

        for record in file_records:
            file_id = record[0]
            file_path = record[2]
            thumb_path = record[13] if len(record) > 13 else None

            # Удаляем превью
            if thumb_path and os.path.exists(str(thumb_path)):
                try:
                    os.remove(str(thumb_path))
                except:
                    pass

            # Удаляем файл (если не архив)
            if not str(file_path).startswith("[ARCHIVE]"):
                p = Path(str(file_path))
                if p.exists():
                    try:
                        p.unlink()
                    except:
                        pass

            # Удаляем из БД
            cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            deleted += 1

        conn.commit()
        self.db.update_project_stats(self.current_project_id)
        self.selected_file_ids = set()
        self.selected_file_data = []
        self.refresh_tree()
        self.refresh_files()
        messagebox.showinfo("Готово", f"Удалено файлов: {deleted}")

    # ---------- обновление файлов ----------
    def refresh_files(self, keep_page=False):
        if not self.current_project_id:
            for w in self.cards_frame.winfo_children():
                w.destroy()
            self.all_files = []
            self._update_pagination_controls()
            self._update_breadcrumbs()
            return

        name = self.search_var.get().strip() or None
        try:    mn = int(self.min_faces.get())
        except: mn = None
        try:    mx = int(self.max_faces.get())
        except: mx = None

        self.all_files = self.db.get_files_for_project(
            self.current_project_id,
            name_filter=name,
            min_faces=mn,
            max_faces=mx,
            relative_path=self.selected_path
        )
        if not keep_page:
            self.current_page = 0
        else:
            # если текущая страница больше недоступна (например, после удаления файлов)
            total_pages = max(1, (len(self.all_files) + self.page_size - 1) // self.page_size)
            if self.current_page >= total_pages:
                self.current_page = total_pages - 1

        self._show_page()
        self._update_breadcrumbs()

    # ---------- рендеринг одного файла ----------
    def _render_single_file(self, file_record):
        """Запускает рендеринг одного файла в фоновом потоке."""
        if not self.renderer:
            return
        self._set_state("rendering")
        from ui.workers import RenderWorker, CancellationToken
        token = CancellationToken()

        files_to_render = [file_record]

        def single_target(progress_cb, cancel_token):
            # Создаём временный RenderWorker, передаём файлы напрямую
            worker = RenderWorker.__new__(RenderWorker)
            worker.renderer = self.renderer
            worker.db = self.db
            worker.project_id = self.current_project_id
            # Используем метод, принимающий список файлов
            return worker._batch_render(progress_cb, cancel_token, custom_files=files_to_render)

        self.current_worker = BackgroundTask(
            target=single_target,
            cancellation_token=token,
            on_progress=lambda c,t: self.after(0, lambda: self._update_progress(c,t,"Превью", detail="Один файл")),
            on_complete=lambda n: self.after(0, lambda: self._finish_render(n)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    # ---------- рендеринг страницы ----------
    def start_render_page(self):
        """Запускает рендеринг только для файлов на текущей странице, включая архивы."""
        if not self.current_project_id or not self.all_files:
            return
        start = self.current_page * self.page_size
        end = start + self.page_size
        page_files = self.all_files[start:end]

        # Больше не фильтруем – рендерим все записи на странице (архивы, файлы внутри архивов, обычные STL/OBJ)
        files_to_render = page_files

        if not files_to_render:
            messagebox.showinfo("Информация", "На странице нет файлов для рендеринга")
            return

        self._set_state("rendering")
        from ui.workers import RenderWorker, CancellationToken
        token = CancellationToken()

        def page_target(progress_cb, cancel_token):
            worker = RenderWorker.__new__(RenderWorker)
            worker.renderer = self.renderer
            worker.db = self.db
            worker.project_id = self.current_project_id
            return worker._batch_render(progress_cb, cancel_token, custom_files=files_to_render)

        self.current_worker = BackgroundTask(
            target=page_target,
            cancellation_token=token,
            on_progress=lambda c,t: self.after(0, lambda: self._update_progress(c,t,"Превью страницы", detail=f"{c}/{t}")),
            on_complete=lambda n: self.after(0, lambda: self._finish_render(n)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    # ---------- события (основные) ----------
    def select_folder(self):
        folder = None
        if platform.system() == 'Linux':
            try:
                result = subprocess.run(
                    ['zenity', '--file-selection', '--directory',
                     '--title=Выберите папку с STL файлами и архивами',
                     '--filename=' + (self.current_root_path or os.path.expanduser('~'))],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    folder = result.stdout.strip()
                else:
                    return
            except FileNotFoundError:
                logger.warning("Zenity не установлен")
            except Exception as e:
                logger.error(f"Ошибка Zenity: {e}")

        if not folder and platform.system() != 'Linux':
            folder = filedialog.askdirectory(
                title="Выберите папку с STL файлами и архивами",
                initialdir=self.current_root_path or os.path.expanduser('~')
            )
        if folder:
            self.current_root_path = folder
            self.lbl_folder.configure(text=f"📂 {folder}")
            self.btn_scan.configure(state="normal")
            self.status.configure(text=f"Выбрана папка: {folder}")

    def start_scan(self):
        if not self.current_root_path: return
        self._set_state("scanning")
        from ui.workers import ScanWorker, CancellationToken
        token = CancellationToken()
        self.current_worker = ScanWorker(
            self.scanner, self.current_root_path,
            cancellation_token=token,
            on_progress=lambda c,t: self.after(0, lambda: self._update_progress(c,t,"Сканирование", detail=f"Файл {c} из {t}")),
            on_complete=lambda pid: self.after(0, lambda: self._finish_scan(pid)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    def _finish_scan(self, project_id):
        self.current_project_id = project_id
        self.progress.set(1)
        self.lbl_progress.configure(text="Готово ✓")
        self.lbl_progress_detail.configure(text="")
        self.btn_render.configure(state="normal")
        self.btn_render_page.configure(state="normal")
        self.btn_refresh_thumbs.configure(state="normal")
        self.btn_delete_missing.configure(state="normal")
        self._set_state("idle")
        self.refresh_tree()
        self.refresh_files()

    def start_render(self):
        if not self.current_project_id: return
        self._set_state("rendering")
        from ui.workers import RenderWorker, CancellationToken
        token = CancellationToken()
        self.current_worker = RenderWorker(
            self.renderer, self.db, self.current_project_id,
            cancellation_token=token,
            on_progress=lambda c,t: self.after(0, lambda: self._update_progress(c,t,"Превью", detail=f"Обработано {c} из {t}")),
            on_complete=lambda n: self.after(0, lambda: self._finish_render(n)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    def _finish_render(self, count):
        self.progress.set(1)
        self.lbl_progress.configure(text=f"Создано: {count} ✓")
        self.lbl_progress_detail.configure(text="")
        self._set_state("idle")
        self.refresh_files(keep_page=True)

    def start_refresh_thumbs(self):
        if not self.current_project_id: return
        result = messagebox.askyesno("Обновить превью", "Будут пересозданы превью для файлов с заглушками.\nПродолжить?")
        if not result: return
        self._set_state("rendering")
        from ui.workers import RefreshThumbsWorker, CancellationToken
        token = CancellationToken()
        self.current_worker = RefreshThumbsWorker(
            self.renderer, self.db, self.current_project_id,
            cancellation_token=token,
            on_progress=lambda c,t: self.after(0, lambda: self._update_progress(c,t,"Обновление", detail=f"Обновлено {c} из {t}")),
            on_complete=lambda n: self.after(0, lambda: self._finish_render(n)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    def delete_missing_files(self):
        if not self.current_project_id: return
        files = self.db.get_files_for_project(self.current_project_id)
        missing = [f for f in files if not str(f[2]).startswith("[ARCHIVE]") and not os.path.exists(str(f[2]))]
        if not missing:
            messagebox.showinfo("Информация", "Все файлы на месте!")
            return
        if not messagebox.askyesno("Подтверждение", f"Найдено {len(missing)} отсутствующих файлов.\nУдалить их записи?"):
            return
        conn = self.db._get_connection()
        cursor = conn.cursor()
        for record in missing:
            fid = record[0]
            thumb = record[13] if len(record) > 13 else None
            if thumb and os.path.exists(str(thumb)):
                try: os.remove(str(thumb))
                except: pass
            cursor.execute("DELETE FROM thumbnails WHERE file_id = ?", (fid,))
            cursor.execute("DELETE FROM files WHERE id = ?", (fid,))
        conn.commit()
        self.db.update_project_stats(self.current_project_id)
        self.refresh_tree()
        self.refresh_files()
        messagebox.showinfo("Готово", f"Удалено записей: {len(missing)}")

    def stop_operation(self):
        if self.current_worker:
            self.current_worker.cancel()
            self.current_worker = None
        # Немедленно разблокируем интерфейс и сбрасываем прогресс
        self.progress.set(0)
        self.lbl_progress.configure(text="Остановлено")
        self.lbl_progress_detail.configure(text="")
        self._set_state("idle")

    def _on_error(self, msg):
        messagebox.showerror("Ошибка", msg)
        self._set_state("idle")

    def _set_state(self, state):
        if state in ("scanning", "rendering"):
            self.btn_folder.configure(state="disabled")
            self.btn_scan.configure(state="disabled")
            self.btn_render.configure(state="disabled")
            self.btn_render_page.configure(state="disabled")
            self.btn_refresh_thumbs.configure(state="disabled")
            self.btn_delete_missing.configure(state="disabled")
            self.btn_stop.configure(state="normal")
        else:
            self.btn_folder.configure(state="normal")
            self.btn_scan.configure(state="normal" if self.current_root_path else "disabled")
            self.btn_render.configure(state="normal" if self.current_project_id else "disabled")
            self.btn_render_page.configure(state="normal" if self.current_project_id else "disabled")
            self.btn_refresh_thumbs.configure(state="normal" if self.current_project_id else "disabled")
            self.btn_delete_missing.configure(state="normal" if self.current_project_id else "disabled")
            self.btn_stop.configure(state="disabled")

    def refresh_tree(self):
        if self.current_project_id:
            tree = self.db.get_directory_tree(self.current_project_id)
            self.tree_panel.build_tree(tree)

    def _on_tree_select(self, path):
        if not path:
            self.selected_path = None
            self.search_var.set("")
            self.refresh_files()
            return
        clean_path = path
        for prefix in ["📂 ", "📁 ", "📄 ", "📦 ", "⚠ "]:
            clean_path = clean_path.replace(prefix, "")
        clean_path = re.sub(r'\s*\(\d+\)\s*$', '', clean_path).strip()
        if Path(clean_path).suffix:
            self.selected_path = None
            self.search_var.set(Path(clean_path).stem)
        else:
            self.selected_path = clean_path
            self.search_var.set("")
        self.refresh_files()

    def _open_location(self, path):
        if path.startswith("[ARCHIVE]"):
            # Извлекаем имя архива из специального пути
            archive_name = path.replace("[ARCHIVE] ", "")
            # Ищем архив в файловой системе проекта
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.current_project_id,))
            root = cursor.fetchone()
            if root:
                for dirpath, _, filenames in os.walk(root[0]):
                    if archive_name in filenames:
                        archive_path = os.path.join(dirpath, archive_name)
                        # Открываем папку, содержащую архив
                        try:
                            s = platform.system()
                            if s == "Windows":
                                os.startfile(os.path.dirname(archive_path))
                            elif s == "Darwin":
                                subprocess.run(["open", os.path.dirname(archive_path)])
                            else:
                                subprocess.run(["xdg-open", os.path.dirname(archive_path)])
                        except Exception as e:
                            logger.error(f"Ошибка открытия папки архива: {e}")
                        return
            messagebox.showinfo("Архив", f"Архив не найден на диске:\n{archive_name}")
            return

        # Обычный файл (STL/OBJ)
        p = Path(path)
        if p.exists():
            try:
                s = platform.system()
                if s == "Windows":
                    os.startfile(p.parent)
                elif s == "Darwin":
                    subprocess.run(["open", str(p.parent)])
                else:
                    subprocess.run(["xdg-open", str(p.parent)])
            except Exception as e:
                logger.error(f"Ошибка открытия папки: {e}")
        else:
            messagebox.showwarning("Файл не найден", f"Файл не существует:\n{path}")

    def _open_preview(self, path):
        ImagePreviewWindow(self, path)

    def _load_last_project(self):
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, root_path FROM projects WHERE total_files > 0 ORDER BY scan_date DESC LIMIT 1")
            result = cursor.fetchone()
            if result:
                project_id, root_path = result
                self.current_project_id = project_id
                self.current_root_path = root_path
                self.lbl_folder.configure(text=f"📂 {root_path}")
                self.btn_scan.configure(state="normal")
                self.btn_render.configure(state="normal")
                self.btn_render_page.configure(state="normal")
                self.btn_refresh_thumbs.configure(state="normal")
                self.btn_delete_missing.configure(state="normal")
                self.refresh_tree()
                self.refresh_files()
                self.status.configure(text=f"Загружен проект: {Path(root_path).name}")
            else:
                logger.info("Нет сохранённых проектов")
        except Exception as e:
            logger.error(f"Ошибка загрузки проекта: {e}")

    def _on_card_selection_changed(self, mode, card):
        from ui.cards import FileCard

        try:
            if not card.winfo_exists():
                return
        except:
            return

        fid = card.file_id

        if mode == "clear_select":
            for w in self.cards_frame.winfo_children():
                if isinstance(w, FileCard):
                    try:
                        if w.winfo_exists():
                            w._deselect()
                    except:
                        pass
            self.selected_file_ids = {fid}
            self.selected_file_data = [card.file_data]  # Сохраняем данные
            card._select()
            self._last_clicked_card = card

        elif mode == "toggle":
            if fid in self.selected_file_ids:
                self.selected_file_ids.discard(fid)
                self.selected_file_data = [f for f in self.selected_file_data if f[0] != fid]
                card._deselect()
            else:
                self.selected_file_ids.add(fid)
                self.selected_file_data.append(card.file_data)  # Добавляем данные
                card._select()

        elif mode == "range_select":
            all_cards = [w for w in self.cards_frame.winfo_children() if isinstance(w, FileCard)]

            if self._last_clicked_card is None:
                self.selected_file_ids = {fid}
                card._select()
            else:
                try:
                    idx1 = all_cards.index(self._last_clicked_card)
                    idx2 = all_cards.index(card)
                    start, end = min(idx1, idx2), max(idx1, idx2)

                    for w in all_cards:
                        try:
                            if w.winfo_exists():
                                w._deselect()
                        except:
                            pass
                    self.selected_file_ids = set()

                    for i in range(start, end + 1):
                        try:
                            if all_cards[i].winfo_exists():
                                all_cards[i]._select()
                                self.selected_file_ids.add(all_cards[i].file_id)
                        except:
                            pass
                except ValueError:
                    pass
            self._last_clicked_card = card

    def _get_selected_files(self):
        result = self.selected_file_data
        logger.info(f"_get_selected_files: id(self)={id(self)}, returning {len(result)} items")
        return result

    def _show_move_dialog(self, file_records=None):
        logger.info(f"_show_move_dialog called with file_records={file_records}")
        logger.info(f"  type={type(file_records)}, len={len(file_records) if file_records else 'N/A'}")

        if file_records is None:
            logger.info("  file_records is None, calling _get_selected_files")
            file_records = self._get_selected_files()
            logger.info(f"  after call: len={len(file_records)}")
        else:
            logger.info(f"  file_records already provided: {len(file_records)}")

        # ВРЕМЕННАЯ ОТЛАДКА
        logger.info(f"selected_file_data: {len(self.selected_file_data)} элементов")
        for f in self.selected_file_data:
            logger.info(f"  - {f[1]} (id={f[0]})")
        logger.info(f"file_records: {len(file_records)} элементов")

        if not file_records:
            messagebox.showinfo("Информация", "Нет выбранных файлов. Используйте Ctrl+Клик для выделения.")
            return

        folders = self._get_all_folders()
        if not folders:
            messagebox.showinfo("Информация", "Нет доступных папок")
            return

        dialog = MoveFileDialog(self, folders, file_records)
        self.wait_window(dialog)

        if dialog.result is not None:
            moved = 0
            for record in file_records:
                if self.move_file_to_folder(record, dialog.result):
                    moved += 1
            self.selected_file_ids = set()
            self.refresh_files()
            messagebox.showinfo("Готово", f"Перемещено файлов: {moved}/{len(file_records)}")

    def _get_all_folders(self) -> list:
        """Возвращает список всех папок проекта."""
        folders = [("", "📂 Корень")]
        if self.current_project_id:
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.current_project_id,))
            root = cursor.fetchone()
            if root and os.path.exists(root[0]):
                for dirpath, dirnames, _ in os.walk(root[0]):
                    dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                    for d in dirnames:
                        full = os.path.join(dirpath, d)
                        rel = os.path.relpath(full, root[0])
                        folders.append((rel, f"📁 {rel}"))
        return folders

    def move_file_to_folder(self, file_record, target_folder: str):
        """Перемещает файл/архив в указанную папку."""
        file_id = file_record[0]
        file_name = file_record[1]
        file_path = file_record[2]

        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT root_path FROM projects WHERE id = ?", (self.current_project_id,))
        root = cursor.fetchone()
        if not root:
            return False
        root_path = root[0]
        target_dir = os.path.join(root_path, target_folder) if target_folder else root_path
        os.makedirs(target_dir, exist_ok=True)

        if str(file_path).startswith("[ARCHIVE]"):
            archive_name = file_path.replace("[ARCHIVE] ", "")
            old_archive_path = None
            for dirpath, _, filenames in os.walk(root_path):
                if archive_name in filenames:
                    old_archive_path = os.path.join(dirpath, archive_name)
                    break
            if old_archive_path:
                new_archive_path = os.path.join(target_dir, archive_name)
                try:
                    shutil.move(old_archive_path, new_archive_path)
                    logger.info(f"Архив перемещён: {old_archive_path} -> {new_archive_path}")
                except Exception as e:
                    logger.error(f"Ошибка перемещения архива: {e}")
                    return False
            cursor.execute("UPDATE files SET relative_path = ? WHERE id = ?", (target_folder, file_id))
        else:
            old_path = Path(file_path)
            if old_path.exists():
                new_path = os.path.join(target_dir, file_name)
                try:
                    shutil.move(str(old_path), new_path)
                except Exception as e:
                    logger.error(f"Ошибка перемещения: {e}")
                    return False
                cursor.execute("UPDATE files SET file_path = ?, relative_path = ? WHERE id = ?",
                              (new_path, target_folder, file_id))

        conn.commit()
        return True

    def on_closing(self):
        if self.current_worker:
            self.current_worker.cancel()
        self.destroy()
