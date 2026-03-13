from __future__ import annotations

import json
import os
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from wintools import __version__
from wintools.base import BaseModule
from wintools.module_registry import ModuleMeta, get_module_catalog, sort_module_catalog
from wintools.updater.service import (
    UpdateError,
    UpdateInfo,
    check_for_update,
    download_update,
    get_app_dir,
    is_onedir_runtime,
    launch_updater,
)


class WinToolsApp:
    # 伪玻璃主题：使用浅色叠层 + 高光边框模拟玻璃感。
    COLOR_BG = "#E7EEFF"
    COLOR_SURFACE = "#FFFFFF"
    COLOR_GLASS = "#F5F8FF"
    COLOR_GLASS_SOFT = "#F9FBFF"
    COLOR_GLASS_EDGE = "#C6D8FF"
    COLOR_PRIMARY = "#165DFF"
    COLOR_PRIMARY_DARK = "#0E42B3"
    COLOR_TEXT = "#0B1220"
    COLOR_MUTED = "#334155"
    COLOR_BORDER = "#D7E0EF"
    COLOR_SUCCESS = "#16A34A"
    COLOR_WARNING = "#D97706"
    COLOR_ERROR = "#DC2626"

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"WinTools v{__version__}")
        self.root.geometry("1120x720")
        self.root.minsize(940, 620)
        self._apply_window_glass_effect()

        self.module_catalog: list[ModuleMeta] = sort_module_catalog(get_module_catalog())
        self.module_node_map: dict[str, ModuleMeta] = {}
        self.module_id_to_node: dict[str, str] = {}
        self.category_nodes: dict[str, str] = {}
        self.current_module: Optional[BaseModule] = None
        self.current_module_name: Optional[str] = None
        self.ui_state_root: dict[str, object] = self._load_ui_state_root()
        self.nav_state: dict[str, object] = self._load_nav_state()
        self.updater_state: dict[str, object] = self._load_updater_state()

        self.module_desc_var = tk.StringVar(value="")
        self.module_count_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="● 就绪")
        self.module_title_var = tk.StringVar(value="请选择模块")
        self.module_desc_text: Optional[tk.Label] = None
        self.main_pane: Optional[tk.PanedWindow] = None
        self.module_info_card: Optional[ttk.Frame] = None
        self.nav_tree: Optional[ttk.Treeview] = None
        self.check_update_btn: Optional[tk.Button] = None
        self.update_busy = False

        self._configure_styles()
        self._build_ui()
        self._load_default_module()
        self.root.after(1200, lambda: self._start_update_check(manual=False))
        self.root.bind("<Configure>", self._on_window_resize)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

        self.root.configure(bg=self.COLOR_BG)

        style.configure("App.TFrame", background=self.COLOR_BG)
        style.configure("Card.TFrame", background=self.COLOR_GLASS, borderwidth=1, relief="solid")
        style.configure("Content.TFrame", background=self.COLOR_SURFACE, borderwidth=1, relief="solid")
        style.configure("ToolBar.TFrame", background=self.COLOR_GLASS_SOFT, borderwidth=1, relief="solid")
        style.configure("Soft.TFrame", background=self.COLOR_GLASS_SOFT, borderwidth=1, relief="solid")

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
            background=self.COLOR_GLASS_SOFT,
            foreground=self.COLOR_TEXT,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Body.TLabel",
            background=self.COLOR_GLASS_SOFT,
            foreground=self.COLOR_MUTED,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.COLOR_GLASS_SOFT,
            foreground="#526277",
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "Pill.TLabel",
            background="#DCE7FF",
            foreground=self.COLOR_PRIMARY_DARK,
            font=("Microsoft YaHei UI", 9, "bold"),
            padding=(10, 4),
        )
        style.configure("TNotebook", background=self.COLOR_SURFACE, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        main = ttk.Frame(self.root, style="App.TFrame", padding=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.rowconfigure(2, weight=1)
        main.columnconfigure(0, weight=1)

        self._build_header(main)
        self._build_highlight_strip(main)

        body_host = ttk.Frame(main, style="App.TFrame")
        body_host.grid(row=2, column=0, sticky="nsew")
        body_host.rowconfigure(0, weight=1)
        body_host.columnconfigure(0, weight=1)

        pane = tk.PanedWindow(
            body_host,
            orient="horizontal",
            sashwidth=6,
            sashrelief="flat",
            borderwidth=0,
            bg=self.COLOR_BG,
        )
        pane.grid(row=0, column=0, sticky="nsew")
        self.main_pane = pane

        left_panel = ttk.Frame(pane, style="App.TFrame", padding=(0, 0, 10, 0))
        left_panel.rowconfigure(1, weight=1)
        left_panel.rowconfigure(2, weight=0)
        left_panel.columnconfigure(0, weight=1)

        ttk.Label(left_panel, text="模块导航", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        nav_card = ttk.Frame(left_panel, style="Card.TFrame", padding=8)
        nav_card.grid(row=1, column=0, sticky="nsew")
        nav_card.rowconfigure(0, weight=1)
        nav_card.columnconfigure(0, weight=1)

        self.nav_tree = ttk.Treeview(nav_card, show="tree", selectmode="browse")
        self.nav_tree.grid(row=0, column=0, sticky="nsew")
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_module_select)
        self.nav_tree.bind("<<TreeviewOpen>>", self._on_nav_toggle)
        self.nav_tree.bind("<<TreeviewClose>>", self._on_nav_toggle)
        self._build_nav_tree()

        module_count_label = ttk.Label(left_panel, textvariable=self.module_count_var, style="Muted.TLabel")
        module_count_label.grid(row=2, column=0, sticky="w", pady=(8, 0))

        content_shell = ttk.Frame(pane, style="App.TFrame", padding=0)
        content_shell.rowconfigure(0, weight=1)
        content_shell.columnconfigure(0, weight=1)

        pane.add(left_panel, minsize=240, width=270, stretch="never")
        pane.add(content_shell, minsize=520, stretch="always")
        self.root.after(0, self._init_main_pane)

        self.content_frame = ttk.Frame(content_shell, style="App.TFrame", padding=(0, 0, 0, 0))
        self.content_frame.grid(row=0, column=0, sticky="nsew", padx=(2, 0))
        self.content_frame.rowconfigure(1, weight=1)
        self.content_frame.columnconfigure(0, weight=1)

        module_info_card = ttk.Frame(self.content_frame, style="Soft.TFrame", padding=(14, 10), height=96)
        module_info_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        module_info_card.grid_propagate(False)
        module_info_card.columnconfigure(0, weight=1)
        module_info_card.rowconfigure(1, weight=1)
        self.module_info_card = module_info_card

        ttk.Label(module_info_card, textvariable=self.module_title_var, style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.module_desc_text = tk.Label(
            module_info_card,
            textvariable=self.module_desc_var,
            justify="left",
            anchor="nw",
            bg=self.COLOR_GLASS_SOFT,
            fg=self.COLOR_MUTED,
            font=("Microsoft YaHei UI", 9),
            wraplength=760,
        )
        self.module_desc_text.grid(row=1, column=0, sticky="nsew", pady=(4, 0))

        self.module_container = ttk.Frame(self.content_frame, style="Content.TFrame", padding=8)
        self.module_container.grid(row=1, column=0, sticky="nsew")
        self.module_container.rowconfigure(0, weight=1)
        self.module_container.columnconfigure(0, weight=1)

        self._build_status_bar()

        available_count = sum(1 for x in self.module_catalog if x.status in ("available", "beta"))
        planned_count = sum(1 for x in self.module_catalog if x.status == "planned")
        self.module_count_var.set(f"已接入 {available_count} 个可用模块，规划中 {planned_count} 个")

    def _build_nav_tree(self) -> None:
        if self.nav_tree is None:
            return

        self.module_node_map.clear()
        self.module_id_to_node.clear()
        self.category_nodes.clear()
        self.nav_tree.delete(*self.nav_tree.get_children(""))

        categories = ["文件管理", "网络工具", "安全工具", "系统维护", "效率辅助"]
        expanded = set(self.nav_state.get("expanded_categories", categories))  # type: ignore[arg-type]

        for category in categories:
            node = self.nav_tree.insert("", tk.END, text=category, open=(category in expanded))
            self.category_nodes[category] = node

        for item in self.module_catalog:
            parent = self.category_nodes.get(item.category)
            if parent is None:
                parent = self.nav_tree.insert("", tk.END, text=item.category, open=True)
                self.category_nodes[item.category] = parent
            node_id = self.nav_tree.insert(parent, tk.END, text=self._format_nav_text(item))
            self.module_node_map[node_id] = item
            self.module_id_to_node[item.id] = node_id

    def _format_nav_text(self, item: ModuleMeta) -> str:
        if item.status == "available":
            badge = "[可用]"
        elif item.status == "beta":
            badge = "[Beta]"
        else:
            badge = f"[规划-{item.priority}]"
        return f"{item.name} {badge}"

    def _build_header(self, parent: ttk.Frame) -> None:
        header = tk.Frame(parent, bg=self.COLOR_PRIMARY, bd=0, highlightthickness=1, highlightbackground="#6B92FF")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        left = tk.Frame(header, bg=self.COLOR_PRIMARY)
        left.grid(row=0, column=0, sticky="w", padx=16, pady=10)

        tk.Label(
            left,
            text="WinTools 工具集",
            bg=self.COLOR_PRIMARY,
            fg="#FFFFFF",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(
            left,
            text="为 Windows 打造的轻量工具箱，支持模块化扩展。",
            bg=self.COLOR_PRIMARY,
            fg="#DBEAFE",
            font=("Microsoft YaHei UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        right = tk.Frame(header, bg="#EAF2FF", highlightthickness=1, highlightbackground="#D9E6FF")
        right.grid(row=0, column=1, sticky="e", padx=14, pady=10)

        tk.Label(
            right,
            text=f"v{__version__}\n欢迎使用",
            justify="right",
            bg="#EAF2FF",
            fg=self.COLOR_PRIMARY_DARK,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=12,
            pady=5,
        ).pack(fill="x")

        self.check_update_btn = tk.Button(
            right,
            text="检查更新",
            bg="#DCE7FF",
            fg=self.COLOR_PRIMARY_DARK,
            activebackground="#C8DBFF",
            activeforeground=self.COLOR_PRIMARY_DARK,
            relief="flat",
            borderwidth=0,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=3,
            cursor="hand2",
            command=lambda: self._start_update_check(manual=True),
        )
        self.check_update_btn.pack(fill="x", padx=8, pady=(0, 6))

    def _build_highlight_strip(self, parent: ttk.Frame) -> None:
        strip = ttk.Frame(parent, style="Card.TFrame", padding=(10, 7))
        strip.grid(row=1, column=0, sticky="ew", pady=(8, 10))

        ttk.Label(strip, text="非阻塞扫描", style="Pill.TLabel").pack(side="left")
        ttk.Label(strip, text="历史趋势分析", style="Pill.TLabel").pack(side="left", padx=8)
        ttk.Label(strip, text="多标签结果集", style="Pill.TLabel").pack(side="left")
        ttk.Label(strip, text="可拖拽调整左右布局", style="Muted.TLabel").pack(side="right")

    def _build_status_bar(self) -> None:
        self.status_container = tk.Frame(
            self.root,
            bg="#EDF5FF",
            highlightthickness=1,
            highlightbackground=self.COLOR_GLASS_EDGE,
        )
        self.status_container.grid(row=1, column=0, sticky="ew")

        self.status_label = tk.Label(
            self.status_container,
            textvariable=self.status_var,
            anchor="w",
            bg="#EDF5FF",
            fg="#1E3A5F",
            font=("Microsoft YaHei UI", 9),
            padx=10,
            pady=4,
        )
        self.status_label.pack(fill="x")

    def _update_status_style(self, text: str) -> None:
        lowered = text.lower()
        bg = "#EDF5FF"
        border = self.COLOR_GLASS_EDGE
        fg = "#1E3A5F"

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

    def _apply_window_glass_effect(self) -> None:
        try:
            # 伪玻璃：整体轻微透明，搭配浅色叠层与边框高光。
            self.root.attributes("-alpha", 0.985)
        except tk.TclError:
            pass

    def _load_default_module(self) -> None:
        if self.nav_tree is None:
            self.set_status("未发现可用模块")
            return

        if not self.module_node_map:
            self.set_status("未发现可用模块")
            return

        selected_id = self.nav_state.get("selected_module_id")
        target_node = self.module_id_to_node.get(str(selected_id)) if selected_id else None
        if target_node is None:
            target_node = next((n for n, m in self.module_node_map.items() if m.status in ("available", "beta")), None)
        if target_node is None:
            target_node = next(iter(self.module_node_map.keys()), None)
        if target_node is None:
            self.set_status("未发现可用模块")
            return

        self.nav_tree.selection_set(target_node)
        self.nav_tree.focus(target_node)
        self._switch_module(self.module_node_map[target_node])

    def _on_module_select(self, _event: tk.Event[tk.Misc]) -> None:
        if self.nav_tree is None:
            return

        selected = self.nav_tree.selection()
        if not selected:
            return
        node = selected[0]
        item = self.module_node_map.get(node)
        if item is None:
            return
        self._switch_module(item)

    def _switch_module(self, item: ModuleMeta) -> None:
        module_name = item.name

        # 鐐瑰嚮绌虹櫧鍖哄煙鎴栭噸澶嶉€夋嫨褰撳墠妯″潡鏃讹紝涓嶉噸澶嶅嵏杞?鎸傝浇銆?
        if self.current_module_name == module_name:
            return

        if self.current_module is not None:
            self.current_module.unmount()
            self.current_module = None

        for child in self.module_container.winfo_children():
            child.destroy()

        self.current_module_name = module_name
        if item.module_cls is not None and item.status in ("available", "beta"):
            self.current_module = item.module_cls()
            self.current_module.mount(self.module_container, self.set_status)
        else:
            self._render_planned_placeholder(item)

        self.module_title_var.set(module_name)
        self.module_desc_var.set(self._build_desc_for_item(item))
        if item.status == "planned":
            self.set_status(f"模块规划中: {module_name}（{item.priority}）")
        else:
            self.set_status(f"已切换到模块: {module_name}")
        self.nav_state["selected_module_id"] = item.id
        self._save_nav_state()

    def _build_desc_for_item(self, item: ModuleMeta) -> str:
        if item.status in ("available", "beta"):
            return item.description or "暂无说明"
        scenarios = "、".join(item.scenarios[:2]) if item.scenarios else "暂无典型场景"
        return f"目标能力：{item.description} 预计阶段：{item.priority} 典型场景：{scenarios}"

    def _render_planned_placeholder(self, item: ModuleMeta) -> None:
        wrap = ttk.Frame(self.module_container, style="ToolBar.TFrame", padding=16)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(3, weight=1)

        ttk.Label(wrap, text=f"{item.name}（规划中）", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(wrap, text=f"上线阶段：{item.priority}  |  状态：规划中", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(4, 8)
        )
        desc = item.description or "暂无说明"
        ttk.Label(wrap, text=desc, style="Body.TLabel", justify="left").grid(row=2, column=0, sticky="w")
        scenarios = "、".join(item.scenarios) if item.scenarios else "暂无典型场景"
        ttk.Label(wrap, text=f"典型场景：{scenarios}", style="Muted.TLabel", justify="left").grid(
            row=3, column=0, sticky="sw", pady=(10, 0)
        )

    def _on_nav_toggle(self, _event: tk.Event[tk.Misc]) -> None:
        if self.nav_tree is None:
            return
        expanded: list[str] = []
        for category, node in self.category_nodes.items():
            if bool(self.nav_tree.item(node, "open")):
                expanded.append(category)
        self.nav_state["expanded_categories"] = expanded
        self._save_nav_state()

    def _init_main_pane(self) -> None:
        if self.main_pane is None:
            return
        try:
            self.main_pane.sash_place(0, 280, 0)
        except tk.TclError:
            return

    def _on_window_resize(self, _event: tk.Event[tk.Misc]) -> None:
        if self.module_info_card is None:
            return
        if not self.root.winfo_exists() or not self.content_frame.winfo_exists():
            return
        content_h = self.content_frame.winfo_height()
        if content_h <= 0:
            return
        width = self.content_frame.winfo_width()
        if self.module_desc_text is not None:
            self.module_desc_text.configure(wraplength=max(320, width - 56))

        target_h = int(content_h * 0.16)
        target_h = max(88, min(128, target_h))
        self.module_info_card.configure(height=target_h)

    def _ui_state_path(self) -> Path:
        return get_app_dir() / "data" / "ui_state.json"

    def _start_update_check(self, manual: bool) -> None:
        if self.update_busy:
            if manual:
                self.set_status("正在检查更新…")
            return
        self.update_busy = True
        self._set_update_button_busy(True)
        self.set_status("正在检查更新…")
        threading.Thread(target=self._check_update_worker, args=(manual,), daemon=True).start()

    def _check_update_worker(self, manual: bool) -> None:
        supported = is_onedir_runtime()
        skip_version = str(self.updater_state.get("skip_version", "")).strip()
        checked_at = datetime.now().isoformat(timespec="seconds")
        info: Optional[UpdateInfo] = None
        error_message = ""
        result = "no-update"
        try:
            if supported:
                info = check_for_update(
                    current_version=__version__,
                    skip_version=None if manual else skip_version,
                )
                result = "update-found" if info is not None else "no-update"
            else:
                result = "unsupported"
        except UpdateError as exc:
            error_message = str(exc)
            result = "error"

        self.root.after(
            0,
            lambda: self._on_update_check_done(
                manual=manual,
                supported=supported,
                checked_at=checked_at,
                result=result,
                info=info,
                error_message=error_message,
            ),
        )

    def _on_update_check_done(
        self,
        *,
        manual: bool,
        supported: bool,
        checked_at: str,
        result: str,
        info: Optional[UpdateInfo],
        error_message: str,
    ) -> None:
        self.update_busy = False
        self._set_update_button_busy(False)
        self.updater_state["last_check_at"] = checked_at
        self.updater_state["last_result"] = result
        self._save_updater_state()

        if result == "unsupported":
            if manual:
                self.set_status("当前运行形态不支持自动更新（仅 OneDir 支持）")
                messagebox.showinfo("自动更新", "当前仅 OneDir 版本支持自动更新。")
            else:
                self._clear_update_check_status()
            return
        if result == "error":
            self.set_status("更新检查失败")
            if manual:
                messagebox.showerror("自动更新", error_message or "检查更新失败")
            return
        if info is None:
            if manual:
                self.set_status("当前已是最新版本")
                messagebox.showinfo("自动更新", "当前已是最新版本。")
            else:
                self._clear_update_check_status()
            return

        self.set_status(f"发现新版本 {info.version_tag}")
        action = self._show_update_dialog(info)
        if action == "skip":
            self.updater_state["skip_version"] = info.version_tag
            self.updater_state["last_result"] = "skip-version"
            self._save_updater_state()
            self.set_status(f"已跳过版本 {info.version_tag}")
            return
        if action == "update":
            self._apply_update_async(info)

    def _apply_update_async(self, info: UpdateInfo) -> None:
        if self.update_busy:
            return
        self.update_busy = True
        self._set_update_button_busy(True)
        self.set_status("正在下载更新包…")
        threading.Thread(target=self._apply_update_worker, args=(info,), daemon=True).start()

    def _apply_update_worker(self, info: UpdateInfo) -> None:
        try:
            app_dir = get_app_dir()
            staged = download_update(info, app_dir=app_dir)
            launch_updater(staged, current_pid=os.getpid(), app_dir=app_dir)
        except UpdateError as exc:
            self.root.after(0, lambda: self._on_update_apply_failed(str(exc)))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._on_update_apply_failed(f"更新失败：{exc}"))
            return
        self.root.after(0, self._on_update_apply_started)

    def _on_update_apply_started(self) -> None:
        self.update_busy = False
        self._set_update_button_busy(False)
        self.set_status("更新已下载，正在应用…")
        self.updater_state["last_result"] = "apply-started"
        self._save_updater_state()
        messagebox.showinfo("自动更新", "更新已下载，程序将退出并完成替换。")
        self._on_close()

    def _on_update_apply_failed(self, message: str) -> None:
        self.update_busy = False
        self._set_update_button_busy(False)
        self.updater_state["last_result"] = "apply-failed"
        self._save_updater_state()
        self.set_status("更新失败，已回滚")
        messagebox.showerror("自动更新", message)

    def _show_update_dialog(self, info: UpdateInfo) -> str:
        dialog = tk.Toplevel(self.root)
        dialog.title("发现新版本")
        dialog.geometry("430x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        result = {"action": "later"}
        panel = ttk.Frame(dialog, padding=14)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)

        ttk.Label(panel, text=f"当前版本：v{__version__}", style="Body.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text=f"最新版本：{info.version_tag}", style="SectionTitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(4, 2)
        )
        ttk.Label(panel, text="是否现在更新？", style="Body.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 10))

        link_btn = ttk.Button(
            panel,
            text="查看更新说明",
            command=lambda: webbrowser.open(info.release_url) if info.release_url else None,
        )
        link_btn.grid(row=3, column=0, sticky="w")

        btns = ttk.Frame(panel)
        btns.grid(row=4, column=0, sticky="e", pady=(16, 0))

        def choose(action: str) -> None:
            result["action"] = action
            dialog.destroy()

        ttk.Button(btns, text="稍后提醒", command=lambda: choose("later")).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btns, text="跳过此版本", command=lambda: choose("skip")).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(btns, text="立即更新", command=lambda: choose("update")).grid(row=0, column=2)

        dialog.wait_window()
        return str(result["action"])

    def _set_update_button_busy(self, busy: bool) -> None:
        if self.check_update_btn is None:
            return
        self.check_update_btn.configure(
            state="disabled" if busy else "normal",
            text="检查中…" if busy else "检查更新",
        )

    def _clear_update_check_status(self) -> None:
        if "正在检查更新" in self.status_var.get():
            self.set_status("就绪")

    def _load_ui_state_root(self) -> dict[str, object]:
        path = self._ui_state_path()
        try:
            if not path.exists():
                return {}
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            return {}
        return {}

    def _save_ui_state_root(self) -> None:
        path = self._ui_state_path()
        try:
            merged: dict[str, object] = {}
            if path.exists():
                current = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    merged.update(current)
            merged.update(self.ui_state_root)
            self.ui_state_root = merged
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_nav_state(self) -> dict[str, object]:
        default_state: dict[str, object] = {
            "expanded_categories": ["文件管理", "网络工具", "安全工具", "系统维护", "效率辅助"],
            "selected_module_id": "dir-size",
        }
        payload = self.ui_state_root
        state = default_state.copy()
        node = payload.get("app_nav")
        if isinstance(node, dict):
            state.update(node)
        else:
            # Backward compatibility with old flat keys.
            for key in ("expanded_categories", "selected_module_id"):
                if key in payload:
                    state[key] = payload[key]
        return state

    def _load_updater_state(self) -> dict[str, object]:
        default_state: dict[str, object] = {
            "last_check_at": "",
            "skip_version": "",
            "last_result": "",
        }
        node = self.ui_state_root.get("updater")
        state = default_state.copy()
        if isinstance(node, dict):
            state.update(node)
        return state

    def _save_nav_state(self) -> None:
        self.ui_state_root["app_nav"] = dict(self.nav_state)
        # Keep old keys for compatibility with existing files.
        self.ui_state_root["expanded_categories"] = self.nav_state.get("expanded_categories", [])
        self.ui_state_root["selected_module_id"] = self.nav_state.get("selected_module_id", "")
        self._save_ui_state_root()

    def _save_updater_state(self) -> None:
        self.ui_state_root["updater"] = dict(self.updater_state)
        self._save_ui_state_root()

    def _on_close(self) -> None:
        self._save_nav_state()
        self._save_updater_state()
        self.root.destroy()

    def set_status(self, text: str) -> None:
        self.status_var.set(f"● {text}")
        self._update_status_style(text)

    def run(self) -> None:
        self.root.mainloop()


