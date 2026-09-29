"""取舍：启发式粗筛决定页面 kept/rejected，结果与理由记入清单。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import extract_title

# URL 命中即拒
_REJECT_URL_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"/blog(/|$|-)",
        r"/news(/|$|-)",
        r"/career",
        r"/job",
        r"/recruit",
        r"/pricing",
        r"/price",
        r"/about",
        r"/contact",
        r"/press",
        r"/event",
        r"/showcase",
        r"/testimonial",
        r"/download(/|$)",
        r"/community",
        r"/forum",
        r"/login",
        r"/signup",
        r"/register",
        r"/cart",
        r"/shop",
    ]
]

# 标题/正文命中即拒（营销、招聘、公告类）
_REJECT_TEXT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"招聘|加入我们|投递简历|我们正在招聘",
        r"融资|新产品发布|限时优惠|免费试用|立即购买|联系销售",
        r"\b(hiring|we'?re hiring|join us|careers?)\b",
        r"\b(pricing|get started free|book a demo)\b",
    ]
]

# URL 命中即留（文档核心区，压过文本误伤）
_KEEP_URL_PATTERNS = [
    re.compile(p, re.I)
    for p in [r"/docs?(/|$)", r"/api(/|$)", r"/reference", r"/manual", r"/guide", r"/tutorial", r"/handbook"]
]


@dataclass
class Verdict:
    status: str  # kept | rejected
    reason: str


def curate(url: str, page_html: str, content_html: str) -> Verdict:
    """对单页做取舍判定。content_html 为已去样板的正文。"""
    for pat in _REJECT_URL_PATTERNS:
        if pat.search(url):
            return Verdict("rejected", f"url-pattern: {pat.pattern}")
    for pat in _KEEP_URL_PATTERNS:
        if pat.search(url):
            return Verdict("kept", f"doc-url: {pat.pattern}")

    title = extract_title(page_html)
    text = f"{title}\n{_strip_tags(content_html)}"
    for pat in _REJECT_TEXT_PATTERNS:
        if pat.search(text):
            return Verdict("rejected", f"text-pattern: {pat.pattern}")

    # 正文太薄视为非文档页
    if len(_strip_tags(content_html).strip()) < 80:
        return Verdict("rejected", "too-thin: 正文不足 80 字符")

    return Verdict("kept", "default: 通过粗筛")


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)
