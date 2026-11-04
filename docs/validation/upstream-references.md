# 上游固定版本与 M0 路线比较

核查日期：2026-10-14。本文记录资料核查与工程判断，不代表已通过上游安全审计，也不代表本项目集成或运行过该 runtime。下述 commit 来自当日对官方仓库执行的只读 `git ls-remote <url> HEAD`；固定提交不是生产依赖批准。

## 版本与许可证来源

| 对象 | 固定标识 | 本轮核查与用途 |
|---|---|---|
| anthropics/sandbox-runtime | `9a277e5e04af1ab1b04feea4400a6ed8a5b72039` | [提交](https://github.com/anthropics/sandbox-runtime/commit/9a277e5e04af1ab1b04feea4400a6ed8a5b72039)、[package.json](https://github.com/anthropics/sandbox-runtime/blob/9a277e5e04af1ab1b04feea4400a6ed8a5b72039/package.json)：源码包版本 `0.0.79`，Node `>=22.12.0`；该版本号不证明对应 npm 发布包与此提交相同 |
| sandbox-runtime 许可证 | 同一提交 | [LICENSE](https://github.com/anthropics/sandbox-runtime/blob/9a277e5e04af1ab1b04feea4400a6ed8a5b72039/LICENSE) 为 Apache-2.0；采用前仍需核对 vendor 和依赖文件的许可证、通知及实际分发内容 |
| containers/bubblewrap | `1fb0aa26d3eb66254f7742e704add7f82f41a582` | [固定源码树](https://github.com/containers/bubblewrap/tree/1fb0aa26d3eb66254f7742e704add7f82f41a582)。此为资料参考，不代表本机安装版本；实测版本以 JSON 中 `bubblewrap` 字段为准 |
| bubblewrap 许可证 | 固定提交文件核查尚待完成 | 已读[官方主分支 COPYING](https://github.com/containers/bubblewrap/blob/main/COPYING)，其正文为 LGPL 2.1；本轮固定提交文件读取未成功，不能把滚动页面当作该提交逐文件分发核验结果 |

本轮没有复制上游实现进本项目，也没有决定打包其二进制。固定依赖或 fork 前须补充锁定包/二进制校验值、构建来源、完整许可证清单、补丁负责人和更新策略。

## sandbox-runtime 与自研适配路线

固定 [README](https://github.com/anthropics/sandbox-runtime/blob/9a277e5e04af1ab1b04feea4400a6ed8a5b72039/README.md) 将项目标为研究预览，描述 macOS/Linux 机制与代理，并列 Windows alpha：专用账户、WFP 和会话 ACL。它同时记录 Windows per-exec 读写授权限制与初始化时展开 glob 的边界。以上是上游声明，本项目尚未复现实测。

| 维度 | 基于固定 sandbox-runtime 适配/fork | Rust core + 平台适配（设计推荐） |
|---|---|---|
| 初期复用 | 可评估已有多平台包装、网络代理和 helper | 可复用 bwrap/OS API，但需自行建立完整控制层 |
| 运行时与分发 | 需接受其 Node 要求、vendor/helper、安装步骤和版本耦合 | Rust 语言选择待 D3；平台依赖和 Windows 安装成本仍存在 |
| 策略语义 | 必须逐项比较本项目 deny/protected、scoped read、授权与撤销语义；不能直接映射配置后宣称等价 | 可围绕本项目契约编译，但可表达性、安全启动和生命周期均需自行实现并证明 |
| Agent 合同 | 上游接口不能自动满足本项目会话、幂等键、可信审批、文件 worker 和审计要求 | 这些合同全部需要实现、测试和维护 |
| Windows | alpha 和官方限制是评估输入，不能作为生产可用证明 | Job 单独不足以隔离；仍需 token/ACL/网络/IPC、安装与恢复组合 |
| 更新责任 | 跟踪上游差异、维护补丁、固定包和 helper 一致性，升级后重跑相关安全回归 | 跟踪每个平台机制和依赖变化，维护自己的策略编译与回归矩阵 |

工程判断：两条路线均值得继续验证，目前证据不足以选择其中一条。自研 PoC 证明某个原语可调用，不能证明自研成本更低；上游有功能实现，也不能证明满足本项目更严格的策略和审批合同。

固定提交的 [namespace 变更](https://github.com/anthropics/sandbox-runtime/commit/9a277e5e04af1ab1b04feea4400a6ed8a5b72039) 描述了限制嵌套 user/mount namespace 与相关挂载操作的措施，提示只读 bind 需要配合额外约束。本项目把这个方向记为未验证项；未直接移植代码，也未声明已阻断该类绕过。

## 后续需要的对比实验

在相同目标 OS、相同合成工作区和相同允许/拒绝目标上运行两条路线，保存固定版本、有效策略、启动耗时和原始观察。至少覆盖 hardlink、未来保护名、父目录替换、继承句柄、嵌套 namespace、网络/IPC、后代脱离和 supervisor 崩溃。无法表达的策略要验证启动前拒绝，而不是接受后弱化。

还需测量冷/热启动 p50/p95、文件扫描/复制成本、Windows 安装/撤销/恢复、普通开发样例兼容性，以及包装上游接口所需的审批和文件 worker 工作量。当前没有这些数据，不给出性能排名或开发工期保证。

## 机制资料

以下是滚动官方文档，核查日同上；实际能力仍以目标系统探测和测试为准。

- [Linux Landlock](https://docs.kernel.org/userspace-api/landlock.html)：同层允许规则合并、层间叠加和预先打开 FD 的限制，是能力编译与负向测试依据；示例的 best-effort 行为不自动适用于本项目。
- [bubblewrap 官方说明](https://github.com/containers/bubblewrap)：安全策略由调用方参数决定；暴露宿主 IPC 可能扩大能力。需要记录本机版本和实际参数，不能仅记录“用了 bwrap”。
- [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)：Job 管理归入其中的进程，WMI 的 `Win32_Process.Create` 等代执行路径需另行约束。主动关闭 Job 的单项实验不能证明完整隔离和崩溃回收。
- [Microsoft 扩展 Job 限额](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)：用于核对本轮 `KILL_ON_JOB_CLOSE` 相关结构；不是文件或网络控制替代品。
