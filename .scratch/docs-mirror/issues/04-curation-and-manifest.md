# 04: 取舍与清单（混合站）

**What to build:** filtered 模式对图文视频混杂的站点做取舍：启发式粗筛页面，`manifest.json` 逐页记 kept/rejected 及理由，rejected 页面保留在 `raw/` 供审计；指向 rejected 的链接标注处理不造死链；视频不下载只留原 URL 标注，图片可经配置关闭。混合站场景（用户需求 2）到此完整可用。

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] filtered 模式对混合 fixture 站粗筛：无关页面（blog/招聘/营销）rejected，文档页 kept，测试断言取舍结果与理由
- [ ] `manifest.json` 逐页记录 kept/rejected + 理由
- [ ] rejected 页面保留在 `raw/`（完整镜像一页不删，视频除外）
- [ ] 指向 rejected 页面的链接有标注处理，语料库内无死链
- [ ] 视频不下载，原位标注原 URL
- [ ] 图片保留可经站点配置关闭
- [ ] full 模式行为不回归（接缝 1 既有测试保持绿）
