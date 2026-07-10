"""
Главное окно приложения STL Manager.
Содержит панель инструментов, дерево каталога и карточки файлов.
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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger(__name__)


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


class ImagePreviewWindow(ctk.CTkToplevel):
    """Окно для просмотра превью в большом размере."""

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


class STLManagerApp(ctk.CTk):
    """Главное окно."""

    def __init__(self, db, scanner, renderer):
        super().__init__()

        self.db = db
        self.scanner = scanner
        self.renderer = renderer

        self.current_project_id = None
        self.current_root_path = None
        self.current_worker = None
        self.selected_path = None

        self.title("STL Manager")
        self.geometry("1500x900")
        self.minsize(1100, 600)

        self._create_fonts()
        self._create_widgets()
        self._create_layout()

        # Загружаем последний проект после отрисовки интерфейса
        self.after(300, self._load_last_project)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        logger.info("Окно создано")

    def _create_fonts(self):
        self.title_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE+2, weight="bold")
        self.normal_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE)
        self.small_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE-2)
        self.btn_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold")

    def _create_widgets(self):
        # Панель инструментов
        self.toolbar = ctk.CTkFrame(self, height=45, corner_radius=0)

        self.btn_folder = ctk.CTkButton(self.toolbar, text="📁 Выбрать папку",
                                        command=self.select_folder, width=140, font=self.btn_font)
        self.btn_scan = ctk.CTkButton(self.toolbar, text="🔍 Сканировать",
                                      command=self.start_scan, state="disabled", width=140, font=self.btn_font)
        self.btn_render = ctk.CTkButton(self.toolbar, text="🖼 Превью",
                                        command=self.start_render, state="disabled", width=120, font=self.btn_font)
        self.btn_stop = ctk.CTkButton(self.toolbar, text="⏹ Стоп",
                                      command=self.stop_operation, state="disabled",
                                      width=100, font=self.btn_font, fg_color="#D32F2F")
        self.lbl_folder = ctk.CTkLabel(self.toolbar, text="Папка не выбрана",
                                       anchor="w", font=self.normal_font)

        # Прогресс
        self.progress = ctk.CTkProgressBar(self, height=10)
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self, text="Готов", font=self.small_font)

        # Фильтры
        self.filter_frame = ctk.CTkFrame(self, height=35)
        ctk.CTkLabel(self.filter_frame, text="🔎", font=self.normal_font).pack(side="left", padx=5)
        self.search_var = ctk.StringVar()
        self.search_var.trace_add('write', lambda *a: self.refresh_files())
        self.entry_search = ctk.CTkEntry(self.filter_frame, textvariable=self.search_var,
                                         width=180, placeholder_text="Поиск...", font=self.normal_font)
        self.entry_search.pack(side="left", padx=5)

        ctk.CTkLabel(self.filter_frame, text="Полигонов:", font=self.small_font).pack(side="left", padx=(20,5))
        self.min_faces = ctk.StringVar(value="0")
        self.max_faces = ctk.StringVar(value="9999999")
        ctk.CTkEntry(self.filter_frame, textvariable=self.min_faces, width=70, font=self.small_font).pack(side="left", padx=2)
        ctk.CTkLabel(self.filter_frame, text="-", font=self.small_font).pack(side="left")
        ctk.CTkEntry(self.filter_frame, textvariable=self.max_faces, width=70, font=self.small_font).pack(side="left", padx=2)
        ctk.CTkButton(self.filter_frame, text="Применить", command=lambda: self.refresh_files(),
                      width=80, font=self.small_font).pack(side="left", padx=10)
        ctk.CTkButton(
            self.filter_frame,
            text="✖ Сброс",
            command=self._reset_filters,
            width=60,
            font=self.small_font,
            fg_color="transparent",
            border_width=1
        ).pack(side="left", padx=5)

        # Основная область
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")

        # Дерево слева
        from ui.tree_panel import TreePanel
        self.tree_panel = TreePanel(
            self.main_frame,
            on_select=self._on_tree_select,
            font_family=FONT_FAMILY,
            font_size=FONT_SIZE,
            width=250
        )

        # Карточки справа
        self.cards_frame = ctk.CTkScrollableFrame(self.main_frame, label_text="Файлы",
                                                   label_font=self.title_font)

        # Статус
        self.status = ctk.CTkLabel(
            self,
            text="Готов",
            anchor="w",
            font=self.small_font,
            height=25
        )

    def _create_layout(self):
        """Размещает виджеты."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_rowconfigure(4, weight=0)

        self.toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.toolbar.grid_columnconfigure(4, weight=1)

        self.btn_folder.grid(row=0, column=0, padx=3)
        self.btn_scan.grid(row=0, column=1, padx=3)
        self.btn_render.grid(row=0, column=2, padx=3)
        self.btn_stop.grid(row=0, column=3, padx=3)
        self.lbl_folder.grid(row=0, column=4, padx=10, sticky="w")

        self.progress.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 0))
        self.lbl_progress.grid(row=1, column=0, sticky="e", padx=15, pady=(5, 0))

        self.filter_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)

        self.main_frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=2)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.tree_panel.grid(row=0, column=0, sticky="ns", padx=(0, 5))
        self.cards_frame.grid(row=0, column=1, sticky="nsew")

        self.status.grid(row=4, column=0, sticky="ew", padx=5, pady=2)
        self.status.configure(height=25)

    def _load_last_project(self):
        """Загружает последний проект при запуске."""
        try:
            conn = self.db._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, root_path FROM projects
                WHERE total_files > 0
                ORDER BY scan_date DESC
                LIMIT 1
            """)
            result = cursor.fetchone()

            if result:
                project_id, root_path = result
                self.current_project_id = project_id
                self.current_root_path = root_path

                self.lbl_folder.configure(text=f"📂 {root_path}")
                self.btn_scan.configure(state="normal")
                self.btn_render.configure(state="normal")

                self.refresh_tree()
                self.refresh_files()

                logger.info(f"Загружен проект: {root_path} (ID: {project_id})")
                self.status.configure(text=f"Загружен проект: {Path(root_path).name}")
            else:
                logger.info("Нет сохранённых проектов")

        except Exception as e:
            logger.error(f"Ошибка загрузки проекта: {e}")

    def select_folder(self):
        """Диалог выбора папки."""
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
                    # Пользователь нажал "Отмена" или закрыл окно
                    return  # <-- Выходим, не открывая Tkinter
            except FileNotFoundError:
                logger.warning("Zenity не установлен")
            except Exception as e:
                logger.error(f"Ошибка Zenity: {e}")

        # Tkinter только если Zenity недоступен (Windows/macOS)
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
            logger.info(f"Выбрана папка: {folder}")
    def start_scan(self):
        if not self.current_root_path:
            return
        self._set_state("scanning")
        from ui.workers import ScanWorker, CancellationToken
        token = CancellationToken()
        self.current_worker = ScanWorker(
            self.scanner, self.current_root_path,
            cancellation_token=token,
            on_progress=lambda c, t: self.after(0, lambda: self._update_progress(c, t, "Сканирование")),
            on_complete=lambda pid: self.after(0, lambda: self._finish_scan(pid)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    def _finish_scan(self, project_id):
        self.current_project_id = project_id
        self.progress.set(1)
        self.lbl_progress.configure(text="Готово ✓")
        self.btn_render.configure(state="normal")
        self._set_state("idle")
        self.refresh_tree()
        self.refresh_files()

    def start_render(self):
        if not self.current_project_id:
            return
        self._set_state("rendering")
        from ui.workers import RenderWorker, CancellationToken
        token = CancellationToken()
        self.current_worker = RenderWorker(
            self.renderer, self.db, self.current_project_id,
            cancellation_token=token,
            on_progress=lambda c, t: self.after(0, lambda: self._update_progress(c, t, "Превью")),
            on_complete=lambda n: self.after(0, lambda: self._finish_render(n)),
            on_error=lambda e: self.after(0, lambda: self._on_error(e))
        )
        self.current_worker.start()

    def _finish_render(self, count):
        self.progress.set(1)
        self.lbl_progress.configure(text=f"Создано: {count} ✓")
        self._set_state("idle")
        self.refresh_files()

    def stop_operation(self):
        if self.current_worker:
            self.current_worker.cancel()

    def _update_progress(self, current, total, text):
        if total > 0:
            self.progress.set(current/total)
        self.lbl_progress.configure(text=f"{text}: {current}/{total}")

    def _on_error(self, msg):
        messagebox.showerror("Ошибка", msg)
        self._set_state("idle")

    def _set_state(self, state):
        if state in ("scanning", "rendering"):
            self.btn_folder.configure(state="disabled")
            self.btn_scan.configure(state="disabled")
            self.btn_render.configure(state="disabled")
            self.btn_stop.configure(state="normal")
        else:
            self.btn_folder.configure(state="normal")
            self.btn_scan.configure(state="normal" if self.current_root_path else "disabled")
            self.btn_render.configure(state="normal" if self.current_project_id else "disabled")
            self.btn_stop.configure(state="disabled")

    def refresh_tree(self):
        if self.current_project_id:
            tree = self.db.get_directory_tree(self.current_project_id)
            self.tree_panel.build_tree(tree)

    def _on_tree_select(self, path):
        """Обработчик выбора элемента в дереве."""
        if not path:
            return

        clean_path = path
        for prefix in ["📂 ", "📁 ", "📄 ", "📦 ", "⚠ "]:
            clean_path = clean_path.replace(prefix, "")

        clean_path = re.sub(r'\s*\(\d+\)\s*$', '', clean_path).strip()

        logger.info(f"Выбран путь: {path} -> чистый: {clean_path}")

        # Проверяем, является ли это файлом (есть расширение)
        is_file = bool(Path(clean_path).suffix)

        if is_file:
            # Это файл (включая .zip, .stl) — фильтруем по имени
            self.selected_path = None
            # Убираем расширение для поиска
            search_name = Path(clean_path).stem
            self.search_var.set(search_name)
        else:
            # Это папка — фильтруем по relative_path
            self.selected_path = clean_path
            self.search_var.set("")  # Сбрасываем поиск

        self.refresh_files()

    def refresh_files(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()

        if not self.current_project_id:
            ctk.CTkLabel(
                self.cards_frame,
                text="Нет файлов для отображения.\nВыполните сканирование папки.",
                font=self.normal_font,
                text_color="gray"
            ).pack(padx=20, pady=50)
            return

        name = self.search_var.get().strip() or None
        try:
            mn = int(self.min_faces.get())
        except:
            mn = None
        try:
            mx = int(self.max_faces.get())
        except:
            mx = None

        files = self.db.get_files_for_project(
            self.current_project_id,
            name_filter=name,
            min_faces=mn,
            max_faces=mx,
            relative_path=self.selected_path
        )

        from ui.cards import FileCard

        row, col, maxc = 0, 0, 3
        for i in range(maxc):
            self.cards_frame.grid_columnconfigure(i, weight=1, uniform="card")

        for fd in files:
            card = FileCard(
                self.cards_frame, fd,
                on_open=self._open_location,
                on_preview=self._open_preview,
                font_family=FONT_FAMILY, font_size=FONT_SIZE
            )
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            col += 1
            if col >= maxc:
                col = 0
                row += 1

        total = len(files)
        thumbs = sum(1 for f in files if len(f) > 12 and f[12])
        archives = sum(1 for f in files if str(f[2]).startswith("[ARCHIVE]"))
        existing = sum(1 for f in files if len(f) > 15 and f[15] == 'existing')

        self.status.configure(
            text=f"Всего: {total} | STL: {total-archives} | Архив: {archives} | Превью: {thumbs} | Готовых: {existing}"
        )

    def _open_location(self, path):
        if path.startswith("[ARCHIVE]"):
            messagebox.showinfo("Архив", f"Файл в архиве:\n{path}")
            return
        p = Path(path)
        if p.exists():
            try:
                s = platform.system()
                if s == "Windows": os.startfile(p.parent)
                elif s == "Darwin": subprocess.run(["open", str(p.parent)])
                else: subprocess.run(["xdg-open", str(p.parent)])
            except Exception as e:
                logger.error(f"Ошибка открытия: {e}")

    def _open_preview(self, path):
        ImagePreviewWindow(self, path)

    def on_closing(self):
        if self.current_worker:
            self.current_worker.cancel()
        # У Database нет метода close, просто завершаем работу
        self.destroy()

    def _reset_filters(self):
        """Сбрасывает все фильтры."""
        self.search_var.set("")
        self.min_faces.set("0")
        self.max_faces.set("9999999")
        self.selected_path = None
        self.refresh_files()
        logger.info("Фильтры сброшены")
