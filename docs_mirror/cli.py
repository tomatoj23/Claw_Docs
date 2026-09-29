"""CLI 入口：docs-mirror [crawl] <url> | docs-mirror verify <corpus>"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .converter import get_converter
from .crawler import JsShellError
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docs-mirror", description="把文档站抓到本地 Markdown 语料库")
    sub = parser.add_subparsers(dest="command")

    p_crawl = sub.add_parser("crawl", help="抓取站点（可省略此子命令直接给 URL）")
    _add_crawl_args(p_crawl)
    p_verify = sub.add_parser("verify", help="校验语料库完整性与准确性")
    p_verify.add_argument("corpus", help="语料库目录（corpus/<slug>）")

    if argv is None:
        argv = sys.argv[1:]
    # 兼容裸 URL 调用：python -m docs_mirror <url> ... 自动补 crawl 子命令
    if argv and not argv[0].startswith("-") and argv[0] not in ("crawl", "verify"):
        argv = ["crawl", *argv]
    if not argv:
        argv = ["crawl", "-h"]

    args = parser.parse_args(argv)

    if args.command == "verify":
        from .verify import verify_corpus

        report = verify_corpus(Path(args.corpus))
        print(report.render())
        return 0 if report.ok else 1

    converter = get_converter(args.converter)

    if args.seeds_file:
        from .pipeline import run_seeds

        seeds = [
            line.strip()
            for line in Path(args.seeds_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        from .urls import root_prefix

        prefix = root_prefix(args.url)
        corpus = run_seeds(
            seeds,
            Path(args.out),
            _slug_of(args.url),
            converter,
            prefix=prefix,
            workers=args.workers,
            keep_images=not args.no_images,
        )
        print(f"语料库完成: {corpus}")
        print(f"  seeds={len(seeds)} converter={converter.name}")
        return 0

    try:
        corpus = run(
            args.url,
            Path(args.out),
            mode=args.mode,
            converter=converter,
            keep_images=not args.no_images,
            max_pages=args.max_pages,
            scope=args.scope,
        )
    except JsShellError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    n_kept = sum(1 for p in _manifest_pages(corpus) if p["status"] == "kept")
    n_rej = sum(1 for p in _manifest_pages(corpus) if p["status"] == "rejected")
    print(f"语料库完成: {corpus}")
    print(f"  kept={n_kept} rejected={n_rej} converter={converter.name}")
    return 0


def _add_crawl_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("url", help="站点起始 URL")
    p.add_argument("--out", default="corpus", help="输出根目录（默认 corpus/）")
    p.add_argument("--mode", choices=["full", "filtered"], default="full",
                   help="full=整站全要；filtered=取舍过滤混合站")
    p.add_argument("--converter", choices=["pandoc", "markdownify"], default="pandoc",
                   help="HTML→MD 转换器（默认 pandoc=项目内 tools/pandoc/）")
    p.add_argument("--no-images", action="store_true", help="不下载图片")
    p.add_argument("--max-pages", type=int, default=1000)
    p.add_argument("--scope", action="append", default=None,
                   help="抓取范围路径前缀，可多次（默认=起始 URL 目录树）")
    p.add_argument("--seeds-file", default=None,
                   help="种子 URL 清单文件（每行一个），用于超大树：跳过 BFS 直接按清单抓")
    p.add_argument("--workers", type=int, default=8, help="种子模式并发数（默认 8）")


def _slug_of(url: str) -> str:
    from urllib.parse import urlparse

    p = urlparse(url)
    seg = p.path.strip("/").replace("/", "-").removesuffix(".html") or "index"
    return f"{p.netloc.replace(':', '-')}-{seg}"


def _manifest_pages(corpus: Path) -> list[dict]:
    import json

    return json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))["pages"]


if __name__ == "__main__":
    sys.exit(main())
