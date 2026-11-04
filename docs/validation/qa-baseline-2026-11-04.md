# PUSH-5：c19b235 独立复测结论

2026-11-04，测试与兼容性工程师。**允许将这一固定探针版本合入非生产研究分支，须保留反例和能力限制；不通过 M0 出口，更不允许发布或运行不可信产品负载。** 本结论只覆盖下述 SHA 与实际环境，不代表后续新增 PoC 已复核。未修改被测实现。

## 版本、依据与取证边界

- 被测版本：`c19b23585d64d20869adb9654cfbc1f013584d40`，来自 PUSH-1 附件 `01a13ac5-1b81-799d-ac9d-64d35b68ccab`，bundle SHA-256 `09fdcdc431cafaec06ed9c455e8758980b9e622de2f951579a289d460ac6f7e2`。`git bundle verify` 成功，完整七次历史保留；独立 clone 后运行，没有覆盖实现者目录。
- QA 提交基于 main `bb4e544f09cd12fb2521772944060c23cb7f6932`，该 main 仅有设计和 README。已读取恢复分支 `2c71231e285b615b41532e1f077bbb2723ac127f`，其 `tools/m0` 与被测 SHA 的 Git diff 为空。这是源码一致性核对，不是对整个恢复分支重新运行测试。
- 依据根设计 v0.2 §10.2、§11.4、§12、§14.1、PUSH-2 任务和 PUSH-1 结果线程。根设计与历史副本原始 SHA-256 不同，CRLF 归一化后内容相同，见 `qa-evidence-2026-11-04/design-comparison.json`。
- 现有报告 schema 为 `1.0`，不是产品执行协议。另审阅 PUSH-7 `612003f2a78cc4f1670a308f4c2d1df253bd9d2e` 的 `sandbox.integration/0.1.0-draft.1` 和 PUSH-8 `7860b5f3f628750d8c8eb972ec52d445b037d64d` 的 AC01–AC19，作为未来 E2E 设计输入；两者不是已批准或已实现契约。
- D1–D7 仍待确认；不据本报告确认 Rust、首发平台或公开 API。没有安装系统组件、改变宿主安全设置或接触真实秘密。

## 本轮结果

主要复测时间为 UTC 06:28–06:31（北京时间 14:28–14:31）；最终 QA 采集工具和故障夹具在 UTC 06:37 再次验证。每条命令的完整 argv、cwd、时间、耗时和退出码见相应 `capture.json`。所有下表数字来自本轮日志，不沿用历史自测数字。

| 实际环境 / 动作 | 通过 | 失败 / 错误 | 跳过 / 未验证 | 退出码 |
|---|---:|---:|---|---:|
| 原生 Windows AMD64 / Python 3.8.5，unittest | 23 | 0 | 3 个 Linux opt-in 测试跳过 | 0 |
| 同一原生 Windows / Python 3.12.3，unittest | 23 | 0 | 同上 3 项 | 0 |
| WSL2 Ubuntu 26.04 LTS x86_64 / Python 3.14.4，默认 unittest | 21 | 0 | 3 个 Linux opt-in + 2 个 Windows 原生测试跳过 | 0 |
| 同一 WSL / `SBX_M0_INTEGRATION=1` unittest | 24 | 0 | 2 个 Windows 原生测试跳过 | 0 |
| Windows 两个解释器各自 CLI 探针 | 各 1 | 0 | 各 5 项 unverified | 各 2 |
| WSL CLI 探针 | 11 | 2 个保护反例 | 5 项 unverified | 1 |
| Windows 额外 API 故障注入断言 | 3 | 0 | 不代表真实 OS 拒绝/E2E | 0 |
| 原生 Linux 非 WSL | — | — | 无 runner，未执行 | — |
| macOS Intel / Apple Silicon | — | — | 无 runner，未执行；该版本无实现 | — |

原生 Windows 注册表 build 为 `26300.9711`，DisplayVersion `26H2`，AMD64，测试 token 管理员标记为 false，PowerShell `5.1.26100.9711`。同宿主 Python 3.8.5 报 `Windows 10 / 10.0.26100`，3.12.3 报 `Windows 11 / 10.0.26300`，不得把它们当两台独立宿主或两代 OS 的兼容证据；详见 QA-03。

WSL 内核 `6.6.114.1-microsoft-standard-WSL2`，Ubuntu `26.04 LTS`，用户 UID/GID 1000，bwrap `0.11.1`。源码和临时合成目录均在 `/mnt/c/...`，`stat -f -c %T` 返回 `v9fs`；没有执行 WSL ext4、原生 Linux、容器或其它发行版矩阵。WSL 枚举在外层沙箱遇到 `E_ACCESSDENIED`，获准使用现有 WSL 后取证成功；这次限制不算产品缺陷。查询和测试未改变 WSL/宿主安全配置。

## 可复现命令与证据

从被测源码根目录：

```text
python -m unittest discover -s tools/m0/tests -v
```

Linux/WSL 从被测根目录分别执行：

```sh
python3 -m unittest discover -s tools/m0/tests -v
SBX_M0_INTEGRATION=1 python3 -m unittest discover -s tools/m0/tests -v
```

从被测 `tools/m0` 执行（Windows 另以 Python 3.12.3 复跑）：

```text
python -m sandbox_probe --output <本任务证据目录>/probe.json
```

WSL 用 `python3`。采集工具完整命令和作用域内环境见 `tools/qa/README.md`。`capture.json` 是命令日志，`unit-*.stderr.txt` 是完整 unittest 输出，`probe.json` 是未改写原始报告，`probe.stdout.txt` 可与 JSON 对照。`source-status-before/after` 均为空，源码 SHA-256 清单存于每个 capture。

证据目录：`qa-evidence-2026-11-04/windows-py38`、`windows-py312`、`wsl-ubuntu`；补充证据为 `windows-api-faults.json`、`windows-host.json`、`design-comparison.json`、`wsl-filesystem.json`。所有相对位置以本报告所在目录为起点。文件需随任务附件交付；本机绝对路径不是用户下载链接。

交付版采集器改为保存原始 stdout/stderr 字节，随后 `windows-capture-final` 复核仍为 23 通过/3 跳过、探针 exit 2；最终故障夹具增加干净源码检查和禁止覆盖证据，`windows-api-faults-final.json` 三项断言再次通过。这些是工具收尾验证，不混入 WSL 两次反例的复现次数。

早期 Windows 采集文本的 CRCRLF 已单独规范化为 LF，转换前后 SHA-256 和次数见 `log-normalization.json`；未改测试结果、正文或原始 probe.json。最终采集日志保存原字节。

## 独立代码与测试审查

Windows `windows.py:93–154` 使用固定 `-I -S` 子进程，suspended 创建，归入 Job 后才恢复，不继承句柄；ready 文件和运行状态均成立才关闭 Job，等待进程句柄进入结束状态。正常报告包含 PID、先归组、正在运行及关闭后终止四项证据。`KILL_ON_JOB_CLOSE` 的测试仅覆盖主动关闭和这一子进程；无 breakaway、多级后代、宿主代执行或 supervisor 崩溃证据。

额外 QA 夹具分别对 CreateProcessW、AssignProcessToJobObject、ResumeThread 注入错误 5。第一项返回 unavailable，后两项返回 fail；后两项真实 PID 的独立 OpenProcess 查询均返回 87，无 cleanup_errors，QA 临时目录已删除。仅失败 API 为 mock，不把此结果称为完整权限拒绝测试。原测试的 ResumeThread 故障路径也在两个 Windows 解释器下运行。

Linux `linux.py:143–179` 同时检查合法读写、保护对象可读和禁止变更、合成秘密保持不变；hardlink 和未来名称反例为 fail。`_FS_SCRIPT.denied` 捕获所有 OSError，不记录 errno，故这里的 pass 只说明固定操作未成功，不能归因到完整产品 PolicyDenied 或任意路径保护。

网络测试先由宿主正向到达同一端点，再检查 namespace 不同和隔离侧结果。UDP 本轮 send 成功，但宿主未收到包，正确地按接收结果判断；不能因 send 成功误报绕过，也不能把 0.4 秒未收到当成完整外网/DNS 防护。TCP/abstract socket 返回 errno 111，不能独立推广为产品策略裁决。

Linux 回收代码 `linux.py:292–352` 记录 PID 与 start time，保留一秒内回收的判定；finally 前台等待已观察后代，晚到的自行退出不把原失败改写为通过。正常报告根 exit 0、detached child 被观察且回收、返回前观察后代收集均为 true。故障测试部分 launcher 为 mock，合成真实子进程约 0.4 秒自行退出，由真实 reaper 收集；它证明返回前等待，不能证明主动杀死任意失控后代。现有输出上限测试实际运行，超过 16 KiB 触发中止。

三次采集的受控 scratch 均空，故障注入 scratch 已删除；原实现清理路径未观察到残留或漏报。**这不是整机进程/句柄/挂载泄漏证明**：没有句柄计数压力测试、强杀 supervisor 测试或任意后代穷尽测试。`_run` 仅 kill/wait launcher，依赖该固定 namespace 方案处理后代；`_lifecycle` 只等待已观察的身份。不得将其抽取为通用 runner 后沿用当前结论。

report 单元测试通过的仅是报告/分派合同（mock 缺依赖、异常、非法输出、写失败、脱敏与退出码），不能计为相应平台 OS 隔离通过。测试套件将成功复现反例视为测试断言通过，CLI 仍保留 fail；CI 若只看 unittest exit 0 会误判产品可用。以后修复挂载/拒绝方案需按新 SHA 更新预期并独立复测，不应删除反例来维持绿灯。

## 结论与交接门槛

研究分支可接收原有七次有意义提交、固定探针与明确限制。已知 QA-01/02 为研究反例，不阻塞以非生产用途保存历史；任何合并若改变负载、策略或对外承诺，本结论失效。QA-03 为证据归档质量缺口，不阻塞保存研究代码。QA 本轮仅新增 `docs/validation/qa-*` 与 `tools/qa/`，不替运行时修实现，不自行合并。

产品发布阻塞：hardlink/未来名称静默绕过、完整 deny/路径/后代/资源矩阵缺失、无策略编译/RPC/文件 worker/可信审批/安装升级及真实端到端链路；原生 Linux/macOS 未执行。M0 还缺三平台可行性边界、复用比较、安装恢复及产品决定。各条目与 M1/M2 门槛见 `qa-acceptance-matrix.md`；缺陷最小复现与回归条件见 `qa-findings-2026-11-04.md`。

下一步由研发负责人组织恢复历史及 QA 产物评审；运行时的新 PoC 给出新 SHA 和清理证据后重新验收；架构师协调未冻结契约；发布角色在真实安装、升级、失败回滚及所声明平台矩阵通过前不得发布。安全角色可使用原始 Linux 反例报告和 Windows 故障注入记录复核权限/路径/回收边界。
