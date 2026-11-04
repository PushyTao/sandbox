# 本地跨平台 Agent 沙箱 —— 技术方案

| 项 | 内容 |
|---|---|
| 文档版本 | v0.2（评审修订稿） |
| 日期 / 资料核查日期 | 2026-09-30 |
| 状态 | **规划中**；下文“建议”是评审建议，未代替第 14 节的产品决策 |
| 目标平台 | macOS / Linux / Windows；按能力分别验收，不承诺同日交付 |
| 核心实现语言 | 建议 Rust，待确认 |
| 对标范围 | Codex CLI、Claude Code 的本地执行隔离、权限控制与集成体验 |

> 本轮主要调整：明确威胁模型和 Agent 接入边界；修正平台事实与过强保证；补全策略编译、审批、进程和协议契约；将默认断网、最小 Agent 接口及审计提前；把待确认事项改为可取舍的决策表。本文是设计，尚无实现或安全测试结果。

---

## 1. 背景与目标

### 1.1 背景与威胁模型

Agent 会执行模型生成的命令，也会运行仓库脚本、依赖安装脚本及第三方工具。提示注入可以把一次正常任务变成恶意操作。因此，即使产品面向单用户开发机，**沙箱内代码也必须按可能主动绕过限制的不可信代码处理**，不能只防误操作。

建议保护的资产：

- 工作区之外的文件、宿主凭据、Agent 配置、宿主进程及管理接口。
- 工作区内被明确保护的文件和 Git 元数据。
- 被策略禁止的网络目标，以及受限的 CPU、内存、进程和输出资源。

信任假设：宿主内核、管理员、已安装且未被替换的 supervisor/helper、可信策略源及审批界面可信。模型输出、仓库内容、子进程输出和从网络取得的数据均不可信。宿主同用户恶意进程若已能调试/修改 supervisor，通常已超出本方案保护范围；仍需阻止**沙箱子进程**通过这些路径影响宿主。

不承诺抵御内核漏洞、管理员攻击、物理攻击和所有侧信道。不承诺已授权文件不被删除，也不承诺已授权网络服务不会被用于外泄。沙箱不能替代备份、秘密管理和外部操作授权。

### 1.2 目标

- 接近对标产品的常见编码工作流：读代码、改文件、运行构建与测试、受控安装依赖、必要时申请额外权限。
- 同一策略具有统一的含义；后端不能完整表达时，明确拒绝该策略，而不是近似执行。
- 提供独立 CLI、Rust 库、Agent 服务接口；Node/Python 优先提供协议客户端，再按需求提供原生绑定。
- 安全限制必须在不可信代码执行前生效，并覆盖后续子进程。
- 用正向兼容测试和负向绕过测试证明行为，不能只测试“配置已读入”。

### 1.3 非目标

- 不实现模型推理、规划、记忆或完整 Agent 框架。
- 不在首版承诺云端多租户隔离、GPU、图形桌面或浏览器隔离。
- 不把沙箱视为事务：超时、拒绝或取消不会自动撤销已发生的写入和外部操作。
- 首版不实现本地微 VM；但保留其作为更强隔离后端的可能性。
- MCP、浏览器、远程连接器等未进入本沙箱的工具，不自动继承本沙箱权限。

### 1.4 定位与安全承诺

**本方案提供基于 OS 机制、具有明确适用范围的安全边界。** 不宜称为“只有围栏、没有安全边界”，也不能把它等同于虚拟机隔离。

安全性来自权限模型、内核机制、启动器、挂载/ACL、网络出口和可信控制面的组合。Job Object 单独不是文件或网络访问控制；bubblewrap 是构建沙箱的工具，实际强度取决于调用者配置；Seatbelt 接口的长期支持风险应单独管理。这些事实均不能推出“OS 沙箱只能防误操作”。

更高风险场景可选择 VM 或专用主机以减少共享内核风险；VM 同样需要管理共享目录、网络、凭据和审批，不是自动安全的替代品。

---

## 2. 需求与范围

### 2.1 对标基线与事实边界

以下仅概括核查时的公开能力，**产品默认值、可配置能力和独立开源 runtime 必须分开**。实现前应固定参考版本/commit，不能依赖滚动文档长期不变。

| 维度 | 核查结论 | 对本方案的启示 |
|---|---|---|
| Codex 本地后端 | macOS 使用 Seatbelt；Linux 当前默认 `bwrap + seccomp`；Windows 有原生后端 | 不再把 Linux bwrap 写成仅实验性路线 |
| Codex 权限 | 沙箱权限与审批策略分离；可写根内还保护 Git 和 Agent 配置等路径 | 文件、网络与审批分轴建模；保护例外需后端验证 |
| Codex Windows | elevated 使用专用低权限用户、文件权限、网络防火墙等；unelevated 是较弱的受限令牌方案 | “管理员安装”不等于“命令以管理员运行”；不能将两者能力等同 |
| Claude Code 本地产品 | 官方文档列 macOS/Linux/WSL2，原生 Windows 尚未支持；提供网络代理和可配置凭据保护 | 不把云端/Cowork 的 VM 与本地 Bash 沙箱混为一谈 |
| sandbox-runtime | 独立项目的当前 README 已列 Windows alpha 实现 | “Claude Code 不支持 Windows”不能推导“runtime 没有 Windows 代码”，也不能把 alpha 视为生产可用 |
| 集成协议 | Codex app-server 是完整 Agent 接口；本方案是执行接口 | 可以借鉴请求/事件/审批结构，不声称协议兼容 |

来源：[Codex 权限与安全](https://learn.chatgpt.com/docs/agent-approvals-security)、[Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)、[Claude Code sandbox](https://code.claude.com/docs/en/sandboxing)、[sandbox-runtime](https://github.com/anthropics/sandbox-runtime)、[Codex app-server](https://learn.chatgpt.com/docs/app-server)。

### 2.2 功能基线

| 能力 | 最小要求 | 建议阶段 |
|---|---|---|
| 文件隔离 | 明确读范围、写范围、保护例外、私有临时目录 | M1 |
| 网络隔离 | `deny` 必须真实生效；不支持的网络模式报错 | M1 |
| 执行 | argv/cwd/env、流式输出、超时、取消、状态查询 | M1 |
| Agent 接入 | versioned stdio RPC；执行和文件工具使用同一策略 | M1 |
| 审批 | 带外授权、最小增量、期限、撤销、拒绝语义 | M1 |
| 审计 | 策略摘要、后端能力、执行/审批/清理结果 | M1 |
| 交互与后台任务 | PTY/ConPTY、持续 stdin、resize、受管后台进程 | M2 |
| 受控联网 | 域名/端口策略、DNS/IP 防绕过、依赖安装预设 | M2 |
| 原生 Windows | 独立能力验收；需提前做可行性验证 | M0 验证、M2 交付 |
| 凭据 Broker | 长期秘密留在可信侧、按服务限制用途 | M3 |

### 2.3 非功能要求

| 项 | 修订后的要求 |
|---|---|
| 失败模式 | fail-closed：所需能力缺失、策略不可表达、初始化或自检失败时不运行负载 |
| 性能 | 将“准备时间 < 50 ms”改为待测目标；分别记录冷/热启动 p50/p95、策略规模和自检成本，M0 后定 SLO |
| 一致性 | 统一语义 + 能力协商；不以最低公共能力静默削弱所有平台 |
| 分发 | 优先单个用户入口；允许签名 helper、系统组件、平台安装步骤，明确依赖清单 |
| 可运维 | `doctor` 输出能力、版本和失败原因；不自动修改宿主安全设置 |
| 数据处理 | 输出有大小上限和背压，日志脱敏；审计存储不在子进程可写目录 |
| 多会话 | 策略、临时目录、代理授权、输出、审批及进程资源按会话隔离 |

“单静态二进制、零依赖”不作为三平台硬承诺：Linux bwrap、Windows 安装和防火墙配置、Node/Python 宿主运行时都需要明确处理。

---

## 3. 总体架构

### 3.1 实现路线与语言选择

建议采用 **Rust 策略/控制核心 + 平台适配器 + 成熟 OS 工具复用**，而不是首版重写每个平台的所有底层机制。Rust 适合系统接口、类型化协议和资源生命周期管理，但不是唯一可行语言。

| 路线 | 优点 | 主要代价 | 建议 |
|---|---|---|---|
| A：Rust 核心，复用 bwrap/系统机制，平台适配自研 | 可控制契约、分发与跨平台实现 | Windows 和策略编译仍需较多验证 | 首选 |
| B：基于 sandbox-runtime 适配或 fork | 较快获得现有文件/网络能力 | 运行时、版本耦合、协议与产品目标需匹配 | M0 做复用评估，不能先认定不可用 |
| C：以容器/VM 为主要后端 | 更容易提供独立文件视图，VM 减少共享内核风险 | 启动、同步、工具链与宿主开发体验成本 | 隔离等级要求更高时采用 |

不以“Rust 唯一能跨平台”或“与某产品 crate 结构相似”作为架构成立的证据。复用开源代码须记录版本、许可证、补丁维护责任和更新策略。

### 3.2 组件与信任边界

~~~text
可信宿主集成层
  CLI / IDE / Agent harness / Node、Python client
       │ 执行请求（模型可影响）           │ 审批决定（仅可信 UI/宿主可提交）
       ▼                               ▼
  sandbox-server / sandbox-core supervisor
  身份与会话 · 策略合并 · 能力探测 · 审批 · 生命周期 · 审计
       │
  PolicySpec → ResolvedPolicy → BackendPlan
       │
  平台 launcher/helper ─── 可信 egress proxy / credential broker
       │                     ▲ 唯一获准的网络出口
======= 不可信执行边界 =======│====================================
  命令、shell、工具 helper、仓库脚本及全部后代
  受限文件视图 / 私有 temp、HOME / 最小环境 / 受管进程
~~~

`sandbox-spec` 只含版本化数据结构与纯策略运算。`sandbox-core` 负责有系统调用的解析、能力检查和编排；后端负责编译与强制。网络代理是独立可信组件，M1 可先只实现“禁止网络”，无需先实现域名代理。

### 3.3 公共契约

后端 trait 保持内部化，但公共 API 不能只有 `Policy + ExecResult`。至少需要：

- `PolicySpec / EffectivePolicy / Capabilities`：请求的限制、实际生效限制和后端能力。
- `Session / ExecRequest / ExecHandle / ExecEvent / ExecResult`：执行与持续交互。
- `ApprovalRequest / Grant`：不可由模型直接生成有效授权的审批契约。
- `SandboxError`：设置失败、能力缺失、普通命令失败和清理失败分开表达。

API 可保持平台无关，同时返回能力和限制。将来换成 VM 时仍可能增加文件同步、路径映射或启动延迟；抽象 trait 不能保证所有行为无变化。

### 3.4 Agent 接入的两种方式

**方式 A：Agent 在宿主，工具在沙箱（建议优先）。** 推理、会话和可信 UI 在宿主；`exec/read/write/apply_patch/search` 等处理不可信任务的本地工具，统一送入受限 worker。不要只包住 Bash，却让文件工具直接使用宿主权限。模型 API 凭据留在宿主。

宿主 harness 是可信执行路由，不代表模型的工具请求可信。MCP/浏览器/连接器若由宿主提供，应各自做授权；本方案不能宣称隔离了整个 Agent 的所有行为。

**方式 B：整个现成 Agent CLI 放进沙箱。** 更容易覆盖该进程的本地子进程，但要处理模型网络、登录、PTY、配置目录和嵌套沙箱兼容性。沙箱内 Agent 可以请求扩权，不能批准自身请求。所需网络和凭据范围通常比方式 A 更大。

外层调用 `sbx run -- codex ...` 或 `sbx run -- claude ...` 不等于已经完成产品集成；需分别测试其内置工具、外置 MCP、后台服务和网络去向。MCP 适配只是可选入口，不能强迫 Agent 把其他工具也经过该入口。

---

## 4. 策略模型

### 4.1 分开表达执行隔离、文件权限、网络与审批

以下为**建议 schema**，不是已经可用的配置。M1 仅接受已实现字段；未知字段、未来功能或无法强制的限制应报错，不能接受后忽略。

~~~toml
schema_version = 1
execution = "sandboxed"           # sandboxed | unsandboxed；后者默认禁止
filesystem_mode = "workspace-write" # read-only | workspace-write
workspace = "."                  # 相对路径基于明确传入的 config_base

[filesystem]
read_scope = "scoped"             # scoped | host-read；host-read 是显式放宽
readable_roots = ["."]
writable_roots = ["."]
deny_read = [".env", "secrets"]    # 精确路径/子树；首版不支持 ** glob
deny_write = []                   # 精确路径/子树；禁止变更，不单独禁止读
protected_entries = [".git", ".agents", ".codex", ".claude", "sandbox.toml"]
runtime_profile = "host-toolchain-v1" # 宿主维护的版本化只读运行时集合
private_home = true
private_tmp = true

[network]
mode = "deny"                    # deny | proxy-allowlist | unrestricted
allow_domains = []                # deny 模式必须为空；域名模式 M2

[environment]
inherit = ["LANG", "LC_ALL", "TZ"] # 其余按后端/工具链受控生成
# 不继承秘密、SSH_AUTH_SOCK、任意代理或动态加载/启动脚本变量

[process]
timeout_seconds = 300
termination_grace_seconds = 2
max_output_bytes = 10485760
# max_processes / memory_bytes 等硬限制：仅能力探测通过后才能设置

[approval]
mode = "on-request"              # on-request | never；never = 不扩权
allow_unsandboxed = false
max_grant_scope = "session"      # once | session
~~~

`read-only` 限制持久工作区写入，仍可允许明确列出的私有 scratch；并不自动意味着禁止网络。`workspace-write` 也不意味着可读整个宿主。`host-read` 是便利与保密性的取舍，应在有效策略中显式呈现。

`read-only` 与非空的持久 `writable_roots` 视为配置冲突，不能由某个字段静默覆盖另一个。`runtime_profile` 必须解析成可审计的路径/操作集合；安全相关环境变量由 supervisor 固定，单次 exec 的 env 增量不能覆盖。

若提供 `danger-full-access` 兼容别名，它映射到明确的 `unsandboxed` 执行，不作为“更强权限的安全沙箱模式”；只能由可信宿主在硬策略允许时启用。

### 4.2 默认行为、合并与授权上限

- 没有配置时，建议为工作区与运行时只读、网络拒绝、私有 scratch；可信宿主可显式选用 workspace-write。
- 运行时路径由宿主配置生成，包含必要的解释器、动态库、证书和系统文件；不能通过允许整个用户 HOME 解决兼容问题。
- 管理策略定义不可超越的上限。用户策略、项目策略、请求策略和批准的 grant 都不能越过它。
- 不可信仓库中的 `sandbox.toml` 只作为建议；未经宿主信任不能扩权、启用 helper、指定外部代理或切换为 unsandboxed。
- 建议合并规则：允许集合取交集，拒绝集合取并集，资源上限取更严格值；经可信审批新增的权限只扩大指定的软限制，不覆盖硬拒绝。
- 安全控制文件自身受保护；修改后不热加载扩权。新策略生成新版本并重新编译，必要时新建会话。

### 4.3 路径和操作语义

文件判断必须包含操作类型，至少区分 read/list/execute/write/create/remove/rename/link；rename/link 同时检查源与目的地。网络判断使用协议、目标和端口，不混入文件路径函数。

文件规则优先级为：

~~~text
硬拒绝 > deny_read / deny_write > protected 的禁止变更 > 可写/可读授权 > 默认拒绝
~~~

`deny_read` 禁止读取和列举所指对象，并在本方案中同时禁止其写入、替换、删除和链接，避免“读不到但可以破坏”。`protected` 只收回变更权限，不额外授予读取权限。`writable_roots` 默认同时包含读取；执行权限由工作流预设显式生成。目录是否存在、文件名等元数据的完全隐藏不作为跨平台基线。

### 4.4 纯策略与系统解析分离

~~~rust
// 示意签名，不是已发布 API
fn evaluate(policy: &NormalizedPolicy, op: &Operation) -> Decision;
fn resolve(spec: &PolicySpec, host: &HostContext) -> Result<ResolvedPolicy>;
fn compile(policy: &ResolvedPolicy, caps: &Capabilities) -> Result<BackendPlan>;
~~~

只有 `evaluate` 是纯函数。展开用户路径、读取 symlink/reparse point、识别对象、打开句柄、解析 Git 元数据都要访问 OS，不能伪装成“纯 Path → Decision”。

每次执行记录 `policy_hash`、版本化后端及能力报告；返回 `EffectivePolicy` 与请求对照。无法严格实现某字段时返回 `UnsupportedPolicy`，不能只给 warning 后继续。

---

## 5. 路径语义与文件系统隔离

### 5.1 规范化用于编译，内核负责实际访问控制

处理顺序建议为：确定配置基准与工作区 → 展开受支持变量 → 按平台解析路径与对象 → 检查规则冲突 → 生成后端约束。

`realpath` 不能处理尚未创建的路径，也不解决 hardlink 或检查后重命名问题。新建路径应以已打开的可信父目录/句柄为锚；平台可用时采用基于 handle 的相对访问与受限解析方式。不能仅用字符串前缀判定祖先关系。

内核约束能避免应用层“检查一次，随后任意 open”的绕过，但**不能推导整个启动、挂载和文件工具流程没有 TOCTOU**。解析与安装规则之间的替换、父目录 rename、别名和已打开 FD 均需验证；禁止继承不必要的文件/目录句柄。

### 5.2 子目录拒绝必须可表达

Landlock 的同层允许规则会合并，不能先给父目录写权限，再用一条子目录只读规则收回权限。简单 `ro-bind /` 后放开工作区，也不足以证明所有保护例外生效。

建议 Linux 用经过验证的挂载视图表达已有受保护子树，并以 Landlock/seccomp 等补强。编译器必须验证：

- 保护对象不能被写、截断、删除、rename 或经别名访问绕过。
- 工作区根或受保护对象的父目录不能被替换来绕过保护。
- 已存在的 hardlink 共享文件内容，`realpath` 和只读挂载的一条路径不自动保护其它别名。
- 对未来文件名的拒绝与对现存对象的拒绝是不同能力。

首版不承诺任意 `**/.env` 动态 glob。对于尚不存在的受保护条目、无法排除的 hardlink 别名等场景，应使用经验证的受控工作区视图/复制策略，或者拒绝该策略。不能把启动时扫描一次称为永久保护。扫描、复制成本应纳入性能测量。

例如工作区文件与 `.git/config` 或已声明禁止读取的秘密文件共享 inode，仅保护原路径仍可能让别名可读写。受控副本可隔离宿主写入，但必须在复制前排除禁止读取对象的别名，否则复制本身就会泄露内容；单次扫描链接数也不构成竞态安全保证。

来源：[Landlock 规则与限制](https://docs.kernel.org/userspace-api/landlock.html)、[bubblewrap 安全说明](https://github.com/containers/bubblewrap)。

### 5.3 Git 和 Agent 配置保护

建议保护每个获准工作区根的 `.git`、`.agents`、`.codex`、`.claude`、沙箱配置，以及宿主会自动加载的其他指定控制文件。嵌套仓库、子模块和新增工作区也需注册并编译，不能只扫描启动 cwd。

`.git` 既可能是目录，也可能是 `gitdir: ...` 文件；相对目标基于该指针文件目录解析。还要处理关联的 `commondir`、Git 环境变量和外部配置影响，限制解析深度并检测循环。受保护目标在工作区外时仍须受原有读策略约束，不因解析得到就自动授予读取。

包括 `GIT_DIR/GIT_COMMON_DIR` 在内的环境输入必须由受控策略约束，不能在执行时切换到未编译的元数据路径。[Git 官方目录布局](https://git-scm.com/docs/gitrepository-layout)

保护 Git 元数据会阻止 `git add/commit` 等合法工作流。建议首版支持 `status/diff`，把元数据写入作为显式增量授权；长期可增加受控 Git broker，但不能笼统开放整个 `.git` 并继续宣称元数据只读。

此保护无法消除工作区脚本带来的后续风险：用户在宿主运行 Agent 改过的构建脚本仍可能产生副作用。worktree 便于评审，但不是独立安全边界，也不是完整备份。

### 5.4 平台路径与文件系统测试集

| 平台 | 必须覆盖 |
|---|---|
| 通用 | symlink 链、hardlink、父目录替换、非存在路径、rename/link 双端、继承 FD、mount/卷边界 |
| macOS | 卷的实际大小写规则、Unicode 名称、`/tmp` 与 `/private/tmp`、路径别名 |
| Linux | `/proc/self/root`、`/proc/*/fd`、bind mount、用户 namespace、特殊设备与 Unix socket |
| Windows | junction/reparse point、大小写规则、8.3 短名、UNC、`\\?\`、ADS、设备路径、文件 ID/卷 ID、ACL 继承 |

Windows v1 建议仅支持经验证的本地文件系统路径；UNC、设备命名空间等未支持场景直接拒绝。8.3 名称只有在卷启用时才存在，测试需记录条件，不能把目录 junction 当成单文件 symlink 的等价替代。

---

## 6. 执行流程与审批回环

### 6.1 执行流程

1. 可信宿主创建会话，固定工作区、策略来源、授权上限与后端。
2. 探测所需能力，解析策略，生成有效策略与执行计划。
3. 创建私有 HOME/temp、受控环境、进程容器及必要代理；关闭多余 FD/handle。
4. 在可信 bootstrap 内安装隔离；Windows 使用受限身份创建 suspended 进程，加入已配置的 Job 后 resume，避免先启动再约束。
5. 完成必要自检；失败则终止准备，不运行用户命令。
6. 执行 argv；流式输出、超时、stdin 和取消由 supervisor 管理。
7. 记录退出状态，终止会话应结束的后代，清理资源并报告完整性。

默认使用 argv 数组与明确的 cwd，不拼接 shell 命令。需要 shell 时明确指定解释器和脚本文本，shell 及全部后代仍在同一隔离范围。`cd/export` 不跨独立 exec 自动持久化；持续 shell 是显式进程句柄。

### 6.2 审批策略与沙箱策略独立

建议支持：

- `on-request`：边界内直接执行；需要额外能力时申请。
- `never`：不进行交互扩权，请求超限即拒绝；绝不意味着允许所有操作。
- 可信宿主可增加外部业务审批，但不能以“模型认为安全”替代底层权限限制。

审批可以在执行前发生，也可以在失败后由 Agent 提出。普通非零退出、`EACCES` 或 stderr 中出现 “sandbox” 都不能单独证明沙箱拒绝；没有可靠证据时返回“原因未知/可能受限”。

### 6.3 授权对象与重试语义

`ApprovalRequest` 至少包含 session/request ID、argv/cwd/env 摘要、原 policy hash、拟新增路径/目标/动作、权限差异、理由和期限。原执行 ID/`retry_of` 仅在失败后重试时提供，执行前审批可以没有它。宿主决定 `once / session / deny`。

`Grant` 由可信控制面签发或持有，绑定调用者、会话、策略版本、范围及有效期，防重放和跨会话使用。一次授权还绑定不可变的待执行请求，并在启动执行前原子消费；会话授权绑定可复用的权限范围，后续每个新请求重新评估，不要求复用同一命令摘要。会话授权可撤销，不能仅凭同样的命令前缀通配任意 shell 脚本。

**失败后禁止静默自动重跑原命令。** 第一次运行可能已写文件或完成部分远程操作。Agent 必须明确选择重试/改写命令，返回结果注明已有副作用不保证回滚。审批绑定命令文本也不保证其引用的可变脚本内容没变；若审批依赖具体内容，需要固定快照/摘要，否则应按授予的资源权限解释授权。

优先只增加必要路径或网络目标，继续保留其他限制。`unsandboxed` 是独立高权限授权，默认关闭。

### 6.4 控制通道与数据通道

server 的 stdio 可以是**可信客户端与 supervisor**之间的控制通道；子进程的 stdin/stdout 必须是另外的句柄，其输出只能作为数据事件封装。禁止扫描子进程输出中的 JSON、“批准”字样或终端控制序列来触发授权。

模型可访问的工具面只能请求扩权，不能调用可信 `approval.resolve` 或拿到授权凭证。控制管道、socket、代理管理端口及审批令牌不能暴露给负载；还需阻止通过进程句柄、ptrace、继承 FD 等间接获得它们。

### 6.5 清理和存活范围

| 平台 | 机制与限制 |
|---|---|
| Linux | 建议独立 PID namespace、受控 init/reaper，必要时结合具备委派权限的 cgroup v2；进程组不能约束 `setsid`/双重 fork |
| Windows | Job Object、禁止 breakaway、`KILL_ON_JOB_CLOSE`；负载不继承 Job 管理句柄，测试 supervisor 崩溃行为 |
| macOS | 进程组和监督机制需验证；仅 `kill(-pgid)` 不能保证回收全部脱离进程组的后代 |

超时/取消：请求终止 → 宽限期 → 强制终止 → 回收/验证 → 返回结果；Windows 使用对应平台机制，不套用 SIGTERM。supervisor 崩溃、客户端断连和根进程先退出均要测试。

Job 只约束已归入其中的进程。需阻止负载借 WMI、服务或其它宿主代理在 Job 外启动程序；Linux/macOS 同样不能暴露等价的宿主代执行接口。[Job Objects 的子进程规则](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)

`cleanup.guaranteed` 与 `cleanup.best_effort` 必须是可见能力。要求保证回收而后端不能做到时拒绝创建会话；macOS 的强回收可行性是 M0 重点。普通 exec 结束后默认不允许遗留后台进程；显式后台进程必须归属会话、可查询/停止、有 TTL，M2 再提供。

撤销文件权限不会自动收回已打开 FD。需要立即撤销时终止相关进程/会话；网络代理撤销应同步关闭相应活动连接，并清楚区分“仅禁止新连接”。

---

## 7. 网络隔离与凭据管理

### 7.1 排期与基线

建议 **M1 实现网络 deny，M2 实现受控代理联网，M3 实现凭据 Broker**。不能在 M1 接受 `network.mode="deny"` 却只留占位。

默认断网与文件保密都重要。只禁止外连仍无法阻止秘密通过 stdout、文件产物或宿主 Agent 上传到模型服务，因此默认读取范围也应收敛；“断网 = 不会外泄”不是本方案承诺。

### 7.2 强制路径

~~~text
受限进程
  → 平台强制：禁止直连、宿主 IPC 和未授权出口
  → 唯一获准的代理数据通道
  → 代理解析 hostname + 目标 IP/端口校验
  → 外网
~~~

设置 `HTTP_PROXY`/`HTTPS_PROXY` 只帮助兼容代理的程序，不能强制恶意程序遵守。代理未启动、退出或校验失败时，不得恢复直连。

| 平台 | 建议约束 |
|---|---|
| Linux | net namespace + 受限 relay/代理通道；mount 视图隐藏宿主 socket，补充限制 abstract Unix socket 与其它 IPC |
| macOS | Seatbelt 限制外连，只允许经验证的代理端点；Unix socket、Mach 服务和本地 IPC 单独验证 |
| Windows | WFP/防火墙/隔离身份或 AppContainer 能力组合；受限令牌本身不实现网络拒绝 |

Landlock 已有随 ABI 演进的端口级网络能力，不应写“完全管不了网络”；它仍不能单独表达本方案的域名策略。Linux 需按所需能力探测，不以固定内核版本等同完整支持。[内核文档](https://docs.kernel.org/userspace-api/landlock.html)

### 7.3 域名策略必须同时检查网络地址

- 对协议、规范化 hostname 和端口作联合判定。首版建议精确域名；若支持通配符，明确子域与根域语义，禁止模糊字符串后缀匹配。
- 校验 IDNA、大小写、尾点、IPv4/IPv6 字面量和 IPv4-mapped IPv6；默认拒绝 IP 直连与非公共地址例外。
- 由可信代理解析 DNS，校验所有候选 A/AAAA 地址，并连接**已校验的地址**，避免校验后再次解析导致 rebinding。
- 默认拒绝 loopback、私网、链路本地、元数据端点及宿主服务。开发服务器例外按明确地址/端口授权；不要整体开放 localhost。
- 对 HTTP 重定向逐跳重新授权；HTTPS CONNECT 只能限制隧道目的地，不能检查隧道内路径/方法/内容。
- DNS、UDP、QUIC、SSH、SOCKS、Unix socket 和本地 named pipe 不得成为旁路。未支持协议明确拒绝。
- 不向负载提供外部 DNS 出口；若支持域名通配符，还应评估代理代查任意子域名形成的数据通道。

已批准域名仍可能提供上传、消息或可由攻击者控制的内容。允许 `github.com` 或模型 API 不等于防止泄露；对敏感数据需要更窄的服务操作授权或关闭该通道。

域名代理的基础承诺是“目标连接允许列表”，不等于严格的应用层 origin 控制。共享 IP、隧道内 SNI/Host 与 CONNECT 声明不一致等情况需单独处理；需要校验实际应用层服务时，应使用受支持的 TLS 终止/Broker，或拒绝该策略。[CONNECT 语义](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6)

### 7.4 依赖安装采用可选预设

不默认放行所有公共包仓库。提供用户主动启用的“npm/Python/Rust 依赖安装”预设，列出域名、协议、端口及用途，并通过真实安装测试维护。

包元数据域名往往不等于下载域名：例如 PyPI 文件分发、crates 下载、GitHub API/归档/重定向可能分别需要额外目标。初稿列出的四个域名不足以保证所有安装成功，也不应直接扩成无条件通配符。

每次扩展预设都视为权限变化。离线缓存可降低联网需求；共享缓存只读或按会话隔离，防止跨任务污染。依赖安装脚本与其它命令受同样约束，不能作为“准备阶段”在宿主无条件运行。

### 7.5 凭据 Broker 与 HTTPS 限制

建议优先采用**受限服务 Broker**：真实凭据由可信宿主/秘密存储提供，负载只能请求允许的 API 操作。长期秘密不进入 argv、环境、HOME、日志或普通文件。

若需要透明代理替换占位 token：

1. 对 HTTP 可在代理层改写；对 HTTPS 必须能看到应用层请求，通常需要 TLS 终止/MITM 或服务专用代理。普通 CONNECT 隧道看不到 Authorization。
2. TLS 终止需要沙箱内专用信任配置、可信侧私钥保护、上游证书校验和证书固定客户端的兼容处理；不修改宿主全局信任库。
3. 凭据绑定 session、服务 origin、有效期及必要的 HTTP 方法/路径/资源范围；跨 origin 重定向不得携带凭据，响应与错误不得回显真实 token。
4. 会话撤销要同时撤销代理能力和上游短期令牌（若有）；限制重放、调用速率与可执行操作。

“拿不到 token”仍可能“借助 Broker 使用 token 的权限”。因此除了保密，还要限制操作范围。模型接口也可能上传文件、创建资源，不能仅按一个 hostname 放行所有用途。

凭据保密还依赖选定上游服务受信，不能向任意第三方注入秘密并承诺恶意上游永不回传。M3 只支持明确验证的服务/协议；mTLS、签名认证、证书固定等需要专门适配。

Claude Code 当前已有可配置的 credential masking/TLS termination；Anthropic 不同产品的密钥链、VM 与代理设计仍需分别理解，不能视为所有本地沙箱的统一默认。[Claude Code 说明](https://code.claude.com/docs/en/sandboxing)、[跨产品隔离说明](https://www.anthropic.com/engineering/how-we-contain-claude)

---

## 8. 错误处理与可观测性

### 8.1 Fail-closed 与能力探测

探测对象包括 OS/内核、Landlock ABI、namespace/seccomp、bwrap 版本/来源、Seatbelt、Windows 安装状态、Job/ACL/网络控制及资源限制权限。helper 应来自可信安装位置，不能由工作区 PATH 替换。

同一策略可以选择另一个**经验证满足全部要求**的后端；不能按“Landlock 不行 → bwrap 不行 → 任意容器”自动降级。改变隔离等级或权限属于新决策，需可信宿主授权。

### 8.2 错误与执行结果

| 类别 | 含义 |
|---|---|
| InvalidPolicy / UnsupportedPolicy | 策略无效，或当前后端不能完整实现 |
| BackendUnavailable / SetupFailed | 后端、依赖或安装步骤不可用 |
| ApprovalRequired / ApprovalDenied / ApprovalExpired | 尚待授权、被拒绝或已失效 |
| PolicyDenied | 已有可信证据确认某项策略拒绝，附规则 ID 和证据来源 |
| CommandFailed | 普通命令非零退出；不能默认解释为沙箱拒绝 |
| TimedOut / Cancelled / ResourceExceeded | 超时、取消或资源上限触发 |
| CleanupIncomplete | 后代或资源未确认清理，不能返回“成功完成” |

`ExecResult` 分别记录命令 exit code/signal、执行状态、输出截断标记、policy hash、后端、已知拒绝及 cleanup 状态。工作区可能已有变更，与执行状态分开报告。

### 8.3 生效性自检

`doctor` 与 CI 使用测试专用临时目录/合成秘密；**不尝试读取真实私钥或修改真实 .git 配置来做 canary**。

同时测试“应该允许”和“应该拒绝”：

- 可读/可写测试对象成功，受保护写入和秘密读取失败。
- deny 模式真实阻止 TCP/UDP/IPv6 等出口；代理模式允许目标成功、拒绝目标失败。
- 代理故障、未继承控制句柄、后代限制和取消回收按契约生效。

网络拒绝不能仅以“连接失败”证明，要排除 DNS 失败、远端不在线等原因，使用可达的受控测试端点及可信拒绝证据。运行时启动检查按后端与策略关键项执行；完整对抗套件放 CI/`doctor --full`。缓存只作优化，缓存键包含策略、后端、OS 能力及安全相关环境，不替代每次启动的规则安装检查。

Canary 是发现失效的手段，不是完整安全证明；不能用一个读写失败案例推导所有路径都被隔离。

### 8.4 审计与诊断

M1 即输出 JSONL：session/exec/request ID、时间、脱敏命令摘要、策略 hash、权限变化、批准者/期限、后端版本、生命周期和清理结果。日志不写原始秘密、完整环境或默认全量 stdout，避免审计自身成为泄漏渠道。

保证提供启动/退出/授权/代理决策事件；文件系统全量访问、写入和每次内核拒绝事件是**后端可选诊断能力**。文件 watcher 不能作为安全裁决或完整审计。

输出块带 exec ID、流类型和序号，设队列、单次输出和总留存上限。日志落盘失败必须可见；要求完整审计的配置应停止新执行，普通诊断模式可显式允许继续。子进程输出是非可信数据，UI 不执行其中的控制指令。

---

## 9. 平台后端实现

### 9.1 Linux

建议 M1 主路径采用 bwrap 提供独立挂载/PID/网络等视图，结合 seccomp、no_new_privs、最小 capabilities 和受控 FD；Landlock 按可用 ABI 补强或作为受限能力后端，不默认视为完整等价替代。

M0 验证用户 namespace 与发行版 AppArmor/容器环境约束。不要自动关闭宿主安全设置。挂载只暴露工作区和必要运行时；若使用根文件系统只读视图，需另行实现读隐藏，不能把“只读 /”等同“只读必要文件”。

Landlock 权限随 ABI 演进，没有“5.19+ 完整能力”这一稳定下限。安装要求按实际需用的 rename/link、truncate、网络和 IPC 等能力制定；缺失必需能力即拒绝。[内核文档](https://docs.kernel.org/userspace-api/landlock.html)

cgroup v2 的硬资源限制要求可用且具备正确委派；RLIMIT 不能无条件替代整棵进程树的内存/进程配额。

### 9.2 macOS

建议基于 Seatbelt/`sandbox-exec` 生成 profile，并维护实际测试的 macOS 版本矩阵。profile、Mach 服务、文件别名、代理端点及后代进程限制均需要 PoC，不能只复刻一个允许列表。

该接口的长期兼容性是风险。Endpoint Security 是需特殊权限的监控/授权框架，不是无需成本的直接替代后端。若原生机制无法满足必要约束，可评估 Virtualization.framework；届时同时评估工具链、目录同步和性能变化。

进程树强制清理、硬资源配额等不由 Seatbelt 自动提供。未验证能力必须在能力报告和发布说明中标明，不能承诺与 Linux 一致的底层机制。

### 9.3 Windows

建议拆成两条明确能力的路径：

- **正式候选**：专用低权限身份/必要 ACL + 受控启动器 + Job Object + 网络过滤 + UI/IPC 隔离；安装或设置可能需要管理员权限，实际负载不以管理员执行。
- **免安装候选**：当前用户派生的受限令牌等方案；只有验证通过的限制才能声明支持。若不能保证 network=deny，就不能执行要求断网的策略。

Job Object 负责进程组管理和资源控制，不替代 token、ACL 或防火墙。还要验证宿主进程句柄、named pipe、共享内存、注册表、COM/RPC 和桌面对象的攻击面，工作量不只在路径规范化。

若修改持久 ACL、账户或防火墙规则，需定义最小变更、撤销/卸载、崩溃恢复和并发会话处理。不得递归放宽用户 HOME 的权限来修复兼容性。AppContainer/lowbox 与普通 Win32 工具链的兼容性通过 PoC 决定。

WSL2 可作为 Linux 执行环境，但不等于原生 Windows 后端。WSL interop 与宿主挂载可能接触 Windows，应默认阻止未授权 Windows 可执行文件/桥接通道，并单独测试。

参考：[Codex Windows 设计概述](https://learn.chatgpt.com/docs/windows/windows-sandbox)、[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)、[Restricted Tokens](https://learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens)。

### 9.4 容器与 VM 演进

容器与 VM 均可做后端，但不自动获得本方案语义。容器仍共享其宿主内核；暴露 Docker socket 会越过预期边界。VM 需单独处理共享目录、网络代理、凭据、文件同步和产物回传。

本期只保留 BackendPlan 和公共契约的扩展点，不提前实现多种 VM 编排。若第 14 节选择抵御更强敌手，应重新评审平台路线与排期，而不是在原有里程碑中顺带加入。

---

## 10. 测试与验收

### 10.1 测试层次

| 层次 | 重点 |
|---|---|
| 策略单元测试 | 操作 × 路径 × 规则冲突、策略合并、硬拒绝、授权上限、schema 校验 |
| 编译与能力测试 | 必需能力缺失报错；未支持字段不能忽略；生成有效策略可对照 |
| 平台集成 | 真正的允许/拒绝访问、路径别名、子进程、网络、资源回收 |
| 对抗回归 | symlink/hardlink/rename 竞态、继承 FD/handle、IPC、代理绕过、伪造审批 |
| Agent 合同测试 | 工具调用、文件读写、流式输出、批准/拒绝/过期、取消、断连 |
| 工作流测试 | 读代码 → 改文件 → 构建/测试 → diff；受控依赖安装另行验收 |
| 故障注入 | helper/代理崩溃、权限变化、审计失败、父进程退出、超时 |

三平台使用同一语义测试集与各自变体；没有在真实目标环境运行的项标为未验证/不支持，不能以 mock 或 CI skipped 视为通过。

### 10.2 最小安全验收矩阵

| ID | 场景 | 必须观察到的结果 |
|---|---|---|
| FS-1 | 工作区正常读写，向外部合成文件写入 | 合法操作成功；越界变更失败 |
| FS-2 | 工作区 symlink 指向合成秘密 | 读写均拒绝；测试不使用真实私钥 |
| FS-3 | .git 文件/目录、gitdir、commondir、Agent 配置 | 写/删除/替换/rename 被阻止或会话因无法表达而拒绝 |
| FS-4 | hardlink、父目录替换、非存在保护路径 | 无静默绕过；不支持的组合启动前报错 |
| PR-1 | 后代、双重 fork/setsid、Windows breakaway | 权限持续受限，回收行为符合声明能力 |
| PR-2 | 继承 socket/FD/进程句柄、控制通道访问 | 不获得未授权资源或审批能力 |
| NET-1 | deny 模式：IPv4/IPv6、TCP/UDP、DNS、宿主 IPC | 未授权通信失败，合法本地管道行为符合策略 |
| NET-2 | 代理模式：直连、重绑定、私网地址、代理崩溃 | 无旁路；失败不直连 |
| AUTH-1 | 子进程打印审批 JSON、跨会话/过期/replay | 无法签发或重用授权 |
| LIFE-1 | 超时、取消、客户端断开、supervisor 崩溃 | 进程和资源按合同回收，否则显式失败 |
| API-1 | 宿主 Agent 文件工具与 exec 读取同一被禁文件 | 都被拒绝，无工具类型绕过 |
| COMPAT-1 | 固定样例项目的修改/构建/测试 | 能完成边界内常见工作，不靠全量扩权 |

单独通过 `ln -s ...` 用例不足以发布。M1 必须通过其支持范围内的全部必需项；NET-2、PTY、凭据测试随对应能力交付。

### 10.3 发布门槛

策略无法表达、未通过的必需隔离项或无明确能力报告，均为发布阻塞。增加允许项必须同时补充边界测试。依赖升级要重跑受影响的对抗与兼容套件；发布附 OS/后端版本、已知限制和适用策略矩阵。

---

## 11. 交付形态与 Agent 协议

### 11.1 交付顺序

| 形态 | 最小接口 | 阶段 |
|---|---|---|
| CLI | `sbx run`、`sbx doctor`、`sbx policy explain` | M1 |
| Rust 库 | 与服务相同的会话/执行语义，后端 trait 不公开 | M1，先保持内部 API 可调整 |
| stdio 服务 | `sbx serve --stdio`，版本化 JSON-RPC | M1，Agent 主接入点 |
| Node/Python 客户端 | 启动服务并管理请求/事件，不依赖用户拼 shell | M2 |
| 原生绑定 | napi-rs/PyO3，仅在性能或嵌入需求成立时实现 | 后续按需 |
| MCP 适配 | 映射工具接口；不扩大权限、不提供模型可调用的审批决定 | 可选 |

`policy explain` 返回诊断性判定，不授权后续文件操作，也不能保证未来路径状态不变。CLI、库和 RPC 共用 core 与合同测试。

### 11.2 最小 RPC 契约

建议使用 JSON-RPC 2.0 + UTF-8 JSONL。保留 `"jsonrpc":"2.0"`，这是本项目自己的协议，不照搬产品私有字段。server stdout 只输出协议，日志走 stderr，负载输出封装为事件；规定单条消息大小和非法输入处理。

字节内容使用带 encoding 标记的 base64，避免非 UTF-8 输出损坏协议。M1 的 stdin 默认为关闭，也可在启动时传入有界数据并在写完后发送 EOF；持续输入与 PTY 为 M2。输出超过上限时继续排空但丢弃超限部分，设置截断标记；客户端持续不消费事件时，在有界超时后取消执行，避免无界缓存。

| 方法/事件 | 语义 |
|---|---|
| `initialize` | 协议版本协商、客户端身份上下文、能力报告 |
| `session.create/get/close` | 固定工作区和权限上限；关闭会话撤销 grants 并回收资源 |
| `policy.explain` | 查看有效策略及拒绝原因，诊断用途 |
| `exec.start` | argv/cwd/env、初始 stdin、超时和 request key；可信宿主可附授权引用与 retry_of，立即返回 exec ID |
| `exec.status/wait/cancel` | 查询/等待/取消；取消幂等 |
| `exec.output / exec.completed` | 带 session/exec ID 与序号的流式事件 |
| `file.read/write/apply_patch/list` | 由同策略受限 worker 执行；不是 supervisor 直接任意访问宿主 |
| `permissions.request` | 模型可提出权限增量与理由；创建待审请求，不直接授予权限 |
| `approval.requested` | 输出不可伪造的待审请求，等待可信宿主决定 |
| `approval.resolve` | 仅可信控制角色可调用；批准时生成授权，不自动重跑命令 |
| `exec.stdin/resize` | M2 的交互进程能力，未支持时返回明确错误 |

`ExecRequest` 的 request key 只在会话内去重：同 key 同请求返回原 exec，同 key 不同内容报错。它不保证外部副作用 exactly-once；服务崩溃后状态未知时不得盲目重放。

批准后由可信宿主用新的 request key、授权引用及可选 `retry_of` 启动执行。授权凭证保留在宿主与 supervisor 之间；模型只获得状态和非秘密请求 ID。持有请求 ID 不等于有权批准或使用任意 grant。

M1 默认客户端断连即取消执行、撤销授权并清理；不承诺重启后恢复会话。M2 如支持后台运行/重连，应另定义 TTL、状态持久化和事件留存窗口。

### 11.3 会话与数据语义

- 会话不是一个持久 shell；cwd/env 每次请求显式指定。PTY 模式输出可合并，不能承诺保留 stdout/stderr 分离。
- 同一会话内的进程默认属于同一信任域；不同授权级别任务应分隔执行资源。不能让低权限任务通过可写共享状态篡改已批准的高权限执行。
- 多个会话共享同一宿主工作区时会看到彼此写入，不构成文件内容隔离。需要独立性时使用独立工作副本；Git worktree 的共享元数据另行处理。
- 文件/输出只按请求返回；Agent 把内容发给模型或外部服务属于上层数据策略。
- 写文件和补丁需有大小上限、原内容摘要/版本冲突检查以及受限路径访问；冲突返回调用方，不静默覆盖。

### 11.4 集成验收示例

最小自研 Agent 演示应完成：

~~~text
initialize → session.create(workspace-write, network=deny)
→ file.read / exec.start(test) → 接收输出 → file.apply_patch
→ 申请一个额外路径 → 可信 UI 允许一次 → 新 exec 使用 grant
→ 取消一个长任务 → session.close → 确认清理
~~~

另做现成 CLI 包装兼容测试，明确哪些本地工具在外层边界内、哪些远程功能独立授权。`sbx` 不承诺直接替换 Codex/Claude Code 的内部执行器；深度接入需针对其公开扩展接口单独实现适配。

---

## 12. 里程碑与出口条件

以下是建议顺序，不是已承诺工期。每阶段均维护可运行样例与能力矩阵。

| 阶段 | 范围 | 出口条件 |
|---|---|---|
| **M0：可行性与契约** | 三平台最小 PoC；比较复用 runtime 与自研适配；文件例外、网络 deny、回收、安装权限；敲定 Agent 接入与 schema | 明确各平台能保证什么；对无法实现的关键项选替代机制或缩减支持范围；记录参考版本 |
| **M1：可接 Agent 的安全最小版** | 优先 macOS/Linux；CLI + core + stdio RPC；文件 worker、默认断网、私有环境、审批、输出/取消/清理、基础审计 | 10.2 中本阶段全部必需项通过；11.4 自研 Agent 样例闭环；无静默降级 |
| **M2：常用开发工作流** | Windows 原生支持、域名代理、依赖预设、Node/Python 客户端、PTY/受管后台任务 | 每项能力独立验收；三平台各自完成声明支持的工作流；Windows 安装/卸载/恢复通过 |
| **M3：凭据与增强** | 服务 Broker、必要时 TLS 终止、撤销/限流；按需要做原生绑定与更多适配 | 凭据不进入负载、跨目标不注入、权限不可滥用到约定范围外；安全与兼容测试通过 |

M0 应包含 Windows 风险验证，不能等 M2 才首次确认方案是否成立。若 Windows 是首发硬要求，则 M1 必须调整为 Windows 与所选平台共同验收，相应缩减其它范围。

M1 可先覆盖离线修改/构建流程；如果“首次运行即可安装依赖”是首版硬要求，需将 M2 的最小域名代理提前，而不是临时默认全网开放。

---

## 13. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 策略在后端不可表达 | 看起来受限、实际可绕过 | 能力协商 + 编译拒绝 + 负向测试 |
| 不可信路径/FD/IPC 穿透 | 读取秘密或控制宿主 | 最小视图与句柄、平台专项测试、保护启动流程 |
| Agent 宿主工具绕过 | 只有部分操作受保护 | 完整工具清单与执行路由，明确外部能力授权 |
| macOS 接口兼容和回收限制 | 无法达到某些承诺 | M0 验证、版本矩阵、必要时 VM 路线 |
| Windows 安装/ACL/防火墙复杂 | 兼容、维护及恢复风险 | 提前验证，最小权限，安装与回滚可审计 |
| 代理/凭据 Broker 变成高权限代理人 | 已授权服务被滥用 | 会话/操作级授权、短期令牌、限流和撤销 |
| 审批疲劳 | 用户扩大权限或关闭隔离 | 预设、精确增量、可读差异；统计重复审批原因 |
| 自动重试有副作用 | 重复写入或外部操作 | 显式重试、幂等键、未知状态不重放 |
| 可写工作区及缓存污染 | 后续宿主执行受影响 | 产物评审、独立副本、缓存隔离；不承诺沙箱内内容可信 |
| 资源和日志无界 | 宿主耗尽、敏感数据留存 | 超时、背压、配额能力探测、脱敏与留存上限 |
| 上游变化/漏洞 | 参考失效或后端风险 | 固定版本、许可证审查、依赖更新与回归 |

不使用未经核验的安全统计、事故归因、issue 状态或供应商商业变化来支撑架构结论。对安全承诺有影响的事实应链接原始资料，并说明适用版本。

---

## 14. 待确认事项

下表保留产品取舍，避免把工程上必须修正的错误继续当作可选项。**推荐值用于继续评审，不表示已经获得产品确认。**

### 14.1 进入实现前需确认的决策

| ID | 决策 | 推荐方案 | 替代方案及影响 | 状态 |
|---|---|---|---|---|
| D1 | 威胁模型/隔离等级 | 防御不可信用户态代码，信任内核与宿主管理员；采用 OS 隔离 | 若需更强内核隔离或恶意多租户场景，重新评估 VM/专用宿主 | 待确认 |
| D2 | Agent 接入重点 | 两种方式均保留，优先宿主 Agent + 沙箱工具网关 | 若优先现成 CLI 整体隔离，需提前处理模型联网、登录与 PTY | 待确认 |
| D3 | 实现路线 | Rust core + 复用成熟机制；M0 对比 sandbox-runtime 复用成本 | fork runtime 可缩短初期时间，但需接受其依赖与维护耦合；VM 路线改变整体成本 | 待确认 |
| D4 | 首发平台 | macOS/Linux 先交付，Windows M0 验证、M2 交付 | Windows 必须首发时调整 M1 范围和验收，不降低安全要求 | 待确认 |
| D5 | 首版联网要求 | M1 硬断网，M2 域名代理；基础审计 M1 | 若必须首版安装依赖，将最小代理提前；不采用“配置占位但不强制” | 待确认 |
| D6 | 文件读取与工作区模式 | scoped read + 私有 HOME/temp；优先直接工作区，难表达的策略拒绝 | host-read 更兼容但会暴露宿主数据；受控副本更易隔离但有同步/性能成本 | 待确认 |
| D7 | 能力与清理底线 | 必需能力缺失拒绝运行；M0 后确定各平台支持等级 | 是否接受显式标注的 best-effort 回收影响 macOS 原生路线；不能静默降级 | 待确认 |

D1–D3 决定整体方向；D4–D7 决定首版范围。可以先开展 M0 的隔离 PoC，但在关键语义未定前不冻结外部 API。

### 14.2 可以沿用建议继续设计的事项

| ID | 事项 | 建议 | 调整代价 |
|---|---|---|---|
| D8 | 格式与命名 | 配置用 TOML，线协议用 JSON；schema version 从 1 开始；crate/`sbx` 暂作工作名 | 发布前检查命名冲突；早期调整成本低 |
| D9 | 上游配置兼容 | 提供显式转换器，列出不支持字段，不声称无损兼容 | 如需直接读取上游配置，增加版本耦合与合同测试 |
| D10 | 审批与 Git 写入 | 默认只允许窄增量，unsandboxed 关闭；Git 元数据写入单独授权 | 自动 commit 工作流可能需要受控 Git 工具或额外策略 |
| D11 | 分发与依赖 | 接受平台 helper/系统依赖与 Windows 管理员安装步骤 | 若坚持免安装/单文件，需重新约束支持平台和能力 |
| D12 | 凭据范围 | M3 从明确的一两个服务 Broker 开始 | 通用透明 TLS 注入需额外安全设计、信任配置与兼容测试 |
| D13 | 容器/VM 与原生绑定 | 非首版硬要求，先稳定 RPC 与后端合同 | 只有实际需求成立再投入；避免同时维护过多入口 |
| D14 | 性能和资源限额 | M0 实测后确定 SLO、默认配额与必需能力 | 不能以未测的 50 ms 或统一资源上限倒逼弱化隔离 |

以下属于设计底线，不作为可选取舍：不可信负载不能自批权限；不忽略安全字段；授权不能越过硬策略；限制在负载运行前生效；数据通道不充当控制通道；不将未经验证的能力标为已支持。

---

## 附录 A：参考资料与适用范围

核查日期：2026-09-30。以下为可更新的在线资料；进入 M0 后应记录所用 release/commit、测试环境和验证结果。

| 主题 | 一手资料 | 用途 |
|---|---|---|
| Codex 本地沙箱 | [Sandbox](https://learn.chatgpt.com/docs/sandboxing) / [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security) | 平台实现、权限、网络与受保护路径 |
| Codex Windows | [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox) | elevated/unelevated 与安装边界 |
| Codex 集成 | [App Server](https://learn.chatgpt.com/docs/app-server) | 请求、事件、审批结构参考；非本项目协议规范 |
| Claude Code | [Sandboxed Bash tool](https://code.claude.com/docs/en/sandboxing) | 本地产品范围、配置、网络和凭据限制 |
| Claude 跨产品设计 | [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude) | 区分本地、云端和 VM 设计，不直接移植为本地默认 |
| sandbox-runtime | [官方仓库](https://github.com/anthropics/sandbox-runtime) | 复用候选；能力和许可证按固定版本复核 |
| Landlock | [Linux 内核文档](https://docs.kernel.org/userspace-api/landlock.html) | ABI、允许规则语义、网络和已知限制 |
| bubblewrap | [官方仓库](https://github.com/containers/bubblewrap) | namespaces、挂载与调用者安全责任 |
| Windows 原语 | [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) / [Restricted Tokens](https://learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens) / [WFP](https://learn.microsoft.com/en-us/windows/win32/fwp/windows-filtering-platform-start-page) | 生命周期、访问控制与网络机制分别评估 |
| Git 元数据 | [gitrepository-layout](https://git-scm.com/docs/gitrepository-layout) | gitdir、commondir 与共享元数据 |
| HTTP 隧道 | [RFC 9110 CONNECT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6) | 隧道与 TLS 终止的能力区别 |

初稿中的第三方镜像、事故成功率、审批减少比例、单个 SDK issue 的“至今未修复”描述及供应商闭源传闻，均不再作为本方案的事实依据。案例只有在确认版本、配置和复现路径后才进入回归集。

## 附录 B：本地调研产物

初稿提到 `default-workspace/sandbox-landscape-2026-09.md` 与 `default-workspace/awesome-sandbox-README.md`。本次工作区文件清单未发现这两份材料，**本轮未据其内容作判断**；保留为待补充背景，不把它们视为当前目录内已验证的附件。

## 附录 C：评审修订记录

| 问题 | v0.2 处理 |
|---|---|
| 只防误操作、“非安全边界” | 改为明确威胁模型与分层安全承诺 |
| 对标过时、混合不同产品机制 | 区分 Codex、Claude Code、runtime 与云端/VM |
| Landlock 无网络、固定“完整版本” | 改为 ABI/能力探测 |
| pure resolve 与 realpath、TOCTOU 表述冲突 | 分开纯策略、OS 解析与实际强制 |
| 嵌套 deny/glob/别名保护不具可实现性 | 增加可表达性检查和拒绝路径 |
| 审批失败自动重试 | 增加 grant 绑定、防重放、副作用和显式重试 |
| Agent 接口只有同步结果 | 增加会话、流式、取消、文件 worker 与信任边界 |
| 网络和审计全部延后 | 默认拒绝、最小协议与审计提前到 M1 |
| 域名名单与 HTTPS token 注入过度简化 | 补 DNS/IP、旁路、可选预设、Broker/TLS 条件 |
| 进程组等同全树回收 | 改为平台能力与独立验收 |
| 待确认事项只有问句 | 改为推荐、替代影响、状态和设计底线 |

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.1 | 2026-09-30 | 初稿 |
| v0.2 | 2026-09-30 | 本轮架构、安全、Agent 集成与交付范围评审修订；产品决策仍待确认 |
