# PUSH-4 / PR #2：R1 超时回收返工

2026-11-04；安全工程师。返工基于 `70466f551ec801718fc9e012562d749d96be1bb2`，保持原分支和 PR #2。仅修改 `tools/security-tests/` 与 `docs/security/`；原始 `test_m0_review.py`、M0 运行时及先前证据未修改。**本地复测通过，待系统架构师独立复审本次新提交；不自行撤销 R1 的合并阻塞。**

## 缺陷、修复与边界

R1（P2，阻塞 PR #2）：旧 `subprocess.run(timeout=60)` 只杀直接测试 Python。原 Windows 归组失败测试在真实子进程创建后、加入实验 Job 前挂起时，子进程尚未开始其 20 秒自退出代码；被杀测试 Python 的 `finally` 也不会运行。架构师附件 `01a1a57d-9c7e-730c-bd42-6963bbc23722` 提供此故障复现，本次沿用同一 `DuplicateHandle` 注入点和真实 60 秒截止时间。

`bounded_process.py` 为可信固定采集命令增加独立生命周期控制：

1. 采集器先配置不允许 breakaway、带 `KILL_ON_JOB_CLOSE` 的外层 Job；以 `CREATE_SUSPENDED` 创建测试 Python，成功归组后才 `ResumeThread`。Job 句柄不继承，显式继承列表仅含 stdin/stdout/stderr。使用 CPython `_winapi.CreateProcess` 保留主线程句柄，不依赖已丢弃该句柄的 `Popen`。
2. 测试后代从创建时即属于外层 Job，包括尚未归入实验 Job 的挂起进程。正常退出和超时均执行外层回收。先从该 Job 枚举成员，以 `OpenProcess` 获取句柄并用 `IsProcessInJob` 复核归属，再终止精确 Job；不按进程名或未经验证的 PID 杀进程。
3. 对保留的精确进程句柄等待退出，并再次确认 Job 活动列表为空。配置或外层归组失败时不恢复 Python；已创建的根进程也必须通过原始句柄终止并等待。清理失败、句柄等待未证实或成员枚举失败均写入错误，不得报告成功。
4. stdout/stderr 使用独立文件捕获；超时后仍写输出、`timed_out`、子进程退出码及 cleanup 证据，停止后续采集。采集器超时或清理不完整统一退出 1。正常研究探针的退出 1/2 仍按原样记录，不当作产品通过。

机制依据：[Job 继承规则](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)、[嵌套 Job 成员列表](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list)、[TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)。本机实测只证明下面列出的固定案例；这些 API 文档不代替测试。

## 实测与原始证据

| 验证 | 实际结果 | 文件 |
|---|---|---|
| 修改前红灯，保留真实 60 秒 | 回归程序退出 1；旧 collector 抛 `TimeoutExpired`，无 summary；返回时后代仍存活，独立保护句柄完成终止并确认退出 | `red-70466f5/regression.json`；该目录仅有超时前完成的基线输出，缺失 summary 正是旧缺陷 |
| 修改后同一故障，真实 60 秒 | 回归程序退出 0；collector 正确退出 1；故障命令耗时 60.016 秒；3 个保留句柄均确认退出，Job 活动数从 3 到 0；保护端未实施补救终止；两路输出保留，临时目录删除，probe 未继续 | `windows-timeout-final/regression.json`、`windows-timeout-final/collector/summary.json` 及各 stdout/stderr |
| 外层配置失败、外层归组失败、清理失败不得误报成功 | 3 项通过，套件退出 0；前两项 Python 没有运行，已创建进程通过句柄确认退出；第三项释放真实资源后注入失败回执，collector 即使子命令退出 0 仍返回 1 并停止 | `guard-tests/tests.stderr.txt`、`guard-tests/summary.json` |
| Windows 正常采集 | collector 0；基线 26 项中 23 通过、3 Linux 跳过；原安全检查 7 通过；probe 退出 2，1 pass / 5 unverified；每次外层 Job 回收完整 | `windows/summary.json` 及 6 个输出文件 |
| WSL 正常采集 | collector 0；基线 26 项中 24 通过、2 Windows 跳过；原安全检查 5 通过、2 Windows 跳过；probe 退出 1，11 pass / 2 fail / 5 unverified | `wsl/summary.json` 及 6 个输出文件 |

最终 Windows、WSL、故障采集的 `review_tool_sha256` 一致，绑定实际测试的 5 个安全工具文件；`source_sha256` 绑定相同的 8 个 M0 Python 文件。源码哈希按实际工作副本字节记录；Git 的 CRLF 转换可能改变其他检出副本的字节哈希，复核时应同时比较源码内容和换行设置。初次红灯运行在增加工具哈希记录之前，保留其原始结果，不事后伪造摘要。

原先的 `docs/security/evidence/2026-11-04/` 保持不变。输出只规范化换行与本机源码/证据路径，PID、版本、退出码及反例结果未改写。故障注入完全使用合成子进程、临时目录和精确句柄，未按进程名清理，未触碰 Multica 守护进程。

## 环境与复现命令

Windows：AMD64，CPython 3.8.5；Python `platform` 报告 `Windows-10-10.0.26100-SP0`，同机 PowerShell `[Environment]::OSVersion.Version` 报告 `10.0.26300.0`，保留两者差异，不推断市场名称。WSL：Ubuntu，UID 1000，Python 3.14.4，kernel `6.6.114.1-microsoft-standard-WSL2`，glibc 2.43；Linux 实验使用 `/tmp`，未使用 Windows 挂载文件系统作 Linux 夹具。WSL 首次调用被工具沙箱以 `E_ACCESSDENIED` 拒绝，随后按权限流程在已授权上下文运行现有 Ubuntu，无 sudo、配置修改或依赖安装。

从安全分支仓库根运行；`../baseline-c19b235` 是从 `c19b23585d64d20869adb9654cfbc1f013584d40` 提取的可信独立副本。使用新的输出目录，不覆盖随提交保存的证据。

```powershell
python -B tools/security-tests/test_collector_timeout.py --source ../baseline-c19b235 --output-dir ../r1-timeout-recheck
# 预期回归程序 0；其 collector/summary.json 中 collector_exit_code=1。

$env:SBX_REVIEW_M0_ROOT = (Resolve-Path ../baseline-c19b235/tools/m0).Path
python -B tools/security-tests/test_collector_guard.py
# 预期 0，3 项通过。

python -B tools/security-tests/collect_review.py --source ../baseline-c19b235 --output-dir ../r1-windows-recheck
# 预期 collector 0；probe 的原始 exit_code=2。
```

WSL 内从同一仓库根运行；本轮通过 `wsl -d Ubuntu --exec /usr/bin/python3 -B` 调用对应 WSL 绝对路径，等价命令：

```sh
/usr/bin/python3 -B tools/security-tests/collect_review.py --source ../baseline-c19b235 --output-dir ../r1-wsl-recheck
# 本机预期 collector 0；probe 的原始 exit_code=1，保留两个反例。
```

外层故障测试中 `--source` 只选择已审查可信源码，不接收任意工作负载。故障注入仅替换固定安全测试的启动命令，保持原 `WindowsInitializationFailures` 测试实现及基线源码不变；在 `DuplicateHandle` 后暂停 63 秒，让真实 60 秒采集截止先触发。保护端额外持有从真实进程复制的独立句柄，先观察 collector 返回后的状态，再按需补救，不以补救结果掩盖失败。

## 未覆盖与复审要求

这是测试采集器的回收修复，不是产品隔离后端。仅在本机 CPython/Windows 组合验证 `_winapi` 和嵌套 Job；不支持时记录失败并停止。Job 不能替代 token、ACL、网络或 IPC 隔离。未验证采集器自身崩溃、创建与归组间采集器死亡、恶意宿主代理绕过、持续派生竞态或其他 Windows 版本。

Linux 正常采集通过不证明超时后全树回收。该分支仍为直接子进程等待，明确记录 `scope=direct-child-only`、`descendant_cleanup_verified=false`；Linux 超时会标记 cleanup 不完整并失败，不宣称与 Windows 等价。

所有报告仍 `production_ready=false`。硬链接/未来名称反例、完整 M0 未验收、产品安全未通过、D1–D7 未确认等限制均不变。系统架构师需针对本次新 SHA 复核故障注入、启动顺序、精确句柄证据及正常 Windows/WSL 回归，通过后由研发负责人集成。`70466f5` 的旧审核不能覆盖新代码。
