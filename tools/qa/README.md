# PUSH-5 独立取证工具

仅用于复核 `c19b23585d64d20869adb9654cfbc1f013584d40` 的固定 M0 探针。工具不修改 `tools/m0`，不安装依赖，不更改账户、ACL、防火墙或 namespace 设置。测试使用合成文件/进程，不接受任意用户负载。

准备独立、干净的历史 checkout（任务附件 `PUSH-1-m0.bundle` 含完整七次提交），不要覆盖团队实现者的目录。当前 main 尚无该实现时，可以将 bundle clone 到同一任务目录的 `qa-baseline`。以下在包含 `qa-baseline` 与本仓库 `sandbox` 的父目录执行：

```powershell
python sandbox/tools/qa/capture_m0.py --source qa-baseline --output sandbox/docs/validation/qa-new-run/windows-py38
py -3.12 sandbox/tools/qa/capture_m0.py --source qa-baseline --output sandbox/docs/validation/qa-new-run/windows-py312
python sandbox/tools/qa/audit_windows_failures.py --source qa-baseline --output sandbox/docs/validation/qa-new-run/windows-api-faults.json
```

在实际 Linux/WSL 中使用 Linux Python：

```sh
python3 sandbox/tools/qa/capture_m0.py --source qa-baseline --output sandbox/docs/validation/qa-new-run/linux
```

Linux 需要现有可用的 `/usr/bin/bwrap`、user namespace、IPv4/IPv6 和 Git；缺条件时不得安装组件或关闭安全控制来造通过。Windows 3.8/3.12 为本轮实际测试版本，Linux 为 WSL Ubuntu Python 3.14.4；不保证其它组合。所有命令以前台方式收集到结束。

`capture_m0.py` 固定运行版本检查、默认 unittest、Linux opt-in unittest 和报告 CLI；记录时间、cwd、完整 argv、作用域内临时目录、源码摘要、逐条退出码及 stdout/stderr。不会记录整个环境。输出目录必须不存在。`TMP/TEMP/TMPDIR` 只在子进程环境设置到证据目录内，`SBX_M0_INTEGRATION=1` 只用于 Linux 集成套件。工作区、临时目录所在文件系统必须另记，不能把 WSL 的宿主挂载卷结果推广到 ext4。

采集器退出 0 仅表示证据采集完成，**不是测试或产品通过**。验收必须读取 `capture.json.commands[].exit_code`、测试日志和 `probe.json`。探针返回 1 表示存在反例/失败，2 表示存在不可用/未验证；两者均不能升级成通过。采集器异常/超时是采集失败，不能给出完整报告结论；已有输出需保留排查。

`audit_windows_failures.py` 每次仅 mock 一个 Win32 API 返回拒绝，其余使用真实 Job/子进程/清理，并用独立 Win32 API 查询 PID 状态。CreateProcessW 拒绝场景不产生真实子进程；其余两项会创建真实 suspended 子进程。三项断言通过且无临时目录残留才退出 0。它不是真实宿主权限拒绝或产品 E2E 测试。

PUSH-5 返工后，每项还必须满足目标 API 恰好调用一次、错误 operation/code 与注入匹配、PID 和归组阶段符合场景。CreateProcessW 失败不得报告 PID；归组/恢复失败必须有有效 PID，且独立查询确认退出。缺失阶段、提前失败、清理失败均不能计为通过。报告的 `target_call_count` 与 `assertions` 保存每条判定的依据。

夹具回归命令（输出目录必须不存在）：

```powershell
python -B sandbox/tools/qa/regress_windows_audit.py --source qa-baseline --output qa-regression-py38
py -3.12 -B sandbox/tools/qa/regress_windows_audit.py --source qa-baseline --output qa-regression-py312
python -B sandbox/tools/qa/regress_windows_audit.py --source qa-baseline --output qa-early-assign.json --case early-assign
```

前两条执行 11 个控制：正常运行保留三项原始 API 故障；提前归组失败及九项错误/缺失证据控制必须各退出 1，全部符合预期时回归工具退出 0。最后一条单独复现归组提前失败，直接透传夹具退出码，预期 **1**。报告中的错误/PID/阶段变异只发生于真实固定探针完成清理后的返回数据，属于 QA 断言回归，不是新增 OS 隔离证据。完整 stdout/stderr、报告和命令保存在输出目录；见 `docs/validation/qa-rework-2026-11-04.md` 的修复前后结果。

本轮早期采集器将日志解码后写为 UTF-8，产生多余 CRCRLF；提交前仅将这些换行规范化为 LF，正文、测试结果和原始 probe.json 未改写。`log-normalization.json` 记录转换前后摘要和转换次数。交付版本保存 stdout/stderr 原始字节，后续采集以此为准。新运行使用新目录，不覆盖旧证据。原始报告不含秘密；绝对路径仅供复现命令审计，不作为交付链接。
