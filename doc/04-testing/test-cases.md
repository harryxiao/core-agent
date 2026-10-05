# 测试设计：测试用例（Test Cases）

> 用例编号与需求、规格 Scenarios 同号，实现"规格 → 需求 → 测试"全链路可追踪。

---

## 1. 插件注册与组合（TC-PLG）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PLG-01 | CORE-PLG-R1 | 注册一个新插件，不改核心代码 | 注册表可查到，可直接调用 |
| TC-PLG-02 | CORE-PLG-R2 | 执行写操作 → 记录 undo → 回滚 | 副作用完全撤销 |
| TC-PLG-03 | CORE-PLG-R3 | 声明 coeffect 但环境未注入 | 返回 `COEFFECT_MISSING`，拒绝执行 |
| TC-PLG-04 | CORE-PLG-R4 | 运行中 load/unload 插件 | 主循环不中断，切换生效 |
| TC-PLG-05 | CORE-PLG-R2 | 卸载前未确认的 undo | 自动回滚后再卸载 |

## 2. 智能体循环（TC-LOOP）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-LOOP-01 | CORE-LOOP-R1 | 发起一轮对话 | 四阶段全部执行，末了写记忆 |
| TC-LOOP-02 | CORE-LOOP-R2 | 替换 loop 插件为 Plan-Execute | 行为切换，无需改核心 |
| TC-LOOP-03 | CORE-LOOP-R3 | action 失败 | 该轮 undo 回滚，失败写记忆 |
| TC-LOOP-04 | CORE-LOOP-R4 | 触发不可逆操作 | ask_user 确认门触发 |
| TC-LOOP-05 | CORE-LOOP-R4 | 确认门拒绝 | 改写安全动作或终止 |

## 3. 分层记忆（TC-MEM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-MEM-01 | CORE-MEM-R1 | 写入 L2 事实 | 可检索到，归属正确层 |
| TC-MEM-02 | CORE-MEM-R2 | 超 budget 检索 | 按优先级截断，≤ budget |
| TC-MEM-03 | CORE-MEM-R3 | L3 技能结晶为插件 | 注册为代码，undo 可回滚 |
| TC-MEM-04 | CORE-MEM-R3 | 插件溶解回 L3 | 语义+教训回写，历史不丢 |
| TC-MEM-05 | CORE-MEM-R4 | 切换记忆后端 | 同一接口，行为一致 |

## 4. 工具使用（TC-TOOL）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-TOOL-01 | CORE-TOOL-R1 | 枚举 active tools | ≥ 9 个原子工具 |
| TC-TOOL-02 | CORE-TOOL-R2 | 传非法参数 | 返回结构化 `INVALID_ARGS` |
| TC-TOOL-03 | CORE-TOOL-R3 | file_write 后回滚 | 内容恢复原样 |
| TC-TOOL-04 | CORE-TOOL-R4 | 工具超时 | 中止返回 `TIMEOUT`，loop 不崩 |
| TC-TOOL-05 | CORE-TOOL-R3 | 不可逆工具未确认 | 阻断，`IRREVERSIBLE_BLOCKED` |

## 5. MCP 集成（TC-MCP）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-MCP-01 | CORE-MCP-R1 | 连接示例 MCP server | 发现并调用其 tools |
| TC-MCP-02 | CORE-MCP-R2 | 读取 resource/prompt | 纳入上下文 |
| TC-MCP-03 | CORE-MCP-R3 | 调用远程写工具 | 受确认门 + 可逆追踪约束 |
| TC-MCP-04 | CORE-MCP-R4 | stdio 与 http 传输 | 两种均可连通 |
| TC-MCP-05 | —— | server 掉线 | `DEGRADED`，不阻塞其他工具 |
| TC-MCP-06 | mcp「传输层抽象与依赖注入隔离」 | 经 `transport_factory` 注入替身传输（`FakeTransport`） | `MCPClient` 及调用方零改动切换传输实现（锚点：`tests/test_mcp.py`；生产 stdio 分派见 `test_mcp_stdio.py`，http/streamable-http 未接 → C 类） |
| TC-MCP-07 | mcp「MCP Server 模式」 | stdio 本地挂载：外部客户端逐条发 `initialize` / `tools/list` / `tools/call` | 按各自 `id` 应答、无 `id` 通知不应答、EOF 退出；未知方法与提供者异常隔离为错误应答且**循环继续**（锚点：`tests/test_mcp_server_stdio.py::test_initialize_handshake_returns_protocol_version`、`::test_notification_without_id_is_not_answered`、`::test_unknown_method_returns_jsonrpc_error_and_loop_continues`、`::test_handler_exception_is_isolated`） |
| TC-MCP-08 | mcp「工具暴露与白名单」 | 暴露面命名空间 / 白名单两种写法 / 默认最小暴露 | 对外名 `core.<tool_id>`；白名单接受裸名与带前缀；写工具默认不暴露；未暴露调用 `PERMISSION_DENIED` 且不执行；`mcp.*` 远程工具**不**被二级代理暴露（锚点：`::test_exposed_names_are_core_namespaced`、`::test_whitelist_accepts_namespaced_form`、`::test_unexposed_tool_call_is_denied_and_not_executed`、`::test_remote_tools_are_not_exposed_second_hand`） |
| TC-MCP-09 | mcp「MCP Server 模式」 | **端到端**：用本仓 `MCPClient`（`StdioTransport`）拉起 `core-agent mcp serve` 子进程 | 握手 → 发现（含 `core.tools.file_read`、不含写工具）→ 调用真读文件 → 越权拒绝；非 stdio 传输明确拒绝（锚点：`::test_own_client_discovers_and_calls_own_server`、`::test_non_stdio_transport_is_refused`） |
| TC-MCP-10 | mcp「MCP Server 安装与移除」 | **端到端**：`mcp add` 真子进程拉起 stdio echo server → 落盘 → 跨进程 `mcp list` 可见 → 装配期注册 `mcp.<名>.echo` → `mcp remove` 摘除；不可达端点告警跳过且不落盘（锚点：`::test_cli_add_list_remove_roundtrip`、`::test_assembly_registers_remote_tools`、`::test_unreachable_endpoint_degrades_without_blocking`、`::test_cli_add_unreachable_does_not_persist`） |

| TC-MCP-11 | mcp「标准 MCP 互操作（双向）」 | client 携标准三元组握手；解析标准容器键 + **厂商扩展字段被忽略**；`isError` 归一（结构化错误码还原）；server `tools/list`/`tools/call` 的字面应答帧为标准信封；裸形状/旧式应答仍可解析（锚点：`tests/test_mcp_standard_envelope.py`）。**真机**：`core-agent mcp add "claude mcp serve"` 成功（20 工具）；`claude mcp list` 对本 server 报 `✔ Connected` | 双向皆通，旧形状不破裂 |
| TC-MCP-12 | mcp「工具暴露与白名单」 | 未配置白名单时默认暴露面 | 仅纯本地只读（`file_read` + 未声明 coeffect 的 `list`）；`web_fetch`（`network:outbound`）/ `delegate`（`agent:delegate`）**不出**；白名单仍可开放；默认面外调用 `PERMISSION_DENIED`（锚点：`tests/test_mcp_default_exposure.py`、`test_phase13.py` 默认面断言） | 跨边界工具默认不暴露 |
| TC-MCP-13 | mcp「调用转发与错误隔离」 | 远端 JSON-RPC 错误码映射 | `tools/call` 的协议层错误（任意码，如 `-32603 "Tool X not found"`）→ `MCP_TOOL_NOT_FOUND`；其余方法 `-32700/-32600/-32601/-32602` → `MCP_PROTOCOL_MISMATCH`、`-32603`/未知码 → `MCP_UNAVAILABLE`；原始码保留于文本（锚点：`tests/test_mcp_stdio.py` 真子进程端到端 + `map_remote_error` 表驱动） | 错误语义不丢失 |

## 6. 进化引擎（TC-EVO）

| 用例 | 对应需求 | 步骤 | 期望 |
| TC-EVO-01 | CORE-EVO-R1 | 喂轨迹跑一轮进化 | 四阶段闭环执行 |
| TC-EVO-02 | CORE-EVO-R2 | 注入单插件缺陷 | 诊断归因到该插件 |
| TC-EVO-03 | CORE-EVO-R3 | 候选过门 | 产出世代化不可变产物 |
| TC-EVO-04 | CORE-EVO-R4 | 候选在留出集退化 | 自动回滚，不发布 |
| TC-EVO-05 | CORE-EVO-R3 | 候选不过验证门 | 丢弃 + 教训写记忆 |
| TC-EVO-06 | evolution/spec.md「自动课程」+「冷路径驱动」 | 冷路径开课：本批失败按插件归因（含并列、含已发布观察期目标） | 课程产出**有界、有序、确定**的议程（失败数降序 → 已处理降权 → `plugin_id` 升序），权重恒 < 1.0 作诊断**先验** ⇒ **只破并列、不压证据**；`evolve run --goal X` 时 X **直接采用**（不被证据改写，仍走四阶段 + 人工 `confirm`）（锚点：`tests/test_evolution_curriculum.py`、`tests/test_evolution.py::test_diagnoser_prior_breaks_tie`、`::test_prior_never_overrides_evidence`、`::test_worker_auto_agenda_breaks_tie`、`::test_worker_explicit_goal_overrides_evidence`、`tests/test_entry.py::test_evolve_run_forwards_explicit_goal`） |

## 7. 权限与审批管控（TC-PERM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PERM-01 | CORE-PERM-R1 | 触发高危操作 | 默认拦截 `DENY_BY_DEFAULT` |
| TC-PERM-02 | CORE-PERM-R2 | 提交审批 → 超时未批 | 默认拒绝，审计归档 |
| TC-PERM-03 | CORE-PERM-R3 | 沙箱内执行异常 | fail-closed，沙箱自动销毁 |
| TC-PERM-04 | CORE-PERM-R4 | coeffect 越权调用 | 拒绝执行，记录越权 |
| TC-PERM-05 | permission/spec.md「沙箱执行颗粒度」 | `config.yaml` 写 `permission.sandbox.host_allowlist: mcp.example.com`，启动装配后对 http 端点发起出站 | 白名单经 `ConfigSpec` 单一真源三面解析（CLI flag / env / config.yaml，优先级链一致），组合根注入 `SandboxPolicy`（`MCPClient` 与 `SandboxManager` 共用同一实例）；白名单内越过守卫、白名单外 `PERMISSION_DENIED`（锚点：`tests/test_permission_sandbox_config.py::test_build_runtime_injects_configured_allowlist` / `::test_configured_allowlist_governs_production_transport` / `::test_yaml_csv_is_trimmed_and_deduped` / `::test_env_overrides_yaml` / `::test_cli_overrides_env_and_yaml`） |
| TC-PERM-06 | permission/spec.md「沙箱执行颗粒度」 | 未声明 `permission.sandbox.host_allowlist` 启动装配，对任意主机发起 http 出站 | 白名单为空白名单 ⇒ **全拒**（fail-closed 安全默认不因新增配置项松动）（锚点：`tests/test_permission_sandbox_config.py::test_default_is_empty_fail_closed` / `::test_unconfigured_production_policy_denies_all_outbound`） |
| TC-PERM-07 | permission/spec.md「沙箱执行颗粒度」 | 白名单条目带 scheme（`https://a.example.com`）/ 端口（`a.example.com:443`）/ 路径（`a.example.com/v1`）/ 内部空白，或取值为非字符串（`123`） | 校验期**阻断启动**并指明键名与合法形态，**不**静默忽略条目（`check_outbound` 实参不含 scheme/端口/路径 ⇒ 此类条目永不匹配）（锚点：`tests/test_permission_sandbox_config.py::test_invalid_entries_block_startup` / `::test_non_string_value_blocks_startup` / `::test_invalid_value_does_not_silently_fall_back`） |

## 8. 任务编排（TC-ORCH）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-ORCH-01 | CORE-ORCH-R1 | 非法状态转移 | 拒绝并报 `ILLEGAL_TRANSITION` |
| TC-ORCH-02 | CORE-ORCH-R2 | 有依赖的子任务拆解 | 按拓扑序执行，无环 |
| TC-ORCH-03 | CORE-ORCH-R3 | 任务交接给子 Agent | 上下文完整传递（TaskHandoff） |
| TC-ORCH-04 | CORE-ORCH-R4 | 长任务中断后恢复 | 从断点续跑，不重头 |

## 9. 可观测性（TC-OBS）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-OBS-01 | CORE-OBS-R1 | 跑一轮 loop | 产出结构化 JSONL，无密钥明文 |
| TC-OBS-02 | CORE-OBS-R2 | 采样多轮 | 完成率/token/错误率指标可查 |
| TC-OBS-03 | CORE-OBS-R3 | 按 trace_id 重放 | 单轮可复现 |
| TC-OBS-04 | CORE-OBS-R4 | 进化经验采集 | 数据源来自统一遥测流 |
| TC-OBS-05 | CORE-OBS-R1 | 未注入 tracer 的组合根装配并结束一条 trace | 事件 JSONL 落 `$CORE_STATE_DIR`，经缓冲包装，导出失败不阻塞 |

## 10. 约束与容错（TC-CONS）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-CONS-01 | CORE-CONS-R1 | 传非法输入 | 前置校验拦截，输出结构化错误 |
| TC-CONS-02 | CORE-CONS-R2 | 连续失败触发熔断 | 熔断/降级，恢复后自动重试 |
| TC-CONS-03 | CORE-CONS-R3 | 上下文超预算 | 压缩中间件裁剪至 ≤ budget |
| TC-CONS-04 | CORE-CONS-R4 | 调整中间件顺序 | 执行顺序随之变化且可观测 |
| TC-CONS-06 | CORE-CONS-R2 | 配置 `constraints.failure_threshold: 2` 后驱动生产链 | 第 2 次执行失败即熔断；第 3 次调用被拒（回「熔断中（CIRCUIT_OPEN）」）、**工具 handler 不再被调用**（锚点：`tests/test_constraints_config.py::test_configured_threshold_drives_production_breaker`） |
| TC-CONS-07 | CORE-CONS-R2 | `constraints.failure_threshold` / `cooldown_s` 取非法值（`0`/`-1`/`2.5`/`abc`/负数冷却） | **校验期拒绝并阻断启动**（`ConfigurationError`），**不**静默兜底为缺省值（锚点：`tests/test_constraints_config.py::test_invalid_threshold_blocks_startup` / `::test_invalid_cooldown_blocks_startup` / `::test_invalid_value_does_not_silently_fall_back`） |
| TC-CONS-05 | CORE-CONS-R1 | 模型输出无法解析为动作 | **不执行工具**，本轮以解析失败终止 reply 收尾、失败原因随观察回灌下一轮（锚点：`tests/test_phase13.py::test_llm_planner_parse_failure_error_code` / `::test_planner_native_tool_call_bad_arguments`；生产实现为动作感知的 `LLMPlanner._parse`，**非** `Validator.parse_output` —— 见 `constraints-interface.md` §2） |

## 11. 技能封装（TC-SKILL）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-SKILL-01 | CORE-SKILL-R1 | 前置条件不满足调用技能 | 拒绝并提示缺失条件 |
| TC-SKILL-02 | CORE-SKILL-R2 | 灰度发布新版本技能 | 按比例路由，退化自动回退 |
| TC-SKILL-03 | CORE-SKILL-R3 | 相似任务路由 | Top-K 命中最佳技能 |
| TC-SKILL-04 | CORE-SKILL-R4 | evolution 结晶产物入库 | 唯一进入技能库，走评审 |

## 12. 上下文工程（TC-CTX）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-CTX-01 | CORE-CTX-R1 | 超预算上下文装配 | 裁剪后 ≤ token 预算 |
| TC-CTX-02 | CORE-CTX-R2 | 索引失效后 fetch | hash 校验触发重建，按需加载 |
| TC-CTX-03 | CORE-CTX-R3 | 多轮对话 | 关键信息自动压实并写回记忆 |
| TC-CTX-04 | CORE-CTX-R4 | 千页文档 | 仅呈现目录索引，细节按需跳转 |

## 13. UI 界面（TC-UI）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-UI-01 | CORE-UI-R1 | CLI 模式发起会话 | 经同一后端 API 层驱动 loop，行为与 Web 一致 |
| TC-UI-02 | CORE-UI-R1 | 在 Web 配置 LLM API 后切 CLI | 配置生效，无需重复配置 |
| TC-UI-03 | CORE-UI-R2 | Web/桌面设置页填 provider/endpoint/key/base URL 并保存 | 写入后端配置源立即生效，密钥不进前端日志 |
| TC-UI-04 | CORE-UI-R2 | 保存 API key 后持久化配置 | key 存本地受保护配置文件，不入库、不进遥测 |
| TC-UI-05 | CORE-UI-R3 | 内核产生分片回复 | 终端增量渲染，不整块刷新 |
| TC-UI-06 | CORE-UI-R3 | 渲染含长输出/工具结果的回复 | 长内容默认折叠，可展开/收起 |
| TC-UI-07 | CORE-UI-R4 | 启动 Web 模式，浏览器打开服务地址 | 加载 SPA，实时流式回复（SSE） |
| TC-UI-08 | CORE-UI-R5 | 安装桌面安装包并启动应用 | 桌面壳自动拉起本地后端，加载同一 SPA 可会话 |
| TC-UI-09 | CORE-UI-R6 | 同版本 Web/桌面打开同一功能页面 | 界面与交互完全一致 |

## 14. IM 网关（TC-IM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-IM-01 | CORE-IM-R1 | 实现新平台 Provider 适配器并注册 | loop/工具/记忆/权限链路零改动复用 |
| TC-IM-02 | CORE-IM-R2 | 用户在 IM 向机器人发消息 | 同一 loop 执行并回推结果 |
| TC-IM-03 | CORE-IM-R2 | 同一用户/群多轮追问 | 按会话/群保持上下文，不重复询问 |
| TC-IM-04 | CORE-IM-R3 | 配置 Telegram/Discord/飞书官方通道凭证与回调 | 消息经官方通道进网关并回推 |
| TC-IM-05 | CORE-IM-R3 | 评估个人微信号直接接入 | 因封号风险拒绝，改用企业微信/公众号 |
| TC-IM-06 | CORE-IM-R4 | 白名单用户发消息 | 正常进入 loop 执行 |
| TC-IM-07 | CORE-IM-R4 | 非白名单用户发消息 | 拒绝，返回拒绝提示（不暴露内部信息） |
| TC-IM-08 | CORE-IM-R5 | IM 触发删除/执行等高危工具 | IM 内二次确认，确认后才执行 |
| TC-IM-09 | CORE-IM-R5 | IM 用户完成任意调用 | 审计标注来源 `im:<platform>:<user_id>` |
| TC-IM-10 | CORE-IM-R6 | 多平台多用户并发交互 | 会话状态互不串扰 |
| TC-IM-11 | CORE-IM-R6 | 某平台长连接断开 | 该平台会话隔离重连，不影响其他平台/主循环 |

## 15. LLM Provider（TC-LLM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-LLM-01 | CORE-LLM-R1 | 内核经 LLMProvider 接口发起请求 | 面向统一请求/响应模型，不感知供应商 |
| TC-LLM-02 | CORE-LLM-R2 | 配置某三方模型 API Key + URL 后调用 | 自动解析路由到对应 provider，返回归一化结果 |
| TC-LLM-03 | CORE-LLM-R3 | 注册自研 Provider 替换默认实现 | 内核 loop 及调用方零改动切换 |
| TC-LLM-04 | CORE-LLM-R4 | 底层返回超时/限流/鉴权/网络异常 | 统一映射为领域异常，不泄漏原始错误结构 |
| TC-LLM-05 | CORE-LLM-R5 | 任意一次模型调用结束 | 审计标注 provider/model 与结果，可追溯 |
| TC-LLM-06 | CORE-LLM-R6 | 瞬时错误 / 超时 / 主模型不可用 / 流中断 / 连接复用 | 退避重试至成功、耗尽抛归一化异常、非可重试错误不重试；超时不挂起调用方；降级切备用模型（审计记实际成功模型）；断流先给已收内容再抛（change `0060`）；同 origin 连续调用复用一条 keep-alive 连接、连接失效自动重建（change `0066`，`tests/test_llm_provider_reuse.py`） |

## 16. 非功能（TC-NFR）

| 用例 | 对应 NFR | 期望 |
|---|---|---|
| TC-NFR-OBS1 | OBS1 | 100% 写操作有审计记录 |
| TC-NFR-OBS2 | OBS2 | 单轮 trace_id 可复现 |
| TC-NFR-PERF1~3 | PERF1~3 | 满足延迟/插拔目标 |
| TC-NFR-SEC1 | SEC1 | 日志/记忆无密钥明文 |
| TC-NFR-SEC2/3 | SEC2/3 | 不可逆操作必确认，爆炸半径可控 |
| TC-NFR-REL1 | REL1 | 进化回滚成功率 100% |
| TC-NFR-PORT1 | PORT1 | Python 3.11+，跨 Linux/macOS/Windows |
| TC-NFR-PORT2 | PORT2 | 兼容 MCP 最新稳定版 |

## 17. 组合与分发（TC-COMP）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-COMP-01 | CORE-COMP-R1 | 用户或部署按名选用某 profile | 解析出该 profile 声明的完整插件集 |
| TC-COMP-02 | CORE-COMP-R2 | 将已结晶技能打包为 bundle | 其他部署引入后复用同一批技能，无需重新结晶 |
| TC-COMP-03 | CORE-COMP-R3 | 提供 patch.yml 声明覆盖项 | 在 profile 组合结果上应用覆盖，原 profile/bundle 不变 |
| TC-COMP-04 | CORE-COMP-R4 | profile 层叠多个 bundle 并叠加 patch.yml 解析 | 按确定顺序合并，同名项由 patch.yml 覆盖，可回退到覆盖前状态 |

## 18. 分布式协作（TC-DIST）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-DIST-01 | CORE-DIST-R1 | 经 A2A Client 向外部 Agent 的 AgentCard 接口发送任务 | 任务被委派，外部 Agent 执行并流式/推送回报进度 |
| TC-DIST-02 | CORE-DIST-R1 | 外部 Agent 经 A2A Server 接口发起调用 | Core-Agent 接受任务并执行，结果经 A2A 协议返回 |
| TC-DIST-03 | CORE-DIST-R2 | 对等 Agent 获取并解析 Core-Agent 的 AgentCard | 得到能力/技能/接口清单，据此协商交互方式 |
| TC-DIST-04 | CORE-DIST-R2 | Core-Agent 验证对等 Agent 的已签名 AgentCard | 有效则接受身份与能力声明，无效则拒绝 |
| TC-DIST-05 | CORE-DIST-R3 | A2A 交互未显式指定绑定 | 以 JSON-RPC 2.0 over HTTP(S) 承载，流式走 SSE |
| TC-DIST-06 | CORE-DIST-R3 | 对等 Agent 仅支持 gRPC 或 REST | 按对端声明的绑定完成同套核心操作 |
| TC-DIST-07 | CORE-DIST-R4 | 云端与嵌入式间下发敏感指令建立连接 | 优先 mTLS 双向认证，仅授予最小权限 scope |
| TC-DIST-08 | CORE-DIST-R4 | 外部 Agent 调用超出已授权 scope | 拒绝并记录审计日志（来源 a2a:<peer>） |
| TC-DIST-09 | CORE-DIST-R5 | 云端控制面委派任务，执行面在 PC 本机 | 云端只承载协调与进度，本机执行结果回传 |
| TC-DIST-10 | CORE-DIST-R5 | 移动终端经 A2A 瘦客户端发现并委派任务 | 移动端仅发现/委派/订阅进度/展示，不承载重型执行 |
| TC-DIST-11 | CORE-DIST-R6 | 两设备 NAT 打洞成功 | 走直连传输；失败回退 relay，上层 A2A 行为不变 |
| TC-DIST-12 | CORE-DIST-R7 | A2A Server 收到需底层工具完成的任务 | 经 MCP 调用工具/数据源完成，再经 A2A 回传 |

## 19. 检索增强生成（TC-RAG）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-RAG-01 | CORE-RAG-R1 | 知识文档完成 embedding 后写入向量库 | 向量落盘于本地 SQLite 向量扩展，无需独立服务或外部向量数据库 |
| TC-RAG-02 | CORE-RAG-R2 | 导入一份知识文档经摄取管线处理 | 文档被分块、逐块生成 embedding 并建立向量索引，可被检索 |
| TC-RAG-03 | CORE-RAG-R2 | 源文档变更导致 hash 不一致 | 触发受影响块增量重建，期间该文档检索降级为旧索引 |
| TC-RAG-04 | CORE-RAG-R3 | 一段文本经本地 embedding 生成 | 由本地 sentence-transformers + BGE 推理完成，不请求外部 embedding API |
| TC-RAG-05 | CORE-RAG-R3 | 经 llm-provider 归一化入口请求远端 embedding 模型 | 无缝切换到远端模型，检索与调用方无感知 |
| TC-RAG-06 | CORE-RAG-R4 | 执行语义检索 | 返回按向量相似度排序的 top-k 片段及相关度得分 |
| TC-RAG-07 | CORE-RAG-R5 | 将检索片段注入生成请求 | 片段经 context 装配器按预算裁剪后注入提示词，由 llm-provider 生成 |
| TC-RAG-08 | CORE-RAG-R5 | 语义检索无相关片段时构建生成请求 | 降级为纯 LLM 生成，不阻断流程 |
| TC-RAG-09 | CORE-RAG-R6 | 一次查询同时涉及知识文档与代码结构 | 文档语义检索走 RAG，代码结构理解走 codebase-memory-mcp，互不重叠 |
| TC-RAG-10 | rag「存储与 Embedding 依赖注入隔离」 | 以替身实现注入 `Embedder` / `VectorStore`（`_FixedEmbedder` / `InMemoryVectorStore`） | `Retriever` 及调用方零改动（锚点：`tests/test_rag.py::test_retriever_delegates_to_store`）；**替换向量库**一侧仅单实现（生产 sqlite-vec 未接 → C 类），登记为半覆盖 |

---

## 20. 版本控制（TC-GIT）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-GIT-01 | CORE-GIT-R1 | 工作区有改动时执行 commit | 改动提交到本地仓库并生成 commit 记录 |
| TC-GIT-02 | CORE-GIT-R1 | 存在多分支时执行 checkout/merge | 工作区切换/合并完成，冲突时明确报告冲突点 |
| TC-GIT-03 | CORE-GIT-R2 | 试图修改 .git 内部文件 | 默认拒绝并提示风险，经显式确认或审批后才允许 |
| TC-GIT-04 | CORE-GIT-R2 | Git 操作中途失败 | 工作区回滚到操作前状态，不处于半提交/半合并状态 |
| TC-GIT-05 | CORE-GIT-R3 | 远程操作提供凭据 | 凭据经 keychain 存储，配置与日志不出现明文凭据 |
| TC-GIT-06 | CORE-GIT-R4 | 请求 force-push 或删除远程分支 | 触发 permission 审批，通过才执行，拒绝则阻断并审计 |
| TC-GIT-07 | CORE-GIT-R5 | 远程操作因网络缓慢超过超时阈值 | 中止操作并返回超时错误，不无限挂起 |
| TC-GIT-08 | CORE-GIT-R5 | 远程操作认证失败（凭据过期/无权限） | 明确报错并提示原因，不泄露凭据与私有仓库地址 |
| TC-GIT-09 | CORE-GIT-R5 | 远程操作因网络抖动中断且可重试 | 按指数退避自动重试，达上限后失败并保持工作区一致 |
| TC-GIT-10 | CORE-GIT-R5 | 远程操作结束（完成或失败） | 释放底层连接资源，避免连接泄漏 |
| TC-GIT-11 | git「GitClient 抽象接口与依赖注入隔离」 | 以替身后端注入（`GitClient(backend=FakeBackend())`） | `GitClient` 及内核 loop 零改动切换底层 git 实现（锚点：`tests/test_git.py`；生产 `build_backend()` 见 `src/core/git/backend.py:50`） |
| TC-GIT-12 | git「GitClient 抽象接口与依赖注入隔离」 | 未注入后端，缺省工厂取后端并在**真实临时仓库**执行 init/commit/status/log/diff/branch/checkout/merge/stash | 全程成功；缺省后端为 stdlib `subprocess` 适配器（零三方依赖）（锚点：`tests/test_git_subprocess.py`；`tests/test_git.py::test_default_backend_is_subprocess_adapter`） |
| TC-GIT-13 | git「GitClient 抽象接口与依赖注入隔离」 | 非仓库目录下执行子命令 / 合并产生冲突 | 抛 `GitError(GIT_COMMAND_FAILED)` 且文本**不含** stderr 原文与路径；冲突走 `MergeResult(merged=False, conflict_files=[...])`（锚点：`tests/test_git_subprocess.py::test_command_failure_normalized_and_no_stderr_echo` / `::test_merge_conflict_reports_files`） |

---

## 21. 部署与托管（TC-DEP）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-DEP-01 | CORE-DEP-R1 | 已安装 Core-Agent 与依赖的宿主机执行启动引导 | 以自托管运行环境启动并对外提供服务，配置从声明式配置读取 |
| TC-DEP-02 | CORE-DEP-R1 | 一套环境配置迁移到另一台宿主机 | 复用同一环境配置完成装配与启动，无需修改业务逻辑 |
| TC-DEP-03 | CORE-DEP-R2 | 发布新版本并执行升级 | 完成滚动升级；失败自动回滚到旧版本，服务不中断或快速恢复 |
| TC-DEP-04 | CORE-DEP-R3 | 探活发现实例异常或不可用 | 触发告警或自动恢复，启动/停止/重启生命周期操作正常 |
| TC-DEP-05 | CORE-DEP-R4 | 将本地自托管的 Core-Agent 部署到自有云平台（BYOC） | 复用同一环境配置与部署抽象运行，自托管与云托管行为一致 |
| TC-DEP-06 | CORE-DEP-R5 | 多个 Web/Desktop 客户端经统一 API 连接常驻 Harness Host | 各客户端建立独立会话并可并发，互不串扰 |
| TC-DEP-07 | CORE-DEP-R5 | 任一客户端经统一接入端点连接 Host | 建立会话，无需各自拉起后端进程 |
| TC-DEP-08 | CORE-DEP-R6 | 已接入客户端网络断线或异常退出 | Host 检测后清理该客户端会话与连接资源，不影响其他客户端 |
| TC-DEP-09 | CORE-DEP-R6 | 客户端长时间无活动超过超时阈值 | 判定连接失效并释放会话与连接资源，避免资源泄漏 |

---

## 22. 核心画像（TC-PROF）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PROF-01 | CORE-PROF-R1 | 主目录存在 `~/.core/Core.md` 时启动 | 读取并加载该文件的人格、宪法与全局规则预设 |
| TC-PROF-02 | CORE-PROF-R1 | 项目根目录存在 `Core.md` 时载入项目 | 读取并加载该文件的项目信息预设 |
| TC-PROF-03 | CORE-PROF-R2 | 装配 LoopContext 时注入「宪法与全局规则」分区 | 作为 constitution:v1 coeffect 注入，作为必保约束参与执行 |
| TC-PROF-04 | CORE-PROF-R2 | 处理「人格」分区 | 落入 L0 记忆层，作为元策略与人格预设参与决策 |
| TC-PROF-05 | CORE-PROF-R3 | cwd 位于项目子目录且项目根存在 Core.md | 向上逐级查找并命中最靠近的项目根 Core.md，注入项目信息 |
| TC-PROF-06 | CORE-PROF-R3 | cwd 向上到文件系统根均无 Core.md | 不注入项目级内容，仅用全局级预设且不报错 |
| TC-PROF-07 | CORE-PROF-R4 | 全局级与项目级对同一配置项给出不同值 | 项目级值生效，覆盖全局级值 |
| TC-PROF-08 | CORE-PROF-R4 | 仓库同时存在 CLAUDE.md 与 Core.md | 仅读取 Core.md 作为自身预设，不加载 CLAUDE.md，互不干扰 |
| TC-PROF-09 | CORE-PROF-R5 | Core.md 不存在时执行读取 | 静默降级，按无该级别预设继续运行，不报错 |
| TC-PROF-10 | CORE-PROF-R5 | Core.md 分区标记格式非法 | 记录告警并跳过非法分区，加载其余合法分区，不阻断启动或载入 |
| TC-PROF-11 | CORE-PROF-R6 | 参照题词规范编写「宪法与全局规则」分区条目 | 每条以命令式「必须/禁止」表述且可判定真伪，可直接注入执行 |
| TC-PROF-12 | CORE-PROF-R6 | 参照题词规范填写人格/项目信息分区 | 人格按身份/工作风格/沟通风格/决策偏好/边界意识结构化，篇幅受控 |
| TC-PROF-13 | CORE-PROF-R7 | 参照全局级题词模板新建 `~/.core/Core.md` | 产出含「宪法与全局规则」「人格」两分区，分别落 coeffect 与 L0 |
| TC-PROF-14 | CORE-PROF-R7 | 参照项目级题词模板新建项目 `Core.md` | 产出含「项目信息」分区，落入 ContextEngine 注入上下文 |

## 23. 技能市场（TC-SKILLHUB）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-SKILLHUB-01 | CORE-SKH-R1 | 调用 SkillHubClient 按关键字搜索市场 | 返回按匹配度排序的 Top-K 技能元数据（不拉取完整技能体） |
| TC-SKILLHUB-02 | CORE-SKH-R2 | 下载签名校验通过的技能 | 以 draft 状态注册到 SkillLibrary，不自动启用 |
| TC-SKILLHUB-03 | CORE-SKH-R4 | 下载签名校验失败的技能 | 拒绝下载并返回 SIGNATURE_INVALID |
| TC-SKILLHUB-04 | CORE-SKH-R3 | 发布技能并经审核 approved | 状态 published，VersionManager 版本 v1→v2 |
| TC-SKILLHUB-05 | CORE-SKH-R3 | 发布技能被审核 rejected | 状态回退，允许修改后重传 |
| TC-SKILLHUB-06 | CORE-SKH-R5 | 指定 source 路由到市场源 | 路由到对应源；源不健康回退官方源；源不存在拒绝路由 |
| TC-SKILLHUB-07 | CORE-SKH-R1 | CLI `skill search <query>`（注入内存市场索引） | 输出该技能版本化元数据；空市场如实报「未找到」、源不健康退出码 1（锚点：`tests/test_skillhub_cli.py`） |
| TC-SKILLHUB-08 | CORE-SKH-R2 | CLI `skill install <skill_id>`（签名有效 / 签名被篡改 / 未接市场 fetcher） | 有效 ⇒ 落 draft 且**重开技能库可见**；篡改 ⇒ 拒绝、退出码 1、不落盘；未接 ⇒ 如实报错不静默成功 |

## 24. 配置管理（TC-CONF）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-CONF-01 | CORE-CFG-R3 | 配置未声明 `features` 段（或缺省）启动装配 | 门控名单内模块（`pet`/`beast`/`evolution`）照常装配 —— 缺省开、与门控落地前行为一致（锚点：`tests/test_feature_gating.py::test_default_assembles_every_gatable_module`） |
| TC-CONF-02 | CORE-CFG-R3 | `features.pet: false`（或 `beast`/`evolution`）启动装配 | 该模块**完全不装配**：不构造实例、不产生装配期副作用（`beast` 不注册神通、`pet` **不读** `pets.json`）、loop 冷路径置空（Evolution），入口拒绝（锚点：同文件 `test_disabled_*` 组） |
| TC-CONF-03 | CORE-CFG-R3 | `features.pet` 缺省开而 `pet.enabled=false` 时调用 `pet` CLI | 模块**已装配**（装配面非空），CLI 仍报「宠物模式未启用」—— feature flag 只管装配、不改二级启用开关（锚点：既有 `tests/test_entry.py::test_pet_disabled_by_default` + `tests/test_feature_gating.py::test_cli_refuses_disabled_module[pet]`） |
| TC-CONF-04 | configuration/spec.md「宠物模式配置」 | `config.yaml` 写 `pet.enabled: true` 且 `pet.persons_dir` 指向含 persona 的目录，调 `pet list` | 前置判定**采信 yaml 层**：不报「宠物模式未启用」，persona 从 yaml 目录加载（此前只解析 CLI/env，yaml 被静默忽略 —— 账本 E21）（锚点：`tests/test_entry.py::test_pet_yaml_admits_and_honors_persons_dir`） |
| TC-CONF-05 | configuration/spec.md「宠物模式配置」 | 同一键在 CLI / env / yaml 三层同时有值，以及 `--config` 指向不存在的文件 | 优先级链 CLI flag > env > config.yaml > 缺省逐层压过；缺文件按「无 yaml 层」处理（不抛 `ConfigurationError`、不阻断前置判定）（锚点：`tests/test_configuration.py::test_config_value_priority_chain` / `::test_config_value_falls_back_to_default` / `::test_config_value_tolerates_missing_file` / `::test_config_value_maps_key_differing_from_map_to`；`tests/test_entry.py::test_pet_env_overrides_yaml` / `::test_pet_missing_config_file_is_tolerated`） |
| TC-CONF-06 | configuration/spec.md「功能开关（feature flag）」 | yaml `features.<模块>: false`（或 env 等价写法）而以 `--feature <模块>=true` 启动；以及裸名 `--feature <模块>` | **CLI 面真的参与装配判定**：以 CLI flag 为准（此前 `--feature` 零消费、静默无效 —— 账本 E23）；裸名视为开（锚点：`tests/test_feature_flag_faces.py::test_flag_precedence_cli_over_yaml` / `::test_bare_flag_means_on` / `::test_flag_carries_explicit_value` / `::test_cli_flag_governs_assembly`（组合根端到端：`--feature beast=false` ⇒ `beast_manager is None`、`pet_manager` 非空）；语法非法 `=false`/`beast=`/空串 ⇒ `非法 --feature` 解析点拒绝：`::test_malformed_flag_is_rejected`） |
| TC-CONF-07 | configuration/spec.md「功能开关（feature flag）」（含 change `0080` 新增场景「env 面以复数前缀生效」） | yaml 将某模块写作 `off` / `no` / `0` / 加引号的 `"false"`；以及 `true` / `on` / `yes` / `1` / 原生布尔 | 假值写法**归一为关闭**（不得因 `bool("<非空字符串>")` 为真被当作开启 —— 账本 E20②）；真值写法归一为开；原生布尔行为逐位不变；env 面（`CORE_FEATURES_<模块>`）同口径归一（锚点：`tests/test_feature_flag_faces.py::test_falsy_spellings_disable` / `::test_truthy_spellings_enable` / `::test_native_bool_unchanged` / `::test_env_value_is_normalized`） |
| TC-CONF-08 | configuration/spec.md「功能开关（feature flag）」 | 某模块 feature flag 取值为 `maybe` / 空串 / 映射（yaml / env / CLI 任一面），以及运行时 `config set features.<模块>=maybe` | 校验失败并**阻断启动**，错误信息含键名与合法取值集合（不静默强转、不退化成缺省）；运行时变更走同一函数、同口径拒绝（锚点：`tests/test_feature_flag_faces.py::test_invalid_value_blocks_startup`（yaml / yaml-空值 / env / cli 四面参数化）/ `::test_apply_change_validates_feature_value`） |
| TC-CONF-09 | configuration/spec.md「配置校验与生效」（change `0085` 新增场景「features 段未知模块名仅告警」） | 注入已知模块名集合（组合根 `GATABLE_MODULES`）时，`features` 段含集合外子键（如拼错的 `peet`）；以及**未注入**时含任意自定义子键 | 注入时：校验通过、不阻断，产生**含子键名**的告警（疑似拼写、拼错将静默不生效）；未注入时：不校验子键、不告警（向后兼容）。作用域**仅** `features` 段（`llm.typo_key` 不告警）（锚点：`tests/test_configuration.py::test_unknown_feature_module_warns_but_does_not_block` / `::test_known_feature_module_produces_no_warning` / `::test_feature_module_not_checked_without_injection` / `::test_feature_warning_scope_only_features`；`tests/test_entry.py::test_config_validate_warns_on_unknown_feature_module`（入口注入已接线）） |

## 25. 宠物模式（TC-PET）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PET-01 | pet-mode「Pet Notification」 | 反馈周期命中时驱动 `wake()`（`feedback_period` 控制命中），以及未命中周期 / 无 notifier 三种情形 | 命中即经通知器投递 `report()` 产出（含宠物名/状态）；未命中静默（不刷屏）；无 notifier 时唤醒照常完成不报错（缺省兜底行为不变）（锚点：`tests/test_pet_core.py::test_wake_notifies_owner_on_feedback_cycle` / `::test_wake_stays_silent_off_feedback_cycle` / `::test_wake_without_notifier_is_silent`） |
| TC-PET-02 | pet-mode「Pet Session Runtime Wiring」 | 经组合根装配的 runtime 激活一只宠物，取其注入的通知可调用体并调用 | 通知**真的到达缺省 sink**（stderr 一行 `[pet] …`）—— 三环连通：生产者（`wake()` 收尾）/ 通道（缺省 stderr）/ 投递点（组合根收口 flush）；真实 IM 通道由宿主注入替换（锚点：`tests/test_pet_wiring.py::test_production_pet_notification_reaches_sink`） |
| TC-PET-03 | pet-mode「Exploration Toolset」+「Pet Session Runtime Wiring」（change `0081`） | 经组合根装配的 runtime 激活宠物，取其会话 loop 的工具面 | 宠物 loop 工具面**仅**白名单真实工具（缺省 `{tools.file_read}`）——未注册即结构化拒绝（fail-closed）；且会话 loop **≠** 主 loop（锚点：`tests/test_pet_wiring.py::test_pet_loop_toolset_restricted_to_explore_allowlist` / `::test_production_pet_session_gets_live_deps`） |
| TC-PET-04 | pet-mode「Pet Safety Bounds」（change `0081`） | 取宠物 loop 的 before 中间件，喂越界动作（不可逆 / 白名单外 / 半径外）与放行动作 | 越界 ⇒ **终止 Action**（本轮终止、动作不执行）且经通知器**告知主人**（含原因）；会话保持 `ACTIVE`（不楔死）；放行/终止动作原样直通（锚点：`tests/test_pet_safety_guard.py::test_out_of_bounds_action_blocked_and_owner_notified` / `::test_allowed_action_passes_through_unchanged` / `tests/test_pet_wiring.py::test_pet_out_of_bounds_action_blocked_and_notified`） |
| TC-PET-05 | pet-mode R8「A 宠物异常不影响 B 宠物」+ 账本 E28 宿主驱动（change `0083`） | 直接驱动 `PetWakeDriver`（会话替身）：逐会话唤醒 / 预期态（`PetError`）与意外异常的混合批次 / 注入 `sleep` 的节拍；以及 `pet run` 组合面（跨进程注册表恢复 → 交给驱动） | 每只宠物各唤醒一次且**顺序同注册序**；让行/退避/未激活 ⇒ `skipped`（含原因）**不影响**同批其余宠物；意外异常 ⇒ `failed` 记因并**继续**（R8）；`run` 每轮 `tick()` 后 `sleep(interval)`；`pet run --interval 0.25` 把注册表恢复的会话交给驱动并呈现「已驱动 N 只宠物」，非法间隔 ⇒ 用法错误退出 1，空注册表 ⇒ 提示 + 退出 0（锚点：`tests/test_pet_driver.py::test_tick_wakes_every_registered_pet` / `::test_tick_skips_expected_states_and_continues` / `::test_tick_isolates_unexpected_failure` / `::test_run_drives_until_interrupted` / `tests/test_entry.py::test_pet_run_drives_restored_sessions` / `::test_pet_run_rejects_bad_interval` / `::test_pet_run_without_pets_hints_and_exits_zero`） |
| TC-PET-06 | pet-mode「Periodic Feedback and Surprise」惊喜真实化（change `0086`） | 无偏好 / 有偏好两种会话调用 `surprise()`；反馈周期命中时驱动 `wake()`；注入第 2 次调用即抛错的 loop | 无偏好 ⇒ `surprise()` 返回 `None`（不谎报）、周期命中只投 `report()`；有偏好 ⇒ 经真实 loop 执行一次并回报**真实产出**、周期命中投「反馈 + 惊喜」两条；惊喜 loop 失败 ⇒ `wake()` 照常返回（fail-soft）（锚点：`tests/test_pet_core.py::test_surprise_without_preference_returns_none` / `::test_surprise_with_preference_runs_loop_and_reports_real_result` / `::test_wake_notifies_report_but_not_surprise_without_preference` / `::test_wake_reports_surprise_on_feedback_cycle_with_preference` / `::test_wake_survives_surprise_failure`） |
| TC-PET-07 | pet-mode「Background Pet Session Lifecycle」/「Pet Micro-tasks」任务一次性、空闲自治睡眠与微任务真实化（change `0087`） | 派发多任务后连续 `wake()`；清空队列后再 `wake()`；注入 `microtasks` 可调用体（含返回 `None` / 抛异常两种）观察通知面；直接测 `terminal_walk`/`system_hint` 探针 | 唤醒**消费队首**（队列 N→N-1）；队列清空 ⇒ 入睡（让行态）、后续唤醒抛 `PET_YIELDING`；`dispatch()` 新任务 ⇒ 自动唤醒；入睡前触发一次微任务、**真实产出**经通知器上报，产出为 `None` ⇒ 不上报，微任务异常 ⇒ 照常入睡（fail-soft）；`terminal_walk` 只报**条数**、不外泄历史内容，不可读/空 ⇒ `None`；`system_hint` 负载不显著 ⇒ `None`（锚点：`tests/test_pet_core.py::test_wake_consumes_dispatched_task` / `::test_wake_with_empty_queue_sleeps_and_rejects` / `::test_dispatch_auto_wakes_sleeping_pet` / `::test_idle_triggers_microtask_and_reports_real_output` / `::test_idle_without_microtask_output_stays_silent` / `::test_idle_microtask_failure_is_soft`；`tests/test_pet_microtask.py::test_terminal_walk_reports_count_only` / `::test_system_hint_silent_when_load_insignificant`） |

| TC-PET-08 | pet-mode「Pet Control Surface」控制面（change `0088`） | 直接驱动 `PetControl`：`status`/`sleep`/`wake`/`assign`/`stop` 五动词、单宠物默认寻址 / 多宠物未指定 / 未知会话 / 无宠物；并跑 CLI（`pet status|sleep|wake|assign`）与 `UIAPILayer.pet_command` 两端 | `status` 返回结构化字段（id/state/sleeping/pending/wake_count/fault）且**不含**偏好与任务正文；`sleep` 置让行态（休眠中 `PetSession.wake()` 被 `PET_YIELDING` 拒）→ `wake` 清让行态恢复；`assign` 入队并清让行态（自动唤醒）；`stop` 终止会话；多宠物未指定 ⇒ `PET_TARGET_AMBIGUOUS` 并列出 id（不猜测）、未知会话 / 无宠物 ⇒ `PET_NOT_FOUND`（CLI 退出码 1，不静默成功）；UI 面落到**同一** `PetControl`（未接 ⇒ `UI_PET_UNSET`，未知动词 ⇒ `UI_PET_UNKNOWN_VERB`）（锚点：`tests/test_pet_control.py::test_status_returns_structured_fields` / `::test_status_does_not_leak_preferences_or_tasks` / `::test_sleep_then_wake_roundtrip` / `::test_assign_enqueues_and_clears_sleeping` / `::test_stop_terminates_session` / `::test_single_pet_default_addressing` / `::test_multiple_pets_without_id_rejected` / `::test_unknown_session_rejected` / `::test_no_pets_rejected`；`tests/test_entry.py::test_pet_status_cli_shows_structured_state` / `::test_pet_sleep_and_wake_cli_roundtrip` / `::test_pet_assign_cli_switches_job` / `::test_pet_control_unknown_session_exits_1`；`tests/test_ui.py::test_ui_pet_command_delegates_to_control` / `::test_ui_pet_command_without_control_raises`） |

---

## 关联

- 测试计划：`doc/04-testing/test-plan.md`
- 需求：`doc/00-product/requirements.md`
- 规格：`doc/openspec/specs/*`
