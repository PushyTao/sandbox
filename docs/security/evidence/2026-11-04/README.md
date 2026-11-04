# PUSH-4 本轮证据与复现

采集日期：2026-11-04（Asia/Shanghai）。评审目标为 `c19b23585d64d20869adb9654cfbc1f013584d40`。使用本任务独立源码副本，不在其他成员目录运行或修改代码。文件内容哈希记录在两个环境的 `summary.json`，八个 Python 源文件的 SHA-256 在两份记录中一致。

## 环境与授权范围

| 项目 | Windows | WSL2 Linux |
|---|---|---|
| 系统/架构 | Python API: `Windows-10-10.0.26100-SP0` / AMD64 | Ubuntu WSL2 / `6.6.114.1-microsoft-standard-WSL2` / x86_64 / glibc 2.43 |
| 解释器 | Python 3.8.5 | `/usr/bin/python3` 3.14.4 |
| 后端依赖 | kernel32 Job/CreateProcess API | `/usr/bin/bwrap` 0.11.1；实际 user/pid/net/ipc/uts namespace 可用 |
| 身份 | 当前运行账户；未切换管理员，token elevation 未单独核验 | 原有 Ubuntu 用户，`id -u` 和 collector 均为 1000 |
| 临时数据 | 本任务 evidence 下由 TemporaryDirectory 生成随机目录 | `/tmp` 下由 TemporaryDirectory 生成随机目录；不以 Windows 挂载目录作为 Linux 夹具 |
| 网络 | 固定 Windows 探针无网络实验 | 合成 loopback/abstract Unix 端点，无第三方请求 |
| 持久宿主变更 | 无账户、ACL、防火墙、驱动或全局设置修改 | 无 sudo、依赖安装、sysctl/AppArmor 或系统配置修改 |

本运行的 Windows 工具沙箱内 WSL 查询/调用返回 `E_ACCESSDENIED`；按权限流程在批准的执行上下文调用已运行的 Ubuntu，再确认实际 Linux UID 为 1000。这是测试环境访问限制，不是被测产品的隔离拒绝。未启动或改变 docker-desktop 环境。

## 复现命令

在包含恢复提交对象的仓库中提取同一源码；本轮 main 尚未包含 M0 代码，因此用独立目录：

```powershell
git archive --format=zip --output=../c19b235-review-source.zip c19b23585d64d20869adb9654cfbc1f013584d40
Expand-Archive -LiteralPath ../c19b235-review-source.zip -DestinationPath ../baseline-c19b235
python -B tools/security-tests/collect_review.py --source ../baseline-c19b235 --output-dir docs/security/evidence/2026-11-04/windows
```

使用新的目标目录复现，避免覆盖既有审查副本和证据。collector 的 `--source` 是可信操作者指定的已审查源码，不能来自模型/仓库配置或未审查下载物；它不是执行隔离接口。若代码已按历史合并，可将 `--source` 指向相应检出根。

本轮 Linux 由 Windows `wsl -d Ubuntu --exec /usr/bin/python3 -B` 调用同一 collector 的 WSL 路径；从 WSL 内该仓库目录等价执行：

```sh
/usr/bin/python3 -B tools/security-tests/collect_review.py --source ../baseline-c19b235 --output-dir docs/security/evidence/2026-11-04/wsl
```

两次最终 collector 均退出 0；这只表示其测试子命令通过和完成采集，**不改写探针退出码**。collector 执行下列固定子命令，环境中设置三个 temp 变量和 `SBX_REVIEW_M0_ROOT`，Linux 另设 `SBX_M0_INTEGRATION=1`；子命令超时上限 60 秒。只允许这些固定研究程序，不接受负载命令。

| 子命令 / 工作目录 | Windows 退出码 | WSL 退出码 |
|---|---|---|
| `python -m unittest discover -s tools/m0/tests -v` / 恢复源码根 | 0：23 pass、3 skip、0 fail | 0：24 pass、2 skip、0 fail |
| `python -B <本安全测试目录>/test_m0_review.py` / 恢复源码根 | 0：7 pass、0 skip、0 fail | 0：5 pass、2 skip、0 fail |
| `python -m sandbox_probe` / 恢复源码 `tools/m0` | 2：1 pass、5 unverified | 1：11 pass、2 fail、5 unverified |

此处 `python` 表示对应环境的 `sys.executable`；摘要已固定版本。3 个 Linux skip 为真实 Linux opt-in 专项；WSL 的 2 个基线 skip 和 2 个新增 skip 均需原生 Windows API。跳过不计入通过。

## 证据文件与解释

每个平台子目录包含：

- `summary.json`：环境、源码哈希、各子命令退出码、探针状态计数与临时根清理结果。
- `baseline-tests.stderr.txt`：基线逐项结果；stdout 为空。
- `security-tests.stderr.txt`：独立检查逐项结果；stdout 为空。
- `probe.stdout.txt`：原始语义不变的 JSON 报告；stderr 为空。

日志只规范化换行并将本机工作区绝对路径替换为占位符；未把失败改为成功。报告中的 PID、版本和单项结果保留。没有导出完整环境、真实密钥或凭证。两个 summary 均记录 `temporary_fixture_removed=true`；Windows 归组失败用例通过独立保留的进程 handle 验证退出，不依赖“PID 查不到”等模糊结果。

新增 7 项测试覆盖 CLI 拒绝负载参数、hardlink 与复制泄漏、resolve 后父目录替换、未来名称、目录 symlink 清理、Windows Job 配置失败和归组失败。前 3 个文件反例测试通过的含义是**简化方法失败得到重现**，不是文件隔离实现通过。目录 symlink 清理仅证明固定案例，不能推导 junction/reparse/竞态安全。

Windows 探针只验证一个固定子进程；Linux `PR-1.root-exit` 只验证一个固定 setsid 子进程及已观察后代收集。supervisor 崩溃、恶意后代、完整清理和实际产品审批均未验证。所有报告 `production_ready=false`。

## 完整性与旁证

- `git diff --quiet c19b23585d64d20869adb9654cfbc1f013584d40 2c71231e285b615b41532e1f077bbb2723ac127f -- tools/m0` 退出 0：被测基础代码与已恢复集成分支一致。
- 当前根设计原始字节 SHA-256：`e23cabd1e62799004a6b45990e0ea38907fa9a15b4c4c3d5b1f51309de8f11a6`；恢复设计副本：`5ade7cf27eae163360e2635aefd76a9c3651311b7f41b8443aae3e5ad75bfdcd`。以 Python 文本模式统一换行后逐字符相同，不将不同字节哈希误报为语义变化。
- 当前文档还参考了 PUSH-7/8 的草案；版本与文件在安全 README 中明确列出。没有声称复测它们的协议夹具、UI 或真实服务。
- 一手平台资料核查日期为 2026-11-04，链接随相应论断给出。在线资料的新版能力不计入本轮旧解释器/实际 kernel 的实测能力。
