## ADDED Requirements

### Requirement: 工作树隔离配置

系统 SHALL 将 `orchestration.worktree_isolation` 纳入 ConfigSpec 单一真源，三面（CLI flag
`--orchestration.worktree-isolation` / env `CORE_ORCHESTRATION_WORKTREE_ISOLATION` /
config.yaml 的 `orchestration.worktree_isolation`）一一对应并参与优先级链
（CLI > env > config.yaml > 默认值）。默认值 SHALL 为 `false`，即不启用子 Agent 工作树隔离，
行为与引入前一致。

取值 SHALL 接受布尔值或 `true` / `false` 字符串；其他取值 SHALL 在校验期判为错误并**阻断
启动**，错误信息 SHALL 指明键名与合法取值，SHALL NOT 静默降级。访问器
`orchestration_worktree_isolation()` SHALL 在配置未加载或未配置时返回默认值 `false`。

仅当该配置为 true 时，组合根 SHALL 构造工作树管理器并在主工具面注册
`tools.worktree.list` / `tools.worktree.discard`；为 false 时 SHALL NOT 构造管理器，
SHALL NOT 注册上述工具，SHALL NOT 创建状态目录下的工作树根。

#### Scenario: 缺省关闭

- **GIVEN** 配置未声明 `orchestration.worktree_isolation`
- **WHEN** 读取访问器并构造运行时
- **THEN** 访问器 SHALL 返回 false，运行时 SHALL 不含工作树管理器与工作树工具
- **AND THEN** 委托行为与持久化字段 SHALL 与引入前逐字一致

#### Scenario: 三面取值与优先级

- **GIVEN** yaml 为 false、env 为 false、CLI 为 true
- **WHEN** 加载配置
- **THEN** 访问器 SHALL 返回 true（CLI 优先）
- **AND THEN** 运行时 SHALL 组装工作树管理器并注册两个工作树工具

#### Scenario: 非法取值阻断启动

- **GIVEN** 取值为 `maybe` 或无法解释为布尔的其他字符串
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明
  `orchestration.worktree_isolation` 与合法取值
- **AND THEN** SHALL NOT 回退为默认值继续启动
