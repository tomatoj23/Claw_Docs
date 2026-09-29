"""管线编排：抓取 → raw/ 完整镜像 → 去样板 → 取舍 → 转换 → 链接改写 → 语料库落盘。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from .converter import Converter
from .crawler import Asset, Crawler, Page
from .curation import Verdict, curate
from .extract import extract_content, extract_title
from .urls import normalize_url, relpath_between, root_prefix, strip_fragment, url_to_relpath


def run(
    start_url: str,
    out_root: Path,
    mode: str = "full",
    converter: Converter | None = None,
    keep_images: bool = True,
    max_pages: int = 1000,
) -> Path:
    slug = _slug(start_url)
    corpus = Path(out_root) / slug
    raw_dir = corpus / "raw"
    prefix = root_prefix(start_url)

    crawler = Crawler(start_url)
    pages, assets = crawler.crawl(max_pages=max_pages)

    # 路径冲突消解：不同 URL 映射到同一路径时加序号后缀（如 / 与 /index.html）
    relpaths: dict[str, str] = {}
    used: set[str] = set()
    for page in pages:
        rel = url_to_relpath(page.url, prefix)
        if rel in used:
            stem = rel.removesuffix(".md")
            n = 2
            while f"{stem}-{n}.md" in used:
                n += 1
            rel = f"{stem}-{n}.md"
        used.add(rel)
        relpaths[page.url] = rel

    # 1. raw/ 完整镜像（除视频），一页不删
    for page in pages:
        raw_path = raw_dir / (relpaths[page.url].removesuffix(".md") + ".html")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(page.html, encoding="utf-8")

    # 图片落盘
    asset_map: dict[str, str] = {}
    for asset in assets:
        if asset.kind == "image" and asset.local_path and getattr(asset, "data", None):
            if not keep_images:
                continue
            p = corpus / asset.local_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(asset.data)
            asset_map[normalize_url(asset.url)] = asset.local_path

    # 2. 取舍 + 正文提取
    results: list[tuple[Page, str, Verdict, str]] = []  # page, content_html, verdict, title
    for page in pages:
        content = extract_content(page.html)
        verdict = (
            Verdict("kept", "mode=full")
            if mode == "full"
            else curate(page.url, page.html, content)
        )
        results.append((page, content, verdict, extract_title(page.html)))

    kept_urls = {strip_fragment(p.url): relpaths[p.url] for p, _, v, _ in results if v.status == "kept"}

    # 3. 转换 + 链接改写，写语料库
    for page, content, verdict, title in results:
        md_rel = relpaths[page.url]
        md_path = corpus / md_rel
        md_path.parent.mkdir(parents=True, exist_ok=True)
        if verdict.status == "kept":
            rewritten = _rewrite_links(content, page.url, md_rel, kept_urls, asset_map)
            md_text = (converter or _default_converter()).convert(rewritten)
            # 正文缺一级标题时才补标题，避免与页内 h1 重复
            if title and not re.match(r"\s*# ", md_text):
                md_text = f"# {title}\n\n{md_text}"
            md_path.write_text(md_text, encoding="utf-8")

    # 4. manifest.json + linkmap.json
    manifest = {
        "start_url": start_url,
        "mode": mode,
        "pages": [
            {
                "url": p.url,
                "local_path": relpaths[p.url],
                "sha256": p.sha256,
                "fetched_at": p.fetched_at,
                "title": t,
                "status": v.status,
                "reason": v.reason,
            }
            for p, _, v, t in results
        ],
        "failed": crawler.failed,
        "assets": [
            {"url": a.url, "kind": a.kind, "local_path": a.local_path, "note": a.note}
            for a in assets
        ],
    }
    (corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    linkmap = {
        strip_fragment(p.url): (relpaths[p.url] if v.status == "kept" else None)
        for p, _, v, _ in results
    }
    (corpus / "linkmap.json").write_text(
        json.dumps(linkmap, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return corpus


def _rewrite_links(
    content_html: str,
    page_url: str,
    page_md_rel: str,
    kept_urls: dict[str, str],
    asset_map: dict[str, str],
) -> str:
    """站内链接改写为本地 .md 相对路径；指向 rejected 的标注不造死链；图片改本地相对路径。"""
    soup = BeautifulSoup(content_html, "lxml")

    for a in soup.find_all("a", href=True):
        href = strip_fragment(a["href"])
        if re.match(r"^(mailto:|javascript:|#)", a["href"]):
            continue
        from urllib.parse import urljoin

        abs_url = normalize_url(urljoin(page_url, href))
        if abs_url in kept_urls:
            target = kept_urls[abs_url]
            frag = _fragment(a["href"])
            rel = relpath_between(target, page_md_rel)
            a["href"] = rel + (f"#{frag}" if frag else "")
        elif _is_internal(abs_url, page_url):
            # 指向被拒/未抓页面：保留文本，标注，不造死链
            a.string = f"{a.get_text()}（未收录）"
            a.unwrap()

    for img in soup.find_all("img", src=True):
        from urllib.parse import urljoin

        abs_url = normalize_url(urljoin(page_url, img["src"]))
        if abs_url in asset_map:
            img["src"] = relpath_between(asset_map[abs_url], page_md_rel)

    return str(soup)


def _fragment(href: str) -> str:
    return href.split("#", 1)[1] if "#" in href else ""


def _is_internal(url: str, page_url: str) -> bool:
    from urllib.parse import urlparse

    return urlparse(url).netloc.lower() == urlparse(page_url).netloc.lower()


def _slug(start_url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(start_url)
    seg = p.path.strip("/").replace("/", "-").removesuffix(".html") or "index"
    return f"{p.netloc.replace(':', '-')}-{seg}"


def _default_converter():
    from .converter import get_converter

    return get_converter("markdownify")
