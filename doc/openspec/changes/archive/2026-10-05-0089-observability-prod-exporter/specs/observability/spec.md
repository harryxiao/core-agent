# Observability Specification Delta

## MODIFIED Requirements

### Requirement: 全链路日志
系统 SHALL 记录模型输入/输出、工具调用、执行耗时与副作用，结构化且敏感信息脱敏。系统**组合根**（`build_runtime`）SHALL 在调用方**未注入** tracer 时装配**生产导出器**：把脱敏后的结构化事件以 JSONL **追加**落 `$CORE_STATE_DIR`（缺省 `~/.core/state`）的 trace 文件，并以**缓冲 / 退避重试导出器**包装 —— 导出失败降级为内存缓冲 + 溢出兜底，SHALL NOT 抛出、SHALL NOT 阻塞主循环。显式注入的 tracer SHALL **优先**（保持可覆盖，SUT/宿主可替换导出面）。

#### Scenario: 记录模型与工具调用
- **GIVEN** 一轮 loop 执行了模型推理和工具调用
- **WHEN** 遥测中心采集事件
- **THEN** 每个事件以结构化 JSONL 记录，含 trace_id/span_id/ts

#### Scenario: 敏感信息脱敏
- **GIVEN** 一个事件包含密钥等敏感值
- **WHEN** 写入日志
- **THEN** 敏感值被脱敏后才落盘（与 coeffect secret 标记联动）

#### Scenario: 组合根装配生产导出器
- **GIVEN** 一次未注入 tracer 的组合根装配
- **WHEN** `build_runtime` 完成装配并结束一条 trace
- **THEN** 事件以 JSONL 落盘到 `$CORE_STATE_DIR` 的 trace 文件，且导出经缓冲 / 退避重试包装（导出失败降级不阻塞主循环）

#### Scenario: 注入的 tracer 优先
- **GIVEN** 调用方显式注入一个 tracer
- **WHEN** `build_runtime` 装配
- **THEN** 使用注入的 tracer（SHALL NOT 被缺省生产导出器覆盖）
