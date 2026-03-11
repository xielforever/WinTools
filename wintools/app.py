from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Type

from wintools.base import BaseModule
from wintools.module_registry import get_module_registry


class WinToolsApp:
    # 统一色彩令牌，便于后续模块复用。
    COLOR_BG = "#f3f6fb"
    COLOR_SURFACE = "#ffffff"
    COLOR_PRIMARY = "#165DFF"
    COLOR_PRIMARY_DARK = "#0E42B3"
    COLOR_TEXT = "#0F172A"
    COLOR_MUTED = "#475569"
    COLOR_BORDER = "#D7E0EF"
    COLOR_SUCCESS = "#16A34A"
    COLOR_WARNING = "#D97706"
    COLOR_ERROR = "#DC2626"

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("WinTools")
        self.root.geometry("1120x720")
        self.root.minsize(940, 620)

        self.registry: Dict[str, Type[BaseModule]] = get_module_registry()
        self.current_module: Optional[BaseModule] = None
        self.current_module_name: Optional[str] = None

        self.module_desc_var = tk.StringVar(value="")
        self.module_count_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="● 就绪")

        self._configure_styles()
        self._build_ui()
        self._load_default_module()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

        self.root.configure(bg=self.COLOR_BG)

        style.configure("App.TFrame", background=self.COLOR_BG)
        style.configure("Card.TFrame", background=self.COLOR_SURFACE, borderwidth=1, relief="solid")
        style.configure("Content.TFrame", background=self.COLOR_SURFACE, borderwidth=1, relief="solid")

        style.configure(
            "HeaderTitle.TLabel",
            background=self.COLOR_PRIMARY,
            foreground="#FFFFFF",
            font=("Microsoft YaHei UI", 20, "bold"),
        )
        style.configure(
            "HeaderSub.TLabel",
            background=self.COLOR_PRIMARY,
            foreground="#DBEAFE",
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "SectionTitle.TLabel",
            background=self.COLOR_SURFACE,
            foreground=self.COLOR_TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Body.TLabel",
            background=self.COLOR_SURFACE,
            foreground=self.COLOR_MUTED,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "Pill.TLabel",
            background="#E8F0FF",
            foreground=self.COLOR_PRIMARY_DARK,
            font=("Microsoft YaHei UI", 9, "bold"),
            padding=(10, 4),
        )

    def _build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        main = ttk.Frame(self.root, style="App.TFrame", padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        main.rowconfigure(2, weight=1)
        main.columnconfigure(1, weight=1)

        self._build_header(main)
        self._build_highlight_strip(main)

        left_panel = ttk.Frame(main, style="App.TFrame", padding=(0, 0, 12, 0))
        left_panel.grid(row=2, column=0, sticky="nsew")
        left_panel.rowconfigure(1, weight=1)
        left_panel.columnconfigure(0, weight=1)

        ttk.Label(left_panel, text="★ 模块导航", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(2, 8))

        nav_card = ttk.Frame(left_panel, style="Card.TFrame", padding=10)
        nav_card.grid(row=1, column=0, sticky="nsew")
        nav_card.rowconfigure(0, weight=1)
        nav_card.columnconfigure(0, weight=1)

        self.nav_list = tk.Listbox(
            nav_card,
            width=24,
            height=16,
            exportselection=False,
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            font=("Microsoft YaHei UI", 10),
            bg=self.COLOR_SURFACE,
            fg=self.COLOR_TEXT,
            selectbackground=self.COLOR_PRIMARY,
            selectforeground="#FFFFFF",
        )
        self.nav_list.grid(row=0, column=0, sticky="nsew")
        self.nav_list.bind("<<ListboxSelect>>", self._on_module_select)

        info_card = ttk.Frame(left_panel, style="Card.TFrame", padding=12)
        info_card.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        info_card.columnconfigure(0, weight=1)

        ttk.Label(info_card, text="★ 工具介绍", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(info_card, textvariable=self.module_count_var, style="Body.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 8))
        ttk.Label(
            info_card,
            textvariable=self.module_desc_var,
            justify="left",
            wraplength=235,
            style="Body.TLabel",
        ).grid(row=2, column=0, sticky="nw")

        self.content_frame = ttk.Frame(main, style="Content.TFrame", padding=14)
        self.content_frame.grid(row=2, column=1, sticky="nsew")
        self.content_frame.rowconfigure(0, weight=1)
        self.content_frame.columnconfigure(0, weight=1)

        self._build_status_bar()

        for module_name in self.registry:
            self.nav_list.insert(tk.END, module_name)

        self.module_count_var.set(f"已接入 {len(self.registry)} 个工具模块")

    def _build_header(self, parent: ttk.Frame) -> None:
        header = tk.Frame(parent, bg=self.COLOR_PRIMARY, bd=0, highlightthickness=1, highlightbackground="#6EA8FE")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        left = tk.Frame(header, bg=self.COLOR_PRIMARY)
        left.grid(row=0, column=0, sticky="w", padx=16, pady=12)

        tk.Label(
            left,
            text="★ WinTools 工具集",
            bg=self.COLOR_PRIMARY,
            fg="#FFFFFF",
            font=("Microsoft YaHei UI", 20, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            left,
            text="为 Windows 打造的轻量工具箱，支持模块化扩展。",
            bg=self.COLOR_PRIMARY,
            fg="#DBEAFE",
            font=("Microsoft YaHei UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        right = tk.Frame(header, bg="#EAF2FF", highlightthickness=1, highlightbackground="#C8DDFC")
        right.grid(row=0, column=1, sticky="e", padx=14, pady=10)

        tk.Label(
            right,
            text="★ 首页\n★ 欢迎使用",
            justify="right",
            bg="#EAF2FF",
            fg=self.COLOR_PRIMARY_DARK,
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=12,
            pady=6,
        ).pack()

    def _build_highlight_strip(self, parent: ttk.Frame) -> None:
        strip = ttk.Frame(parent, style="Card.TFrame", padding=(10, 8))
        strip.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 12))

        ttk.Label(strip, text="★ 非阻塞扫描", style="Pill.TLabel").pack(side="left")
        ttk.Label(strip, text="★ 历史趋势分析", style="Pill.TLabel").pack(side="left", padx=8)
        ttk.Label(strip, text="★ 多标签结果集", style="Pill.TLabel").pack(side="left")

    def _build_status_bar(self) -> None:
        self.status_container = tk.Frame(
            self.root,
            bg="#ECFDF3",
            highlightthickness=1,
            highlightbackground="#BBF7D0",
        )
        self.status_container.grid(row=1, column=0, sticky="ew")

        self.status_label = tk.Label(
            self.status_container,
            textvariable=self.status_var,
            anchor="w",
            bg="#ECFDF3",
            fg="#166534",
            font=("Microsoft YaHei UI", 9),
            padx=10,
            pady=4,
        )
        self.status_label.pack(fill="x")

    def _update_status_style(self, text: str) -> None:
        lowered = text.lower()
        bg = "#ECFDF3"
        border = "#BBF7D0"
        fg = "#166534"

        if any(token in lowered for token in ["扫描中", "处理中", "正在", "停止"]):
            bg = "#FFF7ED"
            border = "#FED7AA"
            fg = "#9A3412"
        elif any(token in lowered for token in ["失败", "异常", "错误", "无效", "不存在"]):
            bg = "#FEF2F2"
            border = "#FECACA"
            fg = "#991B1B"

        self.status_container.configure(bg=bg, highlightbackground=border)
        self.status_label.configure(bg=bg, fg=fg)

    def _load_default_module(self) -> None:
        if self.nav_list.size() == 0:
            self.set_status("未发现可用模块")
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
            self.set_status(f"模块不存在: {module_name}")
            return

        # 点击空白区域或重复选择当前模块时，不重复卸载/挂载。
        if self.current_module is not None and self.current_module_name == module_name:
            return

        if self.current_module is not None:
            self.current_module.unmount()

        for child in self.content_frame.winfo_children():
            child.destroy()

        self.current_module = module_cls()
        self.current_module_name = module_name
        self.current_module.mount(self.content_frame, self.set_status)

        self.module_desc_var.set(module_cls.description or "暂无说明")
        self.set_status(f"已切换到模块: {module_name}")

    def set_status(self, text: str) -> None:
        self.status_var.set(f"● {text}")
        self._update_status_style(text)

    def run(self) -> None:
        self.root.mainloop()