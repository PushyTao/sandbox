# sandbox

本项目按[跨平台 Agent 沙箱设计 v0.2](docs/design/2026-09-30-agent-sandbox-design.md)开展实现。目前交付范围是 **M0 的部分可行性探针和证据记录**；完整 M0 尚未验收，M1–M3 尚未实现，不能用于运行不可信任务。

`tools/m0` 使用 Python 标准库执行固定的合成实验。它不是通用命令执行器，不接受待隔离的任意程序，不提供生产安全边界。Python 是本轮探针工具，生产实现语言与路线仍由待确认的 D3 决定。

## 当前范围

| 内容 | 本轮边界 |
|---|---|
| 报告 | 记录环境、观察结果和限制；`production_ready` 始终为 `false` |
| Windows | 探测 suspended 子进程先加入 Job、再恢复运行，以及关闭 Job 后终止该固定子进程 |
| Linux | 使用 bubblewrap 对固定文件、namespace 和进程生命周期场景取证；不等同完整策略实现 |
| macOS | 未实现、未验证 |
| 平台支持 | 单项原语通过不表示该平台的沙箱后端已支持 |

Windows Job 探针使用当前身份，未设置受限令牌、文件 ACL 或网络拒绝。Linux PoC 的运行时挂载也不能视为已经实现设计要求的 scoped read。WSL 中的 Linux 证据不能计作原生 Windows 支持。

## 运行

需要 Python 3.8 或更新版本。Linux 探针还需要 `bwrap` 和实际可用的用户 namespace；发行版或外层容器可能禁止这些机制。Windows Job 探针需要原生 Windows。探针不会安装依赖，也不会自动更改账户、ACL、防火墙或内核设置。

从仓库根目录运行单元测试：

```text
python -m unittest discover -s tools/m0/tests -v
```

从仓库根目录进入模块目录，再生成本机报告：

```text
cd tools/m0
python -m sandbox_probe --output m0-report.json
```

Linux 环境如果只有 `python3`，将上面命令中的 `python` 换成 `python3`。在 WSL 内执行 Linux 命令；不要将 Windows Python 启动的探针称为 WSL/Linux 测试。

| 退出码 | 含义 |
|---|---|
| `0` | 本次选中的观察项全部通过；不表示产品可用或完成安全验收 |
| `1` | 至少一项观察失败 |
| `2` | 存在不可用或未验证项，且没有失败项 |

当前报告保留未验证项；Linux 还主动重现不完整挂载方案的绕过，重现后记录 `fail` 并返回 `1`。这些是有意义的研究结果，不应通过隐藏条目或改成 `pass` 消除。没有失败但存在未验证项时返回 `2`。单元测试通过只证明被测试的软件行为，不证明 OS 隔离完整生效。

## 设计与后续工作

- [M0 范围与待决项](docs/decisions/0001-m0-scope.md)：D1–D7 均待确认；记录审批信任、Git 授权优先级、运行时和审计缺口。
- [验收矩阵](docs/validation/acceptance-matrix.md)：把实际观察与设计验收项分开，保留未覆盖场景。
- [固定上游资料与路线比较](docs/validation/upstream-references.md)：记录核查日期、提交和许可证来源；未完成 runtime 的本地集成比较。
- [贡献说明](CONTRIBUTING.md)：复现、证据和修改要求。
- [本轮实施计划](docs/superpowers/plans/2026-10-14-m0-feasibility.md)：只推进设计明确允许的 M0。

完成 M0 还需要三平台证据、受保护路径可表达性、完整后代回收与上游复用实测，以及 D1–D7 的产品决定。M1 需要真正的策略编译、默认断网、文件 worker、可信审批、会话/RPC、输出与取消、审计和适用安全矩阵全部通过。Windows 正式后端、域名代理、客户端和 PTY 属于 M2；凭据 Broker 属于 M3。
