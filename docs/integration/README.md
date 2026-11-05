# M0：Codex / Claude Code 接入核验

PUSH-7，核验日期 **2026-10-22**。结论：存在可研究的公开工具入口；当前仓库没有完成本地服务接入，也没有任一平台的端到端兼容或安全通过结论。优先保留宿主 Agent、把产品策略选中的工具交给同策略受限 worker；不能仅包 shell 或增加 MCP 就宣称覆盖全部工具。

交付包括本页覆盖矩阵、[实验合同](experimental-contract.md)、[最小闭环与 SESSION-01](agent-loop-and-handoff.md)、[验证记录](validation.md)及固定 JSON-RPC 夹具。代码基线 `bb4e544f09cd12fb2521772944060c23cb7f6932`，本轮只新增 `docs/integration/` 和 `examples/protocol-fixtures/`。

## 版本与证据分级

| 对象 | 固定版本/来源 | 本轮实际核验层次 |
|---|---|---|
| Codex CLI | 本机 `0.154.0`；[rust-v0.154.0 release](https://github.com/openai/codex/releases/tag/rust-v0.154.0)，commit `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`；annotated tag object `36eab01061df3cde5f95ec20a526777b430091ba` | Windows 版本/帮助、该 binary 导出的实验 schema、固定 commit 静态源码；没有运行模型/工具任务 |
| Claude Code | 本机 `2.1.296`；[v2.1.296 release](https://github.com/anthropics/claude-code/releases/tag/v2.1.296)，公开发行/changelog commit `2301018b1f61073c501a8e7a4813ef48c239163b` | Windows 版本/帮助与滚动官方文档；该 commit 不是对安装二进制实现的源码审计 |
| Claude 更新发行 | [v2.1.307](https://github.com/anthropics/claude-code/releases/tag/v2.1.307)，commit `1132b8a98e93300bb3822197fb7eee12ce4fb906` | 仅页面核验；未安装。列表页 Latest 与具体发行页快照有差异，不能据此宣称全局最新 |
| 历史探针 | PUSH-1 bundle，HEAD `c19b23585d64d20869adb9654cfbc1f013584d40` | 本轮验证完整 bundle、读取范围/评审/入口；未重跑历史探针，不复用其 pass 作为本轮结果 |

官方文档为滚动内容；以下与固定版本源码不同的文档能力均需实际版本复验。Windows 版本查询成功不代表 Windows sandbox 兼容；Linux/macOS 本轮未验证。原设计的旧官方能力描述以本表的日期/版本限定，未修改根设计。

## Codex 接入口及覆盖矩阵

官方 app-server 提供 Agent 会话、审批和事件，CLI 当前仍标实验性；`dynamicTools` 是客户端处理额外工具调用的入口。它与本项目的执行合同不是同一协议。外部 MCP 连接仍支持；旧 `codex mcp-server` 已移除，不能照抄旧 Agents SDK 示例。[App server](https://learn.chatgpt.com/docs/app-server)、[MCP removal](https://learn.chatgpt.com/docs/mcp-server)、[external MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

0.154.0 还存在独立 exec-server/environment 接入：配置可指向 WebSocket 或 stdio program，`include_local=false` 可移除配置中的 local environment。它采用自己的 process/fs 协议；接入本项目需要专门的版本兼容桥及安全评审，不能把现有 server URL 直接填进去就声称适配。此事实来自固定源码，不代表该实验接口已经稳定或本轮已运行。[环境配置源码](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/exec-server/src/environment_toml.rs)、[exec-server README](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/exec-server/README.md)。

| 类别 | 原生/扩展路由与候选映射 | 仍需检查的旁路/限制 |
|---|---|---|
| exec | 选定 environment 的 process 执行；兼容桥再映射 exec.start/status/cancel | 内置 local 环境、独立命令执行入口、配置 fallback 与取消生命周期须实测；不能默认所有执行都去远端 |
| read | 选定环境的文件访问或通过 shell 读取；映射受限 file.read | app-server 自身 `fs/readFile` 使用 local environment，不能当线程远程文件路由 |
| write | executor fs/writeFile 或 shell 写；映射受限 file.write | app-server `fs/writeFile` 同样是本地客户端/UI入口；必须按产品策略限用 |
| apply_patch | 固定源码使用 turn 所选 environment filesystem；候选桥必须保留 patch/冲突语义 | 单独添加 MCP patch 不会替换原生 patch，不能遗漏写路径 |
| search | 需分别盘点原生文件搜索和 shell/rg 路径；本项目 file.search 只是提案 | 不能因 exec 走远端推定全部搜索都受同一策略；各方法需实际 trace |
| MCP / dynamic tools | 客户端或外部 MCP server 各自处理；可新增网关工具 | 增加工具不禁用原有本地工具；本地 MCP 进程/远端 MCP 不自动进入本项目沙箱 |
| 浏览器 / web / 远程连接器 | 各产品/插件/服务独立执行 | 模型网络、浏览器用户态、远端副作用不是本地 exec-server 隔离结果 |

固定源码特别区分两个同名 fs 接口：app-server 客户端 `fs/readFile`/`fs/writeFile` 调用 `try_local_environment()`，且传 `sandbox=None`；executor 的文件协议属于选定环境。此处说明调用面差异，不声称发现已利用漏洞。[app-server fs processor](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/app-server/src/request_processors/fs_processor.rs#L50)、[apply_patch runtime](https://github.com/openai/codex/blob/6b9826e3aa83b1a5947db50f4332cb9c65f1b340/codex-rs/core/src/tools/runtimes/apply_patch.rs)。

## Claude Code 接入口及覆盖矩阵

除 MCP/Agent SDK 自定义工具外，官方 **Mods** 已提供原生工具接管候选：终端要求 ≥2.1.287；`tool.call` 不调用 `next` 而返回 `{result: ...}` 时可不执行原工具，结果必须符合该 build 的工具类型。覆盖子 Agent/MCP 的声明来自文档，本机 2.1.296 满足文档版本门槛但未运行 Mods。[Mods overview](https://code.claude.com/docs/en/plugins/mods/overview)、[v2.1.287](https://github.com/anthropics/claude-code/releases/tag/v2.1.287)、[Mods events](https://code.claude.com/docs/en/plugins/mods/events)。

关键风险：Mod 在调用 next 之前抛错/超时/返回错形且未正确处理时可被跳过，原工具继续；catch 失败也可继续。故不能把 Mod 当独立隔离边界。必须验证加载失败、关闭 Mods、回调错误、顺序、子 Agent、重入和取消都不会意外回落宿主。Mods 在 headless/SDK 可运行，但本身未沙箱化；HTTP 30 秒/4 MiB 限制也需用短请求、状态查询、显式取消来适配。[Mods events](https://code.claude.com/docs/en/plugins/mods/events)、[administration](https://code.claude.com/docs/en/plugins/mods/admin)、[reference](https://code.claude.com/docs/en/plugins/mods/reference)。

| 类别 | 官方工具/可选路由 | 仍需检查的旁路/语义 |
|---|---|---|
| exec | Bash，另盘点 PowerShell、Monitor；Mods 接管或禁用原工具并提供 MCP exec | 仅匹配 Bash 不足；原工具/Mod fallback、hooks、子 Agent 启动都需核对 |
| read | Read → 受限 file.read | 读取分页/路径语义需映射；Bash sandbox 不保护独立 Read |
| write | Write → 受限 file.write | 覆盖/编码/冲突/部分失败需定义，不能宿主直接写 |
| apply_patch | 原生 Edit 为字符串替换，不等同统一 diff；本次参考未列独立 apply_patch | 映射 Edit 的 old_string/new_string/replace_all 或提供专用 MCP patch；转换前须原内容检查 |
| search | Glob/Grep 与 shell 搜索；文档指出默认工具集随平台不同 | 不假设三平台有同名工具；执行期间枚举实际暴露工具并逐个检查 |
| MCP | 远端/本地/SDK 进程内自定义工具；可直接构建网关工具 | tools 与 allowedTools 含义不同；未列自动批准不等于禁用；MCP 自身范围另控 |
| 浏览器/远程 | Chrome 集成、WebFetch/WebSearch、远程 MCP | 浏览器共享登录态/远端行为不属于本项目本地沙箱；需要独立授权策略 |

工具语义来源：[tools reference](https://code.claude.com/docs/en/tools-reference)、[SDK custom tools](https://code.claude.com/docs/en/agent-sdk/custom-tools)、[MCP](https://code.claude.com/docs/en/mcp)、[Chrome](https://code.claude.com/docs/en/chrome)。

普通 PreToolUse 可控制权限及更新参数，PostToolUse 改输出已晚于副作用；不能用改写输出伪造工具已经在服务运行。普通 settings hook 与 SDK callback 超时行为不同，SDK canUseTool 也并非必经路径；每一种应分别测试。`--tools` 不限制 MCP；收敛 MCP 配置不等于完整禁用旁路。[Hooks](https://code.claude.com/docs/en/hooks)、[SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions)、[SDK hooks](https://code.claude.com/docs/en/agent-sdk/hooks)、[CLI reference](https://code.claude.com/docs/en/cli-reference)。

官方 sandbox 当前明确限定 shell 命令及后代，Read/Edit/Write、hooks、MCP 等仍在外部；原生 Windows 的 shell 不使用该 sandbox。此为文档声明，未在本轮实测。Agent SDK 保留 Claude Code Agent loop，Client SDK/API 的 tool_use/tool_result 则由自研程序执行；两类不能混称正式 CLI 适配。[Sandbox scope](https://code.claude.com/docs/en/sandboxing)、[Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)、[programmatic CLI](https://code.claude.com/docs/en/headless)、[API tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works)。

## 决策边界

本轮建议研究 Codex 固定 executor 协议桥、Claude Mods 失败闭合条件或 MCP 加明确工具禁用两条候选；不实现未评审 adapter。调用方策略选择哪些请求进服务，但服务必须最终强制权限；缺版本、能力、路径保护或可信审批依赖时拒绝运行，不能返回宿主执行作为兼容降级。具体最小调用程序和各未满足依赖见闭环文档。
