"""正文提取：剥样板，只剩承载文档语义的正文。"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

import re

# 整页范围剥除的样板标签
_STRIP_TAGS = ["script", "style", "noscript", "nav", "footer", "aside", "header", "form", "iframe"]

# 常见样板容器选择器（站点配置包可追加）
_STRIP_SELECTORS = [
    "[role=navigation]",
    "[role=banner]",
    "[role=contentinfo]",
    "[role=search]",
    ".sidebar",
    ".toc",
    ".breadcrumb",
    ".breadcrumbs",
    ".menu",
    ".navbar",
    ".header",
    ".footer",
    ".pagination",
    ".advertisement",
    "a.headerlink",
    ".headerlink",
    "[class*=banner]",
    "[id*=sidebar]",
    "[class*=sidebar]",
]

# 正文候选容器，按优先级
_CONTENT_SELECTORS = [
    "main",
    "article",
    "[role=main]",
    ".document",
    ".rst-content",
    ".md-content",
    ".main-content",
    ".body",
    "#content",
    ".content",
]


def extract_content(html: str, extra_strip_selectors: list[str] | None = None) -> str:
    """返回干净正文 HTML（可能包含 img/a 等内联标签）。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in _STRIP_TAGS:
        for el in soup.find_all(tag):
            el.decompose()
    selectors = _STRIP_SELECTORS + (extra_strip_selectors or [])
    for sel in selectors:
        for el in soup.select(sel):
            el.decompose()
    _strip_vb(soup)
    _dedupe_code_blocks(soup)

    container = _find_content_container(soup)
    return container.decode_contents() if container else soup.body.decode_contents() if soup.body else str(soup)


def _strip_vb(soup: BeautifulSoup) -> None:
    """剥掉 Visual Basic 代码块与页签（语料库只保留 C#）。"""
    for code in soup.find_all("code"):
        classes = " ".join(code.get("class") or [])
        if re.search(r"\b(vb|lang-vb|visualbasic|vbnet)\b", classes, re.I):
            target = code.find_parent("pre") or code
            target.decompose()
    # 多语言页签里 VB 的标题/面板（如 <li><a>Visual Basic</a></li> 或 div[title=Visual Basic]）
    for el in soup.find_all(attrs={"title": re.compile(r"visual\s*basic", re.I)}):
        el.decompose()
    # Learn 站交互残渣（工具栏/评分/助手入口/反馈区）整体剥掉；含标题的保留
    for el in soup.find_all(attrs={"data-bi-name": True}):
        if el.find(["h1", "h2"]):
            continue
        target = el.find_parent("li") or el
        target.decompose()
    # 语言切换按钮列表（data-bi-name="lang-*"）是 UI 样板，整块剥掉
    for el in soup.find_all(attrs={"data-bi-name": re.compile(r"^lang-", re.I)}):
        target = el.find_parent("ul") or el.find_parent("li") or el
        target.decompose()


def _dedupe_code_blocks(soup: BeautifulSoup) -> None:
    """同页重复代码块（API 参考的多目标框架 data-moniker 变体）只留第一份。"""
    seen: set[str] = set()
    for pre in soup.find_all("pre"):
        key = re.sub(r"\s+", " ", pre.get_text()).strip()
        if key and key in seen:
            pre.decompose()
        else:
            seen.add(key)


def _find_content_container(soup: BeautifulSoup) -> Tag | None:
    best: Tag | None = None
    best_len = 0
    for sel in _CONTENT_SELECTORS:
        for el in soup.select(sel):
            text_len = len(el.get_text(strip=True))
            if text_len > best_len:
                best, best_len = el, text_len
        if best is not None and best_len > 100:
            return best
    # 兜底：取文本量最大的块级容器
    for el in soup.find_all(["div", "section"]):
        text_len = len(el.get_text(strip=True))
        if text_len > best_len:
            best, best_len = el, text_len
    return best


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""
