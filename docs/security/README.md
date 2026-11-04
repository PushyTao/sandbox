# PUSH-4：M0 独立安全复核

评审日期：2026-11-04；角色：安全工程师。结论适用于下列固定版本及合成实验，不是产品认证。

**可合并：`c19b23585d64d20869adb9654cfbc1f013584d40` 可以作为明确非生产、仅运行固定合成实验的研究工程进入 main。** 本轮没有确认该范围内新增的阻断级探针自身缺陷。应保留 README 的非生产限制、两项反例、未验证项和 `production_ready=false`，不得接入任意用户负载。此意见不代表已经合并，也不批准其它分支上的实现。

**需修复：直接工作区方案的硬链接别名与未来保护名称反例阻断产品使用。证据不足：完整文件策略、审批与管理服务、宿主 IPC、全树清理、Windows 隔离组合和 macOS 后端。产品安全验收保持未通过；完整 M0 也未验收。** D1–D7 仍待确认，本报告不改变 D1，也不选定语言、首发平台或外部协议。

## 版本与范围

| 输入 | 本轮处理 |
|---|---|
| 根设计 v0.2 `2026-09-30-agent-sandbox-design.md` | 阅读 §§1、4–10、14；以当前 main `bb4e544f09cd12fb2521772944060c23cb7f6932` 为文档提交基线 |
| 恢复代码 `c19b23585d64d20869adb9654cfbc1f013584d40` | 从已获取 Git 对象提取到本任务独立副本；审查全部 `tools/m0/sandbox_probe/*.py` 及三个测试文件，并重新实测 |
| 集成分支 `2c71231e285b615b41532e1f077bbb2723ac127f` | `git diff --quiet c19b235 <集成提交> -- tools/m0` 退出 0；复测可用于该提交中未变化的 M0 代码，不覆盖额外集成文档 |
| PUSH-8 `7860b5f3f628750d8c8eb972ec52d445b037d64d` | 阅读 `docs/console/trust-and-contracts.md` 作为审批/控制台草案输入；未实现、未联调 |
| PUSH-7 `612003f2a78cc4f1670a308f4c2d1df253bd9d2e` | 阅读 `docs/integration/experimental-contract.md` 作为工具通道草案输入；未把夹具当真实服务 |

仅新增 `docs/security/` 与 `tools/security-tests/`；未改运行时、历史提交或其他角色文件。七个恢复提交由研发负责人原样集成，不在本变更中重复导入。

## 本轮结果

| 环境 | 基线单元/集成套件 | 新增安全检查 | 原生探针报告 |
|---|---|---|---|
| Windows，Python 报告 `Windows-10-10.0.26100-SP0`，AMD64，Python 3.8.5 | 26 项：23 通过、3 个 Linux 专项跳过；退出 0 | 7 项通过；退出 0 | 1 pass、5 unverified；退出 2 |
| Ubuntu WSL2，kernel `6.6.114.1-microsoft-standard-WSL2`，x86_64，UID 1000，Python 3.14.4，bwrap 0.11.1 | `SBX_M0_INTEGRATION=1`，26 项：24 通过、2 个 Windows 专项跳过；退出 0 | 5 通过、2 个 Windows 专项跳过；退出 0 | 11 pass、2 fail、5 unverified；退出 1 |
| macOS、原生 Linux 发行版/其他内核、Windows 其他版本 | 未执行 | 未执行 | 无本轮证据 |

原始日志、JSON、源码 SHA-256 和精确复现方式见 [证据说明](evidence/2026-11-04/README.md)。Windows 版本字符串照录 Python API，不据此推定市场名称。WSL 不能代替原生 Windows，也不能外推所有 Linux。测试套件通过与探针反例 `fail` 同时成立：前者断言“确实重现反例”，后者表示候选保护失败。

## 探针自身审查

以下代码位置均指 `c19b235`，不是本安全文档提交。

| 项目 | 结论与证据 | 限制 |
|---|---|---|
| 任意代码入口 | `report.py:150` 的 CLI 只接受报告输出路径；独立测试确认命令、工作区、平台覆盖和位置参数被拒绝，且不调用探针。`linux.py:57` 的脚本调用者为固定本地代码；Windows `windows.py:89` 使用固定 `-I -S -c` 脚本 | Python 私有函数不是安全 API；操作者必须信任检出的代码、解释器和启动环境。`--output` 是可信操作者的宿主写路径，不能直接承接模型输入 |
| helper 与启动前约束 | `linux.py:22` 固定 `/usr/bin/bwrap`，检查解析目标及祖先的 root 所有权/组和其他用户写权限；不查工作区 PATH。`windows.py:81` 先配置 Job、以 suspended 创建，再归组、resume | 未验证 helper 安装/更新竞态、ACL 变体或签名；Linux `/usr` 很宽且未加 seccomp，Windows 使用当前身份；均非完整后端 |
| 初始化失败与回收 | Windows 原生独立测试分别注入 Job 配置失败和归组失败；前者没有创建进程，后者没有 resume，并通过保留的同一进程 handle 确认退出。既有 ResumeThread 失败测试亦通过。Linux `linux.py:292` 的初始化故障测试前台收集已观察合成子进程，本轮通过 | Linux 只跟踪已观察 PID/starttime；不能保证未观察恶意后代。真实 supervisor 崩溃、断连、全部取消分支仍未覆盖；Windows 极端终止/等待失败会报告 cleanup_errors，不能宣称无残留 |
| 越界删除 | 删除路径来自自身 TemporaryDirectory，未发现负载传入任意递归删除根。新增真实目录 symlink 清理测试在两环境中均保留外部合成哨兵；整个外层夹具也删除成功 | 哨兵仅是本测试根内的兄弟目录；未验证并发路径替换、Windows junction/其他 reparse tag、mount/卷边界。不把 symlink 测试替代这些测试 |
| 网络伪阳性 | `linux.py:206` 使用本地可达的正向对照和不同 net namespace。UDP 由宿主是否收到包判断；本轮 `sendto` 返回成功但宿主未收包，报告未错误地依赖发送错误 | 仅 loopback TCP/UDP IPv4/IPv6 及 abstract Unix；0.4 秒观察不能代替所有网络协议、外部路由或 IPC 证明 |
| 文件伪阳性 | `linux.py:143` 同时验证普通读写、受保护对象可读、合成外部秘密不变；`linux.py:110` 未复现反例只会写 unverified，不写 pass | `denied` 接受任意 OSError；只能解释为指定操作未成功，不能推断完整策略拒绝原因。文件操作矩阵仍不完整 |
| 秘密、输出与报告 | `report.py:69`/`linux.py:90` 避免输出任意异常消息；Linux `_run` 合计限 16 KiB、8 秒，输出上限故障用例通过；固定报告 `production_ready=false`，空结果/缺能力不能成为成功 | Windows `CreateProcessW` 的环境参数为 None，会继承宿主环境，固定子程序不输出环境，但此模式禁止推广给不可信负载；报告文件本身并非防篡改审计存储 |

## 分级发现与交接

等级按**如果将候选用于生产会造成的影响**划分；“研究合并阻断”另列，避免把预期反例当作新探针漏洞。P1 为可破坏核心边界、产品上线前必须解决；本轮没有确认 P0（在受限固定研究范围内直接危及宿主）的新问题。

| ID / 级别 | 条件、证据与定位 | 研究合并 / 产品 | 负责人、修复及复测门槛 |
|---|---|---|---|
| SEC-01 / P1，已验证已知反例 | 同文件系统内，可写 alias 与受保护对象共享 inode；只读 bind 原路径仍可经 alias 修改内容。`linux.py:168`；WSL `FS-4.hardlink=fail`。新增合成测试另证明名称过滤复制会把禁止读取对象的别名内容带入副本 | 不阻断明确非生产研究；阻断宣称保护对象的产品策略 | 运行时工程师修复、架构师决定对象/副本契约；按 [FS-A/C](negative-regressions.md) 覆盖读/写/链接/导入，无法证明则启动前拒绝；安全独立复测 |
| SEC-02 / P1，已验证已知反例 | 保护挂载只针对现有条目，负载能新建 `.agents/config`。`linux.py:174`；WSL `FS-4.future-name=fail` | 同上 | 运行时工程师；按 [FS-N](negative-regressions.md) 验证 create/mkdir/rename/link 到未来控制名称被阻止或策略被拒绝，不靠一次扫描 |
| SEC-03 / P1，缺口与有限反例 | `linux.py:134` 只检查当前被挂载保护目录的 rename；不覆盖工作区根/其他祖先替换及启动竞态。新增确定性实验表明缓存的 resolve 结果在父目录替换后会读取新对象；没有声称已绕过某个尚不存在的生产实现 | 不阻断固定研究；保护范围证据不足 | 架构师＋运行时；按 FS-P/C 设计对象锚定、快照和导回冲突检测；生产实现出现后再做真正并发负向测试 |
| SEC-04 / P1，设计缺口 | 服务端认证、不可伪造 grant、消费/撤销尚无实现；仅有 v0.2 §§6/11 与 PUSH-7/8 草案。Git protected 优先级和可审批写入仍有歧义 | 不阻断研究；AUTH-1/API-1 无产品证据 | 架构师协调运行时、接入、控制台；采用 [AUTH 矩阵](negative-regressions.md)，批准不能绕过硬拒绝，不先提供 Git 写 grant |
| SEC-05 / P1，平台缺口 | Windows `windows.py:157` 明确 token/ACL/network/IPC/后代未验证；Linux `linux.py:391` 明确嵌套 namespace、handles、完整清理等未验证；macOS 无实现 | 不阻断研究；不满足平台产品验收 | 运行时＋测试兼容性；逐项取得 [能力矩阵](threat-model.md) 的目标平台证据，缺必需能力必须拒绝 |

交由研发负责人协调所属实现者，不在独立评审中修改业务实现。修复后由安全角色对固定修复 SHA 复测；本报告不是授权扩大宿主权限或关闭安全设置。

## 接受范围与未覆盖

研发负责人可据本报告继续研究代码的严格 review/合并流程，保留七个有意义的历史提交。新安全文档和合成测试仍需其他角色独立复核。未运行真实恶意程序、未读取真实秘密、未访问第三方测试目标、未修改账户/ACL/防火墙/系统信任。没有测试实际审批服务、安装升级、完整控制台、外部 Agent 端到端链路或产品发布。没有发现新阻断项不等于证明绝对安全。

具体信任边界见 [威胁模型](threat-model.md)，不可取消的条件和待实现用例见 [负向回归](negative-regressions.md)。
