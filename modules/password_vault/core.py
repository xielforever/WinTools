from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import string
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

DB_FILE = Path("data") / "dir_size_history.db"
VAULT_MARKER = b"WinToolsPasswordVault"
PBKDF2_ROUNDS = 240_000
SALT_BYTES = 16
NONCE_BYTES = 16
MAC_BYTES = 32
VAULT_NAME = "default"

StrengthLevel = Literal["弱", "中", "强"]


class VaultError(Exception):
    pass


class VaultAuthError(VaultError):
    pass


class VaultCorruptedError(VaultError):
    pass


@dataclass(slots=True)
class VaultItem:
    item_id: str
    site: str
    account: str
    password: str
    note: str
    tags: list[str]
    favorite: bool
    strength: StrengthLevel
    updated_at: str
    last_used_at: str | None


@dataclass(slots=True)
class VaultSettings:
    vault_name: str = VAULT_NAME
    auto_lock_minutes: int = 5
    copy_ttl_seconds: int = 30
    default_gen_length: int = 16
    gen_charset_flags: str = "upper,lower,digits,symbols"


class PasswordVaultStore:
    def __init__(self) -> None:
        self._init_db()

    def unlock(self, master_password: str) -> list[VaultItem]:
        password = master_password.strip()
        if not password:
            raise VaultAuthError("主密码不能为空")

        row = self._load_row()
        if row is None:
            self.save(password, [])
            return []

        salt = bytes(row["salt"])
        verifier_blob = bytes(row["verifier_blob"])
        items_blob = bytes(row["items_blob"])

        enc_key, mac_key = _derive_keys(password, salt)
        marker = _decrypt_blob(verifier_blob, enc_key, mac_key)
        if marker != VAULT_MARKER:
            raise VaultAuthError("主密码错误")

        data = _decrypt_blob(items_blob, enc_key, mac_key)
        try:
            raw_items = json.loads(data.decode("utf-8"))
        except Exception as exc:
            raise VaultCorruptedError("密码箱数据损坏") from exc
        if not isinstance(raw_items, list):
            raise VaultCorruptedError("密码箱数据格式异常")

        items: list[VaultItem] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            password_text = str(raw.get("password", ""))
            tags = _normalize_tags(raw.get("tags", []))
            items.append(
                VaultItem(
                    item_id=str(raw.get("item_id", str(uuid4()))),
                    site=str(raw.get("site", "")),
                    account=str(raw.get("account", "")),
                    password=password_text,
                    note=str(raw.get("note", "")),
                    tags=tags,
                    favorite=bool(raw.get("favorite", False)),
                    strength=_ensure_strength(str(raw.get("strength", "")), password_text),
                    updated_at=str(raw.get("updated_at", _now_iso())),
                    last_used_at=_optional_text(raw.get("last_used_at")),
                )
            )
        return items

    def save(self, master_password: str, items: list[VaultItem]) -> None:
        password = master_password.strip()
        if not password:
            raise VaultAuthError("主密码不能为空")

        existing = self._load_row()
        if existing is None:
            salt = os.urandom(SALT_BYTES)
        else:
            salt = bytes(existing["salt"])
            enc_old, mac_old = _derive_keys(password, salt)
            marker = _decrypt_blob(bytes(existing["verifier_blob"]), enc_old, mac_old)
            if marker != VAULT_MARKER:
                raise VaultAuthError("主密码错误")

        enc_key, mac_key = _derive_keys(password, salt)
        verifier_blob = _encrypt_blob(VAULT_MARKER, enc_key, mac_key)
        serialized = [asdict(_normalized_item_for_save(x)) for x in items]
        items_blob = _encrypt_blob(json.dumps(serialized, ensure_ascii=False).encode("utf-8"), enc_key, mac_key)

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO password_vault(vault_name, salt, verifier_blob, items_blob, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(vault_name)
                DO UPDATE SET
                    salt=excluded.salt,
                    verifier_blob=excluded.verifier_blob,
                    items_blob=excluded.items_blob,
                    updated_at=excluded.updated_at
                """,
                (VAULT_NAME, salt, verifier_blob, items_blob, _now_iso()),
            )

    def load_settings(self) -> VaultSettings:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT vault_name, auto_lock_minutes, copy_ttl_seconds, default_gen_length, gen_charset_flags
                FROM password_vault_settings
                WHERE vault_name = ?
                """,
                (VAULT_NAME,),
            ).fetchone()
        if row is None:
            settings = VaultSettings()
            self.save_settings(settings)
            return settings
        return VaultSettings(
            vault_name=str(row["vault_name"] or VAULT_NAME),
            auto_lock_minutes=int(row["auto_lock_minutes"] or 5),
            copy_ttl_seconds=int(row["copy_ttl_seconds"] or 30),
            default_gen_length=int(row["default_gen_length"] or 16),
            gen_charset_flags=str(row["gen_charset_flags"] or "upper,lower,digits,symbols"),
        )

    def save_settings(self, settings: VaultSettings) -> None:
        normalized = VaultSettings(
            vault_name=VAULT_NAME,
            auto_lock_minutes=_clamp(settings.auto_lock_minutes, 1, 30),
            copy_ttl_seconds=_clamp(settings.copy_ttl_seconds, 10, 120),
            default_gen_length=_clamp(settings.default_gen_length, 8, 64),
            gen_charset_flags=settings.gen_charset_flags or "upper,lower,digits,symbols",
        )
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO password_vault_settings(
                    vault_name, auto_lock_minutes, copy_ttl_seconds, default_gen_length, gen_charset_flags, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(vault_name)
                DO UPDATE SET
                    auto_lock_minutes=excluded.auto_lock_minutes,
                    copy_ttl_seconds=excluded.copy_ttl_seconds,
                    default_gen_length=excluded.default_gen_length,
                    gen_charset_flags=excluded.gen_charset_flags,
                    updated_at=excluded.updated_at
                """,
                (
                    normalized.vault_name,
                    normalized.auto_lock_minutes,
                    normalized.copy_ttl_seconds,
                    normalized.default_gen_length,
                    normalized.gen_charset_flags,
                    _now_iso(),
                ),
            )

    def _init_db(self) -> None:
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS password_vault (
                    vault_name TEXT PRIMARY KEY,
                    salt BLOB NOT NULL,
                    verifier_blob BLOB NOT NULL,
                    items_blob BLOB NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS password_vault_settings (
                    vault_name TEXT PRIMARY KEY,
                    auto_lock_minutes INTEGER NOT NULL,
                    copy_ttl_seconds INTEGER NOT NULL,
                    default_gen_length INTEGER NOT NULL,
                    gen_charset_flags TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _get_conn(self) -> sqlite3.Connection:
        self._init_db()
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_row(self) -> sqlite3.Row | None:
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT vault_name, salt, verifier_blob, items_blob FROM password_vault WHERE vault_name = ?",
                (VAULT_NAME,),
            ).fetchone()


def evaluate_password_strength(password: str) -> StrengthLevel:
    pwd = password or ""
    if len(pwd) < 8:
        return "弱"
    types = 0
    if any(c.islower() for c in pwd):
        types += 1
    if any(c.isupper() for c in pwd):
        types += 1
    if any(c.isdigit() for c in pwd):
        types += 1
    if any(not c.isalnum() for c in pwd):
        types += 1

    weak_patterns = {"123456", "12345678", "password", "qwerty", "admin", "111111"}
    if pwd.lower() in weak_patterns:
        return "弱"
    if len(pwd) >= 12 and types >= 3:
        return "强"
    if len(pwd) >= 10 and types >= 2:
        return "中"
    return "弱"


def generate_password(length: int, use_upper: bool, use_lower: bool, use_digits: bool, use_symbols: bool) -> str:
    pools: list[str] = []
    if use_upper:
        pools.append(string.ascii_uppercase)
    if use_lower:
        pools.append(string.ascii_lowercase)
    if use_digits:
        pools.append(string.digits)
    if use_symbols:
        pools.append("!@#$%^&*()-_=+[]{};:,.?")
    if not pools:
        pools.append(string.ascii_letters + string.digits)
    target_len = _clamp(length, 8, 64)

    chars: list[str] = [secrets.choice(pool) for pool in pools]
    combined = "".join(pools)
    while len(chars) < target_len:
        chars.append(secrets.choice(combined))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def normalize_item(
    site: str,
    account: str,
    password: str,
    note: str,
    item_id: str | None = None,
    tags: list[str] | None = None,
    favorite: bool = False,
    last_used_at: str | None = None,
) -> VaultItem:
    clean_site = site.strip()
    clean_account = account.strip()
    clean_password = password.strip()
    if not clean_site:
        raise ValueError("站点/用途不能为空")
    if not clean_password:
        raise ValueError("密码不能为空")
    return VaultItem(
        item_id=item_id or str(uuid4()),
        site=clean_site,
        account=clean_account,
        password=clean_password,
        note=note.strip(),
        tags=_normalize_tags(tags or []),
        favorite=bool(favorite),
        strength=evaluate_password_strength(clean_password),
        updated_at=_now_iso(),
        last_used_at=last_used_at,
    )


def charset_flags_to_tuple(flags: str) -> tuple[bool, bool, bool, bool]:
    vals = {x.strip() for x in flags.split(",") if x.strip()}
    return ("upper" in vals, "lower" in vals, "digits" in vals, "symbols" in vals)


def tuple_to_charset_flags(use_upper: bool, use_lower: bool, use_digits: bool, use_symbols: bool) -> str:
    vals: list[str] = []
    if use_upper:
        vals.append("upper")
    if use_lower:
        vals.append("lower")
    if use_digits:
        vals.append("digits")
    if use_symbols:
        vals.append("symbols")
    return ",".join(vals)


def _derive_keys(master_password: str, salt: bytes) -> tuple[bytes, bytes]:
    block = hashlib.pbkdf2_hmac("sha256", master_password.encode("utf-8"), salt, PBKDF2_ROUNDS, dklen=64)
    return block[:32], block[32:]


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        ctr = counter.to_bytes(4, "big")
        out.extend(hashlib.sha256(enc_key + nonce + ctr).digest())
        counter += 1
    return bytes(out[:length])


def _encrypt_blob(data: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    stream = _keystream(enc_key, nonce, len(data))
    cipher = bytes(a ^ b for a, b in zip(data, stream))
    mac = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    return nonce + cipher + mac


def _decrypt_blob(blob: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    if len(blob) < NONCE_BYTES + MAC_BYTES:
        raise VaultCorruptedError("密文长度异常")
    nonce = blob[:NONCE_BYTES]
    mac = blob[-MAC_BYTES:]
    cipher = blob[NONCE_BYTES:-MAC_BYTES]
    expected = hmac.new(mac_key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise VaultAuthError("主密码错误或数据已损坏")
    stream = _keystream(enc_key, nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream))


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_tags(raw: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in raw:
        t = str(x).strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_strength(value: str, password: str) -> StrengthLevel:
    if value in ("弱", "中", "强"):
        return value  # type: ignore[return-value]
    return evaluate_password_strength(password)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _normalized_item_for_save(item: VaultItem) -> VaultItem:
    return VaultItem(
        item_id=item.item_id,
        site=item.site.strip(),
        account=item.account.strip(),
        password=item.password,
        note=item.note.strip(),
        tags=_normalize_tags(item.tags),
        favorite=bool(item.favorite),
        strength=evaluate_password_strength(item.password),
        updated_at=item.updated_at or _now_iso(),
        last_used_at=item.last_used_at,
    )
