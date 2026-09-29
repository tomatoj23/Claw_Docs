# Spec: docs-mirror — 文档站本地化语料库工具

Status: ready-for-agent

## Problem Statement

用 LLM 开发时经常要查 API 文档，但网络搜索又慢又贵，部分语言/库没有本地文档可用。手工保存网页得到的 HTML 噪音大、链接失效、体积臃肿，对 LLM 不友好。需要一套脚本：对纯文档站能整站抓到本地并整理成链接可用的语料库；对图文视频混杂、含大量无关内容的站点，能智能判断哪些该要、哪些不该要。

## Solution

一个 Python CLI 工具 `docs-mirror`：输入一个文档站 URL，产出一个本地 Markdown 语料库（`corpus/<站点slug>/`），站内链接全部改写为本地文件互链、图片落盘到本地。流水线为：抓取过滤 → 完整镜像（除视频）→ 干净正文 HTML → 可插拔转换 → Markdown 语料库。混合站点的取舍由脚本启发式粗筛 + agent 裁决沉淀为站点配置包，重复执行零成本。原始完整镜像保留在 `raw/`，用于校验转换质量、审计取舍误判、以及转换器升级后离线重转。

## User Stories

1. As an LLM 开发者, I want 输入一个文档站 URL 就把整站抓成本地 Markdown 语料库, so that 查 API 不再依赖慢而贵的网络搜索
2. As an LLM 开发者, I want 语料库内所有站内链接改写为指向本地 Markdown 文件, so that agent 沿链接跳转时不会跳出本地、不会 404
3. As an LLM 开发者, I want 正文中的图片下载到本地并以相对路径引用, so that 离线状态下图片引用仍然有效
4. As an LLM 开发者, I want 视频一律不下载只在原位标注原 URL, so that 语料库不被无用的大体积媒体拖垮
5. As an LLM 开发者, I want 导航、侧栏、页脚、横幅等样板被剥离只留正文, so that 喂给 LLM 的上下文没有噪音
6. As an LLM 开发者, I want 面对图文视频混杂的站点时由脚本粗筛出候选页面, so that 无关内容（博客、招聘、营销页）不进入语料库
7. As an agent, I want 脚本产出待审清单让我裁决取舍边界, so that 智能判断的准确性由我兜底而不是纯启发式
8. As an agent, I want 裁决结果沉淀为站点配置包, so that 同一站点重跑时取舍零成本且结果一致
9. As an LLM 开发者, I want 每个已抓页面在清单中记录 kept/rejected 及理由, so that 我能审计取舍是否误杀
10. As an LLM 开发者, I want 被过滤掉的页面也保留在完整镜像里, so that 发现误杀后可以复核找回而不必重爬
11. As an LLM 开发者, I want 完整镜像（除视频）一页不删地保留, so that 可以用它核对转换后的文档、发现脚本疏漏
12. As an LLM 开发者, I want HTML→Markdown 转换器可插拔, so that 可以先用 markdownify 顶上、以后换成自己项目里更精确的转换器
13. As an LLM 开发者, I want 完整镜像留档使重转不需要重新爬站, so that 转换器升级后离线即可全量重出语料库
14. As an LLM 开发者, I want 语料库生成索引文件, so that agent 能快速定位某个 API 文档在哪个文件
15. As an LLM 开发者, I want 抓取结果带清单（URL、抓取时间、内容 hash）, so that 为将来的增量更新留好数据基础
16. As an LLM 开发者, I want 遇到 JS 重渲染站点时明确报错提示而不是产出残缺语料, so that 我知道该换手段而不是被静默坑
17. As an LLM 开发者, I want 图片保留可通过站点配置关掉, so that 纯文字场景下语料库更轻
18. As an LLM 开发者, I want 外部链接保持原样不改写, so that 语料库不丢失指向真实互联网的引用
19. As an LLM 开发者, I want 转换完成后对 kept 页面做校验（链接、图片、标题树、代码块、表格、正文文本比对）, so that 转换疏漏能被自动发现而不是靠人眼
20. As an LLM 开发者, I want 同一站点重跑时行为确定、可重复, so that 语料库是可信赖的基础设施而不是一次性产物
21. As an LLM 开发者, I want 抓取对目标站点保持礼貌（并发限制、间隔、User-Agent 标明来源）, so that 不会给别人的服务造成负担
22. As an LLM 开发者, I want CLI 有 full/filtered 两种模式入口, so that 纯文档站走整站直抓、混合站点走取舍流程
23. As an agent, I want 通过薄 ZCode skill 调用这套工具, so that 用户说"把 xx 文档扒下来"时我直接执行并承担裁决角色

## Implementation Decisions

- **整体架构**：Python CLI 项目 `docs-mirror`，核心逻辑独立于 ZCode 可单独运行；外层一个薄 ZCode skill 只负责调用 CLI 并承担取舍裁决角色。
- **流水线分段**：抓取过滤 → 完整镜像落盘 → 干净正文 HTML 提取 → HTML→MD 转换 → 语料库落盘 + 索引。每段输入输出均为文件，可分段重跑。
- **完整镜像（Raw Mirror）**：全部已抓页面的原始 HTML + 图片一页不删（视频除外，只在清单记原 URL）。它是校验基准、取舍审计依据、重转数据源。输出目录中为 `raw/`。
- **取舍机制**：脚本启发式粗筛（URL 模式、正文密度、样板识别）产出待审清单（manifest），由 agent 裁决边界并沉淀为站点配置包；不逐页调用 LLM。站点配置包可覆盖启发式（URL 通配规则、样板选择器、图片开关等）。
- **清单（Manifest）**：每页记录源 URL、抓取时间、内容 hash、kept/rejected、理由。第一版即写入；增量同步逻辑为二期，不在本 spec 范围。
- **转换契约**：爬虫输出干净正文 HTML（去样板、站内链接与图片路径已本地化），转换器只做 HTML→MD，单文件进单文件出。适配器接口下优先用项目内 vendored pandoc（`tools/pandoc/`，由 `scripts/install_pandoc.py` 安装，不依赖全局 pandoc、不跨项目），回落 markdownify；两适配器可经配置切换。
- **去样板归属**：样板剥离由爬虫侧负责（内置启发式 + 站点配置覆盖），不塞给转换器，保持转换器通用。
- **链接改写**：站内链接改写为指向本地 `.md` 相对路径（含锚点）；外部链接保持原 URL；指向被 rejected 页面的链接改写策略为保留原文本并标注（不制造死链）。
- **媒体策略**：正文引用的图片保留（可配置关闭）；视频不下载，原位标注原 URL。
- **JS 重站点**：一期不支持客户端渲染，检测到疑似 JS 站时明确报错提示；不上 Playwright。
- **输出布局**：`corpus/<站点slug>/` 下 `*.md`（镜像源站目录结构）、`assets/`、`raw/`、`manifest.json`、`linkmap.json`、`_INDEX.md`。
- **依赖**：requests、beautifulsoup4、markdownify、lxml（环境已装）；pandoc 3.12 vendored 于 `tools/pandoc/`（gitignore，`scripts/install_pandoc.py` 安装）；trafilatura/readability 可选补充，正文提取先用启发式实现。
- **技术栈**：Python 3.14，pytest 测试。

## Testing Decisions

- 好的测试只测外部行为（CLI 产出的语料库文件与清单），不测实现细节（内部函数、启发式中间值）。
- **接缝 1（主）**：CLI 端到端。pytest 起本地 fixture HTTP 服务，含两个虚构站点：站点 A 纯文档站（多页互链 + 图片）、站点 B 图文视频混合站（含 blog/视频/广告/侧栏噪音）。跑 `docs-mirror` CLI，断言语料库产物：md 正文内容正确、站内链接改写后有效、assets 落盘、manifest 的 kept/rejected 与理由、`raw/` 完整性。测试全程零外网。
- **接缝 2**：转换器契约。pandoc 与 markdownify 两个适配器跑同一套契约断言（同一输入 HTML 片段集合，断言输出 md 的标题/代码块/表格/链接等不变量），保证将来切换可替换。
- 链接改写、去样板、取舍启发式等行为一律通过接缝 1 的 fixture 覆盖，不开独立单元测试接缝。
- 先例：`HTML_TO_MD` 项目的 pytest 风格（fixture 驱动、断言外部产物）。

## Out of Scope

- 增量更新/同步（manifest 一期只写不读）
- JS 客户端渲染站点支持（Playwright）
- 逐页 LLM 调用做取舍
- 视频内容下载或转写
- 多站点聚合语料库、向量索引、RAG 集成
- 认证/登录墙后的内容抓取
- 对非文档类站点（电商、论坛等）的适配

## Further Notes

- 转换器已定为项目内 vendored pandoc（3.12，`tools/pandoc/`，只用 tools/ 内二进制、不依赖全局 pandoc、不跨项目引用）；GFM 输出、读写两侧关 smart 保字形、`--wrap=none` 不折行、`--eol=lf` 换行确定。曾评估的 `HTML_TO_MD` 项目仅借其校验器思路，不做代码依赖。
- 其六维校验器（链接/图片/标题树/代码块/表格/正文比对）可为本项目校验段提供直接参考甚至复用。
- `raw/` 完整镜像同时服务于用户明确提出的"核对转换后文档、避免脚本疏漏"诉求。
