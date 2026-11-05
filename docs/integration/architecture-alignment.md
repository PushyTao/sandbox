# PUSH-7 与 PUSH-3 的实验契约对齐

日期：2026-11-05。PUSH-3 的 `c0abe9cd2532074cb2deb29e2699de815cfaee25` 已于 2026-11-04 获研发负责人“接受为 M0 候选”的评审结论；这不批准 D1–D7，也不冻结 API。本页是接入侧迁移与验收交接，未实现 adapter、服务或跨平台隔离。

依据固定版本的 [架构实验合同](https://github.com/PushyTao/sandbox/blob/c0abe9cd2532074cb2deb29e2699de815cfaee25/docs/architecture/m0-experimental-contract.md)、[A01–A24 验证场景](https://github.com/PushyTao/sandbox/blob/c0abe9cd2532074cb2deb29e2699de815cfaee25/docs/architecture/m0-contract-validation.md) 和 [架构决策提案](https://github.com/PushyTao/sandbox/blob/c0abe9cd2532074cb2deb29e2699de815cfaee25/docs/decisions/0002-m0-architecture-proposal.md)。不复制或改写其它团队的源文档。

## 两个草案不能互换

现有 `integration-draft-1.json` 与 `validate_fixtures.py` 仅描述 `sandbox.integration/0.1.0-draft.1` 的 19 个历史静态场景。新候选为 `sandbox.architecture/0.1.0-draft.1`。即使都称 draft.1，也不能替换版本字符串后宣布兼容。旧夹具保留作提案演变和回归证据；没有新的架构版线协议实现或兼容性认证。

| 项目 | 接入旧草案 | 架构候选要求与接入动作 |
|---|---|---|
| 初始化 | 精确协商 integration 版本 | 精确协商 architecture 版本；版本不匹配即停止建会话、写入及审批。协议字段存在不等于后端能力 verified |
| 连接与身份 | owner/可信控制面尚待裁决 | 单一权威服务、Agent stdio 桥与独立认证管理 IPC；不启动两个互不共享状态的 stdio server 并传同一 sessionId 假装共享 |
| 主体与角色 | 不信任 client.role | 服务从可信启动关系/OS 认证绑定主体、角色和连接代次；同一用户或 loopback 不等于认证。ID 不提供授权 |
| 会话创建 | workspace/策略/能力与 owner 绑定 | 创建前登记意图及 sessionId/owner；creating → ready 后才可执行。固定 environment revision、policyHash、后端与能力；保存新 revision 不修改现有会话 |
| 并发 | 每 session 一个有副作用操作 | 每登记工作区一个活动 session；每 session 一个在途操作，**读文件也计入**；全服务四个操作，Busy 无隐式队列。别名、祖先范围及共享 Git 元数据由服务判断 |
| 执行状态 | accepted/running/cancelling/terminal | accepted/preparing/running/terminating/terminal；准备失败也要给已接受操作终态。取消 ACK 不等于资源已回收 |
| 变更与重试 | 主要规定 session 内执行 key | 变更携带 expectedInstanceId；实例不匹配拒绝。先鉴权再查询去重；相同 key/内容/控制绑定返回旧结果，不重复消费授权或写文件 |
| 创建 ACK 丢失 | 未定义创建记录查询 | 创建键为 instance＋主体＋session.create＋requestKey；owner 连接代次是记录绑定，不能放进键空间造成重连二次创建。session.creation.get 查询旧记录；新连接无接管权 |
| 审批 ACK 丢失 | once 消费，但未规定决定去重 | 控制面 decisionKey＋待审 revision 做原子决定；同键同决定返回原结果，不签第二份 grant。不同键处理已决定对象返回 ApprovalAlreadyResolved |
| 文件写/patch | expectedSha256/expectedAbsent | 首发前确定 requestKey；同键重试先取旧 operationId/结果，不重新比较已经变化的旧 hash；新键才按当前 hash 校验。仍限同策略 worker、单文件，无宿主兜底 |
| 输出和事件 | 每 exec 的 seq；completed 一次 | 增加每 session 的 eventCursor；seq 与 cursor 独立。completed 只生成一次，但网络可重复投递同一事件，客户端去重；终态后不再输出 |
| 清理 | cleanup.complete 布尔值 | cleanup.status 为 pending/complete/incomplete/unknown，与能力声明 guaranteed/best_effort/unsupported/unverified 分开。后续恢复不改写旧终态 |
| 拥塞/断连 | 客户端阻塞时取消清理 | owner 阻塞 5 秒需取消并关闭会话；observer 自有队列，落后只断订阅并标 gap。桥必须转发上游 owner EOF |
| 留存/重启 | 不保证重启恢复 | 结果关闭后留存 24 小时，过期 ResultExpired；旧键不能变新执行。实例重启拒绝旧请求，无法证明副作用时 OutcomeUnknown，不自动重放 |

创建记录额外受每主体 10,000 条限制；到期墓碑保留到实例结束且仍计配额。会话变更键上限 10,000；达到限额仍须保留关闭、取消、查询。事件环保留最近 1,000 条且总编码大小 ≤1 MiB，EventsExpired 后取快照，不能因删事件而删去重键。上述均为候选实验参数，不是产品 SLO。

传输保留 UTF-8 JSONL、base64 字节、1 MiB 含 LF 帧上限、16 KiB 解码输出块及 10 MiB 每操作输出留存；新增 stdin/write/patch 单次解码上限 256 KiB，编码后仍受帧上限约束。BOM、batch、重复键、非有限数字和未知安全字段应拒绝。现有静态校验器不是网络解析器，**没有验证这些原始字节拒绝行为**。

## SESSION-01 的候选裁决及最小复现

采用单 owner 候选 A：控制台在线不会延续断开的 Agent owner。观察、审批、管理角色分别鉴权；M1 不提供 owner 接管、重连续跑或后台任务。多个 Agent 不能通过为同一工作区另建 session 绕过并发限制；需要独立登记且经服务证明不冲突的工作区。

前置条件：真实服务 I1；已认证的执行主体连接 A；同一服务上有观察/审批权限的控制台 C；环境 E1/revision 3；ready 会话 S1 由 A 所有；X1 在途；存在未决审批 P1。ID 均为合成标签，不能作为权限来源。

1. 断开 A，保持 C 在线。服务原子转 S1 为 closing、增加 generation、使 P1 失效、撤销 grants、取消并核验 X1 和 worker。A 显示 OutcomeUnknown，不能伪造已收到 completed。
2. C 提交 P1 的迟到决定，期望 -32007 / SessionClosing，无新 grant/负载；C 从权威快照或审计观察清理。重复关闭无额外执行或重复清理副作用。
3. 单独重新准备场景，只断 C；A 的 X1 继续。若 C 是 approver，pending 保留原 TTL，不自动批准或续期。若 C 自己是执行 owner，则必须按 owner 路径关闭。
4. 分别固定三个竞态顺序：关闭先于批准 → 拒绝；批准先于关闭但尚未消费 → 撤销；消费先于关闭 → 已登记操作进入取消/回收。不能用一次顺序实验代替另外两种。
5. 再从 creating 阶段断开 A：即便从未收到创建 ACK 或 helper 随后报告成功，也不得转 ready/启动负载；迟到资源同样进入清理。新连接只能经鉴权查询原记录，不创建替代资源或接管 owner。

对应 PUSH-3 A02/A03/A04/A23/A24。这里明确了候选设计，实际鉴权、原子仲裁、资源回收和多连接验证均未完成，不能把“SESSION-01 已有裁决”记作动态验收通过。

## 验证交接表

以下是待真实后端执行的步骤与预期，不是已经通过的测试。架构文档给出的请求字段可供实现评审；其未完整规定的响应 schema 不在这里擅自冻结。

| 场景 | 最小操作与必须观察的结果 | 架构验证编号 |
|---|---|---|
| 版本隔离 | 只提供 integration 版本连接 architecture 服务；VersionMismatch，零 session/用户负载，禁止静默降级 | A19 |
| 创建 ACK 丢失 | 原连接同键同内容重试仍是原 session；改变内容冲突；原 owner EOF 后新连接查询原记录，不能复活 | A23/A24 |
| 创建与容量 | 旧 key 的结果优先于工作区 Busy；新 key 受工作区/配额约束；到期键 ResultExpired，重启旧 instance 拒绝 | A23 |
| 审批 ACK 丢失 | 同 decisionKey 查询/重试不再签 grant；不同 key 已决定拒绝；批准本身启动数为零 | A06 |
| once 准备失败 | 消费在准备前登记；setup_failed 不退回 once；同执行 key 查失败，新执行需新审批 | A07 |
| 文件 ACK 丢失 | 同键返回原 operationId；文件变化不导致重写或错误重验旧 hash；新键用旧 hash 返回 FileConflict | A14 |
| 快照与重复事件 | 快照 C 后只应用 >C；相同 cursor 去重；缺口重取快照。完成事件重投不能产生第二个任务或重复输出 | A17 |
| owner/observer 拥塞 | owner 持续阻塞导致取消并关闭；observer 落后仅断订阅。输出截断准确计数且不无限缓冲 | A17/A18 |
| owner EOF 与迟到批准 | 按上节五步逐项测试；控制台仍开不能成为隐式 owner | A02/A03/A04/A23/A24 |
| 实例重启 | 携旧 expectedInstanceId 的变更拒绝；查询不确定副作用给 OutcomeUnknown，不重放 | A14/A23 |

每次记录 OS/架构、服务/backend/helper 版本与摘要、已认证角色、实例/对象标识、策略/revision、输入、字节输出、事件序列、资源核验证据、退出码及清理结果。模型/worker/日志中不得出现控制凭据或 grantRef；可信 harness 的引用也须服务端认证与对象绑定。

## 尚待收敛的接口与实施入口

- 架构 §4 用小写 `setup_failed` 等 outcome，§7 正文又使用 `SetupFailed/Cancelled/TimedOut/ResourceExceeded`，示例为小写 `exited`。需在冻结 schema 前统一枚举及 resource_exceeded 的线格式；当前不能据大小写猜测或做自动转换。
- 完整 initialize/能力/限额返回、creation.get、快照与错误 payload schema 仍需架构/运行时/控制台共同评审。旧夹具中的 cleanup.complete/cancelling 不应直接作为新服务响应模板。
- 真实后端、受限文件 worker、认证控制通道及三平台资源清理仍是 adapter 的前置条件。旧工具覆盖矩阵限定 2026-10-22 固定版本取证；本次没有重新认证更新后的 Codex/Claude Code 运行行为。
- 研发负责人可独立合入此 M0 文档和离线校验改进，保留旧提交；不得因此宣称外部工具已接入或完整 M0 已验收。后续接入实现从候选版本、上述 schema 决定与真实能力证据开始。
