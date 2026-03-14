from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LATEST_RELEASE_API = "https://api.github.com/repos/xielforever/WinTools/releases/latest"
TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
ASSET_PATTERN = re.compile(r"^WinTools-v\d+\.\d+\.\d+-windows-onedir\.zip$")


class UpdateError(RuntimeError):
    pass


@dataclass(slots=True)
class UpdateInfo:
    version_tag: str
    release_url: str
    asset_name: str
    asset_url: str
    asset_digest: Optional[str]
    published_at: str


@dataclass(slots=True)
class StagedPackage:
    version_tag: str
    release_url: str
    archive_path: Path
    extracted_dir: Path
    app_bundle_dir: Path


def is_onedir_runtime() -> bool:
    """Return True when running a PyInstaller one-dir bundle."""
    if not getattr(sys, "frozen", False):
        return False
    app_dir = Path(sys.executable).resolve().parent
    return (app_dir / "_internal").exists() and (app_dir / "WinTools.exe").exists()


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def check_for_update(current_version: str, skip_version: Optional[str] = None, timeout: int = 10) -> Optional[UpdateInfo]:
    current_tag = current_version if current_version.startswith("v") else f"v{current_version}"
    current_parts = _parse_tag(current_tag)
    if current_parts is None:
        return None

    req = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"WinTools/{current_version}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"检查更新失败：{exc}") from exc

    if bool(payload.get("prerelease")) or bool(payload.get("draft")):
        return None

    tag = str(payload.get("tag_name", "")).strip()
    latest_parts = _parse_tag(tag)
    if latest_parts is None:
        return None

    if skip_version and tag == skip_version:
        return None
    if latest_parts <= current_parts:
        return None

    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        raise UpdateError("发布资产数据格式异常")
    asset = _select_asset(assets)
    if asset is None:
        raise UpdateError("发布资产不完整：未找到 OneDir ZIP 包")

    digest = str(asset.get("digest", "")).strip() or None
    release_url = str(payload.get("html_url", "")).strip()
    published_at = str(payload.get("published_at", "")).strip()

    return UpdateInfo(
        version_tag=tag,
        release_url=release_url,
        asset_name=str(asset["name"]),
        asset_url=str(asset["browser_download_url"]),
        asset_digest=digest,
        published_at=published_at,
    )


def download_update(info: UpdateInfo, app_dir: Path) -> StagedPackage:
    staging_dir = app_dir / "data" / "updates" / "staging" / info.version_tag
    extracted_dir = app_dir / "data" / "updates" / "extracted" / info.version_tag
    archive_path = staging_dir / info.asset_name

    staging_dir.mkdir(parents=True, exist_ok=True)
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir, ignore_errors=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(
        info.asset_url,
        headers={"User-Agent": f"WinTools/{info.version_tag}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except Exception as exc:
        raise UpdateError(f"下载更新失败：{exc}") from exc

    archive_path.write_bytes(data)
    _verify_digest_if_present(archive_path, info.asset_digest)

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            bad_name = zf.testzip()
            if bad_name is not None:
                raise UpdateError(f"下载包损坏：{bad_name}")
            zf.extractall(extracted_dir)
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"解压更新包失败：{exc}") from exc

    app_bundle_dir = _locate_extracted_bundle(extracted_dir)
    _validate_bundle(app_bundle_dir)

    return StagedPackage(
        version_tag=info.version_tag,
        release_url=info.release_url,
        archive_path=archive_path,
        extracted_dir=extracted_dir,
        app_bundle_dir=app_bundle_dir,
    )


def launch_updater(staged: StagedPackage, current_pid: int, app_dir: Path) -> None:
    updater_exe = app_dir / "WinToolsUpdater.exe"
    if not updater_exe.exists():
        raise UpdateError("当前版本不支持自动更新：未找到 WinToolsUpdater.exe")

    runtime_updater_exe = _prepare_runtime_updater_exe(updater_exe)
    backup_dir = app_dir.parent / f"{app_dir.name}_bak"
    restart_exe = app_dir / "WinTools.exe"
    # Keep updater logs outside the app directory so the swap target stays absent
    # until the final rename from "<app>_next" -> "<app>".
    log_path = app_dir.parent / ".wintools-updater" / "update.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    args = [
        str(runtime_updater_exe),
        "--pid",
        str(current_pid),
        "--app-dir",
        str(app_dir),
        "--new-dir",
        str(staged.app_bundle_dir),
        "--backup-dir",
        str(backup_dir),
        "--restart-exe",
        str(restart_exe),
        "--log-file",
        str(log_path),
    ]
    try:
        subprocess.Popen(
            args,
            close_fds=True,
            cwd=str(runtime_updater_exe.parent),
            **_windows_subprocess_kwargs(),
        )
    except Exception as exc:
        raise UpdateError(f"启动更新器失败：{exc}") from exc


def _parse_tag(tag: str) -> Optional[tuple[int, int, int]]:
    m = TAG_PATTERN.match(tag.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _select_asset(assets: list[object]) -> Optional[dict[str, object]]:
    for item in assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        url = str(item.get("browser_download_url", "")).strip()
        if not ASSET_PATTERN.match(name):
            continue
        if not url:
            continue
        return item
    return None


def _verify_digest_if_present(archive_path: Path, digest: Optional[str]) -> None:
    if not digest:
        return
    digest = digest.strip().lower()
    if not digest.startswith("sha256:"):
        return
    expected = digest.split(":", 1)[1]
    actual = hashlib.sha256(archive_path.read_bytes()).hexdigest().lower()
    if actual != expected:
        raise UpdateError("下载包校验失败：SHA256 不匹配")


def _locate_extracted_bundle(extracted_dir: Path) -> Path:
    candidate = extracted_dir / "WinTools"
    if candidate.exists():
        return candidate
    for child in extracted_dir.iterdir():
        if child.is_dir() and (child / "WinTools.exe").exists():
            return child
    raise UpdateError("更新包结构无效：未找到应用目录")


def _validate_bundle(bundle_dir: Path) -> None:
    required = [bundle_dir / "WinTools.exe", bundle_dir / "_internal"]
    missing = [str(p.name) for p in required if not p.exists()]
    if missing:
        raise UpdateError(f"更新包结构无效：缺少 {', '.join(missing)}")


def _prepare_runtime_updater_exe(source_exe: Path) -> Path:
    runtime_dir = Path(tempfile.gettempdir()) / "WinToolsUpdaterRuntime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Best-effort cleanup for old updater copies.
    now = time.time()
    for stale in runtime_dir.glob("WinToolsUpdater-*.exe"):
        try:
            if now - stale.stat().st_mtime > 24 * 3600:
                stale.unlink()
        except Exception:
            pass

    runtime_exe = runtime_dir / f"WinToolsUpdater-{int(now)}.exe"
    try:
        shutil.copy2(source_exe, runtime_exe)
    except Exception as exc:
        raise UpdateError(f"准备更新器失败：{exc}") from exc
    return runtime_exe


def _windows_subprocess_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }
