"""转换器：干净 HTML 片段 → Markdown。适配器可插拔。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol

from markdownify import markdownify as _md

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 单次 pandoc 调用超时：挂起的二进制不得无限期冻结整批转换
PANDOC_TIMEOUT_SECONDS = 120


class Converter(Protocol):
    name: str

    def convert(self, html_fragment: str) -> str: ...


class MarkdownifyConverter:
    name = "markdownify"

    def convert(self, html_fragment: str) -> str:
        return _md(html_fragment, heading_style="ATX", code_language_callback=_code_lang)


class PandocConverter:
    """项目内 tools/pandoc/ 的 pandoc 二进制转换（scripts/install_pandoc.py 安装），
    不依赖全局 pandoc、不依赖其他项目。"""

    name = "pandoc"

    # 读写两侧关 smart：`--`、直引号等字形保持原文，不被改写成弯引号/长短破折号；
    # --wrap=none 不折行；--eol=lf 输出换行确定（跨平台产物一致）。
    _ARGS = ["-f", "html-smart", "-t", "gfm-smart", "--wrap=none", "--eol=lf"]

    def __init__(self, exe: Path | None = None):
        self._exe = exe or find_pandoc()
        if self._exe is None:
            raise FileNotFoundError(
                f"项目内 pandoc 未找到（{_PROJECT_ROOT / 'tools' / 'pandoc'}），"
                "先跑 python scripts/install_pandoc.py"
            )

    def convert(self, html_fragment: str) -> str:
        proc = subprocess.run(
            [str(self._exe), *self._ARGS],
            input=html_fragment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=PANDOC_TIMEOUT_SECONDS,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pandoc 转换失败: {proc.stderr.strip()}")
        return proc.stdout


def find_pandoc() -> Path | None:
    """定位项目内 vendored pandoc 二进制（只认 tools/pandoc/，不查全局 PATH）。"""
    tools = _PROJECT_ROOT / "tools" / "pandoc"
    for name in ("pandoc.exe", "pandoc"):
        p = tools / name
        if p.is_file():
            return p
    return None


def get_converter(name: str = "pandoc") -> Converter:
    if name == "pandoc":
        try:
            return PandocConverter()
        except Exception as e:
            print(f"[warn] 项目内 pandoc 不可用（{e}），回落 markdownify")
            return MarkdownifyConverter()
    return MarkdownifyConverter()


def _code_lang(el) -> str | None:
    """语言标注可能挂在 <pre> 或内层 <code> 上，两个都看。"""
    for node in (el, *el.find_all("code")):
        classes = node.get("class") or []
        for c in classes:
            if c.startswith("language-"):
                return c[len("language-"):]
        if node.get("data-lang"):
            return node.get("data-lang")
    return None
