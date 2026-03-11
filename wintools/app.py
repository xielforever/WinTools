from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Type

from wintools.base import BaseModule
from wintools.module_registry import get_module_registry


class WinToolsApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("WinTools")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)

        self.registry: Dict[str, Type[BaseModule]] = get_module_registry()
        self.current_module: Optional[BaseModule] = None
        self.current_module_name: Optional[str] = None
        self.module_desc_var = tk.StringVar(value="")

        self._build_ui()
        self._load_default_module()

    def _build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        nav_frame = ttk.Frame(main, padding=(0, 0, 10, 0))
        nav_frame.grid(row=0, column=0, sticky="nsew")
        nav_frame.rowconfigure(3, weight=1)

        ttk.Label(nav_frame, text="\u6a21\u5757\u5bfc\u822a", font=("Microsoft YaHei UI", 10, "bold")).grid(row=0, column=0, sticky="w")

        self.nav_list = tk.Listbox(nav_frame, width=24, height=16, exportselection=False)
        self.nav_list.grid(row=1, column=0, sticky="nsew", pady=(8, 10))
        self.nav_list.bind("<<ListboxSelect>>", self._on_module_select)

        ttk.Label(nav_frame, text="\u5de5\u5177\u4ecb\u7ecd", font=("Microsoft YaHei UI", 9, "bold")).grid(row=2, column=0, sticky="w")
        ttk.Label(
            nav_frame,
            textvariable=self.module_desc_var,
            wraplength=220,
            justify="left",
            foreground="#3a3a3a",
        ).grid(row=3, column=0, sticky="nw", pady=(6, 0))

        self.content_frame = ttk.Frame(main, relief="groove", padding=12)
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.rowconfigure(0, weight=1)
        self.content_frame.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="\u5c31\u7eea")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken", padding=(8, 4))
        status_bar.grid(row=1, column=0, sticky="ew")

        for module_name in self.registry:
            self.nav_list.insert(tk.END, module_name)

    def _load_default_module(self) -> None:
        if self.nav_list.size() == 0:
            self.set_status("\u672a\u53d1\u73b0\u53ef\u7528\u6a21\u5757")
            return
        self.nav_list.selection_set(0)
        self._switch_module(self.nav_list.get(0))

    def _on_module_select(self, _event: tk.Event[tk.Misc]) -> None:
        selected = self.nav_list.curselection()
        if not selected:
            return
        module_name = self.nav_list.get(selected[0])
        self._switch_module(module_name)

    def _switch_module(self, module_name: str) -> None:
        module_cls = self.registry.get(module_name)
        if module_cls is None:
            self.set_status(f"\u6a21\u5757\u4e0d\u5b58\u5728: {module_name}")
            return

        # Avoid remounting when user clicks blank area or re-selects the current module.
        if self.current_module is not None and self.current_module_name == module_name:
            return

        if self.current_module is not None:
            self.current_module.unmount()

        for child in self.content_frame.winfo_children():
            child.destroy()

        self.current_module = module_cls()
        self.current_module_name = module_name
        self.current_module.mount(self.content_frame, self.set_status)

        self.module_desc_var.set(module_cls.description or "\u6682\u65e0\u8bf4\u660e")
        self.set_status(f"\u5df2\u5207\u6362\u5230\u6a21\u5757: {module_name}")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def run(self) -> None:
        self.root.mainloop()