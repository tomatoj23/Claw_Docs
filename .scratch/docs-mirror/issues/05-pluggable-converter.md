# 05: 可插拔转换器

**What to build:** HTML→MD 转换器抽为适配器契约（干净 HTML 片段 → md，单文件进单文件出）；pandoc（项目内 `tools/pandoc/` vendored 二进制）与 markdownify 双适配器实现同一契约并经配置切换；换转换器后可拿 `raw/` 完整镜像离线重转全库，不需重新爬站。

**Blocked by:** 03

**Status:** ready-for-agent

- [x] 转换器适配器契约定义（输入干净 HTML 片段、输出 md，不抛异常）
- [x] pandoc 与 markdownify 两个适配器均通过接缝 2 契约测试（同一输入集、断言标题/代码块/表格/链接等不变量）
- [ ] 转换器经配置切换，切换后从 `raw/` 重转产出语料库
- [x] 重转过程零网络访问；pandoc 不可用时回落 markdownify 并给出提示

## Comments

- 2026-09-29 转换器定为项目内 vendored pandoc 3.12（`tools/pandoc/`，`scripts/install_pandoc.py` 安装，gitignore 不入库），替换原计划的跨项目 `HTML_TO_MD` 适配器——严禁跨项目文件依赖。输出 GFM，读写两侧关 smart 保字形、`--wrap=none`、`--eol=lf`。CLI `--converter pandoc|markdownify`，默认 pandoc。
