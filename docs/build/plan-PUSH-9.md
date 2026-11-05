# PUSH-9：M0 测试与分发前置材料计划

**目标：**为现有 Python 探针提供可审阅的三 OS 测试配置、复现和归档方法，以及未来安装升级验收清单。

**依据：**PUSH-9 的验收要求及 `docs/design/2026-09-30-agent-sandbox-design.md` §12、§14。这是既定 M0 范围内的构建文档和配置变更，不增加运行时行为或冻结产品接口。

**范围：**仅 `.github/workflows/`、`docs/build/`、必要时 `tools/build/`；本轮沿用已有 unittest 入口，不另造测试框架。Python 标准库是探针依赖，Rust 和首发平台未定。禁止修改 `tools/m0`、宿主安全设置、实际发布或重复恢复基线。

## 实施与验证

- [x] 读取设计、父任务及 PUSH-1 交接；验证原 bundle 完整性，并在独立任务分支保留 c19b235 的七个提交。
- [x] 复跑 Windows 基线；记录 Python、OS、架构、权限、命令和退出码。
- [x] 创建 `.github/workflows/m0-tests.yml`：仅手动触发、三种标准 runner、固定 Actions SHA、固定实验用 Python、只读权限、时间上限；保留 skipped 和未验证边界。
- [x] 创建 `docs/build/README.md`：环境依赖与许可证、Actions 来源、测试/探针退出码、非生产归档和校验、CI 成本与启动条件。
- [x] 创建 `docs/build/release-checklist.md`：组件配对、每平台前置条件、Windows 安装撤销、升级回滚卸载、独立评审和 D1–D7 门槛。
- [x] 保存 `docs/build/evidence/` 和本轮验证记录；检查 YAML 结构及内嵌 Python 可解析，不宣称 GitHub 执行通过。
- [x] 独立只读评审，确认无重要问题；检查变更只覆盖归属文件。

提交后执行归档重复生成、解包复测和补丁应用检查，再交付补丁、保留历史的 bundle、非生产源码归档和 SHA-256 清单。此步骤的实际结果记录在交付附件 `handoff-verification.json`，最终提交标识与交接状态以任务结果评论为准。由研发负责人在恢复基线上集成；不推送、不创建重复 PR、不自行合并。

## 验收边界

本机结果只覆盖实际 Windows/Python 组合。Linux、macOS 和 GitHub runner 未运行时保持未验证；macOS 通用 unittest 通过也不能算 sandbox 通过。外部 CI 未触发，无等待外部流水线的交付条件。归档可重复只指同一 Git 提交和 Git 工具生成的源码 ZIP，不承诺跨 Git 版本或产品二进制可重现。
