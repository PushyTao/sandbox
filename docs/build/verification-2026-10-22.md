# PUSH-9 验证与交接记录

日期：2026-10-22。交付范围仅为 M0 构建配置、文档和证据，**不代表 M0 或产品验收完成**。

## 基线和变更范围

- 基线：`c19b23585d64d20869adb9654cfbc1f013584d40`，从 PUSH-1 官方交接 bundle 导入；`git bundle verify` 返回 0，完整七个提交保留。
- 分支：`build/PUSH-9-m0-ci`，在本任务 checkout 中工作；没有改动运行时或 `tools/m0/tests`。
- 归属文件：`.github/workflows/m0-tests.yml`、`docs/build/`；没有新增生产依赖、API 或安装器。
- 原始设计副本 SHA-256：`5ade7cf27eae163360e2635aefd76a9c3651311b7f41b8443aae3e5ad75bfdcd`。
- 2026-10-22 只读远端查询：`main=bb4e544f09cd12fb2521772944060c23cb7f6932`；恢复分支 `feat/PUSH-2-m0-integration=2c71231e285b615b41532e1f077bbb2723ac127f`；远端存在 `refs/pull/1/head`。Multica 的父任务 PR 链接查询为空，不能据此宣称 GitHub 没有 PR。基线仍未进入 main；首次恢复/PR 归研发负责人，本任务不另建恢复 PR。

## 实际环境与结果

2026-10-22 的本机记录在 `evidence/2026-10-22/`。`evidence/` 根目录的文件保留 2026-10-14 同一任务早期复核，不替代本次结果。

| 环境项 | 实际记录 |
|---|---|
| Python 所见平台 | `Windows-10-10.0.26100-SP0`，`AMD64`，原生 Windows、非 WSL |
| 权限 | `IsUserAnAdmin=False`，普通用户执行；未改宿主安全设置 |
| Python | CPython 3.8.5，MSC v.1924 64 bit (AMD64) |
| Git | 2.54.0.windows.1 |
| 项目运行依赖 | Python 标准库；未安装 Rust 或其它工具链 |
| CI/本机的差异 | CI 规划 Python 3.12.10，Windows Server 2022 等 runner；本机结果不证明这些组合通过 |

平台值是解释器实际返回值，不据此推定 Windows 营销版本或其它 build 已通过。原始环境 JSON 包含时间、完整解释器版本、命令、工作目录和退出码。

| 命令/检查 | 退出码 | 结果与范围 |
|---|---|---|
| `python -m unittest discover -s tools/m0/tests -v`（仓库根目录，`SBX_M0_INTEGRATION=0`） | 0 | 共 26 项：23 通过、0 失败、3 Linux opt-in 项跳过；原始日志 `evidence/2026-10-22/windows-unittest.log` |
| `python -m sandbox_probe --output ../../docs/build/evidence/2026-10-22/windows-probe.json`（`tools/m0`） | 2 | Job 生命周期 1 项通过；filesystem/token/network/ipc/descendants 共 5 项 unverified；不是失败被忽略 |
| 本地 YAML/内嵌 Python 检查 | 0 | 已有 PyYAML 6.0.2 解析 workflow，检查仅手动触发、固定 SHA、三 OS/架构、只读权限、无凭据持久化；内嵌 Python 经 AST 解析并实际执行，能生成明确范围的 summary |
| `git diff --check` | 0 | 未发现空白错误；交付前还对 staged 内容复核 |
| `git diff --name-only c19b23585d64d20869adb9654cfbc1f013584d40 -- tools/m0` | 0，空输出 | 原探针和测试未修改 |

YAML 检查使用了本机既有 PyYAML，仅作为临时静态检查工具，不是探针或 CI 依赖，也没有新增依赖安装。可复查配置/语法的最小命令：

```text
python -c "import pathlib,yaml,ast; w=yaml.safe_load(pathlib.Path('.github/workflows/m0-tests.yml').read_text(encoding='utf-8')); assert list(w['on'])==['workflow_dispatch']; [ast.parse(s['run']) for s in w['jobs']['tests']['steps'] if s.get('shell')=='python']; print('YAML and embedded Python parsed')"
```

该检查不是 GitHub Actions 服务端校验，也未执行 checkout/setup-python；其本地 metadata 中 runner/image 为空是预期情况。本机未使用 CPython 3.12.10，不补写该版本通过记录。

## 未执行矩阵和阻断项

| 项目 | 状态 |
|---|---|
| GitHub Ubuntu 24.04 x64 / Windows 2022 x64 / macOS 15 arm64 | 未触发，全部未验证；不等待外部任务 |
| 本轮原生 Linux / WSL 集成 | 未执行；历史报告另见 `docs/validation/` |
| macOS sandbox / macOS Intel / Windows arm64 / Linux arm64 | 未实现或未验证，均无支持承诺 |
| 全新安装、覆盖升级、配置迁移、服务注册/停止、失败恢复、回滚、卸载 | 全部未执行，仅有未来清单；不存在候选安装包 |
| 产品构建、签名、部署、公开发布 | 均未执行、未授权；只生成非生产源码评审归档 |
| 完整 M0、架构/安全/QA 平台验收、D1–D7 决策 | 未齐备；已知文件保护反例仍阻断产品发布 |

## 交接方式

独立只读配置/文档评审于 2026-10-22 完成：未发现 Critical/Important 缺陷，可以交架构、安全和 QA 进一步验收。评审者另行执行 `python -B -m unittest discover -s tools/m0/tests -v`，退出码 0，23 项通过、3 项跳过；YAML/内嵌 Python AST、证据 JSON 和 staged 空白检查通过。这不是产品安全或平台支持签字。

提供相对于 c19b235 的格式化补丁、保留提交历史的 bundle、非生产源码 ZIP 和 SHA256SUMS。产物以实际最终提交 SHA 命名，具体值写在任务结果评论和附件清单，避免文档自引用提交摘要。接收者先核对摘要，再在研发负责人恢复的历史上集成；不新建第二套基线。

归档检查使用 [README 中的方法](README.md#非生产源码归档与校验)：同一提交连续生成两个 ZIP 比对 SHA-256、检查 CRC、解包到全新目录复跑测试；实际摘要及检查结果随交付附件记录。只对已生成的源码归档作完整性声明，不推广到未生成的产品二进制。

下一步由架构师协调独立架构/安全审查，QA 按环境提供平台结论，研发负责人完成恢复与补丁集成。CI 运行须先确认授权范围；发布仍须满足 `release-checklist.md` 全部门槛。
