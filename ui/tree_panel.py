"""
Панель с древовидным каталогом файлов.
Использует ttk.Treeview. Сохраняет состояние открытых узлов.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TreePanel(ctk.CTkFrame):
    """Древовидный каталог на основе Treeview."""

    def __init__(self, master, on_select=None, font_family="Arial", font_size=12, **kwargs):
        super().__init__(master, **kwargs)

        self.on_select = on_select
        self.font_family = font_family
        self.font_size = font_size

        self._history = []
        self._current_path = None
        self._expanded_nodes = set()
        self._tree_data = []

        # Стиль
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                       background="#2b2b2b",
                       foreground="white",
                       fieldbackground="#2b2b2b",
                       borderwidth=0,
                       font=(font_family, font_size - 1))
        style.map("Treeview",
                 background=[("selected", "#4a4a4a")],
                 foreground=[("selected", "white")])

        # Верхняя панель
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=22)
        top_bar.pack(fill="x", pady=0)
        top_bar.pack_propagate(False)

        ctk.CTkLabel(
            top_bar, text="📁",
            font=ctk.CTkFont(family=font_family, size=font_size, weight="bold")
        ).pack(side="left", padx=(2, 0))

        self.btn_back = ctk.CTkButton(
            top_bar, text="←", command=self._navigate_back,
            width=22, height=18,
            font=ctk.CTkFont(family=font_family, size=font_size-3),
            fg_color="transparent", border_width=1, state="disabled"
        )
        self.btn_back.pack(side="right", padx=1)

        self.btn_up = ctk.CTkButton(
            top_bar, text="⬆", command=self._navigate_up,
            width=22, height=18,
            font=ctk.CTkFont(family=font_family, size=font_size-3),
            fg_color="transparent", border_width=1, state="disabled"
        )
        self.btn_up.pack(side="right", padx=1)

        ctk.CTkButton(
            top_bar, text="📋", command=self._show_all,
            width=22, height=18,
            font=ctk.CTkFont(family=font_family, size=font_size-3),
            fg_color="transparent", border_width=1
        ).pack(side="right", padx=1)

        ctk.CTkButton(
            top_bar, text="⊟", command=self._collapse_all,
            width=22, height=18,
            font=ctk.CTkFont(family=font_family, size=font_size-3),
            fg_color="transparent", border_width=1
        ).pack(side="right", padx=1)

        ctk.CTkButton(
            top_bar, text="⊞", command=self._expand_all,
            width=22, height=18,
            font=ctk.CTkFont(family=font_family, size=font_size-3),
            fg_color="transparent", border_width=1
        ).pack(side="right", padx=1)

        # Treeview
        tree_container = ctk.CTkFrame(self, fg_color="transparent")
        tree_container.pack(fill="both", expand=True, pady=0)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_container,
            columns=(),
            show="tree",
            selectmode="browse"
        )
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ctk.CTkScrollbar(
            tree_container,
            orientation="vertical",
            command=self.tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Теги цветов
        self.tree.tag_configure("empty_folder", foreground="#888888")
        self.tree.tag_configure("archive", foreground="#FF9800")
        self.tree.tag_configure("broken", foreground="#FF6B6B")
        self.tree.tag_configure("folder", foreground="#4FC3F7")
        self.tree.tag_configure("file", foreground="white")

        # События (только выбор)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Заглушка
        self._placeholder = self.tree.insert("", "end", text="Выполните сканирование...", tags=("placeholder",))
        self.tree.tag_configure("placeholder", foreground="gray")

    # ============================================================
    # НАВИГАЦИЯ
    # ============================================================

    def _show_all(self):
        self._current_path = None
        self._update_nav_buttons()
        if self.on_select:
            self.on_select(None)

    def _navigate_up(self):
        if self._current_path:
            parent = str(Path(self._current_path).parent)
            if parent == '.':
                parent = None
            self._history.append(self._current_path)
            self._current_path = parent
            self._update_nav_buttons()
            if self.on_select:
                self.on_select(self._current_path)

    def _navigate_back(self):
        if self._history:
            prev = self._history.pop()
            self._current_path = prev
            self._update_nav_buttons()
            if self.on_select:
                self.on_select(self._current_path)

    def _update_nav_buttons(self):
        self.btn_up.configure(state="normal" if self._current_path else "disabled")
        self.btn_back.configure(state="normal" if self._history else "disabled")

    # ============================================================
    # РАЗВЕРНУТЬ / СВЕРНУТЬ ВСЁ
    # ============================================================

    def _expand_all(self):
        """Разворачивает все узлы."""
        for item in self.tree.get_children():
            self._expand_recursive(item)
        self._expanded_nodes = set()  # очищаем, т.к. все открыты

    def _expand_recursive(self, item):
        self.tree.item(item, open=True)
        for child in self.tree.get_children(item):
            self._expand_recursive(child)

    def _collapse_all(self):
        """Сворачивает все узлы."""
        for item in self.tree.get_children():
            self._collapse_recursive(item)
        self._expanded_nodes.clear()

    def _collapse_recursive(self, item):
        self.tree.item(item, open=False)
        for child in self.tree.get_children(item):
            self._collapse_recursive(child)

    # ============================================================
    # СОБЫТИЯ ДЕРЕВА
    # ============================================================

    def _on_tree_select(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        item = selection[0]
        values = self.tree.item(item, "values")
        if not values or len(values) < 2:
            return
        path, is_dir = values[0], values[1]
        if is_dir:
            if self._current_path and self._current_path != path:
                self._history.append(self._current_path)
            self._current_path = path
            self._update_nav_buttons()
        if self.on_select:
            self.on_select(path)

    # ============================================================
    # ПОСТРОЕНИЕ ДЕРЕВА
    # ============================================================

    def build_tree(self, tree_data):
        self._tree_data = tree_data
        if self._placeholder:
            self.tree.delete(self._placeholder)
            self._placeholder = None

        # Полная очистка и перестроение
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not tree_data:
            self._placeholder = self.tree.insert("", "end", text="Нет вложенных папок", tags=("placeholder",))
            return

        # Строим заново
        for item in tree_data:
            self._add_tree_item("", item)

        # Восстанавливаем открытые узлы (которые были до перестроения)
        self._restore_expanded()

    def _add_tree_item(self, parent, item):
        is_dir = item.get('is_dir', False)
        name = item.get('name', 'Без имени')
        path = item.get('path', '')
        children = item.get('children', [])
        file_count = item.get('file_count', 0)

        if is_dir:
            text = f"📁 {name} ({file_count})" if file_count > 0 else f"📁 {name}"
            tags = ("folder",) if file_count > 0 else ("empty_folder",)
        else:
            text = name
            if "📦" in name:
                tags = ("archive",)
            elif "⚠" in name:
                tags = ("broken",)
            else:
                tags = ("file",)

        # При первоначальном построении не открываем ничего (откроется позже)
        node = self.tree.insert(parent, "end", text=text, values=(path, is_dir), open=False, tags=tags)

        for child in children:
            self._add_tree_item(node, child)

    def _restore_expanded(self):
        """Восстанавливает открытые узлы из _expanded_nodes."""
        for item in self.tree.get_children():
            self._restore_expanded_recursive(item)

    def _restore_expanded_recursive(self, item):
        values = self.tree.item(item, "values")
        if values and len(values) >= 2:
            path = values[0]
            if path in self._expanded_nodes:
                self.tree.item(item, open=True)
        for child in self.tree.get_children(item):
            self._restore_expanded_recursive(child)
