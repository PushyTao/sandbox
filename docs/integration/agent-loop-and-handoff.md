# 最小 Agent 闭环及跨团队交接

日期：2026-10-22。PUSH-7 只交付文档与固定实验夹具，没有 adapter 或可执行 sandbox service。以下是可验证的验收程序，不是已执行的集成测试。

## 三条路线的选择

| 路线 | 模型/登录凭据 | 本地工具覆盖条件 | 主要代价/状态 |
|---|---|---|---|
| 宿主现成 Agent + 工具网关 | 留宿主 | 所有选定工具都真正委托受限 worker，内置同类工具及旁路必须分别禁用/验证 | 官方扩展入口可调查；不能由新增 MCP 工具推出已全覆盖 |
| 整体 CLI 包装 | 需沙箱内受控登录或代理 | CLI 及本地后代受外层真实约束；已有远程服务/浏览器/控制 socket 不因此受限 | 模型联网、HOME、PTY、嵌套沙箱和更新兼容成本高；未实测 |
| 自研最小 harness 样例 | 留可信宿主 | 模型仅有五类本地工具，调度器统一送本地服务；审批另走控制面 | 最容易检查完整路由；不是 Codex/Claude Code 正式适配，也不实现完整 Agent 产品 |

建议先把第三条用于验证合同和后端，再针对具体版本验证第一条。第二条保留独立实验。该建议不代替 D2 决策，不要求所有外部连接器都经过本地服务；产品策略必须逐一决定哪些任务提交服务。

## 可复核闭环

1. 使用临时合成工作区，文件 `answer.txt` 初值 `wrong\n`，外部合成文件 `outside/marker.txt`。预置只读解释器及不依赖网络的固定测试脚本，测试检查 answer 为 `right\n`。不得使用真实秘密。
2. 宿主连接模型或明确标注的人工驱动工具调用器。模型只获得 exec/read/write/apply_patch/search schema；没有 approval.resolve、任意宿主 I/O、grant 或管理 socket。人工驱动通过只算协议验收，模型参与闭环必须另测并记录模型/SDK版本。
3. initialize 精确协商实验合同；session.create 请求 scoped 文件权限、network=deny、受限 file worker 和目标清理级别。先保存有效策略、backend/version/capabilities；缺任何必需项都不启动负载。
4. file.read/search 查看 answer；exec.start 运行固定测试，观察非零退出、stdout/stderr 分流和完整清理；file.apply_patch 带旧内容摘要修改为 right，再跑测试应退出 0。额外用 file.write 验证同一策略，不提供独立宿主直写后门。
5. exec 和所有文件工具分别尝试访问/修改外部 marker、保护名称及别名；预期全部拒绝或会话因不能表达策略而拒绝。核对 marker 哈希无变化；“某工具没被模型选中”不能当拒绝通过。
6. 请求一个可审批软限制的精确外部路径；先拒绝一次，再测试过期，最后可信 UI 批准 once。模型工具直接调用 approval.resolve 及伪造角色应拒绝。负载打印同名 JSON 只能显示为输出；不创建审批状态。
7. 明确选择继续后，可信 harness 附受保护授权引用及新 requestKey 执行；服务原子消费 once。相同 grant 的第二次使用、跨 session、过期、撤销及硬拒绝覆盖均失败。不得在普通失败后自动重新执行。
8. 启动有可观测后代的固定长任务，重复 cancel，再做超时及 owner 断连三组独立实验。核对 PID/开始时间或原生句柄及资源，避免 PID 重用误判；每组保留实际清理证据。
9. session.close，检查 grants 已撤销、文件 worker/全部受管后代已结束、私有 temp/输出队列收回。控制台需正确区分 closing、closed、closed_incomplete 和 outcome unknown。

网络 deny 应测 IPv4/IPv6、TCP/UDP、DNS/代理及平台 IPC；整树清理、文件别名和未来保护名称沿用安全团队验收，不能只靠网关单元测试。Windows、Linux、macOS 各单独记录 OS/架构/后端版本与证据；WSL 不计原生 Windows。

## 依赖与责任

| 未满足依赖 | 协调方 | 解除条件 |
|---|---|---|
| D1–D7、实验契约评审 | 研发负责人/架构师 | 明确政策及签字的合同版本；不冻结本草案 |
| 可强制的 exec 与 file worker、network deny、路径保护和清理 | 运行时/安全 | 对应真实平台正反例及 capability 报告；现有 Job/namespace 探针不能替代 |
| 带外可信身份/审批、grant 消费/撤销、防重放 | 架构/安全/控制台 | 模型不能获得审批控制通道；并发/断连负向测试通过 |
| 环境、session、owner 与 observer 的对应 | 架构/控制台 | 下面 SESSION-01 得到明确裁决及合同样例 |
| 固定版本的工具委托/禁用机制与旁路枚举 | 接入工程师 | 各工具和 hooks/plugins/MCP/远程访问真实观测，升级需重测 |
| 跨平台环境与测试驱动/模型调用预算 | QA/研发负责人 | 三平台分别运行；缺环境记未验证，人工轨迹不称真实 Agent 闭环 |
| 发布/安装/崩溃恢复能力 | 构建/运行时 | 在支持平台验证持久系统变更回收；本轮不改宿主安全设置 |

## 提交架构师协调：SESSION-01

问题：设计 §11.2 要求客户端断连取消，但控制台和 Agent 同时查看同一 session 时，“客户端”是谁？不能把最后一个观察者断开当 owner 断开，也不能因控制台仍开着而让孤儿任务继续。

最小复现请求（协议提案，非可运行命令）：可信宿主 H 创建环境 E；Agent 连接 A 创建 session S 并 exec.start 长任务 X；控制台连接 C 订阅 S；断开 A，保持 C；随后 C 提交过期的 once 审批，再重复关闭 S。交换断开顺序重做一次。

| 候选 | 行为与取舍 |
|---|---|
| A：单 owner，控制台为 observer/独立 approver（建议供评审） | A 断开即取消 X/撤销 grant；C 可见 closing/清理结果。只断 C 不影响 A。最贴合 M1，不隐式转移所有权 |
| B：持久 environment owner/受管 lease | A 断开是否存活由经认证 lease 决定，需要续期、重连身份、持久状态、事件留存和 supervisor 崩溃合同；超出当前 M1 基线 |

请架构师在 PUSH-3 协调 PUSH-8，明确 owner 的可信建立、观察者权限、审批 UI 断连时 pending 的取消/期限、owner 断连与审批竞态的线性化点。建议 closing 先撤销 pending/grants，迟到批准返回 SessionClosing，无新执行；取消结果通过可信审计让 C 可见。多个 Agent 共享环境建议使用不同 session，不凭同一目录推定隔离。

本提案未添加 `session.attach` 或所有权转移公开接口。选择 B 前不实现后台/重连，选择 A 也必须经身份与多连接实际验证。
