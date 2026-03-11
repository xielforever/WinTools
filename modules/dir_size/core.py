from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional


@dataclass(slots=True)
class DirSizeResult:
    path: str
    size_bytes: int


class ScanCancelled(Exception):
    """Raised when a user stops an in-progress scan."""


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def scan_directory_sizes(root_path: str, should_cancel: Optional[Callable[[], bool]] = None) -> List[DirSizeResult]:
    """Show only current level (root + direct subfolders), with recursive total size for each row."""
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")

    totals: Dict[Path, int] = {}

    # Single bottom-up walk to compute recursive size of every folder under root.
    for current_root, dirs, files in os.walk(root_path, topdown=False, onerror=None):
        if should_cancel is not None and should_cancel():
            raise ScanCancelled("Scan cancelled by user")

        current_path = Path(current_root)
        total_size = 0

        for filename in files:
            if should_cancel is not None and should_cancel():
                raise ScanCancelled("Scan cancelled by user")

            file_path = current_path / filename
            try:
                total_size += file_path.stat().st_size
            except PermissionError:
                continue
            except FileNotFoundError:
                continue
            except OSError:
                continue

        for dirname in dirs:
            child_path = current_path / dirname
            total_size += totals.get(child_path, 0)

        totals[current_path] = total_size

    # Keep output limited to current level: root + direct child folders.
    results: List[DirSizeResult] = []
    results.append(DirSizeResult(path=str(root), size_bytes=totals.get(root, 0)))

    try:
        entries = list(root.iterdir())
    except PermissionError as exc:
        raise PermissionError(f"Access denied: {root}") from exc

    for entry in entries:
        if should_cancel is not None and should_cancel():
            raise ScanCancelled("Scan cancelled by user")

        if not entry.is_dir():
            continue

        results.append(DirSizeResult(path=str(entry), size_bytes=totals.get(entry, 0)))

    results.sort(key=lambda item: item.size_bytes, reverse=True)
    return results