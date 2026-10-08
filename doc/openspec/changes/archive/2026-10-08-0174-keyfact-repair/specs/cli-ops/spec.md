## MODIFIED Requirements

### Requirement: 运维命令集
系统 SHALL 提供统一的 CLI 命令集，覆盖六组：生命周期（start / stop / restart / kill）、状态（status / doctor / logs / version / help）、资产（install / uninstall / list / info）、连接（mcp add / mcp remove / mcp list）、安全（auth / permission-mode）、网关（gateway）；并 SHALL 提供一次性运维子命令：`memory maintain`（触发记忆压实与遗忘归档）、`evolve run`（强制跑一轮进化冷路径）、`rag ingest <path>`（知识文档摄取建索引）、`rag search <query>`（语义检索 top-k 片段）、`rag ask <query>`（检索片段注入生成）、`memory repair-keyfacts`（修复失效关键事实：按会话重抽 + 清理旧条目；`--dry-run` 只报告）；以上均不改变运行态、不启动常驻进程。

#### Scenario: 生命周期命令
- **GIVEN** core-agent 进程运行中
- **WHEN** 执行 start / stop / restart / kill
- **THEN** 对应启停 / 重启 / 强杀进程，运行状态一致

#### Scenario: 状态查询命令
- **GIVEN** core-agent 进程运行中
- **WHEN** 执行 status / doctor / logs / version / help
- **THEN** 返回运行状态 / 健康诊断 / 日志 / 版本 / 帮助，不改变运行态

#### Scenario: 记忆维护命令
- **GIVEN** 记忆中存在陈旧且低价值的 L2 episodic 条目
- **WHEN** 执行 `memory maintain`
- **THEN** 装配运行时后触发一次记忆维护（压实 + 遗忘归档），打印归档条数；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 关键事实修复命令
- **GIVEN** 记忆中遗留 change `0173` 修复前判据产生的失效关键事实（`ref` 非 `coeffect:` 形态且取值已被抹）
- **WHEN** 执行 `memory repair-keyfacts`
- **THEN** 装配运行时后按会话重抽该会话的关键事实（材料含已归档 L4 条目）、落库新条目并清理该会话的旧条目，
  打印识别/重抽/清理条数与备份文件路径；`--dry-run` 时只报告、不删除、不落库；
  命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 进化冷路径命令
- **GIVEN** 运行期已累积若干 trace（未达触发阈值）
- **WHEN** 执行 `evolve run`
- **THEN** 装配运行时后**强制**跑一轮进化冷路径并打印结局（诊断/提案或 `no_op`）；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 知识摄取命令
- **GIVEN** 一份本地知识文档文件
- **WHEN** 执行 `rag ingest <path> --doc-id <id>`
- **THEN** 装配运行时后摄取该文档（分块 → embedding → 落盘索引）并打印块数／文档 id；同一文档再次摄取按 `content_hash` 判定为无变更（不重复重建）；命令为一次性动作，不改变运行态、不启动常驻进程

#### Scenario: 语义检索命令
- **GIVEN** 索引中已有若干知识文档的块
- **WHEN** 执行 `rag search <query> --top-k N`
- **THEN** 打印按相似度降序的 top-k 片段（含块 id、来源文档、得分、文本节选）；**不调用生成**（无需 LLM 配置即可运行）

#### Scenario: 检索增强生成命令
- **GIVEN** 索引中已有若干知识文档的块，且装配链可为检索增强链路提供生成器
- **WHEN** 执行 `rag ask <query>`
- **THEN** 检索片段经预算裁剪注入提示词，由 llm-provider 生成并打印答案；检索无命中时降级为纯 LLM 生成（不阻断）；生成器缺失（服务层未装配生成器）时以结构化错误 `GENERATION_UNAVAILABLE` 拒绝，CLI 打印提示并以退出码 1 结束（fail-closed，不静默给空答案）

#### Scenario: 资产与连接命令
- **GIVEN** core-agent 运行中
- **WHEN** 执行 install / uninstall / list / info 与 mcp add / mcp remove / mcp list
- **THEN** 安装 / 卸载 / 列出插件或 MCP 连接，复用插件来源与安装生命周期

#### Scenario: 安全与网关命令
- **GIVEN** core-agent 运行中
- **WHEN** 执行 auth / permission-mode / gateway
- **THEN** 对应鉴权 / 设置权限模式 / 启停本地服务网关
