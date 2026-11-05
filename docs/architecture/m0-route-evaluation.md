# M0 三路线比较与固定来源

核查日期：2026-11-04。状态：研究建议。固定提交用于可追溯调查，不表示依赖准入、许可证审查完成或运行兼容已通过。

## 实际核查版本

| 对象 | 本轮依据 | 验证层级 |
|---|---|---|
| 本项目 | 研究代码 `c19b23585d64d20869adb9654cfbc1f013584d40`；main `bb4e544f09cd12fb2521772944060c23cb7f6932` | 完整源码审阅；Windows 本轮测试，详见独立评审 |
| sandbox-runtime | `98a4016d27609ed34dd1fb43d23ed6efb6eeeb77`，官方 HEAD 只读查询退出 0 | 固定 README、package.json、sandbox-schemas.ts 阅读；未安装、未执行 |
| bubblewrap | `1fb0aa26d3eb66254f7742e704add7f82f41a582`，官方 HEAD 查询退出 0 | 固定 README/COPYING 阅读；本轮 Windows 没有 bwrap 实测 |
| 平台机制资料 | Microsoft Job Objects、Linux Landlock、Git repository layout，2026-11-04 读取 | 滚动官方文档，不能代替 OS/文件系统/安装组合实测 |

sandbox-runtime 固定 [package.json](https://github.com/anthropics/sandbox-runtime/blob/98a4016d27609ed34dd1fb43d23ed6efb6eeeb77/package.json) 的源码版本是 `0.0.81`，Node 要求 `>=22.12.0`，声明 Apache-2.0，包含 TypeScript 构建和 vendor 产物。本轮固定 LICENSE 页面读取失败，因此只记录 package 声明，不能称已完成文件级许可证验证，也不能把源码版本当作同版本 npm 包的内容证明。

固定 [README](https://github.com/anthropics/sandbox-runtime/blob/98a4016d27609ed34dd1fb43d23ed6efb6eeeb77/README.md) 仍标 research preview 和 Windows alpha。Windows 已记录 per-exec allowRead/allowWrite 不支持，以及匿名/派生令牌、系统服务代发流量和 DNS 的边界限制；部分残留只报告而不拒绝启动。**架构推论：不能原样接受该固定 Windows 实现来满足本项目主动绕过威胁模型下的 network deny/fail-closed。** 这是文档依据的准入判断，未在本机重现上游攻击；不得改写为本轮实测漏洞结论。

固定 [sandbox-schemas.ts](https://github.com/anthropics/sandbox-runtime/blob/98a4016d27609ed34dd1fb43d23ed6efb6eeeb77/src/sandbox/sandbox-schemas.ts) 的读权限允许默认放开，并支持在 deny 内重新 allow；本项目 scoped read 和硬拒绝优先与此不同。包装层须证明转换后的每个操作集合等价或更严格；仅重命名 allow/deny 字段不够。不把本项目单次 grant 映射成 session-wide 全局放宽。

bubblewrap 固定 [README](https://github.com/containers/bubblewrap/blob/1fb0aa26d3eb66254f7742e704add7f82f41a582/README.md) 明确安全边界取决于调用参数及暴露资源；它不是现成策略产品。固定 [COPYING](https://github.com/containers/bubblewrap/blob/1fb0aa26d3eb66254f7742e704add7f82f41a582/COPYING) 为 LGPL 2.1 文本；各文件声明、依赖和实际打包义务仍交构建核验。

## 取舍

| 路线 | 隔离与跨平台差异 | 维护与分发成本 | 当前结论 |
|---|---|---|---|
| A：Rust 控制核心＋自研策略适配，复用 OS 工具 | Linux 的 namespace/mount/seccomp、macOS 的原生策略与回收、Windows 的身份/ACL/网络/Job 分别证明；同一 API 不等于同一保障 | 自己维护策略编译、控制面、文件 worker、故障恢复；仍有 helper/签名/系统依赖，不承诺零依赖单文件 | 保留设计首选方向，D3 未批准；Python 原语探针不证明 Rust 成本或性能 |
| B：sandbox-runtime 适配/fork | 可评估已有包装/代理；策略语义、单次增量、控制通道与清理需补合同；固定 Windows 限制不能静默接纳 | Node/vendor、配置及 API 变化、补丁回合并与依赖供应链；包装层仍需本服务核心 | 保留 macOS/Linux 实验候选；固定 Windows 版本不满足本项目所需边界。不能由此推断未来版本也不可用 |
| C：VM 后端（容器单列） | 独立 guest 内核可减少共享宿主内核攻击面；共享目录、代理/管理接口仍可能穿越。容器通常共享内核，不能当作等价 VM | 镜像/虚拟化可用性、架构差异、启动内存、工具链同步、宿主路径映射、签名更新恢复成本 | 若 D1/D7 要求原生机制达不到的强度则重评；尚未选择具体 VM 产品或验证版本 |

上述成本判断是架构分析，无工期或性能排名。Rust 不自动带来安全；复用不自动保持语义；VM 也不能省略审批与共享目录保护。[Landlock 文档](https://docs.kernel.org/userspace-api/landlock.html)和 [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)支持按机制/能力分别建模，不能把 Job 成功等同文件或网络隔离。

## 同条件比较实验

运行时与 QA 在获授权的目标 runner 上，为 A/B 使用同一合成工作区、策略意图和攻击矩阵。先固定 OS/架构、内核、文件系统、安装权限、二进制摘要、上游源码/package/helper 配对。要求不改宿主设置的实验可先做；需要安装/持久变更的实验先由负责人安排恢复方案。

1. 合法读写/构建成功；hardlink、未来保护名、父目录替换、嵌套 namespace、继承 FD/IPC 越界失败，或初始化明确拒绝，负载启动计数为 0。
2. 同时经 exec 和 file worker 访问同一目标；采用可达的合成网络端点验证 deny，分别覆盖 DNS/代理/宿主代发路径。
3. once 增量必须仅作用于绑定操作；不能让同会话低权限进程借新权限访问；撤销时验证存量句柄和连接处理。
4. 自然退出、取消、超时、owner EOF、supervisor 崩溃逐项取证，检查真实资源身份；不以根进程退出作清理证明。
5. 在相同策略规模分别测冷/热准备 p50/p95、CPU/内存、工作副本导入/导出成本；保留失败/拒绝样本，不只统计成功路径。
6. Windows 安装/升级/卸载/回滚单独评估；拒绝弱化策略来换兼容。VM 候选只有被选作实验对象后才固定版本并运行同一矩阵。

接受上游前由运行时维护兼容清单、构建维护许可证/产物来源、安全评审边界、QA保留回归结果；更新后重跑受影响的对抗与工作流，不自动追 main。本轮没有执行上述 A/B/VM 对比，完整 M0 的复用评估出口仍未满足。
