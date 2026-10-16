## ADDED Requirements

### Requirement: 运行环境事实

系统 SHALL 在推理用系统提示中提供可选的**运行环境事实**块，使模型按**宿主实际 OS 与默认
shell 方言**规划命令，而非假定一切为 POSIX bash。

- **事实内容**：块 SHALL 至少包含操作系统标识（Windows / Darwin / Linux 等）与默认 shell
  方言（powershell / bash / unknown）；SHALL 在可得时附带壳的简短标签（含主次版本更佳）；
  SHALL 含与该方言相关的路径与句法约束（有界、不得无界膨胀）。
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
