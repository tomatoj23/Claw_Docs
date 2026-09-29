"""URL 与本地路径的映射规则。"""

from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote, urldefrag, urlparse

_HTML_EXT = re.compile(r"\.html?$", re.I)


def strip_fragment(url: str) -> str:
    return urldefrag(url)[0]


def normalize_url(url: str) -> str:
    """去 fragment；host 小写；路径保证以 / 开头。保留 query（极少数文档页需要）。"""
    url = strip_fragment(url)
    p = urlparse(url)
    path = unquote(p.path) or "/"
    return f"{p.scheme}://{p.netloc.lower()}{path}" + (f"?{p.query}" if p.query else "")


def is_internal(url: str, base_url: str) -> bool:
    return urlparse(url).netloc.lower() == urlparse(base_url).netloc.lower()


def root_prefix(start_url: str) -> str:
    """起始 URL 的目录前缀，如 /site-a/index.html -> /site-a/。语料库路径以此为根。"""
    path = unquote(urlparse(start_url).path)
    return path if path.endswith("/") else posixpath.dirname(path) + "/"


def url_to_relpath(url: str, prefix: str = "") -> str:
    """https://x/docs/api/foo.html -> docs/api/foo.md（剥离 prefix 后）；/docs/ -> docs/index.md。"""
    p = urlparse(url)
    path = unquote(p.path) or "/"
    if prefix and path.startswith(prefix):
        path = "/" + path[len(prefix):]
    if path.endswith("/"):
        path += "index"
    elif _HTML_EXT.search(path):
        path = _HTML_EXT.sub("", path)
    rel = path.lstrip("/")
    if not rel:
        rel = "index"
    return rel + ".md"


def asset_relpath(url: str, prefix: str = "") -> str:
    """图片 URL -> assets/ 下的相对路径（镜像站点路径，query 冲突时加短 hash）。"""
    p = urlparse(url)
    path = unquote(p.path) or "/asset"
    if prefix and path.startswith(prefix):
        path = path[len(prefix):]
    path = path.lstrip("/") or "asset"
    if path.startswith("assets/"):
        path = path[len("assets/"):]
    if p.query:
        root, ext = posixpath.splitext(path)
        path = f"{root}_{abs(hash(p.query)) % 10000:04d}{ext}"
    # 防目录穿越
    path = posixpath.normpath(path).lstrip("../")
    return posixpath.join("assets", path)


def relpath_between(target: str, current: str) -> str:
    """target 相对 current 所在目录的 posix 相对路径。两者都是库内相对路径（a/b.md）。"""
    base = posixpath.dirname(current) or "."
    return posixpath.relpath(target, base)
