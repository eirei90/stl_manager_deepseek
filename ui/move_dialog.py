"""
Диалог выбора папки для перемещения файлов.
Показывает список перемещаемых файлов.
"""

import customtkinter as ctk

class MoveFileDialog(ctk.CTkToplevel):
    def __init__(self, master, folders: list, file_records: list):
        super().__init__(master)
        self.result = None
        self.folders = folders
        self.file_records = file_records
        self.selected_path = ""

        count = len(file_records)
        if count == 1:
            title = f"Переместить: {file_records[0][1][:40]}"
        else:
            title = f"Переместить {count} файлов"

        self.title(title)
        self.geometry("450x400")  # Уменьшена высота
        self.minsize(380, 300)
        self.resizable(True, True)

        # Список файлов (компактный, только если >1)
        row = 0
        if count > 1:
            ctk.CTkLabel(
                self, text=f"📄 Перемещаемые файлы ({count}):",
                font=ctk.CTkFont(size=11, weight="bold"),
                anchor="w"
            ).pack(fill="x", padx=15, pady=(8, 2))

            file_list = ctk.CTkScrollableFrame(self, height=60)  # Уменьшена высота
            file_list.pack(fill="x", padx=15, pady=(0, 5))

            for record in file_records[:5]:  # Показываем только 5
                name = record[1][:45]
                ctk.CTkLabel(
                    file_list,
                    text=f"  • {name}",
                    font=ctk.CTkFont(size=10),
                    anchor="w",
                    text_color="#CCCCCC"
                ).pack(fill="x", pady=0)

            if count > 5:
                ctk.CTkLabel(
                    file_list,
                    text=f"  ... и ещё {count - 5}",
                    font=ctk.CTkFont(size=9),
                    anchor="w",
                    text_color="#888888"
                ).pack(fill="x")

        # Куда переместить (компактно)
        ctk.CTkLabel(
            self, text="📁 Куда переместить:",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w"
        ).pack(fill="x", padx=15, pady=(8, 2))

        self.lbl_selected = ctk.CTkLabel(
            self, text="📂 Корень",
            font=ctk.CTkFont(size=11),
            text_color="#4FC3F7"
        )
        self.lbl_selected.pack(pady=1)

        # Список папок
        self.folder_frame = ctk.CTkScrollableFrame(self, height=180)
        self.folder_frame.pack(fill="both", expand=True, padx=15, pady=5)

        for path, display in folders:
            btn = ctk.CTkButton(
                self.folder_frame, text=display,
                command=lambda p=path, d=display: self._select_folder(p, d),
                font=ctk.CTkFont(size=11),
                fg_color="#2b5a2b" if path == "" else "transparent",
                border_width=1, height=28
            )
            btn.pack(fill="x", pady=1)

        # Кнопки
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=8)

        ctk.CTkButton(
            btn_frame, text="✅ Переместить",
            command=self._move,
            width=120, height=28,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2E7D32", hover_color="#1B5E20"
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="❌ Отмена",
            command=self._cancel,
            width=80, height=28,
            font=ctk.CTkFont(size=12),
            fg_color="#757575", hover_color="#616161"
        ).pack(side="left", padx=5)

        self.after(100, self.lift)

    def _select_folder(self, path, display):
        self.selected_path = path
        name = display.replace("📁 ", "").replace("📂 ", "")
        self.lbl_selected.configure(text=f"📁 {name}" if path else "📂 Корень")
        for w in self.folder_frame.winfo_children():
            if isinstance(w, ctk.CTkButton):
                w.configure(fg_color="#2b5a2b" if w.cget("text") == display else "transparent")

    def _move(self):
        self.result = self.selected_path
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
