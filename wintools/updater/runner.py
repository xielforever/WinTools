from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def main() -> int:
    args = _parse_args()
    log_file = Path(args.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        _log(log_file, "Updater started")
        _wait_for_process_exit(args.pid, timeout_seconds=120, log_file=log_file)

        app_dir = Path(args.app_dir)
        new_dir = Path(args.new_dir)
        backup_dir = Path(args.backup_dir)
        restart_exe = Path(args.restart_exe)

        next_dir = app_dir.parent / f"{app_dir.name}_next"
        if next_dir.exists():
            shutil.rmtree(next_dir, ignore_errors=True)

        _log(log_file, f"Copy new bundle to temp: {new_dir} -> {next_dir}")
        shutil.copytree(new_dir, next_dir)

        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        _log(log_file, f"Backup current app: {app_dir} -> {backup_dir}")
        shutil.move(str(app_dir), str(backup_dir))

        try:
            _remove_swap_target_if_present(app_dir, log_file)
            _log(log_file, f"Switch to new app: {next_dir} -> {app_dir}")
            shutil.move(str(next_dir), str(app_dir))
        except Exception:
            _log(log_file, "Switch failed, restoring backup")
            if app_dir.exists():
                shutil.rmtree(app_dir, ignore_errors=True)
            if backup_dir.exists():
                shutil.move(str(backup_dir), str(app_dir))
            raise

        _log(log_file, f"Restart app: {restart_exe}")
        subprocess.Popen([str(restart_exe)], close_fds=True)
        _log(log_file, "Update completed")
        return 0
    except Exception as exc:
        _log(log_file, f"Update failed: {exc!r}")
        return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WinTools external updater")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--new-dir", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--restart-exe", required=True)
    parser.add_argument("--log-file", required=True)
    return parser.parse_args()


def _wait_for_process_exit(pid: int, timeout_seconds: int, log_file: Path) -> None:
    start = time.time()
    while time.time() - start < timeout_seconds:
        if not _is_process_alive(pid):
            _log(log_file, f"Target process exited: pid={pid}")
            return
        time.sleep(0.5)
    raise TimeoutError(f"Wait for process timeout: pid={pid}")


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            out = (proc.stdout or "").strip()
            if not out:
                return False
            if out.lower().startswith("info:"):
                return False
            # tasklist returns a CSV row when process exists.
            return str(pid) in out
        except Exception:
            # Fall back to os.kill probe below.
            pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _log(log_file: Path, msg: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")


def _remove_swap_target_if_present(app_dir: Path, log_file: Path) -> None:
    if not app_dir.exists():
        return
    _log(log_file, f"Remove stale swap target: {app_dir}")
    last_error: Exception | None = None
    for _ in range(10):
        try:
            shutil.rmtree(app_dir, ignore_errors=False)
            return
        except FileNotFoundError:
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error is not None:
        raise last_error


if __name__ == "__main__":
    raise SystemExit(main())
