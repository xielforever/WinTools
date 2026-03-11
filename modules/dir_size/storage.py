from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TypedDict

from modules.dir_size.core import DirSizeResult

DB_FILE = Path("data") / "dir_size_history.db"


class Snapshot(TypedDict):
    id: int
    scanned_at: str
    root_path: str
    root_path_key: str
    root_size_bytes: int
    dir_count: int
    top_dirs: list[dict[str, int | str]]


class TrendPoint(TypedDict):
    scanned_at: str
    root_size_bytes: int


def _normalize_path(path: str) -> str:
    return str(Path(path).resolve()).lower()


def init_db() -> None:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT NOT NULL,
                root_path TEXT NOT NULL,
                root_path_key TEXT NOT NULL,
                root_size_bytes INTEGER NOT NULL,
                dir_count INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_top_dirs (
                run_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                FOREIGN KEY(run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scan_runs_root_time
            ON scan_runs(root_path_key, scanned_at)
            """
        )


def _get_conn() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def save_scan_snapshot(root_path: str, results: List[DirSizeResult]) -> Snapshot:
    abs_root = str(Path(root_path).resolve())
    normalized_root = _normalize_path(abs_root)

    root_size = 0
    for item in results:
        if _normalize_path(item.path) == normalized_root:
            root_size = item.size_bytes
            break

    scanned_at = datetime.now().isoformat(timespec="seconds")

    with _get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO scan_runs(scanned_at, root_path, root_path_key, root_size_bytes, dir_count)
            VALUES(?, ?, ?, ?, ?)
            """,
            (scanned_at, abs_root, normalized_root, root_size, len(results)),
        )
        run_id = int(cursor.lastrowid)

        top_rows = [(run_id, row.path, row.size_bytes) for row in results[:20]]
        conn.executemany(
            "INSERT INTO scan_top_dirs(run_id, path, size_bytes) VALUES(?, ?, ?)",
            top_rows,
        )

    snapshot: Snapshot = {
        "id": run_id,
        "scanned_at": scanned_at,
        "root_path": abs_root,
        "root_path_key": normalized_root,
        "root_size_bytes": root_size,
        "dir_count": len(results),
        "top_dirs": [{"path": row.path, "size_bytes": row.size_bytes} for row in results[:20]],
    }
    return snapshot


def load_last_snapshot(root_path: str) -> Optional[Snapshot]:
    target = _normalize_path(root_path)

    with _get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, scanned_at, root_path, root_path_key, root_size_bytes, dir_count
            FROM scan_runs
            WHERE root_path_key = ?
            ORDER BY scanned_at DESC, id DESC
            LIMIT 1
            """,
            (target,),
        ).fetchone()

        if row is None:
            return None

        top_rows = conn.execute(
            "SELECT path, size_bytes FROM scan_top_dirs WHERE run_id = ? ORDER BY size_bytes DESC",
            (int(row["id"]),),
        ).fetchall()

    snapshot: Snapshot = {
        "id": int(row["id"]),
        "scanned_at": str(row["scanned_at"]),
        "root_path": str(row["root_path"]),
        "root_path_key": str(row["root_path_key"]),
        "root_size_bytes": int(row["root_size_bytes"]),
        "dir_count": int(row["dir_count"]),
        "top_dirs": [{"path": str(x["path"]), "size_bytes": int(x["size_bytes"])} for x in top_rows],
    }
    return snapshot


def query_trend_points(root_path: str, limit: Optional[int] = None) -> list[TrendPoint]:
    target = _normalize_path(root_path)

    sql = """
        SELECT scanned_at, root_size_bytes
        FROM scan_runs
        WHERE root_path_key = ?
        ORDER BY scanned_at ASC, id ASC
    """
    params: list[object] = [target]

    if limit is not None and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [{"scanned_at": str(x["scanned_at"]), "root_size_bytes": int(x["root_size_bytes"])} for x in rows]