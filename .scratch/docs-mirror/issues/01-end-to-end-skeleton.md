# 01: 端到端骨架打通（tracer bullet）

**What to build:** `docs-mirror <url>` 最小全链路跑通——对本地 fixture HTTP 服务上的单页文档站，抓取页面 → `raw/` 落盘 → 默认转换器（markdownify）转 md → `corpus/<站点slug>/` 输出。pytest 测试接缝 1（本地 fixture HTTP 服务 + CLI 端到端断言）随票建立，全程零外网。CLI 可脱离 ZCode 独立运行。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `docs-mirror <url>` 对单页 fixture 站产出 `corpus/<slug>/` 下的 `.md` 与 `raw/` 原始 HTML
- [ ] `manifest.json` 记录源 URL、抓取时间、内容 hash
- [ ] pytest 端到端测试建立（本地 fixture HTTP 服务）且全部通过、不访问外网
- [ ] 依赖仅限 requests / beautifulsoup4 / markdownify / lxml，无 ZCode 环境可独立运行
