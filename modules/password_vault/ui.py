from __future__ import annotations

import ctypes
import json
import time
import tkinter as tk
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from modules.password_vault.core import (
    PasswordVaultStore,
    VaultAuthError,
    VaultCorruptedError,
    VaultError,
    VaultItem,
    VaultSettings,
    charset_flags_to_tuple,
    evaluate_password_strength,
    generate_password,
    normalize_item,
    tuple_to_charset_flags,
)
from wintools.base import BaseModule, StatusCallback


class PasswordVaultModule(BaseModule):
    name = "密码箱"
    description = "本地加密保存账号密码，支持自动锁定、检索筛选、密码生成与强度提示。"

    def __init__(self) -> None:
        self.parent: Optional[ttk.Frame] = None
        self.set_status: Optional[StatusCallback] = None
        self.store = PasswordVaultStore()
        self.settings = self.store.load_settings()

        self.master_var = tk.StringVar()
        self.items: list[VaultItem] = []
        self.master_password: str = ""
        self.item_id_by_iid: dict[str, str] = {}
        self.clipboard_token: int = 0

        self.search_var = tk.StringVar()
        self.tag_filter_var = tk.StringVar(value="全部标签")
        self.only_favorite_var = tk.BooleanVar(value=False)
        self.sort_var = tk.StringVar(value="更新时间(新到旧)")
        self.session_left_var = tk.StringVar(value="会话剩余：未解锁")
        self.auto_lock_var = tk.StringVar(value=str(self.settings.auto_lock_minutes))
        self.copy_ttl_var = tk.StringVar(value=str(self.settings.copy_ttl_seconds))

        self.unlock_btn: Optional[ttk.Button] = None
        self.lock_btn: Optional[ttk.Button] = None
        self.tree: Optional[ttk.Treeview] = None
        self.action_frame: Optional[ttk.Frame] = None
        self.tag_combo: Optional[ttk.Combobox] = None
        self.empty_hint_btn: Optional[ttk.Button] = None

        self.session_deadline_ts: float = 0.0
        self.session_tick_token: int = 0
        self._state_loaded = False

    def mount(self, parent: ttk.Frame, set_status: StatusCallback) -> None:
        self.parent = parent
        self.set_status = set_status
        self._build_ui(parent)
        self._load_ui_state()
        self._state_loaded = True
        self._apply_filters_and_render()

    def unmount(self) -> None:
        self._lock(clear_master_input=False)
        self._save_ui_state()
        self.item_id_by_iid.clear()

    def _build_ui(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)

        top = ttk.Frame(parent, style="ToolBar.TFrame", padding=(10, 8))
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        top.columnconfigure(8, weight=1)

        ttk.Label(top, text="主密码:").grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")
        master_entry = ttk.Entry(top, textvariable=self.master_var, show="*")
        master_entry.grid(row=0, column=1, pady=4, sticky="ew")
        master_entry.bind("<KeyRelease>", lambda _e: self._touch_activity())

        self.unlock_btn = ttk.Button(top, text="解锁/创建", command=self._unlock)
        self.unlock_btn.grid(row=0, column=2, padx=(10, 8), pady=4)

        self.lock_btn = ttk.Button(top, text="锁定", command=self._lock, state="disabled")
        self.lock_btn.grid(row=0, column=3, pady=4)

        ttk.Label(top, text="自动锁定(分钟):").grid(row=0, column=4, padx=(14, 6), pady=4, sticky="e")
        auto_lock_combo = ttk.Combobox(
            top,
            textvariable=self.auto_lock_var,
            width=6,
            state="readonly",
            values=("1", "5", "10", "30"),
        )
        auto_lock_combo.grid(row=0, column=5, pady=4, sticky="w")
        auto_lock_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_settings_changed())

        ttk.Label(top, text="复制有效期(秒):").grid(row=0, column=6, padx=(10, 6), pady=4, sticky="e")
        copy_ttl_combo = ttk.Combobox(
            top,
            textvariable=self.copy_ttl_var,
            width=6,
            state="readonly",
            values=("30", "60", "90"),
        )
        copy_ttl_combo.grid(row=0, column=7, pady=4, sticky="w")
        copy_ttl_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_settings_changed())

        ttk.Label(top, textvariable=self.session_left_var, style="Muted.TLabel").grid(
            row=0, column=8, sticky="e", padx=(12, 0)
        )

        hint = tk.Label(
            top,
            text="首次使用会在 SQLite 中创建加密密码库，主密码无法找回；复制密码会在有效期后自动清空。",
            bg="#F8FAFF",
            fg="#475569",
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        )
        hint.grid(row=1, column=0, columnspan=9, sticky="w", pady=(6, 0))

        filter_card = ttk.Frame(parent, style="ToolBar.TFrame", padding=(10, 8))
        filter_card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        filter_card.columnconfigure(1, weight=1)

        ttk.Label(filter_card, text="搜索:").grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")
        search_entry = ttk.Entry(filter_card, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, pady=4, sticky="ew")
        search_entry.bind("<KeyRelease>", lambda _e: self._on_filter_changed())

        self.tag_combo = ttk.Combobox(filter_card, textvariable=self.tag_filter_var, width=18, state="readonly")
        self.tag_combo.grid(row=0, column=2, padx=(10, 8), pady=4, sticky="w")
        self.tag_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filter_changed())

        ttk.Checkbutton(
            filter_card,
            text="仅看收藏",
            variable=self.only_favorite_var,
            command=self._on_filter_changed,
        ).grid(row=0, column=3, padx=8, pady=4, sticky="w")

        sort_combo = ttk.Combobox(
            filter_card,
            textvariable=self.sort_var,
            width=16,
            state="readonly",
            values=("更新时间(新到旧)", "站点名(A-Z)", "最近使用(新到旧)"),
        )
        sort_combo.grid(row=0, column=4, padx=(8, 0), pady=4, sticky="w")
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_filter_changed())

        body = ttk.Frame(parent, style="Card.TFrame", padding=8)
        body.grid(row=2, column=0, sticky="nsew")
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        self.action_frame = ttk.Frame(body)
        self.action_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Button(self.action_frame, text="新增", command=self._add_item, state="disabled").grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(self.action_frame, text="编辑", command=self._edit_item, state="disabled").grid(
            row=0, column=1, padx=6
        )
        ttk.Button(self.action_frame, text="删除", command=self._delete_item, state="disabled").grid(
            row=0, column=2, padx=6
        )
        ttk.Button(self.action_frame, text="收藏切换", command=self._toggle_favorite, state="disabled").grid(
            row=0, column=3, padx=6
        )
        ttk.Button(self.action_frame, text="复制密码", command=self._copy_password, state="disabled").grid(
            row=0, column=4, padx=(6, 0)
        )

        table = ttk.Frame(body)
        table.grid(row=1, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

        columns = ("fav", "site", "account", "tags", "strength", "updated")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        self.tree.heading("fav", text="收藏")
        self.tree.heading("site", text="站点/用途")
        self.tree.heading("account", text="账号")
        self.tree.heading("tags", text="标签")
        self.tree.heading("strength", text="强度")
        self.tree.heading("updated", text="更新时间")
        self.tree.column("fav", width=60, anchor="center")
        self.tree.column("site", width=210, anchor="w")
        self.tree.column("account", width=210, anchor="w")
        self.tree.column("tags", width=180, anchor="w")
        self.tree.column("strength", width=80, anchor="center")
        self.tree.column("updated", width=170, anchor="w")

        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _e: self._edit_item())

        self.empty_hint_btn = ttk.Button(body, text="新增第一条密码", command=self._add_item, state="disabled")
        self.empty_hint_btn.grid(row=2, column=0, sticky="w", pady=(8, 0))

        self.tree.insert("", tk.END, values=("未解锁密码箱", "", "", "", "", ""))
        self._refresh_tag_combo([])

    def _unlock(self) -> None:
        master = self.master_var.get().strip()
        if not master:
            messagebox.showwarning("提示", "请输入主密码")
            return
        try:
            items = self.store.unlock(master)
        except VaultAuthError as exc:
            messagebox.showerror("主密码错误", str(exc))
            self._set_status("密码箱解锁失败：主密码错误")
            return
        except VaultCorruptedError as exc:
            messagebox.showerror("数据损坏", str(exc))
            self._set_status("密码箱异常：数据损坏")
            return
        except VaultError as exc:
            messagebox.showerror("错误", str(exc))
            self._set_status("密码箱异常")
            return

        self.master_password = master
        self.items = items
        self._set_action_enabled(True)
        if self.unlock_btn is not None:
            self.unlock_btn.config(state="disabled")
        if self.lock_btn is not None:
            self.lock_btn.config(state="normal")
        self._touch_activity()
        self._apply_filters_and_render()
        self._set_status(f"密码箱已解锁，共 {len(self.items)} 条记录")

    def _lock(self, clear_master_input: bool = True) -> None:
        self.master_password = ""
        self.items = []
        self.item_id_by_iid.clear()
        self.session_deadline_ts = 0
        self.session_tick_token += 1
        self.session_left_var.set("会话剩余：未解锁")
        if clear_master_input:
            self.master_var.set("")
        self._set_action_enabled(False)
        if self.unlock_btn is not None:
            self.unlock_btn.config(state="normal")
        if self.lock_btn is not None:
            self.lock_btn.config(state="disabled")
        if self.tree is not None:
            for iid in self.tree.get_children(""):
                self.tree.delete(iid)
            self.tree.insert("", tk.END, values=("未解锁密码箱", "", "", "", "", ""))
        if self.empty_hint_btn is not None:
            self.empty_hint_btn.config(state="disabled")
        self._set_status("密码箱已锁定")

    def _touch_activity(self) -> None:
        if not self.master_password:
            return
        minutes = int(self.auto_lock_var.get() or self.settings.auto_lock_minutes)
        self.session_deadline_ts = time.time() + minutes * 60
        self.session_tick_token += 1
        token = self.session_tick_token
        self._run_session_tick(token)

    def _run_session_tick(self, token: int) -> None:
        if self.parent is None:
            return
        if token != self.session_tick_token:
            return
        if not self.master_password:
            self.session_left_var.set("会话剩余：未解锁")
            return
        remain = int(self.session_deadline_ts - time.time())
        if remain <= 0:
            self._lock(clear_master_input=False)
            self._set_status("会话已超时，密码箱已自动锁定")
            return
        mm = remain // 60
        ss = remain % 60
        self.session_left_var.set(f"会话剩余：{mm:02d}:{ss:02d}")
        self.parent.after(1000, lambda: self._run_session_tick(token))

    def _on_settings_changed(self) -> None:
        settings = VaultSettings(
            auto_lock_minutes=int(self.auto_lock_var.get() or self.settings.auto_lock_minutes),
            copy_ttl_seconds=int(self.copy_ttl_var.get() or self.settings.copy_ttl_seconds),
            default_gen_length=self.settings.default_gen_length,
            gen_charset_flags=self.settings.gen_charset_flags,
        )
        self.settings = settings
        self.store.save_settings(settings)
        self._touch_activity()
        self._set_status("密码箱设置已更新")

    def _on_filter_changed(self) -> None:
        if self._state_loaded:
            self._save_ui_state()
        self._apply_filters_and_render()

    def _apply_filters_and_render(self) -> None:
        if self.tree is None:
            return
        self.item_id_by_iid.clear()
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)

        if not self.master_password:
            self.tree.insert("", tk.END, values=("未解锁密码箱", "", "", "", "", ""))
            self._refresh_tag_combo([])
            return

        rows = list(self.items)
        keyword = self.search_var.get().strip().lower()
        if keyword:
            rows = [
                x
                for x in rows
                if keyword in x.site.lower() or keyword in x.account.lower() or keyword in x.note.lower()
            ]

        if self.only_favorite_var.get():
            rows = [x for x in rows if x.favorite]

        selected_tag = self.tag_filter_var.get().strip()
        if selected_tag and selected_tag != "全部标签":
            rows = [x for x in rows if selected_tag in x.tags]

        sort_mode = self.sort_var.get().strip()
        if sort_mode == "站点名(A-Z)":
            rows.sort(key=lambda x: x.site.lower())
        elif sort_mode == "最近使用(新到旧)":
            rows.sort(key=lambda x: x.last_used_at or "", reverse=True)
        else:
            rows.sort(key=lambda x: x.updated_at, reverse=True)

        if not rows:
            self.tree.insert("", tk.END, values=("无匹配结果", "", "", "", "", ""))
        else:
            for item in rows:
                iid = self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        "Y" if item.favorite else "",
                        item.site,
                        item.account,
                        ",".join(item.tags),
                        item.strength,
                        item.updated_at,
                    ),
                )
                self.item_id_by_iid[iid] = item.item_id

        self._refresh_tag_combo(self.items)
        if self.empty_hint_btn is not None:
            self.empty_hint_btn.config(state="normal" if self.master_password and not self.items else "disabled")

    def _refresh_tag_combo(self, source_items: list[VaultItem]) -> None:
        if self.tag_combo is None:
            return
        tags = sorted({tag for item in source_items for tag in item.tags}, key=str.lower)
        values = ["全部标签", *tags]
        current = self.tag_filter_var.get().strip() or "全部标签"
        if current not in values:
            current = "全部标签"
            self.tag_filter_var.set(current)
        self.tag_combo.configure(values=values)

    def _add_item(self) -> None:
        if not self._ensure_unlocked():
            return
        payload = self._show_edit_dialog("新增密码")
        if payload is None:
            return
        site, account, password, note, tags, favorite = payload
        strength = evaluate_password_strength(password)
        if strength == "弱":
            if not messagebox.askyesno("弱密码提示", "当前密码强度为“弱”，仍要继续保存吗？"):
                return
        try:
            item = normalize_item(site, account, password, note, tags=tags, favorite=favorite)
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc))
            return
        self.items.append(item)
        self._save_items()

    def _edit_item(self) -> None:
        if not self._ensure_unlocked():
            return
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        payload = self._show_edit_dialog("编辑密码", item)
        if payload is None:
            return
        site, account, password, note, tags, favorite = payload
        password_changed = password != item.password
        if password_changed:
            if not messagebox.askyesno("确认覆盖密码", "你修改了密码字段，确认覆盖原密码吗？"):
                return
        strength = evaluate_password_strength(password)
        if strength == "弱" and password_changed:
            if not messagebox.askyesno("弱密码提示", "当前密码强度为“弱”，仍要继续保存吗？"):
                return

        try:
            updated = normalize_item(
                site,
                account,
                password,
                note,
                item_id=item.item_id,
                tags=tags,
                favorite=favorite,
                last_used_at=item.last_used_at,
            )
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc))
            return
        for idx, row in enumerate(self.items):
            if row.item_id == item.item_id:
                self.items[idx] = updated
                break
        self._save_items()

    def _delete_item(self) -> None:
        if not self._ensure_unlocked():
            return
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        if not messagebox.askyesno("确认删除", f"确定删除记录：{item.site} / {item.account} ?"):
            return
        self.items = [x for x in self.items if x.item_id != item.item_id]
        self._save_items()

    def _toggle_favorite(self) -> None:
        if not self._ensure_unlocked():
            return
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        for idx, row in enumerate(self.items):
            if row.item_id == item.item_id:
                row.favorite = not row.favorite
                row.updated_at = _now_iso()
                self.items[idx] = row
                break
        self._save_items()

    def _copy_password(self) -> None:
        if not self._ensure_unlocked():
            return
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        if self.parent is None:
            return
        self.parent.clipboard_clear()
        self.parent.clipboard_append(item.password)
        self.clipboard_token += 1
        token = self.clipboard_token
        ttl = int(self.copy_ttl_var.get() or self.settings.copy_ttl_seconds)
        self.parent.after(ttl * 1000, lambda: self._clear_clipboard_after_timeout(token))
        self._start_clipboard_countdown(token, ttl)
        self._touch_activity()

        for idx, row in enumerate(self.items):
            if row.item_id == item.item_id:
                row.last_used_at = _now_iso()
                self.items[idx] = row
                break
        self._save_items()

    def _start_clipboard_countdown(self, token: int, remain_seconds: int) -> None:
        if self.parent is None:
            return
        if token != self.clipboard_token:
            return
        if remain_seconds <= 0:
            return
        self._set_status(f"密码已复制，{remain_seconds}s 后自动清空")
        self.parent.after(1000, lambda: self._start_clipboard_countdown(token, remain_seconds - 1))

    def _clear_clipboard_after_timeout(self, token: int) -> None:
        if self.parent is None:
            return
        if token != self.clipboard_token:
            return
        self._clear_system_clipboard()
        try:
            self.parent.clipboard_clear()
        except tk.TclError:
            pass
        self._set_status("剪贴板中的密码已自动清空")

    def _clear_system_clipboard(self) -> None:
        user32 = ctypes.windll.user32
        if self._open_clipboard_with_retry(user32):
            try:
                user32.EmptyClipboard()
            finally:
                user32.CloseClipboard()

    def _open_clipboard_with_retry(self, user32: object) -> bool:
        for _ in range(10):
            if user32.OpenClipboard(wintypes.HWND(0)):
                return True
            time.sleep(0.02)
        return False

    def _selected_item(self) -> Optional[VaultItem]:
        if self.tree is None:
            return None
        selected = self.tree.selection()
        if not selected:
            return None
        iid = selected[0]
        target_id = self.item_id_by_iid.get(iid)
        if target_id is None:
            return None
        for x in self.items:
            if x.item_id == target_id:
                return x
        return None

    def _show_edit_dialog(
        self,
        title: str,
        item: Optional[VaultItem] = None,
    ) -> Optional[tuple[str, str, str, str, list[str], bool]]:
        if self.parent is None:
            return None

        dialog = tk.Toplevel(self.parent)
        dialog.title(title)
        dialog.geometry("560x390")
        dialog.resizable(False, False)
        dialog.transient(self.parent.winfo_toplevel())
        dialog.grab_set()

        site_var = tk.StringVar(value=item.site if item else "")
        account_var = tk.StringVar(value=item.account if item else "")
        password_var = tk.StringVar(value=item.password if item else "")
        note_var = tk.StringVar(value=item.note if item else "")
        tags_var = tk.StringVar(value=",".join(item.tags) if item else "")
        favorite_var = tk.BooleanVar(value=item.favorite if item else False)
        strength_var = tk.StringVar(value=evaluate_password_strength(password_var.get()))

        use_upper, use_lower, use_digits, use_symbols = charset_flags_to_tuple(self.settings.gen_charset_flags)
        gen_len_var = tk.StringVar(value=str(self.settings.default_gen_length))
        gen_upper_var = tk.BooleanVar(value=use_upper)
        gen_lower_var = tk.BooleanVar(value=use_lower)
        gen_digits_var = tk.BooleanVar(value=use_digits)
        gen_symbols_var = tk.BooleanVar(value=use_symbols)
        result: dict[str, tuple[str, str, str, str, list[str], bool]] = {}

        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="站点/用途:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=site_var).grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="账号:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=account_var).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="密码:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=password_var, show="*").grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(frame, textvariable=strength_var, style="Muted.TLabel").grid(row=2, column=2, sticky="w", padx=(8, 0))

        ttk.Label(frame, text="标签(逗号分隔):").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=tags_var).grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="备注:").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(frame, textvariable=note_var).grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(frame, text="收藏", variable=favorite_var).grid(row=5, column=1, sticky="w", pady=(2, 8))

        gen_frame = ttk.Frame(frame)
        gen_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        ttk.Label(gen_frame, text="生成密码长度:").grid(row=0, column=0, padx=(0, 6), pady=4, sticky="w")
        ttk.Combobox(
            gen_frame,
            textvariable=gen_len_var,
            width=6,
            state="readonly",
            values=("12", "16", "20", "24", "32"),
        ).grid(row=0, column=1, pady=4, sticky="w")
        ttk.Checkbutton(gen_frame, text="大写", variable=gen_upper_var).grid(row=0, column=2, padx=(10, 4), pady=4)
        ttk.Checkbutton(gen_frame, text="小写", variable=gen_lower_var).grid(row=0, column=3, padx=4, pady=4)
        ttk.Checkbutton(gen_frame, text="数字", variable=gen_digits_var).grid(row=0, column=4, padx=4, pady=4)
        ttk.Checkbutton(gen_frame, text="符号", variable=gen_symbols_var).grid(row=0, column=5, padx=4, pady=4)

        def on_generate() -> None:
            try:
                length = int(gen_len_var.get())
            except ValueError:
                length = 16
            pwd = generate_password(
                length=length,
                use_upper=gen_upper_var.get(),
                use_lower=gen_lower_var.get(),
                use_digits=gen_digits_var.get(),
                use_symbols=gen_symbols_var.get(),
            )
            password_var.set(pwd)
            self.settings.default_gen_length = length
            self.settings.gen_charset_flags = tuple_to_charset_flags(
                gen_upper_var.get(), gen_lower_var.get(), gen_digits_var.get(), gen_symbols_var.get()
            )
            self.store.save_settings(self.settings)

        ttk.Button(gen_frame, text="生成密码", command=on_generate).grid(row=0, column=6, padx=(10, 0), pady=4)

        def on_password_change(*_args: object) -> None:
            strength_var.set(evaluate_password_strength(password_var.get()))

        password_var.trace_add("write", on_password_change)

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=7, column=1, sticky="e", pady=(12, 0))

        def on_ok() -> None:
            tags = [x.strip() for x in tags_var.get().split(",") if x.strip()]
            result["value"] = (
                site_var.get(),
                account_var.get(),
                password_var.get(),
                note_var.get(),
                tags,
                favorite_var.get(),
            )
            dialog.destroy()

        ttk.Button(btn_row, text="取消", command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btn_row, text="确定", command=on_ok).grid(row=0, column=1)

        dialog.wait_window()
        return result.get("value")

    def _save_items(self) -> None:
        if not self._ensure_unlocked():
            return
        try:
            self.store.save(self.master_password, self.items)
        except VaultError as exc:
            messagebox.showerror("保存失败", str(exc))
            self._set_status("密码箱保存失败")
            return
        self._apply_filters_and_render()
        self._touch_activity()
        self._set_status(f"密码箱已保存，共 {len(self.items)} 条记录")

    def _set_action_enabled(self, enabled: bool) -> None:
        if self.action_frame is None:
            return
        state = "normal" if enabled else "disabled"
        for child in self.action_frame.winfo_children():
            if isinstance(child, ttk.Button):
                child.config(state=state)

    def _ensure_unlocked(self) -> bool:
        if not self.master_password:
            messagebox.showinfo("提示", "请先解锁密码箱")
            return False
        return True

    def _ui_state_path(self) -> Path:
        return Path("data") / "ui_state.json"

    def _load_ui_state(self) -> None:
        path = self._ui_state_path()
        try:
            if not path.exists():
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return
            module_state = payload.get("password_vault")
            if not isinstance(module_state, dict):
                return
            self.search_var.set(str(module_state.get("search", "")))
            self.tag_filter_var.set(str(module_state.get("tag_filter", "全部标签")))
            self.only_favorite_var.set(bool(module_state.get("only_favorite", False)))
            self.sort_var.set(str(module_state.get("sort", "更新时间(新到旧)"))
                              if str(module_state.get("sort", "")) else "更新时间(新到旧)")
        except Exception:
            return

    def _save_ui_state(self) -> None:
        path = self._ui_state_path()
        try:
            root_payload: dict[str, object] = {}
            if path.exists():
                current = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(current, dict):
                    root_payload = current
            root_payload["password_vault"] = {
                "search": self.search_var.get(),
                "tag_filter": self.tag_filter_var.get(),
                "only_favorite": self.only_favorite_var.get(),
                "sort": self.sort_var.get(),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(root_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _set_status(self, text: str) -> None:
        if self.set_status is not None:
            self.set_status(text)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
