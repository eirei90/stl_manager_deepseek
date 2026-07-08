"""
Главное окно приложения STL Manager.
Интерфейс на CustomTkinter с поддержкой кириллицы и отображением файлов из архивов.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import logging
import os
import sys
import platform
from PIL import Image
from typing import Optional, Tuple

# Настройка темы
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

logger = logging.getLogger(__name__)


def detect_system_font() -> str:
    """
    Определяет подходящий системный шрифт с поддержкой кириллицы.
    НЕ создаёт виджеты Tkinter — только возвращает имя шрифта.
    """
    system = platform.system()

    if system == "Windows":
        return "Segoe UI"
    elif system == "Darwin":
        return "SF Pro Display"
    else:  # Linux
        # Проверяем наличие шрифтов в системе через fc-list
        import subprocess
        try:
            result = subprocess.run(
                ['fc-list', ':lang=ru', 'family'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # Берём первый доступный шрифт с кириллицей
                fonts = result.stdout.strip().split('\n')
                # Приоритетные шрифты
                preferred = ['DejaVu Sans', 'Ubuntu', 'Liberation Sans', 'Noto Sans']
                for pref in preferred:
                    for font_line in fonts:
                        if pref in font_line:
                            font_name = font_line.split(':')[0].strip()
                            logger.info(f"Определён системный шрифт: {font_name}")
                            return font_name
                # Если не нашли предпочтительный — берём первый
                font_name = fonts[0].split(':')[0].strip()
                logger.info(f"Определён системный шрифт: {font_name}")
                return font_name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback для Linux без fc-list
        logger.warning("Не удалось определить шрифт через fc-list, используется Arial")
        return "Arial"


def get_system_font() -> Tuple[str, int]:
    """
    Возвращает кортеж (имя_шрифта, размер).
    Без создания виджетов Tkinter.
    """
    font_name = detect_system_font()
    return (font_name, 12)


# Получаем шрифт ДО создания окна
SYSTEM_FONT = get_system_font()
FONT_FAMILY = SYSTEM_FONT[0]
FONT_SIZE = SYSTEM_FONT[1]

logger.info(f"Системный шрифт: {FONT_FAMILY}, размер: {FONT_SIZE}")


class STLManagerApp(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self, db, scanner, renderer):
        super().__init__()

        self.db = db
        self.scanner = scanner
        self.renderer = renderer

        self.current_project_id: Optional[int] = None
        self.current_root_path: Optional[str] = None

        # Настройка окна
        self.title("STL Manager - Управление 3D моделями (включая архивы)")
        self.geometry("1400x900")
        self.minsize(1024, 600)

        # Шрифты создаём ПОСЛЕ инициализации окна
        self._setup_fonts()

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

        logger.info(f"Главное окно создано (шрифт: {FONT_FAMILY})")

    def _setup_fonts(self):
        """Настройка шрифтов после создания окна."""
        # Проверяем, доступен ли шрифт в Tkinter
        available_fonts = tk.font.families()

        if FONT_FAMILY in available_fonts:
            actual_font = FONT_FAMILY
        else:
            # Пробуем найти альтернативу
            logger.warning(f"Шрифт {FONT_FAMILY} не найден в Tkinter, поиск альтернативы...")

            alternatives = ['DejaVu Sans', 'Ubuntu', 'Liberation Sans', 'Noto Sans',
                          'Segoe UI', 'Arial', 'Helvetica', 'TkDefaultFont']

            actual_font = 'TkDefaultFont'  # Fallback по умолчанию
            for alt in alternatives:
                if alt in available_fonts:
                    actual_font = alt
                    logger.info(f"Используется альтернативный шрифт: {alt}")
                    break

        self.title_font = ctk.CTkFont(family=actual_font, size=FONT_SIZE + 2, weight="bold")
        self.normal_font = ctk.CTkFont(family=actual_font, size=FONT_SIZE)
        self.small_font = ctk.CTkFont(family=actual_font, size=FONT_SIZE - 2)
        self.button_font = ctk.CTkFont(family=actual_font, size=FONT_SIZE, weight="bold")
        self.status_font = ctk.CTkFont(family=actual_font, size=FONT_SIZE - 1)

        # Сохраняем реально используемый шрифт для карточек
        self.actual_font_family = actual_font

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

        self.lbl_folder = ctk.CTkLabel(
            self.toolbar,
            text="Папка не выбрана",
            anchor="w",
            font=self.normal_font,
            wraplength=500
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

        ctk.CTkLabel(
            self.filter_frame,
            text="🔎 Поиск:",
            font=self.normal_font
        ).pack(side="left", padx=5)

        self.entry_search = ctk.CTkEntry(
            self.filter_frame,
            textvariable=self.search_var,
            width=200,
            placeholder_text="Введите имя файла...",
            font=self.normal_font
        )
        self.entry_search.pack(side="left", padx=5)

        ctk.CTkLabel(
            self.filter_frame,
            text="Полигонов от:",
            font=self.normal_font
        ).pack(side="left", padx=(20, 5))

        self.entry_min_faces = ctk.CTkEntry(
            self.filter_frame,
            textvariable=self.min_faces_var,
            width=80,
            font=self.normal_font
        )
        self.entry_min_faces.pack(side="left", padx=5)

        ctk.CTkLabel(
            self.filter_frame,
            text="до:",
            font=self.normal_font
        ).pack(side="left", padx=5)

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
            text="Поддерживаются архивы: 7z, RAR, ZIP | Шрифт: " + self.actual_font_family,
            anchor="w",
            font=self.status_font,
            height=25
        )

    def _create_layout(self):
        """Размещает виджеты."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.toolbar.grid_columnconfigure(3, weight=1)

        self.btn_select_folder.grid(row=0, column=0, padx=5, pady=5)
        self.btn_scan.grid(row=0, column=1, padx=5, pady=5)
        self.btn_render.grid(row=0, column=2, padx=5, pady=5)
        self.lbl_folder.grid(row=0, column=3, padx=10, sticky="w")

        self.progress_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=2)
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.lbl_progress.grid(row=0, column=1, padx=10)
        self.lbl_current_file.grid(row=1, column=0, columnspan=2, padx=10, sticky="w")

        self.filter_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        self.cards_frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=2)
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

        from ui.workers import ScanWorker

        self.scan_worker = ScanWorker(
            scanner=self.scanner,
            root_path=self.current_root_path,
            on_progress=self._on_scan_progress,
            on_complete=self._on_scan_complete,
            on_error=self._on_scan_error
        )
        self.scan_worker.start()

    def _on_scan_progress(self, current: int, total: int):
        """Обновление прогресса сканирования."""
        self.after(0, lambda: self._update_scan_progress(current, total))

    def _update_scan_progress(self, current: int, total: int):
        """Безопасное обновление прогресса."""
        self.progress_bar.set(current / total if total > 0 else 0)
        self.lbl_progress.configure(text=f"Сканирование: {current}/{total}")

    def _on_scan_complete(self, project_id: int):
        """Завершение сканирования."""
        self.after(0, lambda: self._finish_scan(project_id))

    def _finish_scan(self, project_id: int):
        """Безопасное завершение сканирования."""
        self.current_project_id = project_id
        self.progress_bar.set(1.0)
        self.lbl_progress.configure(text="Сканирование завершено")
        self.btn_render.configure(state="normal")
        self.status_bar.configure(text="Сканирование завершено. Можно создать превью.")
        self.refresh_file_list()
        logger.info(f"Сканирование завершено. Project ID: {project_id}")

    def _on_scan_error(self, error_msg: str):
        """Ошибка сканирования."""
        self.after(0, lambda: self._handle_scan_error(error_msg))

    def _handle_scan_error(self, error_msg: str):
        """Безопасная обработка ошибки."""
        self.progress_bar.set(0)
        self.lbl_progress.configure(text="Ошибка сканирования!")
        self.status_bar.configure(text=f"Ошибка: {error_msg}")
        messagebox.showerror("Ошибка", f"Не удалось выполнить сканирование:\n{error_msg}")
        self._set_ui_state("idle")

    def start_render_all(self):
        """Запускает рендеринг всех превью."""
        if not self.current_project_id:
            messagebox.showwarning("Предупреждение", "Сначала выполните сканирование!")
            return

        self._set_ui_state("rendering")

        from ui.workers import RenderWorker

        self.render_worker = RenderWorker(
            renderer=self.renderer,
            db=self.db,
            project_id=self.current_project_id,
            on_progress=self._on_render_progress,
            on_complete=self._on_render_complete,
            on_error=self._on_render_error
        )
        self.render_worker.start()

    def _on_render_progress(self, current: int, total: int):
        """Обновление прогресса рендеринга."""
        self.after(0, lambda: self._update_render_progress(current, total))

    def _update_render_progress(self, current: int, total: int):
        """Безопасное обновление прогресса рендеринга."""
        self.progress_bar.set(current / total if total > 0 else 0)
        self.lbl_progress.configure(text=f"Создание превью: {current}/{total}")

    def _on_render_complete(self, rendered_count: int):
        """Завершение рендеринга."""
        self.after(0, lambda: self._finish_render(rendered_count))

    def _finish_render(self, rendered_count: int):
        """Безопасное завершение рендеринга."""
        self.progress_bar.set(1.0)
        self.lbl_progress.configure(text=f"Превью созданы ({rendered_count} шт.)")
        self.status_bar.configure(text=f"Создано превью: {rendered_count} файлов")
        self.refresh_file_list()
        self._set_ui_state("idle")
        logger.info(f"Рендеринг завершён: {rendered_count} файлов")

    def _on_render_error(self, error_msg: str):
        """Ошибка рендеринга."""
        self.after(0, lambda: self._handle_render_error(error_msg))

    def _handle_render_error(self, error_msg: str):
        """Безопасная обработка ошибки рендеринга."""
        self.lbl_progress.configure(text="Ошибка создания превью!")
        self.status_bar.configure(text=f"Ошибка: {error_msg}")
        messagebox.showerror("Ошибка", f"Не удалось создать превью:\n{error_msg}")
        self._set_ui_state("idle")

    def refresh_file_list(self):
        """Обновляет список карточек файлов."""
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        if not self.current_project_id:
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

        from ui.cards import FileCard

        row = 0
        col = 0
        max_cols = 3

        for file_data in files:
            card = FileCard(
                self.cards_frame,
                file_data=file_data,
                on_open=self._open_file_location,
                font_family=self.actual_font_family,
                font_size=FONT_SIZE
            )
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        for i in range(max_cols):
            self.cards_frame.grid_columnconfigure(i, weight=1)

        self.status_bar.configure(text=f"Отображено файлов: {len(files)} | Шрифт: {self.actual_font_family}")

    def _open_file_location(self, file_path: str):
        """Открывает расположение файла (если это не файл из архива)."""
        import subprocess

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
        if state == "scanning":
            self.btn_select_folder.configure(state="disabled")
            self.btn_scan.configure(state="disabled")
            self.btn_render.configure(state="disabled")
        elif state == "rendering":
            self.btn_select_folder.configure(state="disabled")
            self.btn_scan.configure(state="disabled")
            self.btn_render.configure(state="disabled")
        else:  # idle
            self.btn_select_folder.configure(state="normal")
            self.btn_scan.configure(state="normal")
            if self.current_project_id:
                self.btn_render.configure(state="normal")

    def on_closing(self):
        """Действия при закрытии окна."""
        self.db.close()
        self.destroy()