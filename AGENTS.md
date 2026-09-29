# Claw_Docs

把 API/技术文档站抓取到本地，整理成 LLM 开发时可离线检索的 Markdown 语料库。领域词汇见 `CONTEXT.md`。

## Agent skills

### Issue tracker

本地 markdown：spec 和 ticket 存于 `.scratch/<feature-slug>/`。See `docs/agents/issue-tracker.md`.

### Triage labels

默认五角色标签：needs-triage / needs-info / ready-for-agent / ready-for-human / wontfix。See `docs/agents/triage-labels.md`.

### Domain docs

single-context（根目录 `CONTEXT.md` + `docs/adr/`）。See `docs/agents/domain.md`.
