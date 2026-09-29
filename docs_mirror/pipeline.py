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
from .urls import canonical_url, normalize_url, relpath_between, root_prefix, strip_fragment, url_to_relpath


def run(
    start_url: str,
    out_root: Path,
    mode: str = "full",
    converter: Converter | None = None,
    keep_images: bool = True,
    max_pages: int = 1000,
    scope: list[str] | None = None,
) -> Path:
    slug = _slug(start_url)
    corpus = Path(out_root) / slug
    corpus.mkdir(parents=True, exist_ok=True)
    raw_dir = corpus / "raw"
    prefix = root_prefix(start_url)

    crawler = Crawler(start_url, scope_prefixes=scope)
    pages, assets = crawler.crawl(max_pages=max_pages)
    if not pages and crawler.failed:
        raise RuntimeError(
            f"零页抓取成功（失败 {len(crawler.failed)} 条，多为限速）。"
            f"首条: {crawler.failed[0]['error'][:120]}"
        )

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

    kept_urls = {canonical_url(p.url): relpaths[p.url] for p, _, v, _ in results if v.status == "kept"}

    # 3. 转换 + 链接改写，写语料库
    for page, content, verdict, title in results:
        md_rel = relpaths[page.url]
        md_path = corpus / md_rel
        md_path.parent.mkdir(parents=True, exist_ok=True)
        if verdict.status == "kept":
            rewritten = _rewrite_links(content, page.url, md_rel, kept_urls, asset_map)
            rewritten = _preserve_anchors(rewritten)
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
        "truncated": crawler.truncated,
        "assets": [
            {"url": a.url, "kind": a.kind, "local_path": a.local_path, "note": a.note}
            for a in assets
        ],
    }
    (corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    linkmap = {
        canonical_url(p.url): (relpaths[p.url] if v.status == "kept" else None)
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

        abs_url = canonical_url(urljoin(page_url, href))
        if abs_url in kept_urls:
            target = kept_urls[abs_url]
            frag = _fragment(a["href"])
            rel = relpath_between(target, page_md_rel)
            a["href"] = rel + (f"#{frag}" if frag else "")
        elif _is_internal(abs_url, page_url):
            # 指向被拒/未抓页面：保留原 URL 供回查，标注不造本地死链
            a["href"] = abs_url
            a.string = f"{a.get_text()}（未收录）"

    for img in soup.find_all("img", src=True):
        from urllib.parse import urljoin

        abs_url = canonical_url(urljoin(page_url, img["src"]))
        if abs_url in asset_map:
            img["src"] = relpath_between(asset_map[abs_url], page_md_rel)

    return str(soup)


def _fragment(href: str) -> str:
    return href.split("#", 1)[1] if "#" in href else ""


def _preserve_anchors(html: str) -> str:
    """为带 id/name 的元素补显式 <span id> 锚点，转换后 #fragment 链接仍可定位。"""
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    for el in list(soup.find_all(attrs={"id": True})) + list(soup.find_all("a", attrs={"name": True})):
        anchor_id = el.get("id") or el.get("name")
        if not anchor_id or anchor_id in seen or el.name == "span" and el.get_text() == "":
            continue
        seen.add(anchor_id)
        span = soup.new_tag("span", id=anchor_id)
        el.insert_before(span)
    return str(soup)


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

    return get_converter("pandoc")


# ============ 种子清单驱动（超大 API 树专用） ============

import gzip
from concurrent.futures import ThreadPoolExecutor, as_completed

from .crawler import thread_session
from .urls import url_to_relpath as _u2r


def run_seeds(
    seeds: list[str],
    out_root: Path,
    slug: str,
    converter: Converter,
    prefix: str,
    workers: int = 8,
    keep_images: bool = True,
) -> Path:
    """sitemap 种子驱动的流式抓取：逐页抓取→gzip raw 落盘→转换→md 落盘，内存恒定。

    与 run() 的差异：不做 BFS 链接发现（种子即全集）、并发抓取、raw 用 gzip（约 1/10 体积）。
    链接改写目标集合 = 种子全集（提前算好），跨库/域外链接保留原 URL。
    """
    corpus = Path(out_root) / slug
    raw_dir = corpus / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # 种子全集即 linkmap：提前算好所有 URL→本地路径，转换时直接查
    relpaths: dict[str, str] = {}
    used: set[str] = set()
    for u in seeds:
        rel = _u2r(u, prefix)
        if rel in used:
            stem = rel.removesuffix(".md")
            n = 2
            while f"{stem}-{n}.md" in used:
                n += 1
            rel = f"{stem}-{n}.md"
        used.add(rel)
        relpaths[u] = rel
    kept_urls = {canonical_url(u): relpaths[u] for u in seeds}

    crawler = Crawler(seeds[0], scope_prefixes=["/"])
    manifest_pages: list[dict] = []
    seen_images: set[str] = set()

    def work(url: str) -> dict:
        """单页：抓→raw.gz→去样板→改链接→转 md→落盘。返回 manifest 行。"""
        rel = relpaths[url]
        # 断点续抓：md 已存在则跳过（raw.gz 同时存在），重启不丢进度
        md_path0 = corpus / rel
        if md_path0.exists():
            return {"url": url, "local_path": rel, "sha256": "", "fetched_at": "",
                    "title": "", "status": "kept", "reason": "resumed"}
        try:
            page = crawler.fetch_page(url, session=thread_session())
        except Exception as e:
            return {"url": url, "local_path": rel, "status": "error", "reason": str(e)[:200]}
        if page is None:
            err = crawler.failed[-1]["error"][:200] if crawler.failed else ""
            return {"url": url, "local_path": rel, "status": "error", "reason": err}

        assert page.html is not None
        raw_file = raw_dir / (rel.removesuffix(".md") + ".html.gz")
        raw_file.parent.mkdir(parents=True, exist_ok=True)
        raw_file.write_bytes(gzip.compress(page.html.encode("utf-8"), 6))

        content = extract_content(page.html)
        rewritten = _rewrite_links(content, page.url, rel, kept_urls, {})
        rewritten = _preserve_anchors(rewritten)
        md_text = converter.convert(rewritten)
        title = extract_title(page.html)
        if title and not re.match(r"\s*# ", md_text):
            md_text = f"# {title}\n\n{md_text}"
        md_path = corpus / rel
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")

        row = {
            "url": page.url,
            "local_path": rel,
            "sha256": page.sha256,
            "fetched_at": page.fetched_at,
            "title": title,
            "status": "kept",
            "reason": "seeds",
        }
        if keep_images:
            for img in page.images:
                _fetch_image(img, corpus, prefix, seen_images, crawler)
        return row

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(work, u): u for u in seeds}
        for i, fut in enumerate(as_completed(futures), 1):
            manifest_pages.append(fut.result())
            if i % 500 == 0:
                print(f"  ... {i}/{len(seeds)} 页完成", flush=True)

    manifest_pages.sort(key=lambda r: r["local_path"])
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "start_url": seeds[0],
                "mode": "seeds",
                "pages": manifest_pages,
                "failed": crawler.failed,
                "truncated": False,
                "assets": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (corpus / "linkmap.json").write_text(
        json.dumps({canonical_url(u): relpaths[u] for u in seeds}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return corpus


def _fetch_image(img_url: str, corpus: Path, prefix: str, seen: set[str], crawler: Crawler) -> None:
    """图片去重下载（线程安全由 GIL 保证 set/dict 原子操作）。"""
    from .urls import asset_relpath

    key = canonical_url(img_url)
    if key in seen:
        return
    seen.add(key)
    local = asset_relpath(img_url, prefix)
    dest = corpus / local
    if dest.exists():
        return
    try:
        resp = thread_session().get(img_url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
