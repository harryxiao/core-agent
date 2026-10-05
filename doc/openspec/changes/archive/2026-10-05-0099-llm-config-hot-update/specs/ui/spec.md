# UI Specification Delta

## MODIFIED Requirements

### Requirement: LLM API 可配置
系统 SHALL 支持在 Web 与桌面 UI 内配置 LLM provider、endpoint、API key、base URL 与**模型上下文窗口**
（`context_window`，用于派生 token 预算），并可配置执行循环的预算旋钮（`output_reserve`、
`max_rounds`）。保存 SHALL 把配置**写入后端配置源（config.yaml）并立即生效**：落盘 SHALL 原子提交
（不留下半写状态），运行中的执行循环 SHALL 立即取用新上限（无需重启或重建循环）。API key SHALL
以 `${VAR}` 引用形式保存与回显，**绝不**以明文写入配置文件、库、遥测或前端日志。

#### Scenario: UI 内配置 LLM API
- **GIVEN** 用户打开 Web 或桌面设置页
- **WHEN** 填写 provider/endpoint/key/base URL 并保存
- **THEN** 配置写入后端配置源并立即生效，密钥不进入前端日志

#### Scenario: 密钥安全存储
- **GIVEN** 用户保存了 API key
- **WHEN** 系统持久化配置
- **THEN** key 存储在本地受保护配置文件中，不入库、不进遥测

#### Scenario: 密钥持久化失败
- **GIVEN** 系统持久化 LLM API key 时发生磁盘写满或权限不足
- **WHEN** 保存配置失败
- **THEN** 回滚本次配置变更并提示用户，不留下半写状态，密钥不进入错误日志

#### Scenario: 上下文窗口与预算热生效
- **GIVEN** 系统已在运行，用户经 UI 保存 `context_window` 与预算旋钮
- **WHEN** 保存成功
- **THEN** 运行中的执行循环立即取用派生后的 token 预算与循环次数上限，下一次执行即按新上限判定

#### Scenario: 配置持久化后可重读
- **GIVEN** 用户经 UI 保存 `context_window` / `output_reserve` / `max_rounds`
- **WHEN** 重新加载配置（新进程 / 重新 `load()`）
- **THEN** 保存的值原样生效（非仅内存态），非法取值不落盘
