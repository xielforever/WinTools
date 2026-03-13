from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from modules.dir_size.core import ScanCancelled


@dataclass(slots=True)
class LargeFileResult:
    path: str
    size_bytes: int
    modified_at: str


@dataclass(slots=True)
class LargeFileScanStats:
    scanned_dirs: int = 0
    scanned_files: int = 0
    matched_files: int = 0
    errors: int = 0
    pruned_dirs: int = 0
    pruned_bytes_estimate: int = 0
    pruning_enabled: bool = False
    elapsed_ms: int = 0


ProgressCallback = Callable[[LargeFileScanStats, str], None]
MatchCallback = Callable[[LargeFileResult], None]


def scan_large_files(
    root_path: str,
    min_size_bytes: int,
    reliable_dir_totals: Optional[dict[str, int]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    on_progress: Optional[ProgressCallback] = None,
    on_match: Optional[MatchCallback] = None,
) -> tuple[list[LargeFileResult], LargeFileScanStats]:
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")
    if min_size_bytes < 0:
        raise ValueError("min_size_bytes must be >= 0")

    stats = LargeFileScanStats(pruning_enabled=bool(reliable_dir_totals))
    results: list[LargeFileResult] = []
    normalized_totals = {_normalize_path(k): int(v) for k, v in (reliable_dir_totals or {}).items()}

    started = time.perf_counter()

    def emit_progress(current_path: str) -> None:
        if on_progress is not None:
            on_progress(stats, current_path)

    for current_root, dirs, files in os.walk(str(root), topdown=True, followlinks=False):
        if should_cancel is not None and should_cancel():
            raise ScanCancelled("Scan cancelled by user")

        current_key = _normalize_path(current_root)
        stats.scanned_dirs += 1

        known_total = normalized_totals.get(current_key)
        if known_total is not None and known_total < min_size_bytes:
            # Reliable recursive total proves this subtree cannot contain files >= threshold.
            stats.pruned_dirs += 1
            stats.pruned_bytes_estimate += max(0, known_total)
            dirs[:] = []
            emit_progress(current_root)
            continue

        for filename in files:
            if should_cancel is not None and should_cancel():
                raise ScanCancelled("Scan cancelled by user")

            stats.scanned_files += 1
            file_path = Path(current_root) / filename

            try:
                file_stat = file_path.stat(follow_symlinks=False)
            except (PermissionError, FileNotFoundError, OSError):
                stats.errors += 1
                continue

            size_bytes = int(file_stat.st_size)
            if size_bytes < min_size_bytes:
                continue

            modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat(timespec="seconds")
            matched = LargeFileResult(
                path=str(file_path),
                size_bytes=size_bytes,
                modified_at=modified_at,
            )
            results.append(matched)
            stats.matched_files += 1
            if on_match is not None:
                on_match(matched)

            if stats.scanned_files % 200 == 0:
                emit_progress(str(file_path))

        emit_progress(current_root)

    results.sort(key=lambda item: item.size_bytes, reverse=True)
    stats.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return results, stats


def _normalize_path(path: str) -> str:
    return str(Path(path).resolve()).lower()
