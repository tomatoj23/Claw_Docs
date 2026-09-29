# 07: 索引与 ZCode skill 封装

**What to build:** 语料库生成 `_INDEX.md` 全库索引；薄 ZCode skill 封装——用户说"把 xx 文档扒下来"时 agent 直接调 CLI 执行，filtered 流程中展示待审清单供 agent 裁决取舍，并把裁决沉淀进站点配置包，重跑零人工。

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] `_INDEX.md` 全库索引生成（标题层级 + 文件定位）
- [ ] ZCode skill 接受站点 URL，调 CLI 完成抓取并产出语料库
- [ ] skill 在 filtered 流程中展示待审清单（manifest）供 agent 裁决，裁决结果写入站点配置包
- [ ] 重跑同一站点走站点配置包，取舍零人工且结果一致
