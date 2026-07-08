"""
Главное окно приложения STL Manager.
С кнопкой остановки сканирования/рендеринга.
"""

import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox
from pathlib import Path
import logging
import os
import sys
import platform
import subprocess
from PIL import Image
from typing import Optional, Tuple

# Настройка темы
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger(__name__)


def detect_best_font() -> Tuple[str, int]:
    """Определяет лучший доступный шрифт с поддержкой кириллицы."""
    system = platform.system()

    preferred_fonts = [
        "DejaVu Sans", "Liberation Sans", "Ubuntu", "Noto Sans",
        "FreeSans", "Arial", "Helvetica", "TkDefaultFont",
    ]

    if system == "Windows":
        preferred_fonts = ["Segoe UI", "Arial", "Tahoma", "Verdana"] + preferred_fonts
    elif system == "Darwin":
        preferred_fonts = ["SF Pro Display", "Helvetica Neue", "Helvetica"] + preferred_fonts

    root = tk.Tk()
    root.withdraw()

    try:
        available_fonts = set(tkfont.families())
        logger.info(f"Доступно шрифтов в Tkinter: {len(available_fonts)}")

        for font in preferred_fonts:
            if font in available_fonts:
                logger.info(f"Выбран шрифт: {font}")
                return (font, 12)

        for font in sorted(available_fonts):
            if 'sans' in font.lower():
                logger.info(f"Выбран запасной шрифт: {font}")
                return (font, 12)

        logger.warning("Не найден подходящий шрифт, используется TkDefaultFont")
        return ("TkDefaultFont", 12)

    finally:
        try:
            root.destroy()
        except:
            pass


SYSTEM_FONT = detect_best_font()
FONT_FAMILY = SYSTEM_FONT[0]
FONT_SIZE = SYSTEM_FONT[1]


class STLManagerApp(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self, db, scanner, renderer):
        super().__init__()

        self.db = db
        self.scanner = scanner
        self.renderer = renderer

        self.current_project_id: Optional[int] = None
        self.current_root_path: Optional[str] = None

        # Текущие рабочие потоки
        self.current_worker = None

        # Настройка окна
        self.title("STL Manager - Управление 3D моделями (включая архивы)")
        self.geometry("1400x900")
        self.minsize(1024, 600)

        # Создаём шрифты
        self._create_fonts()

        # Иконка
        try:
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        # Переменные фильтров
        self.search_var = ctk.StringVar()
        self.search_var.trace_add('write', lambda *args: self.refresh_file_list())

        self.min_faces_var = ctk.StringVar(value="0")
        self.max_faces_var = ctk.StringVar(value="9999999")

        self._create_widgets()
        self._create_layout()

        # Обработка закрытия окна
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        logger.info(f"Главное окно создано (шрифт: {FONT_FAMILY})")

    def _create_fonts(self):
        """Создаёт объекты шрифтов."""
        try:
            self.title_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE + 2, weight="bold")
            self.normal_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE)
            self.small_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE - 2)
            self.button_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold")
            self.status_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE - 1)
            self.stop_font = ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold")
            logger.info(f"Шрифты созданы успешно: {FONT_FAMILY}")
        except Exception as e:
            logger.error(f"Ошибка создания шрифта: {e}")
            self.title_font = ctk.CTkFont(size=FONT_SIZE + 2, weight="bold")
            self.normal_font = ctk.CTkFont(size=FONT_SIZE)
            self.small_font = ctk.CTkFont(size=FONT_SIZE - 2)
            self.button_font = ctk.CTkFont(size=FONT_SIZE, weight="bold")
            self.status_font = ctk.CTkFont(size=FONT_SIZE - 1)
            self.stop_font = ctk.CTkFont(size=FONT_SIZE, weight="bold")

    def _create_widgets(self):
        """Создаёт все виджеты."""
        # === Панель инструментов ===
        self.toolbar = ctk.CTkFrame(self, height=50, corner_radius=0)

        self.btn_select_folder = ctk.CTkButton(
            self.toolbar,
            text="📁 Выбрать папку",
            command=self.select_folder,
            width=150,
            font=self.button_font
        )

        self.btn_scan = ctk.CTkButton(
            self.toolbar,
            text="🔍 Сканировать (с архивами)",
            command=self.start_scan,
            state="disabled",
            width=200,
            font=self.button_font
        )

        self.btn_render = ctk.CTkButton(
            self.toolbar,
            text="🖼 Создать превью",
            command=self.start_render_all,
            state="disabled",
            width=180,
            font=self.button_font
        )

        # Кнопка остановки (изначально скрыта)
        self.btn_stop = ctk.CTkButton(
            self.toolbar,
            text="⏹ Остановить",
            command=self.stop_operation,
            width=150,
            font=self.stop_font,
            fg_color="#D32F2F",
            hover_color="#B71C1C",
            state="disabled"
        )

        self.lbl_folder = ctk.CTkLabel(
            self.toolbar,
            text="Папка не выбрана",
            anchor="w",
            font=self.normal_font,
            wraplength=400
        )

        # === Прогресс-бар ===
        self.progress_frame = ctk.CTkFrame(self, height=40)

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            width=400,
            mode="determinate"
        )
        self.progress_bar.set(0)

        self.lbl_progress = ctk.CTkLabel(
            self.progress_frame,
            text="Готов",
            font=self.normal_font
        )

        self.lbl_current_file = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=self.small_font,
            text_color="gray"
        )

        # === Панель фильтров ===
        self.filter_frame = ctk.CTkFrame(self, height=50)

        ctk.CTkLabel(self.filter_frame, text="🔎 Поиск:", font=self.normal_font).pack(side="left", padx=5)

        self.entry_search = ctk.CTkEntry(
            self.filter_frame,
            textvariable=self.search_var,
            width=200,
            placeholder_text="Введите имя файла...",
            font=self.normal_font
        )
        self.entry_search.pack(side="left", padx=5)

        ctk.CTkLabel(self.filter_frame, text="Полигонов от:", font=self.normal_font).pack(side="left", padx=(20, 5))

        self.entry_min_faces = ctk.CTkEntry(
            self.filter_frame,
            textvariable=self.min_faces_var,
            width=80,
            font=self.normal_font
        )
        self.entry_min_faces.pack(side="left", padx=5)

        ctk.CTkLabel(self.filter_frame, text="до:", font=self.normal_font).pack(side="left", padx=5)

        self.entry_max_faces = ctk.CTkEntry(
            self.filter_frame,
            textvariable=self.max_faces_var,
            width=80,
            font=self.normal_font
        )
        self.entry_max_faces.pack(side="left", padx=5)

        self.btn_apply_filter = ctk.CTkButton(
            self.filter_frame,
            text="Применить",
            command=self.refresh_file_list,
            width=100,
            font=self.button_font
        )
        self.btn_apply_filter.pack(side="left", padx=20)

        # === Область с карточками ===
        self.cards_frame = ctk.CTkScrollableFrame(
            self,
            label_text="STL Файлы (включая найденные в архивах)",
            label_font=self.title_font
        )

        # === Строка состояния ===
        self.status_bar = ctk.CTkLabel(
            self,
            text=f"Поддерживаются архивы: 7z, RAR, ZIP | Шрифт: {FONT_FAMILY}",
            anchor="w",
            font=self.status_font,
            height=25
        )

    def _create_layout(self):
        """Размещает виджеты."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Панель инструментов
        self.toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.toolbar.grid_columnconfigure(4, weight=1)  # Растягиваем метку пути

        self.btn_select_folder.grid(row=0, column=0, padx=5, pady=5)
        self.btn_scan.grid(row=0, column=1, padx=5, pady=5)
        self.btn_render.grid(row=0, column=2, padx=5, pady=5)
        self.btn_stop.grid(row=0, column=3, padx=5, pady=5)
        self.lbl_folder.grid(row=0, column=4, padx=10, sticky="w")

        # Прогресс-бар
        self.progress_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.lbl_progress.grid(row=0, column=1, padx=10)
        self.lbl_current_file.grid(row=1, column=0, columnspan=2, padx=10, sticky="w")

        # Фильтры
        self.filter_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)

        # Область карточек
        self.cards_frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=2)

        # Строка состояния
        self.status_bar.grid(row=4, column=0, sticky="ew", padx=5, pady=2)

    def select_folder(self):
        """Диалог выбора папки."""
        folder = filedialog.askdirectory(title="Выберите папку с STL файлами и архивами")
        if folder:
            self.current_root_path = folder
            self.lbl_folder.configure(text=f"📂 {folder}")
            self.btn_scan.configure(state="normal")
            self.status_bar.configure(
                text=f"Выбрана папка: {folder} | Поддерживаются архивы: 7z, RAR, ZIP"
            )
            logger.info(f"Выбрана папка: {folder}")

    def start_scan(self):
        """Запускает сканирование в фоновом потоке."""
        if not self.current_root_path:
            messagebox.showwarning("Предупреждение", "Сначала выберите папку!")
            return

        self._set_ui_state("scanning")

        from ui.workers import ScanWorker, CancellationToken

        # Создаём токен отмены
        cancel_token = CancellationToken()

        self.scan_worker = ScanWorker(
            scanner=self.scanner,
            root_path=self.current_root_path,
            cancellation_token=cancel_token,
            on_progress=self._on_scan_progress,
            on_complete=self._on_scan_complete,
            on_error=self._on_scan_error,
            on_cancelled=self._on_scan_cancelled
        )
        self.current_worker = self.scan_worker
        self.scan_worker.start()

    def _on_scan_progress(self, current: int, total: int):
        """Обновление прогресса сканирования."""
        self.after(0, lambda: self._update_progress(current, total, "Сканирование"))

    def _update_progress(self, current: int, total: int, operation: str):
        """Обновление прогресс-бара."""
        if total > 0:
            self.progress_bar.set(current / total)
        self.lbl_progress.configure(text=f"{operation}: {current}/{total}")

    def _on_scan_complete(self, project_id: int):
        """Завершение сканирования."""
        self.after(0, lambda: self._finish_scan(project_id))

    def _finish_scan(self, project_id: int):
        """Безопасное завершение сканирования."""
        self.current_project_id = project_id
        self.progress_bar.set(1.0)
        self.lbl_progress.configure(text="Сканирование завершено ✓")
        self.btn_render.configure(state="normal")
        self.status_bar.configure(text="Сканирование завершено. Можно создать превью.")
        self.refresh_file_list()
        self.current_worker = None
        self._set_ui_state("idle")
        logger.info(f"Сканирование завершено. Project ID: {project_id}")

    def _on_scan_error(self, error_msg: str):
        """Ошибка сканирования."""
        self.after(0, lambda: self._handle_operation_error("сканирования", error_msg))

    def _on_scan_cancelled(self):
        """Сканирование отменено."""
        self.after(0, lambda: self._handle_cancelled("Сканирование"))

    def _handle_operation_error(self, operation: str, error_msg: str):
        """Обработка ошибки операции."""
        self.progress_bar.set(0)
        self.lbl_progress.configure(text=f"Ошибка {operation}!")
        self.status_bar.configure(text=f"Ошибка: {error_msg}")
        messagebox.showerror("Ошибка", f"Не удалось выполнить {operation}:\n{error_msg}")
        self.current_worker = None
        self._set_ui_state("idle")

    def _handle_cancelled(self, operation: str):
        """Обработка отмены операции."""
        self.progress_bar.set(0)
        self.lbl_progress.configure(text=f"{operation} отменено ⊘")
        self.status_bar.configure(text=f"{operation} прервано пользователем")
        self.current_worker = None
        self._set_ui_state("idle")
        self.refresh_file_list()

    def start_render_all(self):
        """Запускает рендеринг всех превью."""
        if not self.current_project_id:
            messagebox.showwarning("Предупреждение", "Сначала выполните сканирование!")
            return

        if not self.renderer:
            messagebox.showwarning("Предупреждение", "Рендерер недоступен!")
            return

        self._set_ui_state("rendering")

        from ui.workers import RenderWorker, CancellationToken

        cancel_token = CancellationToken()

        self.render_worker = RenderWorker(
            renderer=self.renderer,
            db=self.db,
            project_id=self.current_project_id,
            cancellation_token=cancel_token,
            on_progress=self._on_render_progress,
            on_complete=self._on_render_complete,
            on_error=self._on_render_error,
            on_cancelled=self._on_render_cancelled
        )
        self.current_worker = self.render_worker
        self.render_worker.start()

    def _on_render_progress(self, current: int, total: int):
        """Обновление прогресса рендеринга."""
        self.after(0, lambda: self._update_progress(current, total, "Рендеринг"))

    def _on_render_complete(self, rendered_count: int):
        """Завершение рендеринга."""
        self.after(0, lambda: self._finish_render(rendered_count))

    def _finish_render(self, rendered_count: int):
        """Безопасное завершение рендеринга."""
        self.progress_bar.set(1.0)
        self.lbl_progress.configure(text=f"Превью созданы ({rendered_count} шт.) ✓")
        self.status_bar.configure(text=f"Создано превью: {rendered_count} файлов")
        self.refresh_file_list()
        self.current_worker = None
        self._set_ui_state("idle")
        logger.info(f"Рендеринг завершён: {rendered_count} файлов")

    def _on_render_error(self, error_msg: str):
        """Ошибка рендеринга."""
        self.after(0, lambda: self._handle_operation_error("рендеринга", error_msg))

    def _on_render_cancelled(self):
        """Рендеринг отменён."""
        self.after(0, lambda: self._handle_cancelled("Рендеринг"))

    def stop_operation(self):
        """Останавливает текущую операцию."""
        if self.current_worker:
            logger.info("Пользователь запросил остановку операции")
            self.btn_stop.configure(state="disabled", text="⏳ Останавливаем...")
            self.current_worker.cancel()
        else:
            logger.warning("Нет активной операции для остановки")

    def refresh_file_list(self):
        """Обновляет список карточек файлов."""
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        if not self.current_project_id:
            empty_label = ctk.CTkLabel(
                self.cards_frame,
                text="Нет файлов для отображения.\nВыполните сканирование папки.",
                font=self.normal_font,
                text_color="gray"
            )
            empty_label.pack(padx=20, pady=50)
            return

        name_filter = self.search_var.get().strip() or None

        try:
            min_faces = int(self.min_faces_var.get())
        except ValueError:
            min_faces = None

        try:
            max_faces = int(self.max_faces_var.get())
        except ValueError:
            max_faces = None

        files = self.db.get_files_for_project(
            self.current_project_id,
            name_filter=name_filter,
            min_faces=min_faces,
            max_faces=max_faces
        )

        if not files:
            empty_label = ctk.CTkLabel(
                self.cards_frame,
                text="Файлы не найдены.\nПопробуйте изменить параметры фильтрации.",
                font=self.normal_font,
                text_color="gray"
            )
            empty_label.pack(padx=20, pady=50)
            self.status_bar.configure(text="Файлы не найдены | Шрифт: " + FONT_FAMILY)
            return

        from ui.cards import FileCard

        row = 0
        col = 0
        max_cols = 3

        for i in range(max_cols):
            self.cards_frame.grid_columnconfigure(i, weight=1, uniform="card_col")

        for file_data in files:
            try:
                card = FileCard(
                    self.cards_frame,
                    file_data=file_data,
                    on_open=self._open_file_location,
                    font_family=FONT_FAMILY,
                    font_size=FONT_SIZE
                )
                card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            except Exception as e:
                logger.error(f"Ошибка создания карточки: {e}")
                error_card = ctk.CTkFrame(self.cards_frame, corner_radius=10, fg_color="darkred")
                error_label = ctk.CTkLabel(
                    error_card,
                    text=f"Ошибка загрузки\n{str(e)[:100]}",
                    font=self.small_font,
                    wraplength=180
                )
                error_label.pack(padx=10, pady=10)
                error_card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        self.status_bar.configure(text=f"Отображено файлов: {len(files)} | Шрифт: {FONT_FAMILY}")

    def _open_file_location(self, file_path: str):
        """Открывает расположение файла."""
        if file_path.startswith("[ARCHIVE]"):
            messagebox.showinfo(
                "Файл в архиве",
                f"Этот файл находится внутри архива:\n{file_path}\n\n"
                "Для доступа к оригиналу извлеките архив вручную."
            )
            return

        path = Path(file_path)
        if not path.exists():
            messagebox.showwarning("Файл не найден", f"Файл не существует:\n{file_path}")
            return

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path.parent)
            elif system == "Darwin":
                subprocess.run(["open", str(path.parent)])
            else:
                subprocess.run(["xdg-open", str(path.parent)])
        except Exception as e:
            logger.error(f"Не удалось открыть папку: {e}")
            messagebox.showerror("Ошибка", f"Не удалось открыть папку:\n{e}")

    def _set_ui_state(self, state: str):
        """Управляет состоянием кнопок."""
        if state == "scanning" or state == "rendering":
            self.btn_select_folder.configure(state="disabled")
            self.btn_scan.configure(state="disabled")
            self.btn_render.configure(state="disabled")
            self.btn_stop.configure(
                state="normal",
                text="⏹ Остановить",
                fg_color="#D32F2F",
                hover_color="#B71C1C"
            )
            self.btn_apply_filter.configure(state="disabled")
        else:  # idle
            self.btn_select_folder.configure(state="normal")
            self.btn_scan.configure(state="normal" if self.current_root_path else "disabled")
            if self.current_project_id and self.renderer:
                self.btn_render.configure(state="normal")
            else:
                self.btn_render.configure(state="disabled")
            self.btn_stop.configure(state="disabled", text="⏹ Остановить")
            self.btn_apply_filter.configure(state="normal")

    def on_closing(self):
        """Действия при закрытии окна."""
        # Останавливаем текущую операцию
        if self.current_worker:
            logger.info("Закрытие окна: остановка текущей операции")
            self.current_worker.cancel()
            self.current_worker.join(timeout=2)

        self.db.close()
        self.destroy()