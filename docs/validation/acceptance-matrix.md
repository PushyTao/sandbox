# M0 观察与安全验收矩阵

更新日期：2026-10-14。依据：[设计 §10.2](../design/2026-09-30-agent-sandbox-design.md)。本表区分固定探针的观察和产品验收；**所有完整后端仍未通过验收，M0 尚未完成**。

## 证据状态

`pass` 表示固定观察成立，`fail` 表示候选机制不满足该观察的安全目标，`unavailable` 表示环境或依赖不足，`unverified` 表示尚无充分证据。Linux 的 hardlink/未来文件名反例若成功重现，必须报告 `fail`；反例运行成功不是安全验收通过。

本轮已核对以下原始报告，两份报告的 `production_ready` 均为 `false`：

| 环境 | 原始报告 | 本轮观察 | 完整后端 |
|---|---|---|---|
| 原生 Windows，系统版本字段 `10.0.26100`，AMD64，Python 3.8.5 | [原始报告](windows-2026-10-14.json) | 1 pass，5 unverified；退出码 `2` | 未实现、未验证 |
| Linux / WSL2，内核 `6.6.114.1-microsoft-standard-WSL2`，x86_64，Python 3.14.4，bwrap 0.11.1 | [原始报告](linux-wsl-2026-10-14.json) | 11 pass，2 fail，5 unverified；退出码 `1` | 未实现、未验证 |
| 原生 Linux 的发行版矩阵 | 尚无报告 | 未验证；WSL 证据不能替代全部原生环境 | 未验证 |
| macOS | 尚无报告 | 未实现、未验证 | 未实现、未验证 |

Windows 表中的版本是 Python 报告的系统版本，不据 `release=10` 推断操作系统产品名称。Linux 报告未包含发行版版本，不能从内核字段反推发行版。

在 `tools/m0` 目录分别用原生 Windows Python 和 WSL Linux Python 运行以下命令，可复现报告生成入口：

```text
python -m sandbox_probe --output ../../docs/validation/windows-2026-10-14.json
```

```text
python3 -m sandbox_probe --output ../../docs/validation/linux-wsl-2026-10-14.json
```

后续回填仍须读取 JSON 并保存命令退出码；不能由测试函数名称推断实际结果，也不能把 unit test/mock 通过移入平台验收列。本轮从仓库根目录执行：

```text
# 原生 Windows：26 项，23 项通过，3 项 Linux 专项跳过
python -m unittest discover -s tools/m0/tests -v

# WSL Linux：26 项，24 项通过，2 项 Windows 原生专项跳过
SBX_M0_INTEGRATION=1 python3 -m unittest discover -s tools/m0/tests -v
```

Linux 环境变量显式启用真实隔离与故障测试；省略它会跳过这些测试。跳过不是平台能力通过。审查修复及红/绿回归证据见[审查记录](review-2026-10-14.md)。

| 本轮观察 | 状态 | 精确含义 |
|---|---|---|
| `windows.job_lifecycle` | pass | 已观察到先归 Job 再 resume，子进程运行后因 Job 关闭终止 |
| `windows.filesystem`、`windows.token`、`windows.network`、`windows.ipc`、`windows.descendants` | unverified | 未安装或未测试对应隔离；Job 结果不覆盖这些能力 |
| `LINUX.setup`、`FS-1.workspace`、`FS-2.symlink`、`FS-3.existing`、`ENV.private` | pass | 本轮固定挂载、文件与单个环境变量观察成立 |
| `FS-4.hardlink`、`FS-4.future-name` | fail | 已重现可写 hardlink 别名修改保护文件，以及创建原本不存在的保护名称；候选方案禁止用于生产 |
| `NET-1.ipv4-tcp`、`NET-1.ipv4-udp`、`NET-1.ipv6-tcp`、`NET-1.ipv6-udp`、`NET-1.abstract-unix` | pass | 宿主端点先通过正向对照，隔离侧无法到达；UDP 以宿主未收到报文判断，不以 send 成功与否判断 |
| `PR-1.root-exit` | pass | 观察到固定脱离会话子进程在根退出后被回收；未测试 supervisor 崩溃 |
| `LINUX.production`、`FS-4.nested-userns`、`NET-1.full`、`PR-2.handles`、`LIFE-1.full` | unverified | 完整策略、攻击面与生命周期合同尚未实现或完成验证 |

## 设计项与实际探针的对应关系

| 设计项 | 当前观察 ID / 覆盖 | 尚缺的验收证据 |
|---|---|---|
| FS-1 正常读写及越界写拒绝 | `FS-1.workspace` 观察合成工作区读写；`FS-2.symlink` 检查外部合成文件保持不变 | 任意路径/操作策略；Windows ACL 与 macOS 文件控制 |
| FS-2 symlink 越界 | `FS-2.symlink` 检查指向未挂载合成秘密的读写 | symlink 链、替换竞态、Windows reparse point 与 macOS 别名 |
| FS-3 Git/Agent 元数据保护 | `FS-3.existing` 仅检查已有合成目录的写、删除、rename 和父目录 rename | 真实结构的合成 `.git` 文件/目录、gitdir、commondir、嵌套仓库、控制文件；不测试真实仓库元数据 |
| FS-4 hardlink/未来路径/父目录 | `FS-4.hardlink`、`FS-4.future-name` 专门重现只保护已有路径的反例；`FS-4.nested-userns` 明确未验证 | 安全策略编译/拒绝机制、可选受控副本、对象别名与安装竞态、嵌套 user/mount namespace 攻击 |
| PR-1 后代持续受限与回收 | `PR-1.root-exit` 观察根退出后固定 `setsid` 子进程回收；`windows.job_lifecycle` 只观察单个固定子进程 | 双重 fork、多层后代、Windows breakaway/宿主代执行；Windows 单子进程结果不能证明整树回收 |
| PR-2 FD/handle/控制通道 | `PR-2.handles`、`windows.ipc`、`windows.descendants` 记录未验证 | 已打开 FD/socket/进程句柄、ptrace、WMI/COM/RPC、控制通道和授权凭证保护 |
| NET-1 真实 deny | `NET-1.ipv4-tcp`、`NET-1.ipv4-udp`、`NET-1.ipv6-tcp`、`NET-1.ipv6-udp` 使用可达宿主 loopback 正向对照；`NET-1.abstract-unix` 检查宿主 abstract socket | `NET-1.full`：外网、DNS、pathname socket、其它 socket family、WSL interop；`windows.network` 未验证。私有 namespace 不能替代完整网络/IPC 矩阵 |
| NET-2 代理无旁路 | 没有代理实现 | M2：DNS/IP、重绑定、私网/元数据地址、重定向、代理崩溃、活动连接撤销 |
| AUTH-1 伪造审批/重放 | 无审批实现 | M1：可信角色、一次授权原子消费、跨会话/过期/replay、子进程伪造输出无效 |
| LIFE-1 超时/取消/断连/崩溃 | `windows.job_lifecycle` 检查主动关闭 Job；`LIFE-1.full` 记录其余未验证 | 主动 close 不等于 supervisor 崩溃；需验证断连、取消、超时、异常路径、清理失败传播和资源释放 |
| API-1 文件工具与 exec 同策略 | 无 Agent RPC/file worker 实现 | M1：两种工具访问同一合成被禁文件均失败，不存在宿主文件工具旁路 |
| COMPAT-1 修改/构建/测试 | 固定探针程序可以运行，不是开发工作流验收 | M1：固定样例项目完整闭环，不依赖全面扩权；M2 另验依赖安装 |

辅助观察 `ENV.private` 只覆盖临时 HOME/scratch 和单个合成环境变量清除，不能证明完整环境白名单。`LINUX.setup` 只证明固定程序在指定 namespace 设置下启动；`LINUX.production` 保留策略编译、seccomp、审计 runtime profile 和整树资源限制缺口。Windows 的 `windows.filesystem`、`windows.token`、`windows.network` 分别保留文件、身份和网络未验证状态。

## 发布门槛

完整 M0 还需 macOS 实测、Windows 完整隔离路线可行性、平台安装恢复、直接工作区保护方案、runtime 对比实验及产品决定。当前 `fail`/`unverified` 项必须逐项处理，不能给它们加总分后宣布总体通过。

M1 需实现设计规定的 CLI/core/RPC、同策略文件 worker、真实断网、可信审批、输出/取消/清理、基础审计，并通过本阶段全部必需项。M2/M3 能力分别验收。任何未运行的平台、未覆盖策略或不具备的能力都不能在 capability report 中声明已支持。
