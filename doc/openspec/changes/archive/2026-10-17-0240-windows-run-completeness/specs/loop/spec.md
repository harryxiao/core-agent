## MODIFIED Requirements

### Requirement: 运行环境事实

系统 SHALL 在推理用系统提示中提供可选的**运行环境事实**块，使模型按**宿主实际 OS 与默认
shell 方言**规划命令，而非假定一切为 POSIX bash。

- **事实内容**：块 SHALL 至少包含操作系统标识（Windows / Darwin / Linux 等）与默认 shell
  方言（powershell / bash / unknown）；SHALL 在可得时附带壳的简短标签（含主次版本更佳）；
  SHALL 含与该方言相关的路径与句法约束（有界、不得无界膨胀）。
- **可用性与标签**：块 SHALL 列出宿主 PATH 上**实际可用**的 shell（`pwsh` / `powershell` /
  `bash` 中可用者）；SHALL 区分 `PowerShell 7+（pwsh）` 与 `Windows PowerShell 5.1
  （powershell）` 两种标签；默认 shell 的解释器不可用时 SHALL 明确建议改用 `type=python`
  （当前解释器始终可用）。
- **进程与目录语义**：块 SHALL 说明每次 `code_run` 都是**全新进程**（`cd` 与环境变量不跨调用
  保留），需要指定目录时使用 `cwd`（绝对路径；支持 `~` 展开）。
- **有界回退**：块 SHALL 给出**有界**的 Python 回退规则 —— 仅在目标方言不可用或脚本无法用该
  方言表达时回退 `type=python`，优先 `pathlib` / `tempfile` 等标准库，SHALL NOT 硬编码
  `/tmp`，且 SHALL NOT 用 Python 回退掩盖方言错误。
- **未知 OS 诚实**：OS 不在已知集合时，块 SHALL 声明默认 shell 未知并建议显式 `type`，
  SHALL NOT 声称默认壳为 bash。
- **装配位置**：事实块 SHALL 作为系统提示的**独立块**注入，SHALL NOT 仅埋在工具 description
  里才算满足本 Requirement。
- **注入方向**：环境快照由组合根或测试替身注入；loop/planner SHALL NOT 在热路径强依赖不可
  替换的全局单例而导致单测打到真实 PATH。
- **未注入逐字不变**：未注入环境快照时，系统提示 SHALL NOT 新增「运行环境」块，与既有装配
  **逐字一致**。
- **不替代执行契约**：本 Requirement 只约束提示事实；命令实际执行方言与缺解释器行为见
  tool-use「内置原子工具」。

#### Scenario: 注入后系统提示含运行环境块

- **GIVEN** planner 已注入非空环境快照（含 OS 与默认 shell）
- **WHEN** 装配本轮系统提示
- **THEN** 提示中含独立「运行环境」类块，且可见该 OS 与默认 shell 关键字

#### Scenario: 未注入时不产块

- **GIVEN** planner 未注入环境快照
- **WHEN** 装配本轮系统提示
- **THEN** 不出现「运行环境」块，其余块序与既有行为兼容（无该块时的提示与未引入本能力前一致）

#### Scenario: Windows 且 bash 可用时提示可用方言与版本标签

- **GIVEN** 宿主为 Windows，PATH 上同时存在 `pwsh` 与 `bash`
- **WHEN** 渲染运行环境块
- **THEN** 块中可见 `pwsh` 与 `bash` 两项可用 shell，且默认 shell 标签含 `PowerShell 7+`

#### Scenario: 默认 shell 不可用时建议 python

- **GIVEN** 宿主为 Windows，但 PATH 上既无 `pwsh` 也无 `powershell`
- **WHEN** 渲染运行环境块
- **THEN** 块中明确建议 `type=python`，且不声称默认 PowerShell 可用

#### Scenario: 提示声明全新进程与 cwd 语义

- **GIVEN** planner 已注入任一非空环境快照
- **WHEN** 渲染运行环境块
- **THEN** 块中说明每次 `code_run` 为全新进程、`cd` 与环境变量不保留，并指出用 `cwd`
  （支持 `~`）指定目录
