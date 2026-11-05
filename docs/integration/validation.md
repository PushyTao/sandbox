# PUSH-7 验证与交付边界

日期：2026-10-22。实际环境：Windows NT `10.0.26300.0` / X64；Python `3.8.5`、Node `v24.14.1`、Git `2.54.0.windows.1`。只做版本、帮助、schema/源码及静态夹具验证，不运行模型，不安装/启动 sandbox 服务，不修改宿主安全设置。

## 已执行

| 命令（仓库根，特别标注除外） | 结果 | 退出码 |
|---|---|---:|
| `codex --version` | `codex-cli 0.154.0` | 0 |
| `codex --help`、`codex app-server --help` | 可见 app-server、exec-server、外部 mcp 入口 | 各 0 |
| `codex exec-server --help` | 可见 stdio/WebSocket 及并发配置 | 0 |
| `codex app-server generate-json-schema --help` | 可见实验 schema 导出 | 0 |
| `codex app-server generate-json-schema --experimental --out ./evidence/codex-schema`（任务工作区根） | 426 个 schema 文件；静态读取 dynamicTools、environments、fs 与 command 参数 | 0 |
| `claude --version` | `2.1.296 (Claude Code)` | 0 |
| `claude --help` | 仅核对参数存在，不运行任务 | 0 |
| `git bundle verify ../evidence/PUSH-1-m0.bundle` | 完整历史，HEAD c19b235；仅用 evidence ref 取证，不合并/改写它 | 0 |
| `git show c19b235:docs/decisions/0001-m0-scope.md` 等 | 本轮读取旧范围、评审与 CLI 入口；不是重跑旧测试 | 各 0 |
| `python docs/integration/validate_fixtures.py` | 19 个静态场景、59 帧 JSON-RPC 自洽检查通过 | 0 |
| `python evidence/check-validator-negative-cases.py`（任务工作区根） | 八种非法变体均被拒绝；不是运行时负向测试 | 0 |
| `git diff --cached --check` | 本轮全部六个新增文件无空白错误 | 0 |

Codex 命令虽退出 0，stderr 有清理旧 arg0 临时目录/PATH alias 的访问拒绝警告；不据此宣称运行时环境正常，也未为消除警告改变宿主权限。官方 Git 获取曾因本机代理连接失败，获准的只读获取后成功；不把首次失败隐去为全程无故障。GitHub release 网页与滚动文档分别核验，未声称取得 Claude API 精确 UTC 发布时间或安装最新版。

本轮从官方 `openai/codex` tag 验证：`git cat-file -p` 得到 annotated tag 指向 commit，`git rev-parse 'rust-v0.154.0^{commit}'` 得到 `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`，两命令退出 0。来源链接与源码范围见 README。固定源码/生成 schema 的读取不代替动态路由测试。

## 要求覆盖与未验证

| 要求 | 固定场景 | 静态状态 | Windows / Linux / macOS 真实任务 |
|---|---|---|---|
| 成功、失败 | success / nonzero_exit | 通过形状/配对/终态检查 | 均未验证 |
| 取消/幂等 | cancel_idempotent | 通过重复确认和终态检查 | 均未验证 |
| 超时 | timeout | 有 timed_out 预期终态 | 均未验证 |
| 空/异常输出 | empty_output / non_utf8_output / output_spoof_approval | 无伪输出；base64 字节长度、伪审批数据检查通过 | 均未验证 |
| 大小与截断 | output_truncated / invalid_server_frame | 有界留存/截断标记、传输故障预期 | 均未验证 |
| 服务不可用 | service_unavailable | 客户端诊断，无伪服务端响应 | 均未验证 |
| 版本不匹配/能力不足 | version_mismatch / capability_missing | 显式拒绝预期 | 均未验证 |
| 重复提交 | duplicate_submit | 同请求同 exec，不同内容冲突 | 均未验证 |
| 断连/不完整清理 | disconnect_cleanup / cleanup_incomplete | 明确 unknown/不完整，不伪造断连后收到事件 | 均未验证 |
| 审批/文件冲突 | request_permission / self_approval_denied / file_conflict | 无模型 grant；申请与决策隔离；冲突不覆盖 | 均未验证 |

没有执行的运行时项目统一记“未验证”，不是 skipped=pass。本轮没有跨平台动态测试计数，也没有继承 PUSH-1 的 Windows/WSL pass 数。真实的任务成功/失败、timeout/cancel、资源回收、MCP/Mods/executor 路由均等待后端及环境；安全验收未通过。

## 复核入口

从仓库根执行：

```powershell
python docs/integration/validate_fixtures.py
git diff --check
```

这些命令只检查文档夹具。可下载证据包还包含 `check-validator-negative-cases.py`，对八份内存副本分别破坏字节长度、响应关联、终态唯一性、自批拒绝、版本拒绝、能力拒绝、session 关联与非负输出计数，检查静态校验器确实拒绝；不写回夹具、不启动负载。独立审查及最终 Git 范围由交付评论记录。

独立初审发现通用响应检查不足以保证版本/能力场景必然拒绝，也未校验事件 session 与非负丢弃字节数。新增四项变体先在旧实现复现被接受（脚本退出 1），随后补齐错误 code/kind、会话关联和计数断言；八项变体全部被拒绝（退出 0），原 19 场景/59 帧仍通过。修复保留为独立提交，不抹去初审发现。

未安装/发现 GitHub CLI，未创建 PR/合并。Git commit 首次在受限环境遇到 signal pipe 权限错误，获准后成功；push 首次遇到 schannel 凭据获取失败，获准使用现有配置后成功（退出 0），远端分支 `agent/agent/9b2a0cd116bc`。交付另附保留提交的补丁/源码及证据，不沿用历史鉴权失败作为现状。最终 SHA/审查结果见任务评论。SESSION-01 和实验合同仍需架构师协调评审，实际 adapter 等待真实服务、可信审批及版本路由验证。
