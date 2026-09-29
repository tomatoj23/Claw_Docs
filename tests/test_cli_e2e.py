"""接缝 1：CLI 端到端。本地 fixture 站点上跑 docs_mirror，只断言语料库产物。"""

from __future__ import annotations

import json

from conftest import find_corpus, run_cli


class TestPureDocsSite:
    """纯文档站（site-a）：full 模式整站语料库。"""

    def test_corpus_pages_exist(self, fixture_server, tmp_path):
        result = run_cli(f"{fixture_server}/site-a/index.html", "--out", str(tmp_path))
        assert result.returncode == 0, result.stderr
        corpus = find_corpus(tmp_path)
        assert (corpus / "index.md").exists()
        assert (corpus / "guide.md").exists()
        assert (corpus / "api" / "reference.md").exists()

    def test_links_rewritten_and_valid(self, fixture_server, tmp_path):
        run_cli(f"{fixture_server}/site-a/index.html", "--out", str(tmp_path))
        corpus = find_corpus(tmp_path)
        guide = (corpus / "guide.md").read_text(encoding="utf-8")
        # 站内链接改写为本地相对路径（guide.md 与 api/reference.md 同级目录关系）
        assert "(api/reference.md)" in guide
        assert "(index.md)" in guide
        # 外链保持原样
        index = (corpus / "index.md").read_text(encoding="utf-8")
        assert "https://example.com/external" in index
        # 锚点保留
        assert "api/reference.md#classes" in index
        # 改写后的链接目标真实存在，无死链
        assert (corpus / "api" / "reference.md").exists()
        assert (corpus / "guide.md").exists()

    def test_assets_downloaded(self, fixture_server, tmp_path):
        run_cli(f"{fixture_server}/site-a/index.html", "--out", str(tmp_path))
        corpus = find_corpus(tmp_path)
        assets = list((corpus / "assets").rglob("logo.svg"))
        assert assets, "logo.svg 应下载到 assets/"
        index = (corpus / "index.md").read_text(encoding="utf-8")
        assert "assets/logo.svg" in index

    def test_raw_mirror_complete(self, fixture_server, tmp_path):
        run_cli(f"{fixture_server}/site-a/index.html", "--out", str(tmp_path))
        raw = find_corpus(tmp_path) / "raw"
        # 完整镜像：全部已抓页面的原始 HTML 都在
        htmls = {p.relative_to(raw).as_posix() for p in raw.rglob("*.html")}
        assert "index.html" in htmls
        assert "guide.html" in htmls
        assert "api/reference.html" in htmls

    def test_manifest_records_pages(self, fixture_server, tmp_path):
        run_cli(f"{fixture_server}/site-a/index.html", "--out", str(tmp_path))
        manifest = json.loads(
            (find_corpus(tmp_path) / "manifest.json").read_text(encoding="utf-8")
        )
        pages = {p["url"].rsplit("/", 1)[-1]: p for p in manifest["pages"]}
        assert set(pages) == {"index.html", "guide.html", "reference.html"}
        for p in manifest["pages"]:
            assert p["sha256"]
            assert p["fetched_at"]
            assert p["status"] in ("kept", "rejected")

    def test_boilerplate_stripped(self, fixture_server, tmp_path):
        run_cli(f"{fixture_server}/site-a/index.html", "--out", str(tmp_path))
        for md in find_corpus(tmp_path).rglob("*.md"):
            if md.name == "manifest.md":
                continue
            text = md.read_text(encoding="utf-8")
            assert "超级导航菜单NOISE" not in text
            assert "页脚样板FOOTERNOISE" not in text


class TestMixedSite:
    """图文视频混杂站（site-b）：filtered 模式取舍。"""

    def _run(self, fixture_server, tmp_path):
        result = run_cli(
            f"{fixture_server}/site-b/index.html",
            "--out",
            str(tmp_path),
            "--mode",
            "filtered",
        )
        assert result.returncode == 0, result.stderr
        return find_corpus(tmp_path)

    def test_doc_pages_kept(self, fixture_server, tmp_path):
        corpus = self._run(fixture_server, tmp_path)
        assert (corpus / "docs" / "setup.md").exists()

    def test_irrelevant_pages_rejected_with_reason(self, fixture_server, tmp_path):
        corpus = self._run(fixture_server, tmp_path)
        manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
        by_path = {p["url"]: p for p in manifest["pages"]}
        rejected = [p for p in manifest["pages"] if p["status"] == "rejected"]
        assert rejected, "混合站应有页面被取舍掉"
        for p in rejected:
            assert p["reason"], "rejected 页面必须记录理由"
        # 博客/价格/招聘类页面确定性地被拒
        rejected_urls = " ".join(p["url"] for p in rejected)
        assert "blog" in rejected_urls
        assert "pricing" in rejected_urls
        assert "robots-garbage" in rejected_urls
        assert by_path

    def test_rejected_pages_kept_in_raw_mirror(self, fixture_server, tmp_path):
        corpus = self._run(fixture_server, tmp_path)
        raw = corpus / "raw"
        htmls = {p.relative_to(raw).as_posix() for p in raw.rglob("*.html")}
        assert "blog/2026-01-post.html" in htmls, "rejected 页面留 raw/ 供审计"
        assert "pricing.html" in htmls

    def test_no_video_downloaded(self, fixture_server, tmp_path):
        corpus = self._run(fixture_server, tmp_path)
        assert not list(corpus.rglob("*.mp4")), "视频不下载"
        assert not list((corpus / "assets").rglob("*.mp4"))

    def test_links_to_rejected_annotated_not_dead(self, fixture_server, tmp_path):
        corpus = self._run(fixture_server, tmp_path)
        setup = (corpus / "docs" / "setup.md").read_text(encoding="utf-8")
        # 指向被拒页面的链接不改写成本地死链
        assert "(blog/2026-01-post.md)" not in setup
        assert "blog/2026-01-post" not in setup or "未收录" in setup

    def test_full_mode_regression(self, fixture_server, tmp_path):
        # full 模式在同一混合站上仍然抓全站
        result = run_cli(
            f"{fixture_server}/site-b/index.html", "--out", str(tmp_path), "--mode", "full"
        )
        assert result.returncode == 0, result.stderr
        corpus = find_corpus(tmp_path)
        assert (corpus / "blog" / "2026-01-post.md").exists()
