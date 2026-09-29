"""转换器：干净 HTML 片段 → Markdown。适配器可插拔。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Protocol

from markdownify import markdownify as _md


class Converter(Protocol):
    name: str

    def convert(self, html_fragment: str) -> str: ...


class MarkdownifyConverter:
    name = "markdownify"

    def convert(self, html_fragment: str) -> str:
        return _md(html_fragment, heading_style="ATX", code_language_callback=_code_lang)


class HtmlToMdConverter:
    """调用 HTML_TO_MD 项目的 html_fragment_to_markdown（进程内）。"""

    name = "html_to_md"
    _PROJECT = Path(r"D:\My_Projects\HTML_TO_MD")

    def __init__(self):
        pandoc_py = self._PROJECT / "html_to_md" / "pandoc.py"
        if not pandoc_py.exists():
            raise FileNotFoundError(f"HTML_TO_MD 项目未找到: {pandoc_py}")
        spec = importlib.util.spec_from_file_location("html_to_md_pandoc", pandoc_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self._fn = mod.html_fragment_to_markdown

    def convert(self, html_fragment: str) -> str:
        return self._fn(html_fragment)


def get_converter(name: str = "markdownify") -> Converter:
    if name == "html_to_md":
        try:
            return HtmlToMdConverter()
        except Exception as e:
            print(f"[warn] html_to_md 不可用（{e}），回落 markdownify")
            return MarkdownifyConverter()
    return MarkdownifyConverter()


def _code_lang(el) -> str | None:
    classes = el.get("class") or []
    for c in classes:
        if c.startswith("language-"):
            return c[len("language-"):]
    return el.get("data-lang")
