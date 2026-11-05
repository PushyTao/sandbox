# 接入实验合同与固定样例

核验日期：2026-10-22。版本：`sandbox.integration/0.1.0-draft.1`。
这是 PUSH-7 给架构师/运行时的评审输入，不是已实现、已批准或与 Codex、Claude Code、MCP 兼容的公开 API。依据根设计 v0.2 §§3.4、6、11；D1–D7、控制通道认证和共享会话决策仍未冻结。下面的数值是夹具参数，不是生产默认值。

## 信任边界与传输

- 可信 harness 在宿主持有模型连接，将选定本地工具请求映射到 supervisor；权限、路径、资源限额均由服务最终校验。`initialize.client` 只是诊断信息，不能声明身份、角色或授权。
- 模型工具白名单只包含 `exec.*`、`file.*`、`permissions.request` 和必要查询。`approval.resolve` 及授权引用/秘密不进入模型 schema、上下文、日志或负载环境。审批控制连接必须由服务从带外认证/启动关系识别；客户端写 `role=approver` 无效。
- stdio 用 UTF-8 JSON-RPC 2.0 JSONL，每行一个对象，不支持 batch；请求 id 为非空字符串，同一连接内不得与未完成请求重复。stdout 只写协议，stderr 写脱敏诊断。负载有独立管道，永远作为字节数据封装；负载打印 JSON/终端转义序列不形成控制消息。
- 单帧上限 1,048,576 字节（含 LF，拒绝 BOM）；单输出块原始数据上限 16,384 字节。字节一律 `{encoding:"base64",data:"..."}`。非法 JSON/UTF-8/超长帧不得执行；返回可表达的标准错误后关闭连接、撤销 grants、取消资源。帧无法安全解析时不猜 request id。
- `initialize` 必须是首个业务请求；精确协商实验版本，不接受“尽量兼容”。不匹配返回 `VersionMismatch`，不得建 session。未知安全参数报 `-32602`，不忽略；未知方法报 `-32601`。

## 生命周期、并发和重试

`session.create` 固定工作区、有效策略 hash、后端版本、required capabilities 和 owner 连接。示例工作区 `workspace://fixture` 是由可信宿主预绑定的逻辑引用，不是平台路径；CLI 不得把它原样当成磁盘目录。

候选并发限制：每 session 一个在途有副作用的操作（exec、file.write、file.apply_patch），服务总计四个；超限返回 `Busy`，不排无界队列。能力必须同时覆盖 exec 与文件 worker 的隔离、网络拒绝和必需清理；缺失则 `UnsupportedCapability`，负载启动数为零。能力声明本身不是安全证据。

`exec.start` 使用 argv 数组、明确的 workspace 相对 cwd、受控 env 增量、初始有界 stdin 或关闭 stdin、timeoutMs、requestKey。服务拒绝绝对/越界 cwd 及未知环境项，最终路径/对象裁决留在后端。Unix/Windows 的 argv 转义、路径大小写、编码、进程终止方法不能相互推定。M1 不提供 PTY、持续输入或默认 shell。

状态：`accepted → running → cancelling → terminal`，或 `accepted/running → terminal`。terminal 的 outcome 分为 `exited/cancelled/timed_out/setup_failed`；正常非零退出仍为 `exited`，不可仅凭 stderr 或 EACCES 判为策略拒绝。`exitCode` 可以是 null；平台状态用可选 `platformStatus` 保存，不把 POSIX 信号、Windows NTSTATUS 混成统一整数。

服务在资源准备成功前不得运行用户命令。`exec.start` 返回的 execId 只是已接受；后续准备失败也必须有终态。start 响应先于对应事件，所有 exec 事件共享从 1 递增的 seq。`exec.completed` 仅一次，且在输出排空和清理结果确定后发送；之后不得再发输出。查询返回同一终态快照。

timeoutMs 从实际启动起用单调时钟计算；准备、终止宽限和清理各有服务端上限。超时发起终止全部受管后代，等待清理，返回 timed_out 和 cleanup 状态。运行超时与客户端等待 RPC 超时分开：客户端等不到响应不能推断没执行。

`exec.cancel` 幂等：运行中返回 `cancelling`；再次返回相同状态；终态后返回原终态和 `alreadyTerminal:true`。取消确认不是已经清理。取消与自然退出竞态按服务线性化的终态裁决，不覆盖已经发生的 exited。取消/超时不撤回已经发生的文件和远端副作用。

去重：session 内保存 requestKey 到终态/关闭；同 key、同语义请求返回原 execId，不能再启动；不同内容返回 `DuplicateKeyConflict`。比较规范化后的完整执行请求（包括权限/策略绑定），不比较 JSON 文本顺序或 JSON-RPC id。不承诺 exactly-once。服务不可达时呈现 `ServiceUnavailable`；若发送后连接断开则呈现 `OutcomeUnknown`。不得自动重放可能已接受的执行，也不在断连后新建 session 猜测原执行结果。

## 输出、文件及断连

- stdout/stderr 原始字节保真；客户端显示可采用带替换符 UTF-8 解码，但原始 base64 可复核，UI 转义终端/HTML 控制字符。
- 示例累计留存上限 10,485,760 原始字节，跨两流合计。超限继续排空、丢弃超额字节；完成事件含 `outputTruncated` 与 `droppedBytes`。若客户端持续不消费，队列上限 1,048,576 字节，5 秒发送超时后取消并清理。客户端本身也设接收上限；不能无限缓冲来“保证日志完整”。
- `file.read/write/apply_patch/list/search` 为实验工具集合；search 是对设计文件 worker 的候选扩展。每项都在同策略受限 worker 内操作，不由 supervisor 用宿主权限代读写。文件写/patch 包含 expectedSha256（新文件明确 expectedAbsent）和大小上限，旧内容冲突返回 `FileConflict`，不覆盖。多文件 patch 的原子性暂不承诺，未实现前只能单文件。
- session.close、owner EOF、非法协议或 owner 进程结束都进入 closing：拒绝新请求、撤销全部 grants、取消在途操作、收集进程/临时资源。完整回收才为 closed；否则 closed_incomplete 并记录资源和失败原因。重复 close 返回已知状态。
- 断连后不能把终态事件发送到已死连接并称客户端已收到；客户端显示 outcome/cleanup unknown，真实清理结果留在受保护审计中由可信控制面读取。服务崩溃及重启恢复不在该实验版保证范围，需真实后端提供独立回收证据。

## 审批只可申请

`permissions.request` 绑定服务规范化的不可变 pending request、session、原 policy hash、资源增量、理由及期限；前置审批可无 retryOf。服务生成非秘密 approvalRequestId 并通知可信控制面。模型看得到 pending/denied/expired 等状态，但不能凭 ID 决定审批或消费授权。

可信 UI 审批发生在独立控制角色。once 授权绑定不可变请求并在启动前原子消费；session 授权绑定范围/身份/版本/期限，可撤销，每次执行重新评估。控制面凭据既不返回给模型也不下发到 worker。硬策略不能被 grant 覆盖，Git 硬保护/可审批软限制的歧义由架构决定；本版不展示 Git 写授权。

批准不自动运行/重跑。可信 harness 在用户/模型明确选择继续后，用新 requestKey 提交绑定请求，受保护控制元数据附 grant 引用；模型侧返回已脱敏状态。失败后 retryOf 只用于关联，不意味着副作用可回滚。请求正文指向的脚本若可变，需要可信内容快照/摘要或明确按资源权限授权。

## 错误表

| code | data.kind | 接入处理 |
|---|---|---|
| -32700 / -32600 / -32601 / -32602 | JSON-RPC 标准错误 | 解析/结构/方法/参数失败；不执行 |
| -32001 | VersionMismatch | 显示双方版本，停止初始化 |
| -32002 | UnsupportedCapability | 列缺失能力，零负载启动 |
| -32003 | PermissionDenied | 不能通过客户端角色或请求字段自行授权 |
| -32004 | DuplicateKeyConflict | 新意图才使用新 key；不盲重试 |
| -32005 | Busy | 未接受，可在明确预算内稍后重试 |
| -32006 | FileConflict | 重新读取，交调用方合并 |
| -32007 | SessionClosing | 不接受新操作 |
| -32008 | NotInitialized | 先完成协商 |

`ServiceUnavailable/OutcomeUnknown/InvalidServerFrame` 是客户端传输诊断，不伪造成服务器 JSON-RPC 响应。操作失败和清理失败分别记录；不可用一个 `success` 隐藏部分清理。

## 样例的读取与验证

固定夹具：`examples/protocol-fixtures/integration-draft-1.json`。顶层和 `sender/message` 包装是测试元数据，**只有 message 对象**按 UTF-8 JSONL 发送。`observation` 是断连/带外审计/客户端错误的预期观察，不是 wire 消息，也不是已经发生的执行记录。每个场景独立；执行场景预设已协商 session `s-1` 和受限固定负载，权限来源不能由这些数据建立。

从仓库根执行 `python docs/integration/validate_fixtures.py`，只验证 JSON-RPC 形状、响应配对、二进制长度、顺序/终态、去重及安全样例自洽性。通过不表示存在 server、adapter 或安全隔离。真正运行仍依赖 [闭环计划](agent-loop-and-handoff.md)。
