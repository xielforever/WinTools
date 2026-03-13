from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from modules.dir_size.core import ScanCancelled, format_size
from modules.dir_size.storage import load_last_run_dir_totals_for_root
from modules.large_files.core import LargeFileResult, LargeFileScanStats, scan_large_files
from wintools.base import BaseModule, StatusCallback


class LargeFilesModule(BaseModule):
    name = "大文件定位与清理"
    description = "按阈值扫描大文件，并基于目录大小快照进行可靠剪枝，减少无效扫描。"

    def __init__(self) -> None:
        self.parent: Optional[ttk.Frame] = None
        self.set_status: Optional[StatusCallback] = None

        self.path_var = tk.StringVar()
        self.threshold_mb_var = tk.StringVar(value="100")

        self.scan_btn: Optional[ttk.Button] = None
        self.stop_btn: Optional[ttk.Button] = None
        self.tree: Optional[ttk.Treeview] = None
        self.notebook: Optional[ttk.Notebook] = None

        self.scanning = False
        self.cancel_event = threading.Event()
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()

    def mount(self, parent: ttk.Frame, set_status: StatusCallback) -> None:
        self.parent = parent
        self.set_status = set_status
        self._build_ui(parent)

    def unmount(self) -> None:
        self.cancel_event.set()
        self.scanning = False

    def _build_ui(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        control_card = ttk.Frame(parent, style="ToolBar.TFrame", padding=(10, 8))
        control_card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        control_card.columnconfigure(0, weight=1)

        control = ttk.Frame(control_card, style="ToolBar.TFrame")
        control.grid(row=0, column=0, sticky="ew")
        control.columnconfigure(1, weight=1)

        ttk.Label(control, text="目标目录:").grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")
        ttk.Entry(control, textvariable=self.path_var).grid(row=0, column=1, pady=4, sticky="ew")
        ttk.Button(control, text="选择目录", command=self._choose_dir).grid(row=0, column=2, padx=8, pady=4)

        ttk.Label(control, text="阈值(MB):").grid(row=0, column=3, padx=(8, 4), pady=4, sticky="e")
        ttk.Entry(control, textvariable=self.threshold_mb_var, width=10).grid(row=0, column=4, pady=4, sticky="w")

        self.scan_btn = ttk.Button(control, text="开始扫描", command=self._start_scan)
        self.scan_btn.grid(row=0, column=5, padx=(12, 8), pady=4)

        self.stop_btn = ttk.Button(control, text="停止扫描", command=self._stop_scan, state="disabled")
        self.stop_btn.grid(row=0, column=6, pady=4)

        hint = tk.Label(
            control_card,
            text="按阈值实时展示命中文件，结果按发现顺序刷新，扫描结束后汇总显示",
            bg="#F8FAFF",
            fg="#475569",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        hint.grid(row=1, column=0, sticky="w", pady=(6, 0))

        table_card = ttk.Frame(parent, style="Card.TFrame", padding=8)
        table_card.grid(row=1, column=0, sticky="nsew")
        table_card.rowconfigure(0, weight=1)
        table_card.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(table_card)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        table_tab = ttk.Frame(self.notebook)
        table_tab.rowconfigure(0, weight=1)
        table_tab.columnconfigure(0, weight=1)
        self.notebook.add(table_tab, text="扫描结果")

        table = ttk.Frame(table_tab)
        table.grid(row=0, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

        columns = ("path", "size", "modified")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        self.tree.heading("path", text="文件路径")
        self.tree.heading("size", text="大小")
        self.tree.heading("modified", text="修改时间")

        self.tree.column("path", width=680, anchor="w")
        self.tree.column("size", width=120, anchor="e")
        self.tree.column("modified", width=180, anchor="w")

        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.insert("", tk.END, values=("暂无结果，请点击“开始扫描”", "", ""))

    def _choose_dir(self) -> None:
        folder = filedialog.askdirectory(title="选择要扫描的目录")
        if folder:
            self.path_var.set(folder)
            self._set_status(f"已选择目录: {folder}")

    def _parse_threshold_bytes(self) -> int:
        raw = self.threshold_mb_var.get().strip()
        if not raw:
            raise ValueError("请填写阈值(MB)")
        mb_value = float(raw)
        if mb_value < 0:
            raise ValueError("阈值不能小于 0")
        return int(mb_value * 1024 * 1024)

    def _start_scan(self) -> None:
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("提示", "请先选择目录")
            return
        if self.scanning:
            return

        try:
            threshold_bytes = self._parse_threshold_bytes()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        self.scanning = True
        self.cancel_event.clear()

        if self.scan_btn is not None:
            self.scan_btn.config(state="disabled")
        if self.stop_btn is not None:
            self.stop_btn.config(state="normal")

        self._clear_tree()
        self._set_status("扫描中，请稍候...")

        worker = threading.Thread(target=self._scan_worker, args=(path, threshold_bytes), daemon=True)
        worker.start()
        self._poll_queue()

    def _stop_scan(self) -> None:
        if not self.scanning:
            return
        self.cancel_event.set()
        self._set_status("正在停止扫描...")

    def _scan_worker(self, path: str, threshold_bytes: int) -> None:
        try:
            reliable_totals = load_last_run_dir_totals_for_root(path)
            pruning_enabled = bool(reliable_totals)

            def on_progress(stats: LargeFileScanStats, current_path: str) -> None:
                self.result_queue.put(("progress", (stats, current_path, pruning_enabled)))

            live_batch: list[LargeFileResult] = []

            def on_match(item: LargeFileResult) -> None:
                live_batch.append(item)
                if len(live_batch) >= 30:
                    self.result_queue.put(("match_batch", live_batch.copy()))
                    live_batch.clear()

            results, stats = scan_large_files(
                path,
                threshold_bytes,
                reliable_dir_totals=reliable_totals if pruning_enabled else None,
                should_cancel=self.cancel_event.is_set,
                on_progress=on_progress,
                on_match=on_match,
            )
            if live_batch:
                self.result_queue.put(("match_batch", live_batch.copy()))
            self.result_queue.put(("ok", (results, stats, pruning_enabled)))
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
        except Exception as exc:
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

        if kind == "progress":
            stats, _current_path, pruning_enabled = payload  # type: ignore[misc]
            mode = "已启用(快照)" if pruning_enabled else "未启用(无快照)"
            self._set_status(
                f"扫描中: 文件 {stats.scanned_files} / 命中 {stats.matched_files} / 剪枝目录 {stats.pruned_dirs} / 异常 {stats.errors} | 剪枝: {mode}"
            )
            if self.scanning and self.parent is not None:
                self.parent.after(50, self._poll_queue)
            return

        if kind == "match_batch":
            batch = payload  # type: ignore[assignment]
            self._append_live_rows(batch)
            if self.scanning and self.parent is not None:
                self.parent.after(30, self._poll_queue)
            return

        self.scanning = False
        if self.scan_btn is not None:
            self.scan_btn.config(state="normal")
        if self.stop_btn is not None:
            self.stop_btn.config(state="disabled")

        if kind == "ok":
            results, stats, pruning_enabled = payload  # type: ignore[misc]
            self._fill_tree(results)
            mode = "已启用(快照)" if pruning_enabled else "未启用(无快照)"
            self._set_status(
                f"扫描完成: 文件 {stats.scanned_files} / 命中 {stats.matched_files} / 剪枝目录 {stats.pruned_dirs} / 异常 {stats.errors} | 剪枝: {mode}"
            )
            return

        if kind == "cancelled":
            self._set_status("扫描已停止")
            messagebox.showinfo("已停止", "扫描任务已取消。")
            return

        if kind == "permission_error":
            self._set_status("扫描失败：权限不足")
            messagebox.showerror("权限异常", f"访问被拒绝，请检查权限。\n\n{payload}")
            return

        if kind == "path_error":
            self._set_status("扫描失败：路径无效")
            messagebox.showerror("路径异常", f"目录路径无效。\n\n{payload}")
            return

        if kind == "os_error":
            self._set_status("扫描失败：系统异常")
            messagebox.showerror("系统异常", f"扫描时出现系统错误。\n\n{payload}")
            return

        self._set_status("扫描失败：未知异常")
        messagebox.showerror("未知异常", f"发生未预期错误。\n\n{payload}")

    def _clear_tree(self) -> None:
        if self.tree is None:
            return
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)

    def _fill_tree(self, results: list[LargeFileResult]) -> None:
        if self.tree is None:
            return
        self._clear_tree()

        for item in results:
            self.tree.insert(
                "",
                tk.END,
                values=(item.path, format_size(item.size_bytes), item.modified_at),
            )

    def _append_live_rows(self, batch: list[LargeFileResult]) -> None:
        if self.tree is None:
            return
        for item in batch:
            self.tree.insert(
                "",
                tk.END,
                values=(item.path, format_size(item.size_bytes), item.modified_at),
            )

    def _set_status(self, text: str) -> None:
        if self.set_status is not None:
            self.set_status(text)
