## ADDED Requirements

### Requirement: 自检诊断（`doctor`）与运行状态（`status`）

CLI SHALL 提供 `doctor` 与 `status` 两个**只读**运维子命令：二者 SHALL NOT 改变运行态、SHALL NOT 启动
常驻进程、SHALL NOT 建立外部连接（含 MCP 连接）。

`doctor` SHALL 逐项自检并**逐条**呈现结论（`ok` / `warn` / `fail`），至少覆盖：配置可读且 schema 有效、
LLM 端点**已配置**、状态目录可写、工具与资产注册表可读。**全部项通过** ⇒ 退出码 `0`；**存在 `fail` 项** ⇒
退出码**非零**，且失败项 SHALL 逐条列明（含其名称与原因）。

`status` SHALL 打印运行概览（会话数 / 工具数 / 已安装资产数 / MCP 端点数 / 模型标识 / 循环预算），
并恒以退出码 `0` 结束（概览是信息面，不是判据）。

两项的输出 SHALL NOT 包含任何**密钥值** —— 涉及密钥的项 SHALL ONLY 呈现 `${VAR}` **引用名**与
「可解析 / 不可解析」的**布尔结论**（SHALL NOT 呈现解析结果）。密钥引用不可解析 SHALL 被报为 `fail`
项而非崩溃。

诊断结论 SHALL 由**单一**只读诊断源产出：CLI 与（后续的）其他消费面 SHALL 复用同一份产出，
SHALL NOT 各写一份检查逻辑。该诊断源 SHALL 经**依赖注入**取得全部句柄（SHALL NOT 自行装配运行时）。

#### Scenario: 自检全绿

- **GIVEN** 配置可读且 schema 有效、密钥引用可解析、状态目录可写、注册表可读
- **WHEN** 执行 `core-agent doctor`
- **THEN** 逐项列出检查结论且每项为 `ok`，退出码为 `0`

#### Scenario: 存在失败项时非零退出

- **GIVEN** 某检查项不通过（如 LLM 密钥引用**不可解析**，或配置缺失）
- **WHEN** 执行 `core-agent doctor`
- **THEN** 该项被呈现为 `fail` 并写明原因，退出码**非零**；其余项照常列出

#### Scenario: 诊断输出不含密钥值

- **GIVEN** 密钥引用可解析（其值存在于环境或 keychain）
- **WHEN** 执行 `core-agent doctor` 或 `core-agent status`
- **THEN** 输出中出现的只有引用名（如 `${CORE_DEEPSEEK_KEY}`）与「可解析」结论，
  **不出现**该引用的解析结果

#### Scenario: 运行状态概览

- **GIVEN** 存在若干会话与工具
- **WHEN** 执行 `core-agent status`
- **THEN** 打印会话数 / 工具数 / 已安装资产数 / MCP 端点数 / 模型标识 / 循环预算，退出码为 `0`
