"""安装项目内 pandoc 二进制到 tools/pandoc/（vendored，不装全局、不动 PATH）。

用法: python scripts/install_pandoc.py [--version 3.12]

只写本项目 tools/ 目录；下载 GitHub 官方发布包并解出 pandoc 可执行文件。
版本钉在 PANDOC_VERSION（当前最新稳定版），升级时改这里或传 --version。
"""

from __future__ import annotations

import argparse
import platform
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PANDOC_VERSION = "3.12"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools" / "pandoc"

_RELEASE_URL = "https://github.com/jgm/pandoc/releases/download/{v}/{asset}"


def _asset_name(version: str) -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows" and machine in ("amd64", "x86_64"):
        return f"pandoc-{version}-windows-x86_64.zip"
    if system == "linux" and machine in ("amd64", "x86_64"):
        return f"pandoc-{version}-linux-amd64.tar.gz"
    if system == "darwin" and machine == "arm64":
        return f"pandoc-{version}-arm64-macOS.zip"
    if system == "darwin":
        return f"pandoc-{version}-x86_64-macOS.zip"
    sys.exit(f"[error] 不支持的平台: {system}/{machine}，请手动下载 pandoc 放入 {TOOLS_DIR}")


def _extract(archive: Path, dest: Path) -> Path:
    """从发布包解出 pandoc 可执行文件，返回其路径。"""
    exe_names = ("pandoc.exe", "pandoc")
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            members = [n for n in z.namelist() if Path(n).name in exe_names]
            if not members:
                sys.exit(f"[error] 压缩包内未找到 pandoc: {archive}")
            data = z.read(members[0])
            out = dest / Path(members[0]).name
    else:
        with tarfile.open(archive) as t:
            members = [m for m in t.getmembers() if Path(m.name).name in exe_names]
            if not members:
                sys.exit(f"[error] 压缩包内未找到 pandoc: {archive}")
            f = t.extractfile(members[0])
            data = f.read()
            out = dest / Path(members[0]).name
    dest.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    if not out.name.endswith(".exe"):
        out.chmod(0o755)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="安装项目内 pandoc 到 tools/pandoc/")
    ap.add_argument("--version", default=PANDOC_VERSION, help=f"pandoc 版本（默认 {PANDOC_VERSION}）")
    args = ap.parse_args()

    existing = [p for p in (TOOLS_DIR / "pandoc.exe", TOOLS_DIR / "pandoc") if p.is_file()]
    if existing:
        print(f"[skip] 已存在 {existing[0]}，升级请先删除 tools/pandoc/")
        return 0

    asset = _asset_name(args.version)
    url = _RELEASE_URL.format(v=args.version, asset=asset)
    print(f"下载 {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset
        urllib.request.urlretrieve(url, archive)
        exe = _extract(archive, TOOLS_DIR)
    print(f"安装完成: {exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
