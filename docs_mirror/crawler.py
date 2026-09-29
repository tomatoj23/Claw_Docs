"""爬虫：抓页面、下图片、记清单，产出完整镜像（除视频）。"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .urls import asset_relpath, canonical_url, is_internal, normalize_url, root_prefix, strip_fragment

USER_AGENT = "docs-mirror/0.1 (local docs archiver)"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m3u8"}
JS_SHELL_MARKERS = ('id="root"', 'id="app"', "__NEXT_DATA__", "ng-app")


@dataclass
class Page:
    url: str
    html: str
    sha256: str
    fetched_at: str
    links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)


@dataclass
class Asset:
    url: str
    kind: str  # image | video
    local_path: str | None  # 下载后的库内相对路径；video 恒为 None
    note: str | None = None
    data: bytes | None = None


class JsShellError(RuntimeError):
    """疑似 JS 渲染站，纯 HTTP 抓不到正文。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def looks_like_js_shell(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    body_text = soup.get_text(strip=True)
    if len(body_text) > 200:
        return False
    lowered = html.lower()
    return any(m in lowered for m in JS_SHELL_MARKERS)


class Crawler:
    def __init__(
        self,
        start_url: str,
        delay: float = 0.2,
        timeout: float = 20.0,
        scope_prefixes: list[str] | None = None,
    ):
        self.start_url = normalize_url(start_url)
        self.prefix = root_prefix(start_url)
        # 抓取范围：默认只在起始 URL 的目录树内（防止大域爬爆），可用 scope 覆盖
        self.scope_prefixes = scope_prefixes if scope_prefixes is not None else [self.prefix]
        self.failed: list[dict] = []
        self.truncated = False
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _in_scope(self, url: str) -> bool:
        path = urlparse(url).path
        for p in self.scope_prefixes:
            if path.startswith(p) or path.rstrip("/") == p.rstrip("/"):
                return True
        return False

    def crawl(self, max_pages: int = 1000) -> tuple[list[Page], list[Asset]]:
        pages: list[Page] = []
        assets: dict[str, Asset] = {}
        seen: set[str] = set()
        queue = [self.start_url]

        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            key = canonical_url(url)
            if key in seen:
                continue
            seen.add(key)

            if self._ext(url) in VIDEO_EXT:
                assets.setdefault(url, Asset(url=url, kind="video", local_path=None, note="视频不下载"))
                continue

            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
            except requests.RequestException as e:
                # 单页失败（死链/超时）不拖垮整站，记入 manifest 供审计
                self.failed.append({"url": url, "error": str(e)})
                continue
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype:
                continue
            # 服务器没声明 charset 时 requests 默认 ISO-8859-1，会把 UTF-8 中文解码成乱码
            if "charset" not in ctype.lower():
                resp.encoding = resp.apparent_encoding or "utf-8"

            html = resp.text
            url = normalize_url(str(resp.url))  # 重定向后的最终 URL，尾斜杠保留
            seen.add(canonical_url(url))
            if not pages and looks_like_js_shell(html):
                raise JsShellError(
                    f"疑似 JS 渲染站点（正文为空壳）：{url}。一期不支持客户端渲染，请换静态文档源。"
                )

            page = Page(
                url=url,
                html=html,
                sha256=hashlib.sha256(resp.content).hexdigest(),
                fetched_at=_now(),
            )
            self._extract_refs(page)
            pages.append(page)

            for link in page.links:
                n = normalize_url(link)
                if canonical_url(n) not in seen and is_internal(n, self.start_url) and self._in_scope(n):
                    queue.append(n)
            for img in page.images:
                self._collect_asset(assets, img, "image")
            for vid in page.videos:
                assets.setdefault(
                    vid, Asset(url=vid, kind="video", local_path=None, note="视频不下载，仅记录原 URL")
                )

            if queue:
                time.sleep(self.delay)

        if queue:
            self.truncated = True
        return pages, self._download_images(list(assets.values()))

    def _extract_refs(self, page: Page) -> None:
        soup = BeautifulSoup(page.html, "lxml")
        base = page.url
        for a in soup.find_all("a", href=True):
            href = strip_fragment(urljoin(base, a["href"]))
            if urlparse(href).scheme in ("http", "https"):
                page.links.append(href)
        for img in soup.find_all("img", src=True):
            page.images.append(urljoin(base, img["src"]))
        for tag in soup.find_all(["video", "source"]):
            src = tag.get("src")
            if src:
                page.videos.append(urljoin(base, src))
        for a in soup.find_all("a", href=True):
            href = urljoin(base, a["href"])
            if self._ext(href) in VIDEO_EXT:
                page.videos.append(strip_fragment(href))

    def _collect_asset(self, assets: dict[str, Asset], url: str, kind: str) -> None:
        if self._ext(url) in VIDEO_EXT:
            assets.setdefault(url, Asset(url=url, kind="video", local_path=None, note="视频不下载"))
        else:
            assets.setdefault(url, Asset(url=url, kind=kind, local_path=asset_relpath(url, self.prefix)))

    def _download_images(self, assets: list[Asset]) -> list[Asset]:
        for asset in assets:
            if asset.kind != "image" or asset.local_path is None:
                continue
            try:
                resp = self.session.get(asset.url, timeout=self.timeout)
                resp.raise_for_status()
                asset.data = resp.content
            except requests.RequestException as e:
                asset.local_path = None
                asset.note = f"图片下载失败: {e}"
        return assets

    @staticmethod
    def _ext(url: str) -> str:
        path = urlparse(url).path.lower()
        dot = path.rfind(".")
        return path[dot:] if dot != -1 else ""
