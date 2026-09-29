"""接缝 2：转换器契约。pandoc 与 markdownify 跑同一套不变量断言，保证可互换。"""

from __future__ import annotations

import re

import pytest

from docs_mirror.converter import find_pandoc, get_converter

# 同一输入 HTML 片段集合：标题 / 代码块 / 表格 / 链接 / 图片 / 加粗 / 列表
FRAGMENT = """
<h1>Title</h1>
<h2>Sub</h2>
<p>See <a href="api/ref.md">Ref</a> and <strong>bold</strong>.</p>
<pre><code class="language-python">x = 1</code></pre>
<table><thead><tr><th>Col</th></tr></thead><tbody><tr><td>cell1</td></tr></tbody></table>
<ul><li>item</li></ul>
<img src="assets/logo.svg" alt="Logo">
"""


def _converters():
    names = ["markdownify", "pandoc"]
    if not find_pandoc():
        names.remove("pandoc")
    return names


@pytest.fixture(params=_converters())
def converter(request):
    return get_converter(request.param)


class TestConverterContract:
    """两个适配器对同一片段输出的 md 必须满足同一组不变量。"""

    def test_headings_atx(self, converter):
        md = converter.convert(FRAGMENT)
        assert re.search(r"^# Title$", md, re.M)
        assert re.search(r"^## Sub$", md, re.M)

    def test_code_block_with_language(self, converter):
        md = converter.convert(FRAGMENT)
        assert re.search(r"```\s*python", md)
        assert "x = 1" in md

    def test_table_content_survives(self, converter):
        md = converter.convert(FRAGMENT)
        assert "| Col" in md
        assert "cell1" in md

    def test_link_and_bold(self, converter):
        md = converter.convert(FRAGMENT)
        assert "[Ref](api/ref.md)" in md
        assert "**bold**" in md

    def test_list_item(self, converter):
        md = converter.convert(FRAGMENT)
        assert re.search(r"^[-*] item$", md, re.M)

    def test_image(self, converter):
        md = converter.convert(FRAGMENT)
        assert "![Logo](assets/logo.svg)" in md

    def test_no_exception_on_plain_fragment(self, converter):
        assert converter.convert("<p>just text</p>").strip() == "just text"


class TestPandocFidelity:
    """pandoc 专属：字形保真（smart 关死）。"""

    def test_glyphs_preserved(self):
        if not find_pandoc():
            pytest.skip("项目内 pandoc 未安装")
        md = get_converter("pandoc").convert("<p>A -- B and \"q\" &mdash; ok</p>")
        assert "A -- B" in md
        assert '"q"' in md
        assert "— ok" in md


class TestFallback:
    """pandoc 不可用时回落 markdownify 并给出提示。"""

    def test_falls_back_to_markdownify(self, monkeypatch, capsys):
        monkeypatch.setattr("docs_mirror.converter.find_pandoc", lambda: None)
        conv = get_converter("pandoc")
        assert conv.name == "markdownify"
        assert "回落 markdownify" in capsys.readouterr().out
