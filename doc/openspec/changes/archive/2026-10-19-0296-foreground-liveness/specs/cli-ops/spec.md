# cli-ops — 记忆维护的时间上限（change 0296）

## ADDED Requirements

### Requirement: 记忆维护命令的时间上限

`memory maintain` SHALL 接受可选参数 `--timeout S`（单位**秒**，须为 `> 0` 的整数，
**缺省 `120`**）。命令 SHALL 以 `deadline = 当前单调时钟 + S` 调用记忆压实，并在遗忘归档前
再次检查截止时间：

- 截止后 SHALL NOT 发起新的模型调用，SHALL NOT 执行尚未开始的步骤；
- 命令 SHALL 正常退出（退出码 `0`），并明示「已达到时间上限（部分步骤已跳过）」；
- 非法 `--timeout`（`0` / 负数 / 非整数）SHALL 由参数解析拒绝（argparse 退出码 `2`），
  SHALL NOT 静默回落缺省。

命令仍为一次性动作：不改变运行态、不启动常驻进程。

#### Scenario: 缺省上限

- **GIVEN** 未传 `--timeout`
- **WHEN** 执行 `memory maintain`
- **THEN** 以 120 秒截止时间调用压实，并打印归档条数

#### Scenario: 自定义上限

- **GIVEN** 传入 `--timeout 5`
- **WHEN** 执行 `memory maintain`
- **THEN** 压实收到的截止时间约为当前时刻 + 5 秒

#### Scenario: 截止后跳过遗忘并明示

- **GIVEN** 压实执行超过 `--timeout`
- **WHEN** 命令继续执行
- **THEN** 不执行遗忘归档（或仅执行未越界的部分），打印「已达到时间上限（部分步骤已跳过）」，
  退出码为 `0`

#### Scenario: 非法上限拒绝

- **GIVEN** 传入 `--timeout 0` / `--timeout -1` / `--timeout abc`
- **WHEN** 执行命令
- **THEN** argparse 以退出码 `2` 拒绝，不执行任何维护动作
