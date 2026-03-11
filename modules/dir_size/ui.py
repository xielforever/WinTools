from __future__ import annotations

import os
import queue
import subprocess
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

from modules.dir_size.core import DirSizeResult, ScanCancelled, format_size, scan_directory_sizes
from modules.dir_size.storage import load_last_snapshot, save_scan_snapshot
from wintools.base import BaseModule, StatusCallback


class DirSizeModule(BaseModule):
    name = "\u76ee\u5f55\u5927\u5c0f\u7edf\u8ba1"
    description = (
        "\u4ec5\u5c55\u793a\u5f53\u524d\u5c42\u7ea7\uff08\u6839\u76ee\u5f55\u4e0e\u76f4\u63a5\u5b50\u76ee\u5f55\uff09\uff0c\u4f46\u6bcf\u4e2a\u76ee\u5f55\u5927\u5c0f\u6309\u9012\u5f52\u603b\u5927\u5c0f\u8ba1\u7b97\u3002"
        "\u652f\u6301\u540e\u53f0\u626b\u63cf\u3001\u4e2d\u9014\u505c\u6b62\uff0c\u5e76\u81ea\u52a8\u4fdd\u5b58\u6bcf\u6b21\u7ed3\u679c\u7528\u4e8e\u589e\u957f\u5206\u6790\u3002"
    )

    def __init__(self) -> None:
        self.set_status: Optional[StatusCallback] = None
        self.parent: Optional[ttk.Frame] = None
        self.path_var = tk.StringVar()
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.scanning = False

        self.scan_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        self.cancel_event = threading.Event()

        self.notebook: Optional[ttk.Notebook] = None
        self.scan_index = 0

        self.tree_menu: Optional[tk.Menu] = None
        self.tab_menu: Optional[tk.Menu] = None
        self.context_tree: Optional[ttk.Treeview] = None
        self.context_tab_id: Optional[str] = None

        self.active_scan_tab_id: Optional[str] = None
        self.active_scan_tree: Optional[ttk.Treeview] = None
        self.active_scan_title_base: Optional[str] = None

        # tab_id -> root folder path of this result page
        self.tab_root_paths: Dict[str, str] = {}
        # tab_id -> raw title text (without active marker)
        self.tab_titles: Dict[str, str] = {}

    def mount(self, parent: ttk.Frame, set_status: StatusCallback) -> None:
        self.parent = parent
        self.set_status = set_status
        self._build_ui(parent)

    def unmount(self) -> None:
        self.cancel_event.set()
        self.scanning = False
        if self.tree_menu is not None:
            self.tree_menu.destroy()
            self.tree_menu = None
        if self.tab_menu is not None:
            self.tab_menu.destroy()
            self.tab_menu = None

    def _build_ui(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        intro = ttk.Label(
            parent,
            text=(
                "\u529f\u80fd\u8bf4\u660e\uff1a\u9009\u62e9\u76ee\u5f55\u540e\u4ec5\u5c55\u793a\u5f53\u524d\u5c42\u7ea7\uff08\u6839\u76ee\u5f55\u53ca\u76f4\u63a5\u5b50\u76ee\u5f55\uff09\uff0c\u4f46\u5927\u5c0f\u6309\u9012\u5f52\u603b\u5927\u5c0f\u8ba1\u7b97\u3002\n"
                "\u6bcf\u6b21\u626b\u63cf\u4f1a\u65b0\u5efa\u4e00\u4e2a\u9009\u9879\u5361\u5e76\u5199\u5165 data/dir_size_history.db\uff0c\u4fbf\u4e8e\u540e\u7eed\u5bf9\u6bd4\u548c\u589e\u957f\u8d8b\u52bf\u5206\u6790\u3002"
            ),
            justify="left",
            foreground="#333333",
        )
        intro.grid(row=0, column=0, sticky="w", pady=(0, 8))

        control = ttk.Frame(parent)
        control.grid(row=1, column=0, sticky="ew")
        control.columnconfigure(1, weight=1)

        ttk.Label(control, text="\u76ee\u6807\u76ee\u5f55:").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        ttk.Entry(control, textvariable=self.path_var).grid(row=0, column=1, pady=6, sticky="ew")
        ttk.Button(control, text="\u9009\u62e9\u76ee\u5f55", command=self._choose_dir).grid(row=0, column=2, padx=8, pady=6)

        self.scan_btn = ttk.Button(control, text="\u5f00\u59cb\u626b\u63cf", command=self._start_scan)
        self.scan_btn.grid(row=0, column=3, padx=(0, 8), pady=6)

        self.stop_btn = ttk.Button(control, text="\u505c\u6b62\u626b\u63cf", command=self._stop_scan, state="disabled")
        self.stop_btn.grid(row=0, column=4, pady=6)

        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.notebook.bind("<Button-3>", self._on_tab_right_click)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.tree_menu = tk.Menu(parent, tearoff=0)
        self.tree_menu.add_command(label="\u6df1\u5165\u626b\u63cf\u6b64\u76ee\u5f55", command=self._scan_selected_row_dir)
        self.tree_menu.add_command(label="\u6253\u5f00\u6240\u5728\u4f4d\u7f6e", command=self._open_selected_row_location)

        self.tab_menu = tk.Menu(parent, tearoff=0)
        self.tab_menu.add_command(label="\u5173\u95ed\u5f53\u524d\u7ed3\u679c\u9875", command=self._close_current_tab)
        self.tab_menu.add_command(label="\u5173\u95ed\u5176\u4ed6\u7ed3\u679c\u9875", command=self._close_other_tabs)

    def _normalize_path(self, path: str) -> str:
        return str(Path(path).resolve()).lower()

    def _set_tab_raw_title(self, tab_id: str, raw_title: str) -> None:
        if self.notebook is None:
            return
        self.tab_titles[tab_id] = raw_title
        self._refresh_tab_highlight()

    def _refresh_tab_highlight(self) -> None:
        if self.notebook is None:
            return

        selected = self.notebook.select()
        for tab_id in self.notebook.tabs():
            raw = self.tab_titles.get(tab_id, self.notebook.tab(tab_id, "text"))
            # Active tab gets a visual marker for quick recognition.
            text = f"\u25cf {raw}" if tab_id == selected else raw
            self.notebook.tab(tab_id, text=text)

    def _on_tab_changed(self, _event: tk.Event[tk.Misc]) -> None:
        self._refresh_tab_highlight()

    def _create_result_tree(self, container: ttk.Frame) -> ttk.Treeview:
        columns = ("path", "size", "size_bytes")
        tree = ttk.Treeview(container, columns=columns, show="headings")
        tree.heading("path", text="\u76ee\u5f55\u8def\u5f84")
        tree.heading("size", text="\u5927\u5c0f")
        tree.heading("size_bytes", text="\u5b57\u8282\u6570")

        tree.column("path", width=640, anchor="w")
        tree.column("size", width=130, anchor="e")
        tree.column("size_bytes", width=140, anchor="e")

        # Highlight current scanned root folder row in each result page.
        tree.tag_configure("current_dir", background="#fff2cc", foreground="#111111")

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        tree.bind("<Button-3>", self._on_tree_right_click)
        return tree

    def _create_pending_tab(self, root_path: str) -> None:
        if self.notebook is None:
            return

        tab = ttk.Frame(self.notebook)
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)

        tree = self._create_result_tree(tab)
        tree.insert("", tk.END, values=(root_path, "\u626b\u63cf\u4e2d...", "-"), tags=("current_dir",))

        self.scan_index += 1
        folder_name = root_path.rstrip("\\/").split("\\")[-1] or root_path
        time_tag = datetime.now().strftime("%H:%M:%S")
        base_title = f"{self.scan_index}. {folder_name} [{time_tag}]"

        self.notebook.add(tab, text="")
        self.notebook.select(tab)

        tab_id = str(tab)
        self.active_scan_tab_id = tab_id
        self.active_scan_tree = tree
        self.active_scan_title_base = base_title
        self.tab_root_paths[tab_id] = root_path

        self._set_tab_raw_title(tab_id, f"{base_title} (\u626b\u63cf\u4e2d)")

    def _finalize_active_scan_tab(self, results: list[DirSizeResult]) -> None:
        if self.notebook is None:
            return
        if self.active_scan_tab_id is None or self.active_scan_tree is None:
            return
        if self.active_scan_tab_id not in self.notebook.tabs():
            return

        tree = self.active_scan_tree
        for iid in tree.get_children(""):
            tree.delete(iid)

        root_path = self.tab_root_paths.get(self.active_scan_tab_id, "")
        self._fill_tree(tree, results, current_root_path=root_path)

        if self.active_scan_title_base is not None:
            self._set_tab_raw_title(self.active_scan_tab_id, self.active_scan_title_base)

    def _mark_active_scan_tab(self, suffix: str, message: str) -> None:
        if self.notebook is None:
            return
        if self.active_scan_tab_id is None or self.active_scan_tree is None:
            return
        if self.active_scan_tab_id not in self.notebook.tabs():
            return

        tree = self.active_scan_tree
        for iid in tree.get_children(""):
            tree.delete(iid)
        tree.insert("", tk.END, values=(message, "", ""))

        if self.active_scan_title_base is not None:
            self._set_tab_raw_title(self.active_scan_tab_id, f"{self.active_scan_title_base} ({suffix})")

    def _clear_active_scan_ref(self) -> None:
        self.active_scan_tab_id = None
        self.active_scan_tree = None
        self.active_scan_title_base = None

    def _current_tab_root_for_tree(self, tree: ttk.Treeview) -> str:
        tab_id = str(tree.master)
        return self.tab_root_paths.get(tab_id, "")

    def _is_current_dir_row(self, tree: ttk.Treeview, row_values: tuple[Any, ...]) -> bool:
        if not row_values:
            return False
        row_path = str(row_values[0])
        root_path = self._current_tab_root_for_tree(tree)
        if not root_path:
            return False
        return self._normalize_path(row_path) == self._normalize_path(root_path)

    def _on_tree_right_click(self, event: tk.Event[tk.Misc]) -> None:
        tree = event.widget
        if not isinstance(tree, ttk.Treeview):
            return
        if self.tree_menu is None:
            return

        row_id = tree.identify_row(event.y)
        if not row_id:
            return

        tree.selection_set(row_id)
        tree.focus(row_id)
        self.context_tree = tree

        row_values = tree.item(row_id, "values")
        if self._is_current_dir_row(tree, row_values):
            self.tree_menu.entryconfig(0, state="disabled")
        else:
            self.tree_menu.entryconfig(0, state="normal")

        try:
            self.tree_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tree_menu.grab_release()

    def _on_tab_right_click(self, event: tk.Event[tk.Misc]) -> None:
        if self.notebook is None or self.tab_menu is None:
            return

        try:
            tab_index = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return

        tabs = self.notebook.tabs()
        if tab_index < 0 or tab_index >= len(tabs):
            return

        tab_id = tabs[tab_index]
        self.context_tab_id = tab_id
        self.notebook.select(tab_id)

        try:
            self.tab_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.tab_menu.grab_release()

    def _remove_tab_meta(self, tab_id: str) -> None:
        self.tab_root_paths.pop(tab_id, None)
        self.tab_titles.pop(tab_id, None)

    def _close_current_tab(self) -> None:
        if self.notebook is None:
            return

        tab_id = self.context_tab_id or self.notebook.select()
        if not tab_id:
            return

        if self.scanning and self.active_scan_tab_id == tab_id:
            messagebox.showinfo("\u63d0\u793a", "\u5f53\u524d\u7ed3\u679c\u9875\u6b63\u5728\u626b\u63cf\uff0c\u8bf7\u5148\u505c\u6b62\u626b\u63cf\u3002")
            return

        self.notebook.forget(tab_id)
        self._remove_tab_meta(tab_id)
        self._refresh_tab_highlight()
        self._set_status("\u5df2\u5173\u95ed\u5f53\u524d\u7ed3\u679c\u9875")

    def _close_other_tabs(self) -> None:
        if self.notebook is None:
            return

        keep_tab = self.context_tab_id or self.notebook.select()
        if not keep_tab:
            return

        for tab_id in list(self.notebook.tabs()):
            if tab_id == keep_tab:
                continue
            if self.scanning and tab_id == self.active_scan_tab_id:
                continue
            self.notebook.forget(tab_id)
            self._remove_tab_meta(tab_id)

        self.notebook.select(keep_tab)
        self._refresh_tab_highlight()
        self._set_status("\u5df2\u5173\u95ed\u5176\u4ed6\u7ed3\u679c\u9875")

    def _scan_selected_row_dir(self) -> None:
        tree = self.context_tree
        if tree is None:
            return

        selected = tree.selection()
        if not selected:
            messagebox.showinfo("\u63d0\u793a", "\u8bf7\u5148\u9009\u62e9\u4e00\u884c\u76ee\u5f55\u3002")
            return

        row = selected[0]
        values = tree.item(row, "values")
        if not values:
            return

        if self._is_current_dir_row(tree, values):
            messagebox.showinfo("\u63d0\u793a", "\u5f53\u524d\u76ee\u5f55\u4e0d\u652f\u6301\u518d\u6b21\u6df1\u5165\u626b\u63cf\u3002")
            return

        target_path = str(values[0])
        self.path_var.set(target_path)
        self._set_status(f"\u5df2\u9009\u4e2d\u76ee\u5f55\u8fdb\u884c\u6df1\u5165\u626b\u63cf: {target_path}")
        self._start_scan()

    def _open_selected_row_location(self) -> None:
        tree = self.context_tree
        if tree is None:
            return

        selected = tree.selection()
        if not selected:
            return

        row = selected[0]
        values = tree.item(row, "values")
        if not values:
            return

        target_path = str(values[0])
        if not os.path.exists(target_path):
            messagebox.showerror("\u8def\u5f84\u5f02\u5e38", f"\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a\n{target_path}")
            return

        try:
            # Prefer locating target in Explorer.
            subprocess.Popen(["explorer", f"/select,{target_path}"])
        except Exception:
            try:
                os.startfile(target_path)
            except Exception as exc:
                messagebox.showerror("\u6253\u5f00\u5931\u8d25", f"\u65e0\u6cd5\u6253\u5f00\u6240\u5728\u4f4d\u7f6e\u3002\n\n{exc}")
                return

        self._set_status(f"\u5df2\u6253\u5f00\u76ee\u5f55\u4f4d\u7f6e: {target_path}")

    def _choose_dir(self) -> None:
        folder = filedialog.askdirectory(title="\u9009\u62e9\u8981\u626b\u63cf\u7684\u76ee\u5f55")
        if folder:
            self.path_var.set(folder)
            self._set_status(f"\u5df2\u9009\u62e9\u76ee\u5f55: {folder}")

    def _start_scan(self) -> None:
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u5148\u9009\u62e9\u76ee\u5f55")
            return

        if self.scanning:
            return

        self.scanning = True
        self.cancel_event.clear()

        if self.scan_btn is not None:
            self.scan_btn.config(state="disabled")
        if self.stop_btn is not None:
            self.stop_btn.config(state="normal")

        self._create_pending_tab(path)
        self._set_status("\u626b\u63cf\u4e2d\uff0c\u8bf7\u7a0d\u5019...")

        worker = threading.Thread(target=self._scan_worker, args=(path,), daemon=True)
        worker.start()
        self._poll_queue()

    def _stop_scan(self) -> None:
        if not self.scanning:
            return
        self.cancel_event.set()
        self._set_status("\u6b63\u5728\u505c\u6b62\u626b\u63cf...")

    def _scan_worker(self, path: str) -> None:
        try:
            previous = load_last_snapshot(path)
            results = scan_directory_sizes(path, should_cancel=self.cancel_event.is_set)
            current = save_scan_snapshot(path, results)
            compare: Dict[str, Any] = {"current": current, "previous": previous, "path": path}
            self.result_queue.put(("ok", (results, compare)))
        except ScanCancelled:
            self.result_queue.put(("cancelled", None))
        except PermissionError as exc:
            self.result_queue.put(("permission_error", exc))
        except FileNotFoundError as exc:
            self.result_queue.put(("path_error", exc))
        except NotADirectoryError as exc:
            self.result_queue.put(("path_error", exc))
        except OSError as exc:
            self.result_queue.put(("os_error", exc))
        except Exception as exc:  # Defensive fallback for unexpected errors.
            self.result_queue.put(("unknown", exc))

    def _poll_queue(self) -> None:
        if self.parent is None:
            return

        try:
            kind, payload = self.result_queue.get_nowait()
        except queue.Empty:
            if self.scanning:
                self.parent.after(120, self._poll_queue)
            return

        self.scanning = False
        if self.scan_btn is not None:
            self.scan_btn.config(state="normal")
        if self.stop_btn is not None:
            self.stop_btn.config(state="disabled")

        if kind == "ok":
            results, compare = payload  # type: ignore[misc]
            self._finalize_active_scan_tab(results)
            self._show_compare_status(compare)
            self._clear_active_scan_ref()
            return

        if kind == "cancelled":
            self._mark_active_scan_tab("\u5df2\u53d6\u6d88", "\u626b\u63cf\u4efb\u52a1\u5df2\u53d6\u6d88")
            self._set_status("\u626b\u63cf\u5df2\u505c\u6b62")
            messagebox.showinfo("\u5df2\u505c\u6b62", "\u626b\u63cf\u4efb\u52a1\u5df2\u53d6\u6d88\u3002")
            self._clear_active_scan_ref()
            return

        if kind == "permission_error":
            self._mark_active_scan_tab("\u5931\u8d25", "\u626b\u63cf\u5931\u8d25\uff1a\u6743\u9650\u4e0d\u8db3")
            self._set_status("\u626b\u63cf\u5931\u8d25\uff1a\u6743\u9650\u4e0d\u8db3")
            messagebox.showerror("\u6743\u9650\u5f02\u5e38", f"\u8bbf\u95ee\u88ab\u62d2\u7edd\uff0c\u8bf7\u68c0\u67e5\u6743\u9650\u3002\n\n{payload}")
            self._clear_active_scan_ref()
            return

        if kind == "path_error":
            self._mark_active_scan_tab("\u5931\u8d25", "\u626b\u63cf\u5931\u8d25\uff1a\u8def\u5f84\u65e0\u6548")
            self._set_status("\u626b\u63cf\u5931\u8d25\uff1a\u8def\u5f84\u65e0\u6548")
            messagebox.showerror("\u8def\u5f84\u5f02\u5e38", f"\u76ee\u5f55\u8def\u5f84\u65e0\u6548\u3002\n\n{payload}")
            self._clear_active_scan_ref()
            return

        if kind == "os_error":
            self._mark_active_scan_tab("\u5931\u8d25", "\u626b\u63cf\u5931\u8d25\uff1a\u7cfb\u7edf\u5f02\u5e38")
            self._set_status("\u626b\u63cf\u5931\u8d25\uff1a\u7cfb\u7edf\u5f02\u5e38")
            messagebox.showerror("\u7cfb\u7edf\u5f02\u5e38", f"\u626b\u63cf\u65f6\u51fa\u73b0\u7cfb\u7edf\u9519\u8bef\u3002\n\n{payload}")
            self._clear_active_scan_ref()
            return

        self._mark_active_scan_tab("\u5931\u8d25", "\u626b\u63cf\u5931\u8d25\uff1a\u672a\u77e5\u5f02\u5e38")
        self._set_status("\u626b\u63cf\u5931\u8d25\uff1a\u672a\u77e5\u5f02\u5e38")
        messagebox.showerror("\u672a\u77e5\u5f02\u5e38", f"\u53d1\u751f\u672a\u9884\u671f\u9519\u8bef\u3002\n\n{payload}")
        self._clear_active_scan_ref()

    def _show_compare_status(self, compare: Dict[str, Any]) -> None:
        current = compare["current"]
        previous = compare.get("previous")

        current_size = int(current.get("root_size_bytes", 0))

        if previous is None:
            self._set_status(
                f"\u626b\u63cf\u5b8c\u6210\uff1a{current.get('dir_count', 0)} \u4e2a\u76ee\u5f55\uff0c\u5f53\u524d {format_size(current_size)}\uff08\u9996\u6b21\u8bb0\u5f55\uff09"
            )
            return

        prev_size = int(previous.get("root_size_bytes", 0))
        diff = current_size - prev_size
        if diff >= 0:
            diff_text = f"+{format_size(diff)}"
        else:
            diff_text = f"-{format_size(abs(diff))}"

        self._set_status(
            f"\u626b\u63cf\u5b8c\u6210\uff1a\u5f53\u524d {format_size(current_size)}\uff0c\u4e0a\u6b21 {format_size(prev_size)}\uff0c\u53d8\u5316 {diff_text}"
        )

    def _fill_tree(self, tree: ttk.Treeview, results: list[DirSizeResult], current_root_path: str = "") -> None:
        root_key = self._normalize_path(current_root_path) if current_root_path else ""

        for item in results:
            tags: tuple[str, ...] = ()
            if root_key and self._normalize_path(item.path) == root_key:
                tags = ("current_dir",)
            tree.insert(
                "",
                tk.END,
                values=(item.path, format_size(item.size_bytes), item.size_bytes),
                tags=tags,
            )

        self._sort_by_size_desc(tree)

    def _sort_by_size_desc(self, tree: ttk.Treeview) -> None:
        rows: list[tuple[int, str]] = []
        for iid in tree.get_children(""):
            values = tree.item(iid, "values")
            if len(values) < 3:
                continue
            try:
                bytes_value = int(values[2])
            except (TypeError, ValueError):
                continue
            rows.append((bytes_value, iid))

        rows.sort(key=lambda x: x[0], reverse=True)

        for idx, (_, iid) in enumerate(rows):
            tree.move(iid, "", idx)

    def _set_status(self, text: str) -> None:
        if self.set_status is not None:
            self.set_status(text)