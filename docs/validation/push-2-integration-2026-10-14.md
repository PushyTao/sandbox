# PUSH-2 历史恢复与验证

本记录只证明研究工程的恢复与列明的复测。M0 未完成，M1–M3 未实现；`production_ready` 保持 false。

## 来源与历史

- 用户现有 main：`679aa12198e33d172c45310e92d6fa1aedd7ef88`（初始 README）、`bb4e544f09cd12fb2521772944060c23cb7f6932`（添加技术方案）。
- PUSH-1 附件 `PUSH-1-m0.bundle`，附件 ID `01a13ac5-1b81-799d-ac9d-64d35b68ccab`，经 authenticated Multica CLI 下载；`git bundle verify` 确认完整历史。
- 恢复 HEAD：`c19b23585d64d20869adb9654cfbc1f013584d40`；原始 7 个提交未改写。
- 任务分支集成提交：`9cc5a96`，双亲为用户 main 与恢复 HEAD。解决 README add/add 冲突，保留 M0 范围说明；没有改动 `tools/m0` 实现或测试。
- 已成功推送 `feat/PUSH-2-m0-integration`。这解除 PUSH-1 当时的推送阻塞，不追溯改写其历史报告；推送不等于 main 合并。

## 本轮复测

环境：原生 Windows，Python 报告版本 `10.0.26100`、AMD64、Python `3.8.5`。不根据 `release=10` 字段推断产品名称。运行账户未增权，未改 ACL/防火墙/系统设置。

仓库根目录：

```text
python -m unittest discover -s tools/m0/tests -v
```

结果：退出码 0；26 项中 23 项通过、3 项 Linux 专项跳过。真实 Windows Job 正常路径及 resume 失败清理测试均运行；通用单元测试也包含 mock，不能整体称为 OS 安全验收。

`tools/m0` 目录：

```text
python -m sandbox_probe --output ../../docs/validation/windows-push-2-2026-10-14.json
```

显式保存 `$LASTEXITCODE`，结果为 2：`windows.job_lifecycle` pass，文件/token/network/IPC/descendants 五项 unverified。报告见 [本轮原始 JSON](windows-push-2-2026-10-14.json)。固定子进程在加入 Job 后运行，关闭 Job 后终止；不代表整树回收或完整 Windows 后端。

本轮研发负责人未重跑 Linux/macOS；PUSH-1 的 WSL 原始证据保留在原文件，由 PUSH-5 按自己的环境和 SHA 独立核验。Linux 已知 hardlink 和未来保护名称反例未修复，不把它们从报告中删除。

## 评审与合并门

历史独立审查见 [PUSH-1 记录](review-2026-10-14.md)，只适用于其列明的范围。本轮已分别委派 PUSH-3 架构、PUSH-4 安全、PUSH-5 QA 对恢复基线独立复核；结论以对应任务和 PR 的真实结果为准。在结论到达且阻断问题闭环之前，不将本记录视为合并批准。

Git 采用 merge commit 保留 meaningful commits；目标 main 不直接推送。管理控制台需求、环境与 session 的对应、审批信任合同和 D1–D7 仍需完成，不通过更改能力声明消除这些缺口。
