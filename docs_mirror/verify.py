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
        if _raw_path(raw_dir, p["local_path"]) is None:
            report.problems.append(f"raw 缺页: {p['url']}（期望 raw/{p['local_path'].removesuffix('.md')}.html[.gz]）")

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
        raw_path = _raw_path(raw_dir, p["local_path"])
        if not (md_path.exists() and raw_path):
            continue
        raw_text = _plain(extract_content(_read_raw(raw_path)))
        md_text = _plain(_strip_link_targets(md_path.read_text(encoding="utf-8")))
        ratio = _coverage(raw_text, md_text)
        ratios.append((ratio, p["local_path"]))
        if ratio < 0.6:
            report.problems.append(
                f"正文覆盖率低 {ratio:.0%}: {p['local_path']}（对照 raw/，疑似转换丢失）"
            )
    if ratios:
        avg = sum(r for r, _ in ratios) / len(ratios)
        report.stats["正文覆盖率 平均/最低"] = f"{avg:.1%} / {min(r for r, _ in ratios):.1%}"

    # 标题存在性（用正文 h1 校验；规范化去 ¶ 锚/语法字符后比对）
    title_missing = 0
    for p in kept:
        md_path = corpus / p["local_path"]
        raw_path = _raw_path(raw_dir, p["local_path"])
        if md_path.exists() and raw_path:
            h1 = _first_h1(extract_content(_read_raw(raw_path)))
            h1_norm = _plain(h1)
            md_norm = _plain(_strip_link_targets(md_path.read_text(encoding="utf-8")[:2000]))
            if h1_norm and h1_norm not in md_norm:
                title_missing += 1
                report.problems.append(f"标题丢失: {p['local_path']}（原 h1 {h1!r}）")
    report.stats["标题丢失数"] = title_missing

    return report


def _raw_path(raw_dir: Path, local_path: str) -> Path | None:
    """raw 镜像查找：兼容 .html 与 .html.gz（种子模式压缩存）。"""
    stem = local_path.removesuffix(".md")
    for suffix in (".html.gz", ".html"):
        p = raw_dir / (stem + suffix)
        if p.exists():
            return p
    return None


def _read_raw(path: Path) -> str:
    import gzip

    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes()).decode("utf-8")
    return path.read_text(encoding="utf-8")


def _dead_links(corpus: Path) -> tuple[list[tuple[str, str]], int]:
    dead, total = [], 0
    for md in corpus.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        # 先剥掉代码块与行内代码，代码里的括号方块不是链接
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        for link in re.findall(r"\]\(([^)]+)\)", text):
            link = link.strip()
            if re.match(r"^(https?://|mailto:|#|ftp:|<|data:)", link):
                continue
            target = link.split("#")[0].split('"')[0].strip()
            if not target or " " in target:
                continue
            total += 1
            if not (md.parent / target).resolve().exists():
                dead.append((md.relative_to(corpus).as_posix(), link))
    return dead, total


def _plain(html: str) -> str:
    """规范化纯文本：解码 HTML 实体、去标签/空白/markdown 语法字符，只留词字符与 CJK。"""
    import html as _html

    text = _html.unescape(html)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[^\w一-鿿]", "", text, flags=re.UNICODE)


def _strip_link_targets(md: str) -> str:
    """去掉 markdown 链接目标 URL，只留可见文本（避免 URL 混入正文比对）。"""
    md = re.sub(r"\]\([^)]*\)", "]", md)
    return re.sub(r"<https?://[^>]+>", "", md)


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
