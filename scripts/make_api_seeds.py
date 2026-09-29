"""从微软官方 sitemap 生成 API 参考种子清单（去版本视图变体、剔除 VB）。"""

from __future__ import annotations

import re
import sys

import requests

UA = {"User-Agent": "docs-mirror/0.1"}
SITEMAP_INDEX = "https://learn.microsoft.com/_sitemaps/sitemapindex.xml"
API_PREFIX = "https://learn.microsoft.com/en-us/dotnet/api/"


def main(out_file: str = "seeds-api-core.txt") -> int:
    idx = requests.get(SITEMAP_INDEX, timeout=30, headers=UA).text
    subs = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx) if re.search(r"dotnet_en-us_\d+\.xml$", u)]
    print(f"dotnet en-us 子 sitemap: {len(subs)}")

    names: set[str] = set()
    for sm in subs:
        body = requests.get(sm, timeout=30, headers=UA).text
        for loc in re.findall(r"<loc>([^<]+)</loc>", body):
            if loc.startswith(API_PREFIX):
                names.add(loc[len(API_PREFIX):].split("?")[0].rstrip("/").lower())

    def wanted(n: str) -> bool:
        if n.startswith("microsoft.visualbasic"):
            return False
        return n.startswith(("system", "microsoft.win32", "microsoft.csharp", "microsoft.extensions"))

    sel = sorted(n for n in names if wanted(n))
    with open(out_file, "w", encoding="utf-8") as f:
        for n in sel:
            f.write(API_PREFIX + n + "\n")
    print(f"种子写入 {out_file}: {len(sel)} 条（System.* + Microsoft 核心，剔除 VB）")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
