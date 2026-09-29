"""接缝 1 的共享 fixture：本地静态 HTTP 服务 + CLI 调用助手。"""

from __future__ import annotations

import http.server
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_server():
    """把 tests/fixtures/ 作为站点根起一个本地 HTTP 服务，返回 base URL。"""

    def free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    port = free_port()

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FIXTURES), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=5)


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """真实调用 CLI（python -m docs_mirror），测试与实际使用同一入口。"""
    return subprocess.run(
        [sys.executable, "-m", "docs_mirror", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def find_corpus(out_root) -> Path:
    """CLI 会在 out_root 下产出恰好一个语料库目录，测试直接用它。"""
    dirs = [p for p in Path(out_root).iterdir() if p.is_dir()]
    assert len(dirs) == 1, f"期望恰好一个语料库目录，实际: {dirs}"
    return dirs[0]
