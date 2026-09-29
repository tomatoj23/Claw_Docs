"""CLI 入口：docs-mirror <url> [--out corpus] [--mode full|filtered]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .converter import get_converter
from .crawler import JsShellError
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docs-mirror", description="把文档站抓到本地 Markdown 语料库")
    parser.add_argument("url", help="站点起始 URL")
    parser.add_argument("--out", default="corpus", help="输出根目录（默认 corpus/）")
    parser.add_argument("--mode", choices=["full", "filtered"], default="full",
                        help="full=整站全要；filtered=取舍过滤混合站")
    parser.add_argument("--converter", choices=["markdownify", "html_to_md"], default="markdownify")
    parser.add_argument("--no-images", action="store_true", help="不下载图片")
    parser.add_argument("--max-pages", type=int, default=1000)
    args = parser.parse_args(argv)

    converter = get_converter(args.converter)
    try:
        corpus = run(
            args.url,
            Path(args.out),
            mode=args.mode,
            converter=converter,
            keep_images=not args.no_images,
            max_pages=args.max_pages,
        )
    except JsShellError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    n_kept = sum(1 for p in _manifest_pages(corpus) if p["status"] == "kept")
    n_rej = sum(1 for p in _manifest_pages(corpus) if p["status"] == "rejected")
    print(f"语料库完成: {corpus}")
    print(f"  kept={n_kept} rejected={n_rej} converter={converter.name}")
    return 0


def _manifest_pages(corpus: Path) -> list[dict]:
    import json

    return json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))["pages"]


if __name__ == "__main__":
    sys.exit(main())
