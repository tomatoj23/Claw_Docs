# 05: 可插拔转换器

**What to build:** HTML→MD 转换器抽为适配器契约（干净 HTML 片段 → md，单文件进单文件出）；markdownify 与 HTML_TO_MD 项目的 `html_fragment_to_markdown` 双适配器实现同一契约并经配置切换；换转换器后可拿 `raw/` 完整镜像离线重转全库，不需重新爬站。

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] 转换器适配器契约定义（输入干净 HTML 片段、输出 md，不抛异常）
- [ ] markdownify 与 HTML_TO_MD 两个适配器均通过接缝 2 契约测试（同一输入集、断言标题/代码块/表格/链接等不变量）
- [ ] 转换器经配置切换，切换后从 `raw/` 重转产出语料库
- [ ] 重转过程零网络访问；HTML_TO_MD 不可用时回落 markdownify 并给出提示
