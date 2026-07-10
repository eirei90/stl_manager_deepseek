"""
Панель с древовидным каталогом файлов.
"""

import customtkinter as ctk
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TreePanel(ctk.CTkFrame):
    """Древовидный каталог для навигации по папкам."""

    def __init__(self, master, on_select=None, font_family="Arial", font_size=12, **kwargs):
        super().__init__(master, **kwargs)

        self.on_select = on_select
        self.font_family = font_family
        self.font_size = font_size

        self.tree_font = ctk.CTkFont(family=font_family, size=font_size - 1)
        self.tree_font_bold = ctk.CTkFont(family=font_family, size=font_size - 1, weight="bold")

        # Заголовок
        self.lbl_title = ctk.CTkLabel(
            self, text="📁 Каталог",
            font=ctk.CTkFont(family=font_family, size=font_size, weight="bold"),
            anchor="w"
        )
        self.lbl_title.pack(fill="x", padx=10, pady=(10, 5))

        # Кнопка "Показать все"
        self.btn_all = ctk.CTkButton(
            self, text="📋 Все файлы",
            command=self._show_all,
            font=self.tree_font,
            fg_color="transparent",
            border_width=1,
            height=28
        )
        self.btn_all.pack(fill="x", padx=10, pady=(0, 5))

        # Разделитель
        ctk.CTkFrame(self, height=1, fg_color="gray30").pack(fill="x", padx=10, pady=5)

        # Прокручиваемая область для дерева
        self.tree_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            label_text=""
        )
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Контейнер для элементов дерева
        self.tree_container = ctk.CTkFrame(self.tree_frame, fg_color="transparent")
        self.tree_container.pack(fill="x", expand=True)

        self._buttons = []
        self._tree_data = []

        # Заглушка
        self._placeholder = ctk.CTkLabel(
            self.tree_container,
            text="Выполните сканирование\nдля отображения каталога",
            font=self.tree_font,
            text_color="gray"
        )
        self._placeholder.pack(pady=30)

    def _show_all(self):
        """Показать все файлы."""
        if self.on_select:
            self.on_select(None)

    def build_tree(self, tree_data):
        """Строит дерево из данных."""
        logger.info(f"Построение дерева: {len(tree_data)} элементов")

        # Убираем заглушку
        if self._placeholder:
            self._placeholder.pack_forget()
            self._placeholder = None

        # Очищаем старые кнопки
        for btn in self._buttons:
            btn.destroy()
        self._buttons.clear()

        if not tree_data:
            no_data = ctk.CTkLabel(
                self.tree_container,
                text="Нет вложенных папок",
                font=self.tree_font,
                text_color="gray"
            )
            no_data.pack(pady=20)
            self._buttons.append(no_data)
            return

        # Добавляем элементы
        for item in tree_data:
            self._add_tree_item(self.tree_container, item, depth=0)

    def _add_tree_item(self, parent, item, depth=0):
        """Рекурсивно добавляет элемент дерева."""
        indent = "  " * depth

        if item.get('is_dir'):
            prefix = "📁 " if depth > 0 else "📂 "
        else:
            prefix = "📄 "

        name = item.get('name', 'Без имени')
        path = item.get('path', '')

        btn = ctk.CTkButton(
            parent,
            text=f"{indent}{prefix}{name}",
            command=lambda p=path: self._on_item_click(p),
            font=self.tree_font_bold if depth == 0 else self.tree_font,
            fg_color="transparent",
            hover_color="gray30",
            anchor="w",
            height=26
        )
        btn.pack(fill="x", pady=1)
        self._buttons.append(btn)

        # Добавляем дочерние элементы
        children = item.get('children', [])
        if children:
            for child in children:
                self._add_tree_item(parent, child, depth + 1)

    def _on_item_click(self, path):
        """Обработчик клика по элементу дерева."""
        logger.info(f"Выбран путь: {path}")
        if self.on_select:
            self.on_select(path)
