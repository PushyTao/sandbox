# 贡献说明

先阅读[设计](docs/design/2026-09-30-agent-sandbox-design.md)和[M0 决策记录](docs/decisions/0001-m0-scope.md)。当前仓库处于可行性验证阶段，不能因增加一个探针而扩大对外安全承诺。

## 本地验证

从仓库根目录运行：

```text
python -m unittest discover -s tools/m0/tests -v
```

Linux 上显式启用真实 namespace、输出上限和故障清理测试：

```sh
SBX_M0_INTEGRATION=1 python3 -m unittest discover -s tools/m0/tests -v
```

该测试要求本机 `/usr/bin/bwrap` 可运行，且 IPv4/IPv6 loopback 与用户 namespace 可用。缺少条件时应记录失败/不可用原因，不能把跳过写成已通过。

原生平台验证另行运行：

```text
cd tools/m0
python -m sandbox_probe --output m0-report.json
```

需要时使用 `python3`。保存命令退出码，并检查 JSON 中每个观察项；只查看进程退出或测试数量不足以完成验收。退出码定义见 [README](README.md)。Linux 探针重现候选方案绕过时应为 `1`；没有失败但包含未验证项时为 `2`。

## 修改与证据要求

- 使用临时目录、固定程序和合成秘密；不以真实私钥、用户配置或仓库真实 `.git` 为 canary。
- 探针仅测试明确场景；不增加任意命令入口，不把一次路径扫描或单个拒绝案例描述为完整隔离。
- 不自动修改宿主账户、ACL、防火墙、内核设置、全局环境或信任库。需要这些条件的实验先记录所需权限与恢复方案。
- 对新增行为增加有区分力的正向、负向或故障测试；mock 只验证代码合同，实际 OS 行为必须在目标平台运行。
- 记录 OS/内核、Python、bwrap/helper 版本、命令、日期、退出码和原始 JSON。注明 WSL、容器、管理员或普通用户环境，不能把一个环境的结果推广到其它环境。
- `pass` 仅表示该观察的精确断言成立；缺依赖为 `unavailable`，未实现或证据不足为 `unverified`，观察与预期相反为 `fail`。不要把 skipped 当作通过。
- 报告中不包含秘密、完整环境、令牌或无界输出。共享前检查可能识别用户的路径和主机信息。
- 更改能力声明时同步更新[验收矩阵](docs/validation/acceptance-matrix.md)，保留限制和反例。M0 工具的 `production_ready` 不得改为 `true`。

## 提交与审查

提交说明写清触发条件、观察目标、实际测试和剩余限制。新增平台能力必须同时说明不支持的策略。引用上游时固定 release/commit，并记录许可证来源、补丁维护责任和升级后的回归范围。

只有实际完成推送、PR 或合并后，才能在交付说明中声称对应动作成功。网络或鉴权失败时保留本地成果和精确阻塞原因；不能把本地提交当成已发布。构建探针、设计批准、平台验收和生产发布是不同状态，应分别报告。
