# M0 复现、流水线与源码交接

本目录只描述 Python 标准库可行性探针。没有生产运行时、安装包或已验收的隔离平台；Rust、公共契约、控制台形态和首发范围仍未确定。安装/升级/回滚的未来验收条件见 [release-checklist.md](release-checklist.md)，实际结果见 [verification-2026-10-22.md](verification-2026-10-22.md)。

## 运行环境与依赖

| 对象 | 当前范围 | 依赖/许可证处理 |
|---|---|---|
| M0 Python 源码 | README 声明 Python ≥3.8；实际组合以证据为准 | 无 pip/npm/Rust 构建依赖；本仓库未见 LICENSE，项目许可证待所有者明确，不擅自添加或宣称开源分发许可 |
| 本机解释器 | CPython 3.8.5，Windows AMD64 | 仅既有本机实验环境，不作为生产运行时选择；[对应 LICENSE](https://github.com/python/cpython/blob/v3.8.5/LICENSE) 含 PSF License Version 2 及历史条款 |
| CI 解释器 | CPython 3.12.10，三 OS 明确架构 | 固定实验版本；[对应 LICENSE](https://github.com/python/cpython/blob/v3.12.10/LICENSE) 及所含组件各自许可证；本任务不打包解释器 |
| Linux 真机探针 | 可选 `/usr/bin/bwrap`、可用 user/PID/network namespaces 和 loopback | 通用 CI 不安装/启用；实际二进制来源、版本、许可证仍需随目标环境取证。已有参考见 [upstream-references.md](../validation/upstream-references.md) |
| Windows 探针 | 原生 Windows、Python ctypes/系统 Job API | 当前身份执行合成子进程，无安装、账户、ACL、防火墙变更；Job 不是文件或网络隔离 |
| 归档工具 | Git，复核用 Python hashlib/zipfile | 记录 Git 版本；不把工具二进制放入源码归档 |

没有本项目编译产物或第三方运行库锁文件。未来若分发 Python、bwrap、runtime/helper 或其它组件，必须另建实际物料/版本/摘要与许可证、通知清单，当前资料核查不能代替分发审核。

## 本地入口与退出码

从仓库根目录执行，Linux/macOS 可使用 `python3`：

```text
python -m unittest discover -s tools/m0/tests -v
```

通用检查应清除外部的 `SBX_M0_INTEGRATION=1`，或显式设为 `0`。Windows 两项 native Job 测试仍会执行，Linux 三项实测为 opt-in。基线 c19b235 共 26 项：Windows 默认预期 23 项通过、3 项跳过；Linux/macOS 默认预期 21 项通过、5 项跳过。这只是基线预期，实际以当次日志为准；不得只写“26 项通过”。

要生成真实本机观察报告，另行执行：

```text
cd tools/m0
python -m sandbox_probe --output m0-report.json
```

PowerShell 用 `$LASTEXITCODE`、POSIX shell 用 `$?` 立即保存退出码，不要用后续查看文件的成功覆盖它。报告中的 `pass`、`fail`、`unavailable`、`unverified` 和 `production_ready=false` 必须保留。

| 入口 | 退出码 | 解释 |
|---|---|---|
| unittest | 0 / 非零 | 被选中测试无失败 / 测试或发现过程失败；跳过不代表通过 |
| sandbox_probe | 0 | 选中观察全部通过，仍不是生产就绪 |
| sandbox_probe | 1 | 至少一个失败；包括 Linux 已知绕过反例 |
| sandbox_probe | 2 | 无失败，但有不可用/未验证项 |

Linux 在已具备前置条件且获准的实验环境，可使用 `SBX_M0_INTEGRATION=1 python3 -m unittest discover -s tools/m0/tests -v`。测试会检查已知反例仍被报告为 `fail`；因此 unittest 绿色与探针返回 `1` 可以同时成立。不能改断言/吞退出码使候选看起来安全。macOS 尚无原生探针，通用测试绿色不能算 macOS sandbox 通过。

## 三 OS 手动工作流

配置为 `.github/workflows/m0-tests.yml`，仅 `workflow_dispatch`，输入 `runner_use_authorized` 默认 false。没有 push/PR/schedule 自动触发；没有付费大规格或自托管 runner、安装命令、产品发布或 artifact 上传步骤。本任务未触发任何 CI。输入是操作者声明，不替代仓库所有者对使用范围和费用的授权。

| runner 标签 | Python 架构 | 本轮 GitHub 执行 | 能证明的范围 |
|---|---|---|---|
| ubuntu-24.04 | x64 | 未执行 | 未来只跑通用软件行为测试，真实 Linux 集成关闭 |
| windows-2022 | x64 | 未执行 | 未来包括有限 Job 合成测试，仍没有 ACL/token/network 隔离验收 |
| macos-15 | arm64 | 未执行 | 未来只跑通用测试，不包含 macOS sandbox 实现；不覆盖 Intel |

架构按[官方 runner 表](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)选择。`macos-14` 已进入弃用并有计划失败时段，采用官方替代 `macos-15`；见[退休公告](https://github.com/actions/runner-images/issues/13518)。标签不固定镜像内容，每次须保存 Set up job 的 runner/image 版本；工作流额外打印平台、Python、架构、commit 以及明确白名单的 image 元数据，不输出完整环境或秘密。

首次运行前由负责人确认：恢复基线已合入目标 main、独立评审通过、仓库 Actions 和费用范围获准、三种 runner 可用。手动工作流需先存在于默认分支，见[官方说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)。再选定审查过的 ref 并将输入设为 true；保存 run URL、精确 commit、runner/image、测试日志和 skips。将来启用 PR 自动触发应单独审查费用与不可信贡献者执行边界。

### 固定 Actions 来源

2026-10-14 已核查官方 release、固定 `action.yml` 与 `git ls-remote` tag；2026-10-22 再次只读查询两个 tag，均与下表 SHA 一致。使用完整 SHA，不依赖滚动主版本：

| Action | 版本 / commit | 许可证 |
|---|---|---|
| actions/checkout | [v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) / `3d3c42e5aac5ba805825da76410c181273ba90b1` | [固定源码 MIT](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE) |
| actions/setup-python | [v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0) / `5fda3b95a4ea91299a34e894583c3862153e4b97` | [固定源码 MIT](https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/LICENSE) |

两个固定版本均使用 Node24，要求 Actions Runner ≥2.327.1；见 [checkout README](https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/README.md) 和 [setup-python README](https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/README.md)。这是 Actions 自身依赖，不是产品生产栈。

CPython 下载来源是 [actions/python-versions 发布 3.12.10-14343898437](https://github.com/actions/python-versions/releases/tag/3.12.10-14343898437)，其清单有 Linux 24.04 x64、Windows x64、Darwin arm64 产物。[macOS 15 ARM64 镜像清单](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md#python)也列有该解释器。这里只核查了来源和可用清单，未验证三平台下载后二进制摘要或实际执行。Action SHA 固定不等于镜像/工具缓存全部可重现；需随每次证据记录环境，更新 SHA 或 Python 版本须重新审查。

## 非生产源码归档与校验

只归档一个**明确提交**的跟踪文件，不复制工作目录，避免夹带凭据、缓存或未提交内容。源码 ZIP 不含 Git 历史；历史通过原 bundle 和本任务格式化补丁保存。归档标识包含 `m0-nonproduction`，用于本任务授权的评审交接，不建立公开发行或许可证承诺。

PowerShell 在仓库根目录执行；`artifacts` 应使用空目录，已有文件时停止而非覆盖唯一证据：

```powershell
$revision = git rev-parse --verify HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve source revision' }
if (Test-Path -LiteralPath './artifacts') { throw 'Choose a new empty output directory' }
New-Item -ItemType Directory -Path './artifacts' | Out-Null
$archive = "./artifacts/sandbox-m0-nonproduction-$revision.zip"
git archive --format=zip --prefix=sandbox-m0-nonproduction/ -o $archive $revision
if ($LASTEXITCODE -ne 0) { throw 'Archive failed' }
$digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
$checksumLine = $digest + '  ' + [IO.Path]::GetFileName($archive)
[IO.File]::WriteAllText((Join-Path (Resolve-Path './artifacts').Path 'SHA256SUMS'), $checksumLine + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
git --version
git show --no-patch --format=fuller $revision
```

接收者先对 ZIP 重新计算 SHA-256，与通过同一可信交接渠道取得的 SHA256SUMS 比较；摘要用于完整性，不是签名认证。用 Python `zipfile.ZipFile(...).testzip()` 检查 ZIP CRC，并在全新目录解包后复跑测试。用同一 Git 版本对同一完整 commit 再次 `git archive`，两个 SHA-256 应一致；不承诺不同 Git/zlib 版本的 ZIP 字节相同，更不承诺生产二进制可重复构建。

原基线为 `c19b23585d64d20869adb9654cfbc1f013584d40`，附件 bundle SHA-256 为 `09fdcdc431cafaec06ed9c455e8758980b9e622de2f951579a289d460ac6f7e2`，包含 7 个历史提交。研发负责人负责基线恢复和首次 PR；本任务只交独立构建补丁，避免另建冲突基线。集成时保留原七个提交；用 `git am` 应用补丁或保留本分支提交，PR base 为 main、标题含 PUSH-9，通过独立评审后用 merge commit，禁止 force push 或 squash 有意义提交。

源码归档、构建完成、安装验证、回滚验证和实际发布必须分别记录。当前仅第一项有交接产物，后三者未执行，产品构建也不存在。D1–D7、独立架构/安全评审及 QA 平台证据未齐备时，禁止产品发布。
