"""校验语料库：完整性（抓全了吗）与准确性（转换对了吗）。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .extract import extract_content


@dataclass
class VerifyReport:
    corpus: Path
    problems: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems

    def render(self) -> str:
        lines = [f"校验: {self.corpus}", ""]
        lines.append("== 统计 ==")
        for k, v in self.stats.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        if self.problems:
            lines.append(f"== 问题 ({len(self.problems)}) ==")
            lines.extend(f"  ✗ {p}" for p in self.problems)
        else:
            lines.append("== 问题 == 无 ✓")
        return "\n".join(lines)


def verify_corpus(corpus: Path) -> VerifyReport:
    report = VerifyReport(corpus=corpus)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    pages = manifest["pages"]
    raw_dir = corpus / "raw"

    # ---------- 完整性 ----------
    report.stats["manifest 页数"] = len(pages)
    report.stats["抓取失败数"] = len(manifest.get("failed", []))
    report.stats["是否截断(truncated)"] = manifest.get("truncated", False)
    if manifest.get("truncated"):
        report.problems.append("抓取被 max-pages 截断，语料库可能不完整（manifest.truncated=true）")
    for f in manifest.get("failed", [])[:20]:
        report.problems.append(f"抓取失败: {f['url']} ({f.get('error', '')[:60]})")
    if len(manifest.get("failed", [])) > 20:
        report.problems.append(f"...另有 {len(manifest['failed']) - 20} 条失败，见 manifest.json")

    # raw/ 应覆盖 manifest 的每一页
    for p in pages:
        raw_path = raw_dir / (p["local_path"].removesuffix(".md") + ".html")
        if not raw_path.exists():
            report.problems.append(f"raw 缺页: {p['url']}（期望 {raw_path.relative_to(corpus)}）")

    # kept 页应有 md
    kept = [p for p in pages if p["status"] == "kept"]
    rejected = [p for p in pages if p["status"] == "rejected"]
    report.stats["kept / rejected"] = f"{len(kept)} / {len(rejected)}"
    for p in kept:
        if not (corpus / p["local_path"]).exists():
            report.problems.append(f"kept 页缺 md: {p['local_path']}")
    for p in rejected:
        if (corpus / p["local_path"]).exists():
            report.problems.append(f"rejected 页却存在 md（取舍不一致）: {p['local_path']}")

    # ---------- 死链 ----------
    dead, total = _dead_links(corpus)
    report.stats["本地链接总数"] = total
    report.stats["死链数"] = len(dead)
    for md_rel, link in dead[:20]:
        report.problems.append(f"死链: {md_rel} -> {link}")

    # ---------- 准确性（正文覆盖率） ----------
    ratios = []
    for p in kept:
        md_path = corpus / p["local_path"]
        raw_path = raw_dir / (p["local_path"].removesuffix(".md") + ".html")
        if not (md_path.exists() and raw_path.exists()):
            continue
        raw_text = _plain(extract_content(raw_path.read_text(encoding="utf-8")))
        md_text = _plain(md_path.read_text(encoding="utf-8"))
        ratio = _coverage(raw_text, md_text)
        ratios.append((ratio, p["local_path"]))
        if ratio < 0.6:
            report.problems.append(
                f"正文覆盖率低 {ratio:.0%}: {p['local_path']}（对照 raw/，疑似转换丢失）"
            )
    if ratios:
        avg = sum(r for r, _ in ratios) / len(ratios)
        report.stats["正文覆盖率 平均/最低"] = f"{avg:.1%} / {min(r for r, _ in ratios):.1%}"

    # 标题存在性（用正文 h1 校验；<title> 带站点后缀不逐字比）
    title_missing = 0
    for p in kept:
        md_path = corpus / p["local_path"]
        raw_path = raw_dir / (p["local_path"].removesuffix(".md") + ".html")
        if md_path.exists() and raw_path.exists():
            h1 = _first_h1(extract_content(raw_path.read_text(encoding="utf-8")))
            if h1 and h1 not in md_path.read_text(encoding="utf-8")[:2000]:
                title_missing += 1
                report.problems.append(f"标题丢失: {p['local_path']}（原 h1 {h1!r}）")
    report.stats["标题丢失数"] = title_missing

    return report


def _dead_links(corpus: Path) -> tuple[list[tuple[str, str]], int]:
    dead, total = [], 0
    for md in corpus.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", text):
            link = link.strip()
            if re.match(r"^(https?://|mailto:|#|ftp:|<)", link):
                continue
            target = link.split("#")[0].split('"')[0].strip()
            if not target:
                continue
            total += 1
            if not (md.parent / target).resolve().exists():
                dead.append((md.relative_to(corpus).as_posix(), link))
    return dead, total


def _plain(html: str) -> str:
    """规范化纯文本：去 HTML 标签、空白与 markdown 语法字符，只留词字符与 CJK。"""
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"[^\w一-鿿]", "", text, flags=re.UNICODE)


def _first_h1(content_html: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", content_html, re.S | re.I)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


def _coverage(raw_plain: str, md_plain: str) -> float:
    """raw 正文的字符有多少比例出现在 md 里（顺序无关的分块比对）。"""
    if not raw_plain:
        return 1.0
    chunk = 40
    hits = sum(1 for i in range(0, len(raw_plain), chunk) if raw_plain[i : i + chunk] in md_plain)
    total = (len(raw_plain) + chunk - 1) // chunk
    return hits / total if total else 1.0
