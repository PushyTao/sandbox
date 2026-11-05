# 实验契约验证场景与验收程序

日期：2026-11-04。对应 `sandbox.architecture/0.1.0-draft.1`。**以下是未来真实服务的可执行验收步骤，不是已经通过的测试。** 本轮只有 Windows 探针和文档检查的实际证据，见[独立评审](review-c19b235-2026-11-04.md)。无真实服务时不得用 mock、静态 JSON 解析或宿主直接运行负载替代隔离验收。

## 准备与观测

在授权 runner 上用临时合成数据：服务预登记工作区 W、外部文件 O=`outside\n`、工作区文件 F=`wrong\n`、只读解释器 profile 和固定 `check` 程序（读取 F，等于 `right\n` 返回 0，否则返回 1）。另备固定长任务：报告 ready、派生合成后代，等待服务终止。不得访问真实秘密或真实仓库 `.git`。

服务测试接口只在隔离测试构建中提供故障注入屏障，不对模型/普通用户暴露：审批 CAS 前、grant 消费后启动前、文件提交后 ACK 前、closing 状态落定后、审计写失败和 helper 启动失败。没有屏障时记录竞态覆盖不充分，不能用 sleep 碰巧成功声称竞态已验证。

建立三个独立认证连接：A 为 owner harness、C 为 approver/observer、O 为只读 observer；另有无身份客户端 U 和受限负载 P。准备故意分配给不同主体的第二个 session 作越权测试。驱动保存原始帧（脱敏、限额）、快照、操作去重表的测试观察、启动计数、文件前后 hash、原生资源身份及清理证据。每项按 OS/架构/后端/helper/文件系统/权限环境、固定源码 SHA、命令和退出码单独记录。

## 身份、所有权与授权

| ID | 操作步骤 | 必须断言 |
|---|---|---|
| A01 / PR-2 | U 在 initialize 自报 approver；P 尝试打开管理通道/继承句柄；P 输出 approval.resolve JSON 和控制序列 | U/P 不获得管理能力，零 grant/零额外启动；输出仅是字节；C 才能访问授权的审批 |
| A02 / SESSION-01 | A 启动长任务 X，C/O 订阅；A EOF，C 保持在线，C 随后批准旧请求 | session 先 closing，pending/grant 失效，X/后代清理；晚批 SessionClosing，启动计数不增加，C 看见实际 cleanup |
| A03 | 先关闭 O，再关闭 C，保持 A；另测控制台自己是 owner 的会话 | observer/approver 掉线不取消 A；pending 按原 TTL；控制台作为 owner 掉线则关闭其会话，不接管 |
| A04 | 在 approval CAS 前/后及 grant 消费前/后放置屏障，与 owner EOF 并发；每种顺序分别释放 | closing 先赢不能签发/启动；签发先赢会撤销；消费先赢已登记操作被取消且无孤儿；closing 后不 resume 新负载 |
| A05 / AUTH-1 | 一次软授权执行后，用新 key 再用 grant；更换主体/session/instance/policy/请求内容；再测过期、撤销和硬 Git 保护 | 全部拒绝，零新增启动；相同执行 key 的原内容重试是查询原 exec，并非第二次消费 |
| A06 | 批准后丢失 ACK，以同 decisionKey/内容重试；换内容或换 decisionKey 再批 | 同键返回原决定，仅一个 grant；同键异内容冲突；异键已决返回 ApprovalAlreadyResolved；不会自动执行 |
| A07 | 消费 once 后让 helper 准备失败；同 key 重试；新 key 再用旧 grant | 原失败可查询，不退款、不新启动；新意图需新审批；失败清理有独立结果 |
| A08 | 批准绑定脚本内容后由低权限写者改脚本/缓存；试图同时创建更高权限任务 | 使用可信快照时运行的是批准内容；不能隔离输入或仍有低权限写者则拒绝；argv 相同不足以放行 |
| A09 | 执行中撤销授权，负载持有已打开文件/网络连接；保留普通会话查询 | 阻止新消费，终止关联操作并验证句柄/连接终止；必要时关闭整个会话。未确认时不报告完整撤销 |

## 环境、数据、事件与生命周期

| ID | 操作步骤 | 必须断言 |
|---|---|---|
| A10 / C1 | E:R 创建 S1，保存 R+1；新会话在不同已批准工作区或 S1 清理后创建 | S1 固定 R，下一会话固定 R+1；配置保存不产生执行/授权，也不热更新 S1 |
| A11 | 活动/残留 session 下删除 E；与 session.create 并发；正常关闭并核验后再删 | EnvironmentInUse；创建/删除原子仲裁，不留引用已删环境的新 session；删除永不删除工作区 |
| A12 | 同一目录的别名、父子目录、共享 commondir 分别登记不同环境并并发创建 | 按资源身份检测冲突或拒绝不确定组合；不能按不同环境 ID 绕过单活动工作区规则 |
| A13 / API-1 | exec 与 read/list/search/write/patch 逐个访问 O、保护名和别名，另做 F 合法读写 | 合法成功；所有非法操作拒绝或创建前 UnsupportedPolicy，O hash 不变；不能仅测试一种工具 |
| A14 | 文件 write/patch 已提交后丢 ACK；同 key/内容重试；再同 key异内容、新 key旧hash；服务重启后重放 | 同键返原 operation 和结果，仅一次写；异内容冲突；新键旧 hash 为 FileConflict；重启后旧 session无新副作用，未知结果不重放 |
| A15 | X 取消重复两次；自然退出登记前后分别送取消；另测超时/准备超时 | 只一个结果，已登记结果不被晚取消改写；取消 ACK 与 cleanup 分开，时间按单调时钟；已有写入不回滚 |
| A16 | 返回 start ACK 后准备失败；自然退出后仍有脱离后代；再做 supervisor 崩溃 | 每个已接受操作有结果或明确 unknown；完整清理须由原生身份/资源确认，根退出不足；重启不迁移授权或仅凭 PID 误杀 |
| A17 | 在 snapshot(C) 读取期间产生事件；客户端收到乱序/重复/缺口；observer 停读超过队列/留存 | 只应用 C 后事件，重复去重，缺口重取快照；权限过滤保留脱敏游标；observer 问题不影响 owner |
| A18 | owner 停读；发送超限输出、非 UTF-8、两流交错；接着查询完成快照 | 输出字节正确、合计留存和队列有界、droppedBytes 正确；持续阻塞 5 秒后取消关闭；completed 后无输出，实际 cleanup 独立记录 |
| A19 | 帧刚好上限/超过一字节，非法 UTF-8/BOM/batch/重复 JSON键/未知安全字段；不匹配协议 | 明确错误且零新副作用；致命解析错误关闭 owner并回收；未知版本不写不批，无隐式降级 |
| A20 | 消耗会话10,000键；同键查询；第10,001新键；推进到关闭后24小时再查/重放 | 旧查询仍可；新键 ResourceExceeded/容量拒绝不执行；到期 ResultExpired，旧 session不复活 |
| A21 | 审计介质写失败、配额满；在有活动操作时升级；迁移失败后回滚 | 敏感新操作拒绝、受影响活动操作取消，缺口可见；升级排空并确认资源才替换；不迁移旧 grant，不覆盖工作区 |
| A22 | 清理某工作区失败后新建同资源任务；另在无关工作区建立会话；尝试 UI提交删除路径 | 相关资源封锁，无关资源不误删；仅服务登记并重新验证归属的恢复操作可用；恢复事件不改写历史执行结果 |
| A23 | 创建意图登记后丢 session.create ACK；同主体同 key重试/creation.get；更改请求；再断开owner，用新连接查询或重复原key；重启后带旧expectedInstanceId重发 | 仅一份创建记录/session/资源；同内容返回原结果，异内容冲突；容量检查不掩盖去重结果；新连接不能继承owner或新建替代session；过期旧键不再创建，旧实例请求InstanceMismatch |
| A24 | 在 creating 的资源登记后、helper准备成功前、ready状态提交前分别注入owner EOF；再测试ready先赢的顺序 | 所有顺序都无孤儿：关闭先赢不能变ready/运行负载，迟到helper资源也收尾；ready先赢走正常取消；未收到创建ACK仍须完整清理或显式incomplete |

硬 Git 保护用例至少包含 `.git` 目录、指针、外部 gitdir/commondir、子模块、嵌套仓库、hooks/config、尚不存在的保护条目及 hardlink/rename/link 双端。批准软路径也不能绕过任一硬规则；soft Git 操作在当前 profile 为不支持，不以 mock“成功授权”代替。

## 最小端到端顺序

1. 安装/doctor 记录具体组件配对；真实认证并 initialize；验证 required 能力缺失时零启动。
2. 环境保存→session.create→file.read(F)→exec(check)：预期退出 1。
3. 单文件 patch 将 F 改成 `right\n`→exec(check)：预期退出 0；核对两次清理及输出。
4. 申请 O 的受限软权限，C 拒绝一次、过期一次、允许 once 一次；A 显式继续并新 key执行；跨会话和重放负例必须拒绝。若当前后端不能安全实施该软权限，记录能力不足，此闭环未完成。
5. 取消固定长任务→会话可复用；再启动长任务并 owner EOF→会话关闭、授权撤销、后代与私有资源确认回收；C 观察全程。
6. 关闭后查询、删除配置，工作区 F/O 保留。保存审计/资源证据及模型是否真实参与的说明。

上述人工协议驱动通过只代表服务/后端闭环；真实模型、Codex、Claude Code 及整体 CLI 包装分别固定版本验证所有工具/旁路，不自动互相替代。NET-2、PTY、Broker 是后续能力，未实现请求明确拒绝。
