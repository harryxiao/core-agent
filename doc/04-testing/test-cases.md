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
| TC-LOOP-06 | loop/spec.md「错误与预算控制」（change `0098`） | 未配置 `loop` 段与 `llm.context_window` 启动；配 `llm.context_window=131072`（预留取缺省 `8192`）；配 `loop.max_rounds=3` 端到端跑 loop | 未配置 ⇒ 回落代码缺省 `(10, 65536)`（**与变更前逐位一致**）；配窗口 ⇒ `token_budget = 窗口 − 预留`（`131072-8192=122880`）；`max_rounds=3` ⇒ 真实 loop **第 3 轮**即 `LOOP_LIMIT_EXCEEDED`（组合根注入的派生值真的生效，非类缺省）（锚点：`tests/test_loop_budget_config.py::test_build_runtime_defaults_unchanged` / `::test_build_runtime_injects_derived_limits` / `::test_configured_max_rounds_drives_production_loop`） |
| TC-LOOP-07 | loop/spec.md「执行循环」（change `0101`） | 注入 `trace_observer` 跑一轮（含未达维护间隔、回调抛错、未注入三种）；轮数超限失败收尾并回放 `loop_finished` | 回调每轮调用一次并收到本轮 `trace_id`、**事件已齐**（可回放到 `loop_finished`）、**不受维护节拍节流**；抛错降级留痕（`trace_observer_failed`）不改本轮结局；未注入零副作用；失败轮 `loop_finished.module_id == "loop.default"`、正常轮为空（锚点：`tests/test_loop.py::test_trace_observer_called_once_per_run_with_trace_id` / `::test_trace_observer_sees_all_events_of_the_run` / `::test_trace_observer_not_throttled_by_maintenance_cadence` / `::test_trace_observer_failure_degrades` / `::test_trace_observer_absent_is_noop` / `::test_loop_failure_marks_module_attribution` / `::test_loop_success_has_no_module_attribution`；`tests/test_evolution_wiring.py::test_main_loop_wired_to_worker_trace_observer` / `::test_disabled_evolution_does_not_wire_trace_observer` / `::test_loop_failure_flows_to_module_attribution`） |
| TC-LOOP-08 | loop/spec.md「执行循环」（change `0103`） | 注入装配导出器的 `tracer` 跑一轮 / 连跑 12 轮 / 同时注入 `trace_observer` 在回调里回放本轮 | 开轮 `start_trace`、收尾 `end_trace` 封口：收尾后 `replay(trace_id)` **为空**、本轮事件**经导出器产出**（含 `loop_finished`）；**回调时刻**事件仍可完整回放、封口在其**之后**（顺序守护），封口后 Tracer 内存不随轮次增长；未注入 `tracer` 收尾仍正常（锚点：`tests/test_loop.py::test_loop_releases_trace_after_run` / `::test_loop_emits_to_exporter_on_seal` / `::test_loop_seals_after_trace_observer_snapshot` / `::test_loop_does_not_accumulate_events_across_runs`；`tests/test_phase13.py::test_loop_emits_trace_events`；`tests/test_evolution.py::test_worker_snapshots_events_at_callback_time` / `::test_completed_batch_window_is_bounded`；`tests/test_evolution_wiring.py::test_loop_failure_flows_to_module_attribution`） |

| TC-LOOP-09 | loop/spec.md「异步流式执行」（change `0107`） | 注入装配**捕获导出器**的 `tracer` 跑一轮「首轮调工具、次轮终止回复」的 loop；再用失败工具动作 / 纯终止动作 / 未注入 `tracer` 三种变体跑 | 非终止动作完成 ⇒ 导出事件含 `kind="tool_call"`（载荷 `tool` = 工具 id、`args`、`result.ok`、`latency_ms` 为浮点）——**生产者接线**（此前该 API 零生产调用方）；与 `action_completed` **同判据**：执行失败**仍**产（`result.ok` 为假）、终止动作**不**产、未注入 `tracer` 不产且本轮回复不变（锚点：`tests/test_tool_trace.py::test_tool_action_emits_tool_call_trace` / `::test_failed_tool_action_emits_tool_call_trace_with_failure` / `::test_terminal_action_emits_no_tool_call_trace` / `::test_loop_without_tracer_still_runs`） |
| TC-LOOP-10 | loop/spec.md「执行循环」（change `0114`／ADR-0107） | `astream(session_id="A")` 后的 `LoopContext.session_id`；真装配器端到端 prompt | 标识**经上下文包**传至推理（装配检索）与技能路由，SHALL NOT 只用于记忆写入；A 会话事实不进 B 的 system prompt（详见 §30 TC-SESS-07/08/09/10） |

## 3. 分层记忆（TC-MEM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-MEM-01 | CORE-MEM-R1 | 写入 L2 事实 | 可检索到，归属正确层 |
| TC-MEM-02 | CORE-MEM-R2 | 超 budget 检索 | 按优先级截断，≤ budget |
| TC-MEM-03 | CORE-MEM-R3 | L3 技能结晶为插件 | 注册为代码，undo 可回滚 |
| TC-MEM-04 | CORE-MEM-R3 | 插件溶解回 L3 | 语义+教训回写，历史不丢 |
| TC-MEM-05 | CORE-MEM-R4 | 切换记忆后端 | 同一接口，行为一致 |
| TC-MEM-06 | memory/spec.md「按会话隔离的检索」（change `0114`） | 非空会话标识检索 / 空标识检索 / 与来源排除叠加 | 非空 ⇒ 只返回本会话 + 全局层；空 ⇒ 不过滤（逐字兼容）；过滤先于预算与强化（详见 §30 TC-SESS-01～05） |

## 4. 工具使用（TC-TOOL）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-TOOL-01 | CORE-TOOL-R1 | 枚举 active tools | ≥ 9 个原子工具 |
| TC-TOOL-02 | CORE-TOOL-R2 | 传非法参数 | 返回结构化 `INVALID_ARGS` |
| TC-TOOL-03 | CORE-TOOL-R3 | file_write 后回滚 | 内容恢复原样 |
| TC-TOOL-04 | CORE-TOOL-R4 | 工具超时 | 中止返回 `TIMEOUT`，loop 不崩 |
| TC-TOOL-05 | CORE-TOOL-R3 | 不可逆工具未确认 | 阻断，`IRREVERSIBLE_BLOCKED` |
| TC-TOOL-06 | tool-use「coeffect 副作用契约」（change `0108` / 账本 E34） | `CLIAdapter.adapt` 产出工具的 coeffect 声明；并把它 + 一个只读工具注册进 provider，看 MCP 默认暴露面 | 声明 `["process:spawn"]`（真派生进程，对齐 `code_run`）；默认面**只含**只读工具、`cli.*` **不出现**（空声明会被判为只读而默认放出，与 B7 收窄相反）（锚点：`tests/test_phase16.py::test_cli_adapter_declares_process_spawn` + `::test_cli_adapter_executes_command` / `::test_cli_adapter_nonzero_exit_carries_code` / `::test_gate_deny_precedes_cli_execution` 的 resolver 注入） |
| TC-TOOL-07 | tool-use「质量门禁工具」（change `0111` / phase-27 切片 S1） | 装配 `tools.gate_run`（注入假执行器 / 真 `build_gate_executor`）并按名调用；未批准执行；传白名单外门禁名；`build_runtime` 后读门禁名枚举 | ①定义诚实：`coeffects==["process:spawn","filesystem:write"]`、`reversible is False`、`timeout_s` > 执行器内部 600 上界；②按名返回结构化 `{gate, passed, reason}`；③不可逆 ⇒ 未批准 `IRREVERSIBLE_BLOCKED` 且执行器**零调用**；④未知门禁 `EXECUTION_FAILED` 且**不触达**执行器；⑤门禁名枚举与单一真源 `GATE_COMMANDS` 键**逐字一致**（锚点：`tests/test_gate_run_tool.py`、`tests/test_gate_run_wiring.py`） |

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
| TC-EVO-07 | evolution/spec.md「经验采集」（change `0101`） | 采集带 `module_id` 的失败/成功事件、既有 `tool_call` 事件（直接测适配器 + 端到端经 `maybe_run` 归因） | 带模块归因的事件 ⇒ 可归因到该架构模块的数量证据（`plugin_id == module_id`、失败 ⇒ `success=False`、`task_type="module_health"`）；**既有工具通道逐字不变**（仍 `tool_use`、按工具 id 归因）（锚点：`tests/test_evolution.py::test_worker_adapts_module_attributed_event` / `::test_worker_module_attribution_drives_diagnosis` / `::test_worker_success_module_event_is_not_a_defect` / `::test_worker_tool_channel_unchanged`；`tests/test_evolution_wiring.py::test_successful_loop_produces_no_defect_evidence`） |
| TC-EVO-08 | evolution/spec.md「模块级提案」+「架构级候选强制人工审批（HITL confirm gate）」（change `0102`） | 喂归因到内部核心模块 / 工具的失败 trace 各一轮，观察提案 `kind`；对架构级候选签获批单 `confirm` → `crystallize`；技能级走同一链路；比对归因白名单与全仓 `plugin_id` 声明 | `kind` 由归因驱动（归因白名单 id ⇒ `plugin`/`high`，否则 ⇒ `skill`/`low`），显式 `kind` 恒优先；架构级结晶结局为 **`accepted`**（无产物、`skill_id is None`，**不得**报 `published`）且仍开观察窗；技能级仍 `published` 且技能确实入库；未 `confirm` 者 `crystallize` 抛 `CANDIDATE_PENDING`；白名单与仓内声明**逐元素一致**（锚点：`tests/test_evolution_attribution.py`） |

| TC-EVO-09 | evolution/spec.md「经验采集」（change `0107`） | 把 loop **在生产链路**产出的 `tool_call` 事件喂 `EvolutionWorker._to_traces`；以及未纳入 `PluginRegistry` 的内部核心模块（如 `loop.default`）产生失败证据 | ①工具调用通道**在生产有产出**：按工具 id 归因为 `task_type="tool_use"`、`success` 取 `result.ok`（此前只有消费侧就绪）；②内部模块归因**不依赖注册表** —— `plugin_id` 语义为**归因对象身份**，模块自身失败经 `module_id` 通道承载即可被判为架构级（`plugin`/`high`）（锚点：`tests/test_tool_trace.py::test_tool_call_trace_feeds_evolution_tool_channel`、`tests/test_evolution_attribution.py`、`tests/test_evolution_wiring.py::test_loop_failure_flows_to_module_attribution`） |
| TC-EVO-10 | evolution/spec.md「架构级候选的原生实施（可选）」（change `0112`） | 逐条喂越界补丁路径（`tests/**`、`pyproject.toml`、`src/core/ci_cd/*`、`src/core/permission/*`、`src/core/evolution/*`、`src/core/configuration/*`、`src/core/runtime.py`、绝对路径 / `..` 段 / 非 `.py`）；归因到内部模块的候选产出路径不符约定的补丁 / 目标文件不存在；**未确认**候选筹备；未筹备即落地 | 范围守卫**逐条拒绝**且**不应用**（门禁一次都不跑、工作树逐字不变、制品不落台账）；路径必须**同时**满足形状与归因一致；未确认 / 未筹备 / 非架构级一律 `IMPLEMENT_REJECTED`。（锚点：`tests/test_evolution_executor.py::test_scope_guard_rejects`（19 例参数化）/ `::test_scope_guard_allows_plain_source_module`（对照组）/ `::test_prepare_rejects_path_not_matching_attribution` / `::test_prepare_rejects_missing_target_file` / `::test_prepare_rejects_trusted_module_even_when_attribution_matches` / `::test_prepare_rejects_non_internal_target` / `::test_prepare_requires_confirmed_candidate` / `::test_commit_without_artifact_is_rejected`） |
| TC-EVO-11 | evolution/spec.md「架构级候选的原生实施（可选）」（change `0112`） | 筹备（`prepare`）后读回工作树与台账；注入**恒失败**门禁；筹备后外部改动目标文件再落地；正常筹备 → 签 `op="evolution.implement"` 获批单 → 落地；落地后再落地 | 筹备跑**全部**冻结门后**回退**（工作树读回原内容 ⇒ 不留改动）、制品（补丁 + 原内容 + 各门结论）落**既有候选台账**；门禁不过 ⇒ 回退 + **不落制品** + `GATE_REJECTED`；工作树漂移 ⇒ `IMPLEMENT_STALE` 且不覆盖；复核缺失 / 未批准 / 目标不符 / 复用了 `confirm` 的单 ⇒ `CONFIRM_REQUIRED` 且工作区逐字不变；落地 ⇒ 结局 `implemented` + 候选状态 `implemented` + 效应 `rollback` 可还原；重复落地 ⇒ 拒绝（锚点：`tests/test_evolution_executor.py::test_prepare_restores_worktree_and_stages_artifact` / `::test_prepare_gate_failure_rolls_back_without_artifact` / `::test_prepare_detects_leftover_dirty_worktree` / `::test_commit_requires_matching_implement_ticket`（4 面参数化）/ `::test_commit_rejects_drifted_worktree` / `::test_commit_applies_patch_and_reports_implemented` / `::test_commit_is_not_repeatable` / `::test_staged_is_empty_until_prepare`） |
| TC-EVO-12 | evolution/spec.md「架构级候选的原生实施（可选）」+「架构级候选强制人工审批（HITL confirm gate）」（change `0112`） | `build_runtime` 三态（缺省 / `features.evolution_executor: true` / `false`）观察 `Runtime.evolution_executor`；执行器向台账记一条候选后用**第二个** runtime 读回；跑 `evolve implement` 三态（dry-run / 落地 / **能力未启用**）与 `evolve pending` | 缺省与 `false` ⇒ **不装配**（`is_enabled` 缺省关）且 `evolution`/`loop` 装配面逐字同今；`true` ⇒ 装配且门禁名单 == `tuple(GATE_COMMANDS)`；执行器**未**暴露到 Agent 工具面（无 `implement`/`evolution` 工具 id）；制品跨进程可查（同一 `evolution-pending.json`）；`--dry-run` 打印待复核 diff 且工作树不变；落地落 `implemented`；**能力未启用 ⇒ stderr 说明 + rc 0 + 空 stdout**；`crystallize` 仍恒 `accepted`（R4：`engine.py` 零改动）（锚点：`tests/test_evolution_executor_wiring.py`（6 例）/ `tests/test_evolution_executor_cli.py`（7 例）/ `tests/test_evolution_author.py`（模块路径约定 14/14 命中）/ `tests/test_evolution.py` 既有用例 / `tests/test_feature_gating.py`） |

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
| TC-PERM-08 | permission/spec.md「权限模式」 | `--permission-mode auto-approve` + **无审批通道**下执行不可逆写 / 出站网络 / 无法归类动作 | 一律放行（不返回 `APPROVAL_REQUIRED`）；对照 `interactive` 同动作走审批、无 approver 时 fail-closed 拒绝；注入 guardrail 判拦时 auto-approve 仍 `deny`（权档全放行不越过正交红线）；`read-only` / `high-risk-block` 两档仍拒（锚点：`tests/test_permission_auto_approve.py`、`tests/test_permission.py::test_permission_mode_auto_approve_full_release`） |
| TC-PERM-09 | permission/spec.md「分级权限体系」 | 判定标识仅**命名空间前缀**含只读词子串（`tools.` 含 `"ls"`）；声明字面量 coeffect `agent:delegate`；声明 `agent:other` | 前者 SHALL NOT 判 `read`（按 `high-risk` deny-by-default）；`agent:delegate` 判 `read`；`agent:other` SHALL NOT 因该 coeffect 判 `read`（豁免仅字面量、不放宽为前缀）（锚点：`tests/test_permission.py::test_classify_namespace_substring_not_read` / `::test_classify_delegate_coeffect_is_read` / `::test_classify_non_delegate_agent_coeffect_not_read`） |

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
| TC-OBS-06 | observability/spec.md「全链路日志」（change `0101`） | 构造 `TraceEvent` 不传 / 传 `module_id`；既有四类 `kind` 路径的记录与序列化 | `module_id` 缺省为 `None`（**向后兼容**，既有 trace_id/span_id/ts/kind/payload 语义逐字不变）；传入时按模块归因携带（锚点：`tests/test_observability.py::test_trace_event_module_id_defaults_to_none` / `::test_trace_event_carries_module_attribution`） |
| TC-OBS-07 | observability/spec.md「链路追踪」（change `0103`） | 开一条 trace 记录事件 → 封口 `end_trace`；连续开/封口 10 条；装配捕获导出器 | 封口**交付导出器**（事件真到导出器）且**从内存释放**（此后 `replay` 为空）；`_events` 不随已封口 trace 数增长（内存有界，锚点：`tests/test_observability.py::test_end_trace_releases_in_flight_events` / `::test_end_trace_delivers_events_to_exporter` / `::test_in_flight_memory_does_not_grow_across_traces` / `::test_three_event_kinds_logged`（改为落盘真路径断言）） |

| TC-OBS-08 | observability-interface §2「TraceLogger」（change `0107`） | 经 loop 的生产路径调 `log_tool_call`（`args` 为短载荷原样 / 超长载荷节选字符串） | 载荷形状固定为 `{tool, args, result: {ok, output}, latency_ms}`；`args` 允许**节选字符串**（事件面有界，超长参数 ≤400 字符截断）；唯一生产调用方是执行循环（缺省未注入 `tracer` ⇒ 不产）（锚点：`tests/test_tool_trace.py`） |

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
| TC-CTX-05 | context/spec.md「动态上下文构建」+「上下文自动压实」（change `0114`） | `build(session_id=…)` 透传；`persist(session_id=…)` 归属与 id 会话键 | 事实召回按会话隔离；压实产物按会话归属且 id 带会话键（跨会话不覆盖）（详见 §30 TC-SESS-06/13/14/15） |

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
| TC-UI-10 | CORE-UI-R7 | CLI `session create` 建 id → **另一进程** `run --session <id>` | 会话有效（不再 `UI_SESSION_NOT_FOUND`）；`GET /sessions` 三入口枚举一致 |
| TC-UI-11 | CORE-UI-R2「上下文窗口与预算热生效」（change `0099`） | `apply_llm_config` 后新开 `ConfigManager` 重读同一 yaml；观察**运行中** `DefaultLoop` 的 `_max_rounds`/`_token_budget` | 新进程读到 `model`/`context_window`/`loop_limits()` 即落盘值；运行中 loop **无需重建**即取用新上限（锚点：`tests/test_llm_config_hot_update.py::test_apply_persists_and_survives_reload` / `::test_apply_hot_updates_running_loop`） |
| TC-UI-12 | CORE-UI-R2「密钥安全存储」/「密钥持久化失败」（change `0099`） | `apply_llm_config` 传明文 key / 传窗口不敷预留 / monkeypatch `Path.write_text` 半写后抛 `OSError`；并观察 `set_llm_config` 是否触盘 | 明文 ⇒ `UI_LLM_KEY_UNSET`；非法取值 ⇒ `UI_LLM_CONFIG_INVALID` 且内存与 yaml 均不变；写盘失败 ⇒ 旧 yaml **逐字不变**、内存回退（原子提交）；落盘文件只有 `${OPENAI_API_KEY}`、**无明文**；`set_llm_config`（启动期 hydrate）**不触盘**（锚点：`tests/test_llm_config_hot_update.py::test_plaintext_api_key_rejected` / `::test_invalid_value_rejected_and_original_intact` / `::test_write_failure_leaves_file_untouched` / `::test_api_key_reference_is_preserved_not_plaintext` / `::test_set_llm_config_does_not_touch_disk` / `::test_without_config_manager_keeps_memory_only` / `::test_get_loop_limits_reports_effective_values`；`tests/test_serve.py::test_llm_config_roundtrip_window_and_budget` / `::test_llm_config_invalid_returns_400`；`tests/test_ui.py::test_apply_llm_config_rejects_plaintext` / `::test_apply_llm_config_skips_loop_without_limits_protocol`） |
| TC-UI-13 | CORE-UI-R4「未构建前端时降级为纯 API」/「静态挂载不遮蔽端点」（change `0100`） | monkeypatch `fastapi_serve._DIST_DIR` 分别指向不存在目录与含 `index.html` 的临时 dist | 缺产物 ⇒ 服务照常起、`/llm-config`/`/tools` 全可达、`/` 404（不因缺前端而失败）；有产物 ⇒ `/` 返回 SPA 外壳，且**既有端点不被静态兜底吞掉**（挂载顺序契约）（锚点：`tests/test_serve.py::test_without_dist_is_api_only` / `::test_with_dist_serves_spa_without_shadowing_endpoints`） |
| TC-UI-14 | CORE-UI-R5「sidecar 拉起」（change `0100`） | 用 `Popen` 替身断言 sidecar 的 argv 与 kwargs；令 `Popen` 抛 `OSError`；另起子进程跑 `python -m core.entry serve --help` | argv 逐项为 `[sys.executable, -m, core.entry, serve, --host, 127.0.0.1, --port, <port>]`、**不经 shell**、用**本进程同解释器**；spawn 失败 ⇒ `UI_SIDECAR_FAILED`（不静默成功）；`-m core.entry` 调用面**真的可运行**（`--help` 退出 0 且列出 `--port`）（锚点：`tests/test_desktop_sidecar.py::test_sidecar_spawns_backend_without_shell` / `::test_sidecar_spawn_failure_is_reported_not_silent` / `::test_entry_is_runnable_as_sidecar_target`） |

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
| TC-RAG-01 | CORE-RAG-R1 | 知识文档完成 embedding 后写入向量库 | 向量落盘于本地嵌入式向量库（默认 stdlib `sqlite3`，落 `$CORE_STATE_DIR/rag-index.db`），无需独立服务或外部向量数据库 |
| TC-RAG-02 | CORE-RAG-R2 | 导入一份知识文档经摄取管线处理 | 文档被分块、逐块生成 embedding 并建立向量索引，可被检索 |
| TC-RAG-03 | CORE-RAG-R2 | 源文档变更导致 hash 不一致 | 触发受影响块增量重建，期间该文档检索降级为旧索引 |
| TC-RAG-04 | CORE-RAG-R3 | 一段文本经本地 embedding 生成 | 由本地 `HashEmbedder` 推理完成（确定性向量），不请求外部 embedding API |
| TC-RAG-05 | CORE-RAG-R3 | 经 llm-provider 归一化入口请求远端 embedding 模型 | 无缝切换到远端模型，检索与调用方无感知 |
| TC-RAG-06 | CORE-RAG-R4 | 执行语义检索 | 返回按向量相似度排序的 top-k 片段及相关度得分 |
| TC-RAG-07 | CORE-RAG-R5 | 将检索片段注入生成请求 | 片段经 context 装配器按预算裁剪后注入提示词，由 llm-provider 生成 |
| TC-RAG-08 | CORE-RAG-R5 | 语义检索无相关片段时构建生成请求 | 降级为纯 LLM 生成，不阻断流程 |
| TC-RAG-09 | CORE-RAG-R6 | 一次查询同时涉及知识文档与代码结构 | 文档语义检索走 RAG，代码结构理解走 codebase-memory-mcp，互不重叠 |
| TC-RAG-10 | rag「存储与 Embedding 依赖注入隔离」 | 以替身实现注入 `Embedder` / `VectorStore`（`_FixedEmbedder` / `InMemoryVectorStore` / `SqliteVectorStore`） | `Retriever` 及调用方零改动（锚点：`tests/test_rag.py::test_retriever_delegates_to_store`）；生产落盘实现已接（change 0104）⇒ 由半覆盖转全覆盖 |
| TC-RAG-11 | CORE-RAG-R1（跨进程复用 / 维度守护） | 一次进程 `ingest` 写入落盘索引后，**另一实例**装载同一索引检索；再以不同维度 `put` / `search` | 前者命中该文档块（落盘为真源、向量往返无损）；后者以 `INDEX_CORRUPT` 结构化拒绝并提示重建索引（锚点：`tests/test_rag.py::test_sqlite_store_reused_across_instances` / `test_sqlite_store_rejects_dim_mismatch`） |
| TC-RAG-12 | cli-ops「运维命令集」（知识摄取 / 语义检索 / 检索增强生成） | 依次执行 `rag ingest <path> --doc-id d1`（两次）→ `rag search <query>` → `rag ask <query>` | 摄取打印块数、重复摄取按 content_hash 判为无变更；检索打印 top-k 片段（块 id / 来源 / 得分），**不调用生成**；ask 打印生成答案（片段注入提示词）；均一次性、不改运行态（锚点：`tests/test_rag_wiring.py::test_cli_rag_ingest_then_search_across_assemblies` / `test_cli_rag_ask_prints_answer`） |
| TC-RAG-13 | rag「生成融合」+ 错误码（fail-closed） | 服务层未装配生成器时 `ask`；索引维度不一致时 CLI `rag search` | 分别以 `GENERATION_UNAVAILABLE` / `INDEX_CORRUPT` 结构化错误落 stderr + 退出码 1，不静默给空答案、不抛裸栈（锚点：`tests/test_rag.py::test_service_ask_without_generator_is_structured_error` / `tests/test_rag_wiring.py::test_cli_rag_search_rejects_dim_mismatch_with_hint`） |
| TC-RAG-14 | rag 定位「辅助本地知识库，不注入主链路」（change `0156` / ADR-0148 / **规格中性**） | 架构成例扫描主链路与三面兄弟（`loop` / `context` / `memory` / `notes`）的 import 面 | 四包**均不** `import core.rag`（`core.rag` 仅由组合根 `runtime` 与 CLI `entry` 引用）；把 ADR-0097 ⑥ 的「不注入 loop」固化为可执行不变量（锚点：`tests/test_architecture.py::test_rag_not_imported_by_reference_chain`） |

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
| TC-SKH-01 | CORE-SKH-R1 | `MarketIndex(path=…)` 一次 `put` 后由**另一实例**装载目录 | 命中该条目（`get`/`list` 一致）—— 落盘目录为市场真源，不依赖进程内内存（锚点：`tests/test_skillhub.py::test_index_persists_across_instances`） |
| TC-SKH-02 | CORE-SKH-R1 | 目录文件损坏（非法 JSON）后装载 | `warnings.warn` **降级为空目录**，官方源仍在、`locate` 返回 None，不抛异常（锚点：`test_index_corrupt_file_degrades_to_empty_official`） |
| TC-SKH-03 | CORE-SKH-R5 | `MarketIndex.locate(skill_id)` 在非官方源命中 | 返回 `(源名, MarketSkill)`；未知 skill_id 返回 None（锚点：`test_index_locate_across_sources`） |
| TC-SKH-04 | CORE-SKH-R3 | `SkillPublisher(artifacts=…)` 发布后由消费侧拉取 | 制品入库（`SkillLibrary` 可 `lookup`）且与调用方技能对象**非同一对象**；`SkillHubClient.download` 得 draft（锚点：`test_publish_registers_artifacts_for_fetch`） |
| TC-SKH-05 | CORE-SKH-R5 | 发布到不存在的 source | 抛 `SOURCE_NOT_FOUND`，且**制品库不含**该技能（先上架后入库的顺序保证）（锚点：`test_publish_missing_source_leaves_no_artifact`） |
| TC-SKH-06 | CORE-SKH-R3 | 另一实例 publish → 本实例 `review approved`（未注入 artifacts） | 目录条目 published、市场版本 v2 落盘；制品版本不动（锚点：`test_review_across_instances_bumps_market_version`） |
| TC-SKH-07 | CORE-SKH-R3 | `review approved`（注入 artifacts） | 制品本体版本 == 市场版本，且 `TrustVerifier().verify(body, market.signature)` 为真（**重新签名**）（锚点：`test_review_promotes_artifact_and_resigns`） |
| TC-SKH-08 | CORE-SKH-R3 | `review rejected` 后由另一实例装载目录 | 状态 rejected 落盘；抛 `PUBLISH_REJECTED`（锚点：`test_review_rejected_persists_status`） |
| TC-SKH-09 | CORE-SKH-R3 | CLI 供给侧闭环：本地注册 → `skill publish` → 重开目录 pending → `skill search` 命中 → `skill review approved` → 重开 published/v2 → `skill install` → 重开技能库 draft | 全链路跨 `main()` 调用可见 —— 「本地技能 → 发布 → 索引 → 消费侧 search/install」闭环成立（锚点：`tests/test_skillhub_cli.py::test_supply_chain_publish_search_review_install`） |
| TC-SKH-10 | CORE-SKH-R3 | `skill publish` 未注册技能 / 源不存在；`skill review` 未发布技能 / rejected | 四种情形均退出码 1 + stderr 结构化原因，且**目录不落盘**（rejected 例外：状态落盘为 rejected）（锚点：`test_skill_publish_unregistered_skill_reports_error` 等 4 例） |
| TC-SKH-11 | CORE-SKH-R4 | `skill publish` 后篡改本地市场制品、再 `skill install` | 末端验签失败 ⇒ `SIGNATURE_INVALID`、退出码 1，本地技能库**不被改写**（锚点：`test_skill_install_rejects_tampered_artifact`） |

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
| TC-CONF-10 | configuration/spec.md「循环预算配置」（change `0098` ADDED）+「LLM 提供商配置（必选）」（MODIFIED） | 三键（`llm.context_window` / `loop.output_reserve` / `loop.max_rounds`）分别在 CLI / env / yaml 三面取值；配了窗口与预留但 `context_window <= output_reserve`；`loop:` 段出现在 config.yaml | 三键经 `ConfigSpec` 声明 ⇒ CLI flag / env / yaml 三面齐备且**单一真源**；优先级链 CLI > env > yaml > 缺省逐层压过；`loop:` 段不触发「未知配置段」告警（ConfigSpec 声明段自动进白名单）；`config set loop.<键>` 三面可达且**落盘**（`extra.loop` 浅合并，不得静默丢弃）（锚点：`tests/test_loop_budget_config.py::test_specs_declare_loop_and_context_window_keys` / `::test_cli_overrides_env_and_yaml` / `::test_env_overrides_yaml` / `::test_loop_section_is_not_reported_unknown` / `::test_config_set_loop_key_applies_and_persists` / `::test_config_set_context_window_applies`） |
| TC-CONF-11 | configuration/spec.md「循环预算配置」（change `0098`） | 三键分别写入非法取值（负数 / 小数 / 非数值 / `true`；`max_rounds=0`；`context_window=4096` 配 `output_reserve=8192`） | 一律在 `validate_schema` 判为错误、**阻断启动**（含 `bool` 陷阱），**不静默兜底**为缺省值；交叉校验失败报「窗口不敷输出预留」—— 因 `token_budget <= 0` 的语义是「关闭 token 维度」，静默兜底会把配置错误伪造成「预算维度失效」（锚点：`tests/test_loop_budget_config.py::test_invalid_context_window_blocks_startup`（4 面参数化）/ `::test_invalid_output_reserve_blocks_startup` / `::test_invalid_max_rounds_blocks_startup` / `::test_window_not_exceeding_reserve_blocks_startup` / `::test_invalid_value_does_not_silently_fall_back`） |
| TC-CONF-12 | configuration/spec.md「功能开关（feature flag）」（change `0112` 新增场景「缺省关的可选能力未声明即不装配」） | 不声明 `features.evolution_executor`（缺省）、显式 `false`、显式 `true` 三态启动装配；比对两条名单与并集 | 缺省关名单内能力**未声明即不装配**（fail-closed，仅显式 `true` 装配）；`GATABLE_MODULES` 逐元素断言**不动**（缺省开口径零改动）；两极性各由**独立名单**承载、`KNOWN_FEATURE_MODULES` == 二者之并（供未知开关名告警）（锚点：`tests/test_feature_gating.py::test_opt_in_whitelist_is_evolution_executor` / `::test_two_polarities_are_carried_by_separate_lists` / `::test_known_feature_modules_is_the_union` / `::test_opt_in_module_is_off_until_explicitly_true` / `::test_gating_whitelist_is_pet_beast_evolution`；`tests/test_evolution_executor_wiring.py::test_default_does_not_assemble_executor` / `::test_explicit_true_assembles_executor` / `::test_explicit_false_does_not_assemble_executor` / `::test_executor_flag_is_a_known_feature_name`） |

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

| TC-PET-09 | pet-mode「Task Result Query」结果可见性（change `0113`／ADR-0106，账本 E46） | 唤醒一轮后查 `PetControl.result`；未唤醒即查；同一会话下比对 `status` 键集合与 `snapshot` 字段；寻址三分支（单宠物默认 / 多宠物未指定 / 未注册）；CLI `pet result`（真 argv 与 `_pet_control` 两端）；`UIAPILayer.pet_command("result")` | `wake()` 后返回 `{session_id, has_result, reply, failed}`（正文 = loop 返回值）；未唤醒 ⇒ `has_result=False`、`reply=None`（**不编造**）；**`status` 键集合逐字不变**（六键、不含正文与偏好）、`snapshot()` 也不含 `reply`（结果不落盘）；寻址与既有动词一致（`PET_TARGET_AMBIGUOUS` / `PET_NOT_FOUND`）；三面（`PetControl` / CLI / UIAPI）落到**同一实现**（锚点：`tests/test_pet_result_query.py::test_result_after_wake_exposes_loop_reply` / `::test_result_before_wake_reports_no_result` / `::test_status_keys_unchanged_after_result_added` / `::test_status_does_not_leak_reply_even_when_result_exists` / `::test_result_survives_go_idle` / `::test_result_multiple_pets_without_target_rejected` / `::test_result_unknown_session_rejected` / `::test_cli_pet_result_prints_reply` / `::test_cli_pet_result_no_result_is_honest` / `::test_cli_pet_result_unknown_session_exits_one` / `::test_ui_pet_command_result_uses_same_control`） |

## 26. 插件注册与安装（TC-PLUGIN）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PLUGIN-01 | plugin-registry「插件来源与安装」（change `0093`） | 以 **git-repo** 来源发现插件：仓库含 / 不含根目录 `core-plugin.json`、仓库地址不存在、注入 cloner 抛 `GitError` | 含 manifest ⇒ 返回该 manifest；不含 ⇒ `SOURCE_NOT_FOUND` 且提示缺 `core-plugin.json`；地址不存在 ⇒ `SOURCE_NOT_FOUND`（真实克隆失败已归一）；cloner 故障 ⇒ `SOURCE_NOT_FOUND` 且地址中的 userinfo **不回显**；解析后临时工作区**零残留**（锚点：`tests/test_plugins_sources.py::test_git_repo_source_reads_manifest_from_clone` / `::test_git_repo_source_without_manifest_is_unreachable` / `::test_git_repo_source_clone_failure_normalized` / `::test_git_repo_source_cloner_failure_normalized_and_no_credential_echo` / `::test_git_repo_source_leaves_no_worktree_behind`） |
| TC-PLUGIN-02 | plugin-registry「插件来源与安装」（change `0093`） | 以 **market-registry** 来源发现插件：注入 fetcher 正常 / 抛非领域异常（URL 带 `?token=`）/ 抛 `DomainError`；缺省 fetcher 走 `file://` 文档；缺省 fetcher 读非法 JSON | 注入 fetcher ⇒ 取回该 manifest 且 URL 透传；抛异常 ⇒ `SOURCE_NOT_FOUND` 且 **URL query 中的 token 不回显**；抛 `DomainError` ⇒ **原样透传**（不二次包装）；缺省边 ⇒ 真实 `urllib` 路径取回文档；非法文档 ⇒ `SOURCE_NOT_FOUND`（锚点：`tests/test_plugins_sources.py::test_market_registry_uses_injected_fetcher` / `::test_market_registry_failure_normalized_and_no_credential_echo` / `::test_market_registry_domain_error_passes_through` / `::test_market_registry_default_fetcher_fetches_document_offline` / `::test_market_registry_default_fetcher_rejects_invalid_document`） |
| TC-PLUGIN-03 | plugin-registry「插件来源与安装」（change `0093`） | 以 **mcp-endpoint** 来源发现插件（解析期零网络）；`InstallDispatcher.resolve` 四源分派与 `LOCAL_PATH` 缺文件；CLI `plugin install --source {git-repo, 缺省, ftp}` | mcp-endpoint ⇒ 合成 `{name, url}`（名取端点主机名）、无网络请求；分派 ⇒ 四源各归其解析器、`LOCAL_PATH` 缺文件 ⇒ `SOURCE_NOT_FOUND`；CLI `--source git-repo <本地仓库>` ⇒ 退出码 0 且技能**跨进程落盘可见**；缺省仍为 local-path；非法来源 ⇒ argparse 退出码 2（锚点：`tests/test_plugins_sources.py::test_mcp_endpoint_synthesizes_manifest_without_network` / `::test_dispatcher_routes_all_four_sources` / `::test_dispatcher_local_path_missing_file_raises` / `::test_plugin_install_git_repo_source_persists_skill` / `::test_plugin_install_default_source_is_still_local_path` / `::test_plugin_install_rejects_unknown_source`） |
| TC-PLUGIN-04 | tool-use「插件安装工具」（change `0108` / 账本 E33） | 组合根 `build_runtime` 装配后枚举 `runtime.tools.active_tools()`；取 `tools.install` 的 **Tool** 调其 handler 装一个 skill 资产 | 三 id（`tools.install` / `tools.uninstall` / `tools.list`）在**生产工具面**可达；装完 `runtime.installer.installed()` 反映该次安装（**同一实例**，非一次性注册表）（锚点：`tests/test_install_tools.py::test_install_tools_registered_in_runtime` / `::test_runtime_install_tool_uses_runtime_installer`） |
| TC-PLUGIN-05 | plugin-registry「插件来源与安装」（change `0108` / 账本 E33） | 经 `Runtime.installer` 装一个 cli 资产（本地 manifest `{name, command}`）后再卸载 | 安装后 `cli.<name>` 出现在 `runtime.tools.active_tools()`；卸载后**从工具面摘除**（证明 `uninstaller=dispatcher.uninstall` 已接、非只摘账本）（锚点：`tests/test_install_tools.py::test_runtime_installer_uninstalls_cli_tool`） |
| TC-PLUGIN-06 | plugin-registry「插件来源与安装」（七步链，change `0108` / 账本 E35） | CLI `plugin install <manifest> --kind skill`（离线 resolver + 记录型 installer） | 生命周期按序走完 `verify → install → register → activate`（此前跳过 `verify` / `activate`）（锚点：`tests/test_entry.py::test_plugin_install_runs_full_lifecycle`） |
| TC-PLUGIN-07 | plugin-registry「插件安装持久化」（change `0109` / 账本 E36） | 账本 `PluginInstallRegistry`：`put` 后以**新实例**（新进程语义）读回；检视落盘形状；同名重装；从未写过 / 写入中断 / 文件损坏 / 条目残缺 | `put` 的成果跨实例可见（`plugin-installs.json` 落 `$CORE_STATE_DIR`）；文件是带 `version` 的单文件 JSON；同名重装**覆盖**；无文件 ⇒ 空且**不告警**；`os.replace` 中断 ⇒ **旧文件完好**（非半写）；损坏 ⇒ 告警 + 视为空（不阻断启动）；残缺条目**只跳过该条**、其余照常（锚点：`tests/test_plugin_installs.py::test_path_uses_state_dir` / `::test_put_persists_across_instances` / `::test_file_is_json_object_with_version` / `::test_put_overwrites_same_plugin_id` / `::test_remove_persists_and_reports_missing` / `::test_missing_file_is_empty_and_silent` / `::test_interrupted_write_keeps_previous_file` / `::test_corrupt_file_warns_and_degrades` / `::test_malformed_entry_skipped_others_kept`） |
| TC-PLUGIN-08 | plugin-registry「插件安装持久化」（change `0109` / 账本 E36） | `PluginInstallStore` 按 `kind` 路由（cli → 本账本 / mcp → 端点表）；`records()` 合并两视图；`remove()` 两处覆盖；`PluginInstaller(store=…)` 的 `register` / 构造期水合 / `uninstall` 钩子；无 store 时行为不变 | cli ⇒ 只进账本；mcp ⇒ 只进端点表且**账本无该条**（不两处记账）；合并视图含两类；移除覆盖两处；`register` 即落盘、新实例构造期**水合出该资产**（跨进程 `uninstall` 才不抛「插件未注册」）、`uninstall` 清账；**缺 store** 保持原内存语义；未安装仍 `UNINSTALL_NOT_FOUND`；skill / cli 物化已不在时卸载**幂等**（锚点：`tests/test_plugin_installs.py::test_store_routes_cli_to_ledger` / `::test_store_routes_mcp_to_endpoint_registry` / `::test_store_records_merges_both_views` / `::test_store_remove_covers_both_views` / `::test_installer_register_persists` / `::test_installer_hydrates_from_store` / `::test_installer_uninstall_clears_ledger` / `::test_installer_without_store_keeps_in_memory_behaviour` / `::test_uninstall_missing_still_reports_not_found` / `::test_uninstall_skill_is_idempotent_when_absent` / `::test_uninstall_cli_tool_is_idempotent`） |
| TC-PLUGIN-09 | plugin-registry「插件安装持久化」（change `0109` / 账本 E36） | 端到端（**真实子进程**）：CLI `plugin install --kind cli` → 新进程 `plugin list` → `plugin uninstall` → `plugin list`；CLI `plugin install --kind mcp`（委派）；装配期 `build_runtime` 从账本重建 cli 工具面；账本含**不可重建**条目 | list 显 `demo (cli, local-path)`（改前恒「（无已安装资产）」）、卸载后回到「（无已安装资产）」；mcp 委派 ⇒ 端点表有该条、`plugin-installs.json` 无、`plugin list` 合并视图显 `files (mcp, mcp-endpoint)`、卸载清端点表；装配期 `cli.<name>` 进 `runtime.tools.active_tools()`；坏记录 ⇒ 告警跳过、好记录仍装配（**不阻断**）（锚点：`tests/test_entry.py::test_plugin_install_persists_across_processes` / `tests/test_mcp_endpoints.py::test_cli_plugin_install_mcp_delegates_to_endpoints` / `tests/test_install_tools.py::test_runtime_rebuilds_cli_install_from_ledger` / `::test_runtime_skips_unrebuildable_record`） |

## 27. 文档化记忆（TC-NOTE）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-NOTE-01 | notes/spec.md「canonical Markdown 真相层与可插拔后端」 | `render_note` → `parse_note` 往返一篇含标题/tags/检索关键词/正文的 note | 字段**全量还原**（标题 / tags / 正文 / Search Queries / updated_at / source），即 canonical 格式自描述、不丢字段（锚点：`tests/test_notes.py::test_render_parse_roundtrip`） |
| TC-NOTE-02 | 同上「覆盖式更新」 | 同主题连续两次 `put`（不同内容）后读 canonical 文件 | 文件内容为**第二次**的内容；首次内容**不出现**（覆盖式，非两段拼接）（锚点：`::test_backend_put_is_overwrite`） |
| TC-NOTE-03 | 同上「原子写」 | 桩掉 `os.replace` 抛错后 `put` 新内容 | 抛错且 canonical 文件**逐字**保持旧内容（不出现半截文档）（锚点：`::test_backend_atomic_write_keeps_previous_on_failure`） |
| TC-NOTE-04 | 同上「文件清单」 | 写入两篇后 `list_index`；再 `get` 命中一篇 / 缺失一篇 | 清单含两篇 id；命中篇 `content` 经同一解析器还原 tags（不丢字段）；缺失篇返回 `None`（锚点：`::test_backend_list_index_and_get_roundtrip`） |
| TC-NOTE-05 | 同上「关键词命中」 | 关键词只落在头部 `## Search Queries`（正文不含）时 `search` | 命中该 note、且**只**命中它（**不建向量库**，纯词法）（锚点：`::test_backend_search_hits_search_queries`） |
| TC-NOTE-06 | 同上「中文任务句命中」 | 以无空格任务句「部署流程怎么走」`search` 两篇（其一标题「部署流程」） | 命中「部署流程」篇（CJK 2-gram 切词），无空格不导致空手；另一主题仍可独立按自身关键词命中（锚点：`::test_backend_search_matches_cjk_sentence_query`） |
| TC-NOTE-07 | 同上 + `slug_topic` | 中英任务文本（含标点 / 全标点）转主题 slug | 保留 CJK 与字母数字、空白标点折为单个 `-`、去首尾；纯标点 ⇒ 空串（调用方据此跳过写盘）（锚点：`::test_slug_topic_keeps_cjk_and_folds_punct`） |
| TC-NOTE-08 | 「Consult → Build → Update 循环纪律」任务后写回 | `NoteStore.observe_turn(task, steps, ok=True)` | 对应主题 canonical 文件含「解决过程」与新结论（覆盖式）；`ok=False` ⇒ 返回 `None` 且**不写盘**（锚点：`::test_store_observe_turn_writes_canonical`） |
| TC-NOTE-09 | 同上 任务前注入 | 组合根注入 Consult 钩子（真 `NoteStore.digest`）后跑一轮 loop | 钩子收到**任务文本**；摘要**先于推理**写入 `ctx.notes`（planner 可见）；未注入钩子 ⇒ `ctx.notes` 为空串（不注入笔记块）（锚点：`tests/test_notes_loop.py::test_loop_consult_hook_sees_task_and_feeds_context` / `::test_loop_without_consult_hook_leaves_notes_empty`） |
| TC-NOTE-10 | 同上「钩子故障不改本轮结局」 | Consult 钩子抛错；以及轮数超限的成功/失败轮 | 抛错 ⇒ 摘要置空 + `notes_consult_failed` 留痕、本轮结果与终止语义**不变**；成功轮 ⇒ 经 `TurnObserver` 写回笔记；失败轮 ⇒ **不写**（锚点：`tests/test_notes_loop.py::test_loop_consult_failure_degrades_and_does_not_change_outcome` / `::test_loop_turn_observer_writes_canonical_note` / `::test_loop_failed_round_does_not_write_note`） |
| TC-NOTE-11 | 同上 Consult→Build→Update 闭环 | 同一存储：一轮 loop 走完后再次 `digest` 同一任务 | 读到的即上一轮写回的（闭环成立，无需向量库）（锚点：`tests/test_notes_loop.py::test_consult_update_loop_roundtrip_through_loop`） |
| TC-NOTE-12 | 同上「任务前注入相关笔记」+ 纯词法 | `LLMPlanner` 分别在 `ctx.notes` 非空 / 空两种上下文装配 system prompt | 非空 ⇒ prompt 含「相关笔记：」块与该摘要；空 ⇒ **不含**该块（缺省零行为变化）（锚点：`tests/test_notes_loop.py::test_planner_injects_notes_block_only_when_present`） |
| TC-NOTE-13 | 同上「循环技能可被路由」 | 经组合根装配后按文档化记忆任务路由技能 | 命中 `skills.notes.consult_build_update`，`instructions` 含 Consult 与 Update 两段纪律（锚点：`tests/test_skills.py` 路由用例 + 组合根装配） |
| TC-NOTE-14 | 「结构化错误码与既有链路不变」读取不存在 / 显式创建已存在 | `get` 缺失主题；`create` 已存在主题；`ensure` 已存在主题 | 前者 `NOTE_NOT_FOUND`；中者 `TOPIC_EXISTS` 且**既有内容不被覆盖**；后者为幂等 get-or-create、**不报错**（锚点：`tests/test_notes.py::test_store_get_missing_raises` / `::test_store_create_topic_exists_but_ensure_is_idempotent`） |
| TC-NOTE-15 | 同上 Consult → Update 版本语义 | 同主题先写「旧结论」再覆盖写「新结论」，两次 `consult` | 第二次读到**新结论**且**不含**旧结论（最新即权威）（锚点：`::test_store_consult_update_consult_reads_latest`） |
| TC-NOTE-16 | 同上「既有记忆链路未改」 | `digest` 输出构成；以及 `git diff` 核对 `plugin_registry` / `memory` / `rag` | digest = 命中笔记节选 + **全量标题清单**（总量 ≤1200 字符，不自动注入正文）；三个既有子系统**零改动**（锚点：`::test_store_digest_carries_hits_and_catalog`；变更期 `git diff --stat src/core/{plugin_registry,memory,rag}` 为空） |
| TC-NOTE-17 | 同上「循环纪律 + 分层」 | 架构成例扫描 `notes` 包与 `loop` 包的 import 面 | `loop` **不** import `notes`（反向依赖用例含 `notes`）；`notes` 包可导入、有 `__init__.py`（锚点：`tests/test_architecture.py::test_phase3_loop_no_reverse_dependency` / `::test_packages_importable`） |
| TC-NOTE-18 | 同上 CLI 面 | 跨进程：一进程经 `NoteStore` 写 canonical（含 `observe_turn`），另一进程 `core-agent notes list` / `search <中文任务句>` / `show <id>`；`show` 不存在的 id | 三子命令都在**新进程**里从 canonical Markdown 读到内容（落盘为真源）；中文长句命中；缺失 id ⇒ `NOTE_NOT_FOUND` + 退出码 1（锚点：`tests/test_entry.py` notes 子命令用例 —— change `0149` 起 `show`/`list` 有真锚点，`search` 仍缺（补锚点另立账）；change 0106 端到端冒烟） |
| TC-NOTE-19 | notes/spec.md「Consult → Build → Update 循环纪律」+ evolution 归因 | 扫描仓内全部 `plugin_id = "..."` 声明与 `INTERNAL_PLUGIN_IDS` | 逐元素一致（`notes.store` 已登记）—— `notes` 的缺陷归因为**架构级**（`plugin`/`high`）而非技能级，不绕过人工审批（锚点：`tests/test_evolution_attribution.py::test_internal_plugin_ids_match_declared_plugin_ids`） |

| TC-NOTE-20 | notes/spec.md「canonical Markdown 真相层与可插拔后端」（change `0107` 字段加权） | 两篇均含关键词 K：A **标题**命中、B **仅正文顺带**提及；另一组 tags / `## Search Queries` 命中 vs 正文命中；以及**无任何字段**命中 | A 排 B **之前**且两者**均被命中**（加权只改排序、不改过滤）；元数据命中排在正文命中之前；无命中 ⇒ **空列表**（返回结构不变）（锚点：`tests/test_notes.py::test_backend_search_weights_title_above_content` / `::test_backend_search_weights_meta_above_content` / `::test_backend_search_no_hit_returns_empty`） |
| TC-NOTE-21 | notes/spec.md「Consult → Build → Update 循环纪律」（**显式全局层**，change `0114`） | 内省 Consult/写入面参数名；两会话下同一 query Consult | 均无 `session` 维度；两处命中集**相同** —— 笔记是被有意文档化的刻意知识、不参与会话隔离（详见 §30 TC-SESS-20/21） |

---

## 28. 记忆命名空间接线（TC-NS）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-NS-01 | beast-mode/spec.md「独立记忆命名空间」 | `DefaultLoop(source="beast.baihu")` 落一轮轨迹 | 条目 `source == "beast.baihu"`（锚点：`tests/test_memory_namespace.py::test_loop_writes_injected_source`） |
| TC-NS-02 | 同上（**红线**：缺省不变） | `DefaultLoop()`（不注入 `source`）落一轮轨迹 | `source == "loop"` —— 主 Agent 语义**逐字不变**（锚点：`::test_loop_source_defaults_to_loop`） |
| TC-NS-03 | 同上「记忆分区封存」（读取侧） | 共享记忆含 `beast.*` 与 `loop` 两条同 query 条目；分别 `read(query)` / `read(query, exclude_source_prefixes=("beast.",))` | 缺省仍返回两条（**缺省检索语义不变**）；显式排除 ⇒ 只返回 `loop` 条（锚点：`::test_read_excludes_source_prefixes_but_default_is_unchanged`） |
| TC-NS-04 | 同上（预算 / 强化口径） | 先缺省 `read` 一次（两条都被强化），再带排除 `read` 一次，比对 `reuse_count` | 命中项 +1；被排除项**不进候选** ⇒ 不占预算、`reuse_count` 不变（锚点：`::test_excluded_entries_do_not_consume_budget_or_reinforce`） |
| TC-NS-05 | 同上 + context-interface §2 | `DynamicAssembler(memory=…)` 缺省 vs `exclude_source_prefixes=("beast.",)` 装配同一 query | 缺省事实含 `beast.*`；开启排除 ⇒ 事实**不含** `beast.*`（锚点：`::test_assembler_exclusion_is_opt_in`） |
| TC-NS-06 | orchestration-interface §3（向后兼容） | `TaskHandoff(task="design")` 与 `TaskHandoff(task="design", session_id="beast.qinglong")` | 缺省 `session_id == ""`（既有调用零改动）；显式传值原样保留（锚点：`::test_task_handoff_session_id_is_backward_compatible`） |
| TC-NS-07 | 同上（**转交**，非仅加字段） | 真实 `DefaultLoop(memory=store, source="beast.baihu")` 经 `MultiAgentRouter.handoff(..., TaskHandoff(session_id="beast.baihu"))` | 子 loop 落库条目 `session_id == "beast.baihu"`（证明已接线）（锚点：`::test_handoff_forwards_session_id_to_sub_loop`） |
| TC-NS-08 | beast-mode/spec.md `:54`（E37 端到端） | `build_runtime` + 离线 LLM 替身，`beast_activator.activate_from_cli("qinglong", ["设计架构"])` | 共享记忆出现 `source == "beast.qinglong"` **且** `session_id == "beast.qinglong"` 的条目（**由真实 loop 写入**；改前为 `source="loop"` 混入主记忆）（锚点：`::test_production_summon_writes_beast_namespace_through_real_loop`） |
| TC-NS-09 | 同上 `:89`「记忆分区封存」（E38 端到端） | 召唤后向共享记忆补一条 `loop` 事实，读主 loop 装配器（`runtime.loop` 的 planner）对同一 query 的事实集 | 事实**含** `loop`（不误伤）、**不含**任何 `beast.*`（封存生效）（锚点：`::test_main_loop_context_excludes_sealed_beast_partition`） |
| TC-NS-10 | pet-mode/spec.md「偏好追踪」（fail-soft） | 无记忆后端 / 空文本 / `"editor: vim"` 三种输入调 `PetSession.observe_owner` | 无后端 ⇒ `None` 且 `prefer` 为 `None`（不抛）；空文本 ⇒ `None` 且**零写入**；正常文本 ⇒ 落 L2 `source="user"` 且 `prefer("editor") == "vim"`（锚点：`::test_observe_owner_is_fail_soft_without_memory` / `::test_observe_owner_records_preference` / `::test_observe_owner_ignores_blank_text`） |
| TC-NS-11 | pet-mode/spec.md `:231-234`（E39 端到端） | 生产入口激活：`activate_from_cli("gather", ["editor: vim"])` | 共享 L2 有 `source="user"` 偏好条目、`prefer("editor") == "vim"`、`surprise()` **非 `None`** 且含 `editor=vim`（走真实 loop；改前恒 `None`）（锚点：`::test_production_pet_activation_observes_owner_and_enables_surprise`） |
| TC-NS-12 | 同上 换活入口（控制面） | `PetControl.assign("theme: dark", session_id=…)` | 同一观察口径生效（`prefer("theme") == "dark"`）—— 主人行为入口不止激活一处（锚点：`::test_pet_control_assign_observes_owner`） |
| TC-NS-13 | 同上 R7「**不谎报**」（反例 ×2） | `/pet` 斜杠激活（合成 goal）与 CLI 空 `rest`（合成 goal） | 两者 `_preferences` 均为空、共享记忆**零** `source="user"` 条目（合成文案不观察）（锚点：`::test_slash_activation_does_not_fabricate_preference` / `::test_cli_without_owner_text_does_not_observe`） |

---

## 29. 神兽模式（TC-BEAST）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-BEAST-01 | beast-mode「Task Result Visibility」结果可见性（change `0113`／ADR-0106，账本 E46） | 未执行会话 / 已执行会话分别调 `BeastSession.result_summary()`；经 `summon` CLI（真 argv，runtime 打桩 + fake router）召唤；无 router 的 manager 再召唤一次；查询与召唤全流程挂 `_SpyMemory` | 未执行 ⇒ `has_result=False`、`reply=None`（**不编造**）；已执行 ⇒ 返回 `{agent_id, has_result, reply, failed}`（数据源 = `last_result`，`failed` 如实）；CLI stdout 含结果正文与成败；**无结果时不打印结果行**（不谎报）；查询与召唤**零 L2 写入** —— 封存语义（`source=beast.*` 不被主 loop read 命中）不受结果面影响（锚点：`tests/test_beast_result_visibility.py::test_result_summary_before_run_reports_no_result` / `::test_result_summary_exposes_reply_and_failure` / `::test_result_summary_reflects_failed_run` / `::test_query_writes_nothing_to_memory` / `::test_summon_does_not_write_result_to_l2` / `::test_cli_summon_prints_result_reply` / `::test_cli_summon_without_router_does_not_fabricate_reply`） |

---

## 30. 按会话隔离记忆（TC-SESS）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-SESS-01 | memory/spec.md「按会话隔离的检索」（change `0114`／ADR-0107） | 同店写 A / B / 未归属三组同 query 条目，`read(session_id="A")` | 只返回 `{本会话 A, 全局层未归属}`（锚点：`tests/test_session_isolation.py::test_read_scopes_to_session_plus_global_layer`） |
| TC-SESS-02 | 同上（**反例守门**） | 同上看 `read(session_id="B")` | **不含** A 会话条目 —— 会话之间内容严格隔离（锚点：`::test_other_session_facts_are_invisible`） |
| TC-SESS-03 | 同上（缺省兼容） | `read(query)` 与 `read(query, session_id="")` | 两者**逐字一致**：三组全出现、不过滤（fail-open，未归属调用者不属任何会话）（锚点：`::test_blank_session_id_does_not_filter`） |
| TC-SESS-04 | 同上「过滤先于预算」 | 两会话同长条目，先缺省 `read` 一次，再 `read(budget=1, session_id="A")`，比对 `reuse_count` | 返回项为 A 条（B 条被滤 ⇒ 不占预算）；命中项 +1，被滤项 `reuse_count` **不变**（锚点：`::test_session_filter_precedes_budget_and_reinforcement`） |
| TC-SESS-05 | 同上「与来源排除可叠加」 | A 会话含 `loop` 与 `beast.qinglong` 各一条，`read(session_id="A", exclude_source_prefixes=("beast.",))` | 两条件同时生效，只返回 A 的 `loop` 条（锚点：`::test_session_filter_composes_with_source_exclusion`） |
| TC-SESS-06 | context/spec.md「动态上下文构建」 | 记录型 `read` 替身的装配器分别 `build(session_id="A")` / `build()` | 前者 `read` 收到 `session_id="A"`；后者**不含**该实参（缺省调用形态与既往逐字一致）（锚点：`::test_assembler_forwards_session_id_only_when_present`） |
| TC-SESS-07 | loop/spec.md「会话标识参与推理期检索」（端到端反向守门） | `build_runtime` + A 会话事实，主 loop 规划器分别对 A / B 上下文调 `_system_prompt` | A 的 prompt 含该事实、**B 的不含**（改前 B 可见）（锚点：`::test_prompt_from_one_session_never_reaches_another`） |
| TC-SESS-08 | loop-interface §1（`LoopContext.session_id`） | `astream(session_id="A")` 驱动记录型 planner；再 `perceive("任务")` | 上下文包 `session_id == "A"`（标识真的落到推理期）；缺省 `perceive` 一参调用仍为 `""`（锚点：`::test_loop_threads_session_id_onto_context`） |
| TC-SESS-09 | skills/spec.md「技能路由」+ loop-interface §3（调用形态红线） | `LLMPlanner(skill_router=<1 参 lambda>)._skill_hints("任务一")` | 空标识下**只传 1 实参** ⇒ 既有 1 参替身/闭包不被逼改签名（锚点：`::test_planner_skill_hint_call_shape_is_backward_compatible`） |
| TC-SESS-10 | 同上（透传） | `planner._skill_hints("任务二", "A")` | 路由回调收到 `("任务二", "A")`（会话是归属维度、不只用于记忆写入）（锚点：`::test_planner_forwards_session_to_skill_router_when_present`） |
| TC-SESS-11 | skills/spec.md「技能路由」未命中归属 | `SkillRouter(SkillLibrary(), memory=store).match("无人认领…", session_id="A")` | 未命中条目 `session_id == "A"`、id 为 `skills.miss.A.1`；B 会话 `read` 检索不到它（锚点：`::test_router_miss_record_is_session_scoped`） |
| TC-SESS-12 | 同上（缺省键） | `match("无人认领…")`（不传会话） | id 为 `skills.miss.default.1`、`session_id == ""`（旧调用形态结果逐字不变）（锚点：`::test_router_miss_defaults_to_default_key`） |
| TC-SESS-13 | context/spec.md「上下文自动压实」 | `Compactor.persist(compact(...), session_id="s1")` | 产物 `session_id == "s1"`、id 为 `compaction.fact.s1.0`（锚点：`::test_compactor_persist_attributes_session`） |
| TC-SESS-14 | 同上（缺省键） | `persist(compact(...))` | id 为 `compaction.fact.default.0`、`session_id == ""`（沿用 store 内既有 `session_id or "default"` 口径）（锚点：`::test_compactor_persist_defaults_to_default_key`） |
| TC-SESS-15 | 同上（**反例守门**：跨会话覆盖） | 两会话各压实一次 | 两条产物**并存**（改前 `compaction.fact.0` 后者覆盖前者）（锚点：`::test_two_sessions_compaction_does_not_overwrite`） |
| TC-SESS-16 | pet-mode/spec.md「Pet Session Runtime Wiring」 | 记录型 loop 的 `PetSession(session_id="pet-1")`，`start` + `wake` | `run` 收到 `session_id="pet-1"`（宠物轨迹按宠物会话归属）（锚点：`::test_pet_trajectory_carries_pet_session_id`） |
| TC-SESS-17 | 同上（缺省非空） | `PetSession().session_id` | 为可解析 uuid（始终非空 ⇒ 宠物轨迹天然不进任何前台会话检索）（锚点：`::test_pet_default_session_id_is_non_blank`） |
| TC-SESS-18 | orchestration/spec.md「子任务拆解」 | 真 `TaskScheduler` + 记录型子 loop，`run("task", "goal", session_id="A")` | 子 Agent `arun` 收到 `session_id="A"`（子任务轨迹按发起会话归属）（锚点：`::test_scheduler_forwards_session_id_to_sub_loop`） |
| TC-SESS-19 | 同上（缺省兼容） | `run("task", "goal")`（不传会话） | 子 loop 收到 `""`（与既往语义逐字一致）（锚点：`::test_scheduler_default_keeps_sub_loop_call_unchanged`） |
| TC-SESS-20 | notes/spec.md「Consult → Build → Update 循环纪律」（**显式全局层**） | 内省 `NoteStore.digest` / `consult` / `observe_turn` 参数名 | 三者均**不含** `session` 维度 —— 可执行地钉住「笔记不参与会话隔离」（锚点：`::test_notes_api_has_no_session_dimension`） |
| TC-SESS-21 | 同上「笔记不参与会话隔离」 | 真 `NoteStore` 写入一篇，`DefaultLoop(notes_consult=digest)` 在 A / B 两会话下各 Consult 一次 | 两处 `ctx.notes` **相同**且非空（刻意知识跨会话共享）（锚点：`::test_notes_consult_is_not_session_scoped`） |
| TC-SESS-22 | context/spec.md「上下文自动压实」（id 口径变更） | 既有压实链路用例的产物 id 断言 | `compaction.fact.default.0`（缺省会话键；**id 口径变更而非放宽语义**）（锚点：`tests/test_loop.py::test_loop_compaction_persists_history_and_summarizes_prior_memory`） |

---

## 31. 对话转录与会话历史回灌（TC-XSCRIPT，change `0115`／ADR-0108，账本 E49）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-XSCRIPT-01 | memory/spec.md「对话转录持久化（非记忆层级）」 | `TranscriptStore` append 两条后 `read`；换同路径新实例再 `read` | 往返一致；**跨实例可见**（落盘而非进程内） |
| TC-XSCRIPT-02 | 同上（**反例守门**） | A 会话 append 后 `read("B")` | 空 —— 会话之间转录互不可见（锚点：`tests/test_transcript.py::test_read_is_scoped_by_session`） |
| TC-XSCRIPT-03 | 同上（未归属不落盘） | `append("", "user", "孤儿")` | 纯 no-op（`messages.jsonl` **根本不创建**）（锚点：`::test_unaffiliated_append_is_noop`） |
| TC-XSCRIPT-04 | 同上（`tail` 轮边界） | `tail(sid, turns)` 取 0 / 大于总轮数 / 正常 | `turns=0` ⇒ 空；大于总数 ⇒ 全部；按**轮**（user 起始）切片，尾部未答 user 行**保留** |
| TC-XSCRIPT-05 | 同上（`tail` token 上界） | 5 轮各 160 字符（40 token），`max_tokens=100` 从新到旧累加 | 只留最近 2 轮；**截断后不从中途起**（开头孤儿 assistant 行一并丢弃）（锚点：`::test_tail_token_bound_drops_oldest_lines` / `::test_tail_token_bound_never_starts_mid_round`） |
| TC-XSCRIPT-06 | 同上（降级） | 缺文件 `read`；文件混入坏行 | 缺文件 ⇒ `[]`；坏行**跳过**、不抛（不阻断主流程） |
| TC-XSCRIPT-07 | 同上（`summaries` 派生） | 两会话各写若干条 | `{sid: {title, updated_at}}`；`title` = **首条用户消息**压平换行截断 30 字（超长补「…」）；`updated_at` = 最近一条时间戳；**排除未归属**（锚点：`::test_summaries_title_from_first_user_message`） |
| TC-XSCRIPT-08 | 同上（**反例守门**：非记忆层级） | 转录写入后 `MemoryStore.read` | 结果**不含**转录内容；反向：`MemoryStore.write` 不落进转录（锚点：`tests/test_transcript_memory_boundary.py::test_transcript_never_returned_by_memory_read` / `::test_memory_write_never_reaches_transcript`） |
| TC-XSCRIPT-09 | loop/spec.md「执行循环」回灌 | 真 `DefaultLoop` + 真转录，第二轮捕获 LLM 请求 | 序列 `[system, 历史 user, 历史 assistant, 本轮 user]`（锚点：`tests/test_history_replay.py::test_history_replayed_between_system_and_current_turn`） |
| TC-XSCRIPT-10 | 同上（**四处 accessor 红线**） | 有历史时读 `_task_text` / `_echo` / `LLMPlanner._task` / `_action_steps` / `ctx.messages` | 只见**本轮**（历史在 `ctx.history`，不被当本轮任务/动作序列）（锚点：`::test_current_turn_accessors_see_only_this_turn`） |
| TC-XSCRIPT-11 | 同上（双重上界与关闭） | `history_turns=1` 有 2 轮历史；`history_turns=0`；未注入转录；`session_id=""` | 前者只回灌 1 轮；后三者**零回灌**（锚点：`::test_history_turns_bound_limits_replayed_rounds` / `::test_history_turns_zero_disables_replay` / `::test_no_transcript_means_no_history` / `::test_empty_session_id_never_replays`） |
| TC-XSCRIPT-12 | 同上（历史计入记账） | 200 token 历史 + 本轮，捕获 `ctx.token_used` | 历史 token **计入** `token_used`（预算终止/压实看得见它）（锚点：`::test_history_tokens_counted_into_budget`） |
| TC-XSCRIPT-13 | 同上（落盘时点与门控） | 一轮成功 / 预算耗尽轮（`max_rounds=0`）/ `remember` 抛错 / 推理抛错 | 成功 ⇒ 落 (user, reply) 两条；**终止轮不落合成串**（只留 user 行）；`remember` 抛错 **不影响**已落盘对话（锚点：`tests/test_history_persistence.py::test_turn_failed_with_synthetic_reply_writes_no_reply` / `::test_transcript_lands_before_memory_write` / `::test_user_line_survives_later_failure`） |
| TC-XSCRIPT-14 | 同上（缺省逐字兼容） | `astream("未归属的一轮")`（不传 `session_id`） | 零写入（`messages.jsonl` 不存在）（锚点：`::test_empty_session_id_writes_nothing`） |
| TC-XSCRIPT-15 | ui/spec.md「会话转录的读取面」 | `GET /session/{id}/messages` 正常 / 未登记 | 正常 ⇒ 按追加次序返回；未登记 ⇒ **404 `UI_SESSION_NOT_FOUND`**（不放宽）（锚点：`tests/test_serve.py::test_session_messages_returns_transcript` / `::test_session_messages_unknown_session_404`） |
| TC-XSCRIPT-16 | 同上（枚举派生字段） | `GET /sessions` 注入 / 未注入转录 | 注入 ⇒ 条目附 `title`/`updated_at`（无用户消息 ⇒ `title` 空串、`updated_at` 回落 `created_at`）；未注入 ⇒ 形状**逐字不变**（锚点：`::test_sessions_entry_enriched_with_derived_title` / `::test_sessions_entry_without_transcript_gets_empty_title` / `::test_sessions_entry_shape_unchanged_without_transcript`） |
| TC-XSCRIPT-17 | configuration/spec.md「循环预算配置」 | `loop.history_turns` 缺省 / yaml / env / CLI 四面；非法值 | 缺省 `20`；优先级 CLI > env > yaml；非 ≥0 整数 ⇒ **阻断启动**（报「非法回灌轮数」）；`loop_limits()` **仍 2 元组**（既有 20+ 处解包断言不动）（锚点：`tests/test_loop_budget_config.py::test_history_turns_spec_declared` / `::test_invalid_history_turns_blocks_startup` / `::test_history_turns_keeps_loop_limits_arity`） |
| TC-XSCRIPT-18 | ui/spec.md「会话注册表持久化与跨入口共享」 | 32 线程并发 `create`，换新实例 `list` | 除重后条数 == 线程数（进程内互斥不丢会话）（锚点：`tests/test_session_registry.py::test_concurrent_create_in_process_loses_nothing`） |

---

## 32. 会话列表面与 CLI 会话可见面（TC-XLIST，change `0116`／ADR-0109，账本 E49 B2）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-XLIST-01 | cli-ops/spec.md「会话命令族与交互入口续聊」 | 建会话 + 写 (user, assistant) 两条 → `session show <id>` | 按追加次序打印两行（user 先于 assistant），取自**同一** `TranscriptStore`（锚点：`tests/test_entry.py::test_session_show_prints_transcript`） |
| TC-XLIST-02 | 同上（无转录） | 已登记但无转录的会话 → `session show <id>` | 明示「无对话记录」、退出码 0（不伪造内容）（锚点：`::test_session_show_without_transcript`） |
| TC-XLIST-03 | 同上（**反例**：未登记） | `session show nope` | 退出码 1 + stderr 提示（fail-closed，不放宽会话校验）（锚点：`::test_session_show_unknown_session_rejected`） |
| TC-XLIST-04 | 同上（交互入口续聊） | 顶层 `--session <id>` 进 REPL / 缺省 | 标识透传至 `CLIBridge`；缺省透传**空串**（由 REPL 新建，既有行为不变）（锚点：`::test_repl_resumes_session_via_flag` / `::test_repl_without_flag_passes_empty_session`） |
| TC-XLIST-05 | 同上（续聊复用不新建 + 呈现） | `build_app(api, session_id=<已登记>)`，`create_session` 替换为断言失败 | **不新建**会话；既有转录（user/assistant）渲染进时间线（锚点：`tests/test_repl.py::test_build_app_resumes_existing_session`） |
| TC-XLIST-06 | 同上（**反例**：续接未登记） | `build_app(api, "nope")` | 抛 `UiError`；注册表**仍为空**（不静默新建顶替）（锚点：`::test_build_app_rejects_unknown_session`） |
| TC-XLIST-07 | 同上（缺省不回归） | `build_app(api)` | 新建 1 个 CLI 会话（缺省路径逐字不变）（锚点：`::test_build_app_default_creates_session`） |
| TC-XLIST-08 | 同上（桥接透传） | `CLIBridge(api, connect_impl=…)` 默认 / `session_id="sid-1"` | `connect_impl(api, "")` / `connect_impl(api, "sid-1")`（注入点签名对齐）（锚点：`tests/test_ui.py::test_three_modes_share_api_layer`） |
| TC-XLIST-09 | ui/spec.md「Web 会话列表与切换」 | SPA 构建 + 临时 `CORE_STATE_DIR` 起 `serve` 冒烟 | `npm run build` 通过；`GET /sessions` 呈派生标题、`GET /session/{id}/messages` 可读、SPA 静态产物挂载到 `/`；列表 / 切换 / 新建为显式动作（**无 JS 测试基建** ⇒ 以构建 + 离线冒烟为据，见 change 0116 `tasks.md` §5） |

---

## 33. 未命中记录 id 唯一化与神兽召回自身轨迹（TC-MISS，change `0117`／ADR-0110，账本 E48-b / E54）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-MISS-01 | skills/spec.md「技能路由」（未命中记录的归属与唯一性） | 同一 `MemoryStore` 上先后构造两个 `SkillRouter`（模拟**进程重启**）各记一次未命中 | 两条 **id 不同**（内容派生 ⇒ 重启后不互相覆盖）（锚点：`tests/test_skills.py::test_miss_id_survives_process_restart`） |
| TC-MISS-02 | 同上（幂等） | 同会话对**同一任务**连续两次 `match` 未命中 | 只留 **1** 条（同任务幂等刷新，不增长）（锚点：`::test_duplicate_miss_same_task_is_idempotent`） |
| TC-MISS-03 | 同上（有界） | 同一 router 记 500 条不同任务 | `len(router.misses) < 500` 且末条为**最新**任务（窗口裁剪保留尾部，`_MISS_WINDOW = 64`）（锚点：`::test_miss_diagnostic_window_is_bounded`） |
| TC-MISS-04 | 同上（会话键口径不回归） | 未命中记录的 id 与会话归属 | id 仍以 `skills.miss.<会话键>.` 开头（change `0114` 契约保留，不再钉计数后缀）（锚点：`tests/test_session_isolation.py::test_router_miss_record_is_session_scoped` / `::test_router_miss_defaults_to_default_key`） |
| TC-MISS-05 | memory/spec.md「来源前缀排除与放行（读取面）」 | 同店写 `q1(beast.qinglong)` / `h1(beast.baihu)` / `m1(loop)`；`read(exclude=("beast.",), allow=("beast.qinglong",))` | 返回 `{q1, m1}` —— **放行自身**、**他兽仍排除**、主来源不受影响（锚点：`tests/test_memory_namespace.py::test_read_allow_source_prefixes_carves_out_own_namespace`） |
| TC-MISS-06 | 同上（缺省无副作用） | `allow` 非空但 `exclude` 为空 / 两者皆空 | 与既往**逐字一致**（无排除即无所放行）（锚点：`::test_allow_source_prefixes_without_exclusion_is_noop`） |
| TC-MISS-07 | context-interface.md §2（派生装配器） | `DynamicAssembler(exclude=("beast.",))` 派生出放行自身的实例 | 派生实例只含自身命名空间条目；**原实例**的检索结果不变（封存不受影响）（锚点：`::test_assembler_can_be_derived_for_one_namespace`） |
| TC-MISS-08 | beast-mode/spec.md「Independent Sub-Agent with Shared Capability」（自身轨迹可召回） | 真 `Runtime` 神兽会话的 `_planner._assembler.build(…, session_id="beast.qinglong")` | 含 `beast.qinglong`、**不含** `beast.baihu`；**主**装配器 facts 无任何 `beast.` 源（双向守门）（锚点：`tests/test_beast_wiring.py::test_beast_loop_recalls_own_namespace_only`） |

---

## 34. 宠物记忆独立命名空间（TC-PETNS，change `0118`／ADR-0111，账本 phase-30 §8-A）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PETNS-01 | pet-mode/spec.md「Pet Session Runtime Wiring」（宠物轨迹落独立命名空间） | 真 `Runtime` 激活宠物并 `wake()` 跑完一轮自治任务 | 共享记忆中 `source=pet` 的条目存在，且其 `session_id` **全为**该宠物会话 id（命名空间 + 会话个体双维度）（锚点：`tests/test_pet_memory_namespace.py::test_production_pet_trajectory_lands_in_pet_namespace`） |
| TC-PETNS-02 | 同上（主 Agent 检索面封存宠物命名空间） | 宠物跑完一轮后，主 loop 真实装配器以 `session_id=""`（会话面**不过滤**，改前泄漏路径）检索 | facts 无 `source=pet` 条目、**且**无宠物回复正文（内容级守门）；主线条目**仍出现**（反例守门）（锚点：`::test_main_loop_context_seals_pet_partition`） |
| TC-PETNS-03 | 同上（宠物自身轨迹可召回） | 宠物真实装配器（派生、放行 `pet`）检索，库中另有 `beast.qinglong` | 含 `pet`、**不含** `beast.qinglong`（封存不放行他者）（锚点：`::test_pet_loop_recalls_own_namespace_only`） |
| TC-PETNS-04 | 同上（主人偏好不受封存影响） | `source=user` 偏好 + `source=pet` 轨迹同店，主侧检索 | 偏好条目**仍出现**（刻意知识全局层，逐字不动）（锚点：`::test_user_preference_survives_pet_sealing`） |
| TC-PETNS-05 | 同上（红线：不放宽神兽封存） | 主装配器排除面新增 `pet` 后 | 仍**不含**任何 `beast.*` 源（phase-26 E37/E38/E39 逐字不动）（锚点：`::test_pet_sealing_does_not_relax_beast_sealing`） |

---

## 35. 结晶面门的数据面与留出评测（TC-EVGD，change `0119`／ADR-0112，账本 Phase 31 切片 1：G4+G3）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-EVGD-01 | evolution/spec.md「评测基建」（change `0119`） | `BenchmarkRegistry(path=tmp)` 注册基准 + 设基线后用**同 path 的新实例**读回；损坏 JSON / 结构不符 / 文件缺失三态；`BenchmarkRegistry()` 无 path | 跨进程可读（`list()` 与基线分一致）；损坏 ⇒ 空表 + `warnings` 留痕 + 不抛；**缺失静默**（不告警）；无 path ⇒ 纯内存（既有调用方零行为变化）（锚点：`tests/test_evolution_gate_data.py::test_registry_persists_across_instances` / `::test_registry_corrupt_file_degrades_with_warning` / `::test_registry_missing_file_is_silent` / `::test_registry_without_path_stays_in_memory`） |
| TC-EVGD-02 | evolution/spec.md「留出评测」（change `0119`） | 候选 + 绑定基准（含样本）+ 已注册执行器；无绑定基准 / 无样本 / 无该 `task_type` 执行器；执行器抛异常 | 留出分 = 逐样本真实执行与期望对比后的聚合（全对 ⇒ 1.0、部分对 ⇒ 中间分）；**无法评测 ⇒ 打分器返 `None`**（不产出分数）；执行器异常**冒泡**（不吞成 0 分、不吞成通过）（锚点：`::test_scorer_scores_samples_by_real_execution` / `::test_scorer_partial_match_scores_between` / `::test_scorer_returns_none_when_unable_to_evaluate` / `::test_scorer_propagates_runner_errors` / `::test_benchmark_binds_to_plugin`） |
| TC-EVGD-03 | evolution/spec.md「留出评测」（change `0119`） | `Evaluator.evaluate` 三态：真实打分高于 / 低于已注册基线、无 `score_fn`、有基准+执行器但**未注册基线**；`run_cycle` 在**生产形状**（落盘 registry + 打分器 + 无 runner）与「注册基准 + 基线 + 执行器」两态 | 不退化 ⇒ `publish`、退化 ⇒ `rollback`（生产可达，G5 锚点）；无 `score_fn` / 未注册基线 ⇒ **`freeze`**（不报 publish、不谎报 rollback）；`run_cycle` 相应记 `frozen` / `rollback`（词表 +1 `frozen`，与「已判退化」语义分离）（锚点：`::test_evaluator_publishes_when_not_regressed` / `::test_evaluator_rollback_still_reachable` / `::test_evaluator_freezes_when_score_unavailable` / `::test_evaluator_freezes_without_baseline` / `::test_run_cycle_freezes_in_production_shape` / `::test_run_cycle_rollbacks_with_registered_benchmark`） |
| TC-EVGD-04 | evolution/spec.md「验证门」（change `0119`） | 旧口径候选（`caliber=0`，模拟落盘旧行）`confirm` 后 `crystallize`；现口径候选正常投放；`PendingQueue(path=…)` 记录候选后重开 + 手工剔除 JSON 中 `caliber` 字段后重读 | 旧口径 ⇒ `GATE_CALIBER_STALE` 结构化拒绝、**不发布**、理由**不含**「退化」；现口径 ⇒ 正常 `published`；`caliber` 随台账落盘读回、**缺字段旧行解析为 0**（不 fail-open）（锚点：`::test_crystallize_rejects_stale_caliber` / `::test_crystallize_allows_current_caliber` / `::test_caliber_persists_with_pending_queue`） |
| TC-EVGD-05 | evolution/spec.md「留出评测」+「评测基建」（change `0119`，装配级 + 回归改判） | 真 `build_runtime`（未注册任何基准）下 `runtime.evolution.engine.run_cycle`；既有依赖「缺省即 publish」的用例显式注入能通过的打分器 | 生产装配的评估器**不再是「无参裸桩」** ⇒ 未注册基准时判 `frozen`（真门，非恒通过桩）；既有用例改**显式注入**打分器后仍**真实过门**（读数器仍是真门，非绕过评测 —— 改判理由见 ADR-0112）（锚点：`tests/test_evolution_gate_data.py::test_runtime_evaluator_is_a_real_gate` / `tests/test_evolution.py`（46 例）/ `tests/test_evolution_attribution.py` / `tests/test_evolution_pending.py` / `tests/test_phase14.py` / `tests/test_phase15.py`） |

---

## 36. 结晶面门判定面真实化（TC-EVGJ，change `0120`／ADR-0113，账本 Phase 31 切片 2：G1+G2+G5）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-EVGJ-01 | evolution/spec.md「验证门」+ ci-cd（change `0120`） | `crystallization_gates()` 与单一真源 `GATE_COMMANDS` 的关系；标记键/值面；标记命中**未注册**门名（monkeypatch 标记） | 子集 = `lint` + `test`、**顺序随真源**、命令字符串仍只有一份；`typecheck` / `build`（交付面）不入子集（子集 ∪ 二者 = 全集）；标记只带**门名**（值非命令字符串）；漂移 ⇒ `CiCdError(GATE_FAILED)`（fail-closed）（锚点：`tests/test_evolution_gate_judgment.py::test_crystallization_gates_derived_from_single_source` / `::test_crystallization_gates_exclude_delivery_face_gates` / `::test_crystallization_marks_unknown_gate_fails_closed` / `::test_crystallization_marks_carry_names_not_commands`） |
| TC-EVGJ-02 | evolution/spec.md「验证门」（change `0120`） | `build_review_prompt` 的判据面；`parse_review` 词表参数化表（PASS / pass / 通过 / 前导空行；REJECT / 拒绝 / 含糊 / 空）；`review_with` 三态（PASS / 不可解析 / 调用抛异常） | prompt 带 `kind` / `target_plugin` / `delta` 与判定词表；**只认首行以通过词起首**，词表外一律 `False`；调用抛异常 ⇒ `False`（不外抛）（锚点：`::test_review_prompt_carries_candidate_facts` / `::test_parse_review_fail_closed` / `::test_review_with_llm_passes` / `::test_review_with_llm_garbage_denies` / `::test_review_with_llm_failure_denies`） |
| TC-EVGJ-03 | evolution/spec.md「验证门」（change `0120`） | `run_gate_tests`（只跑标记子集 / 某门未过 / 执行面抛异常）；`Validator` 判据组合：缺省无参、只注入一半、两判据皆过、review 拒、某门禁未过、空测试集 | 逐门执行、结果按门名收集且值**恒 `bool`**；抛异常 ⇒ 该门 `False`；**缺省 `Validator()` ⇒ `passed=False` 且理由含「未注入」**；review 拒 ⇒ 门未过且**不跑**门禁（fail-fast）；空测试集**不得**当通过（`all({})` 为真即 G2 成因）（锚点：`::test_run_gate_tests_runs_only_marked_gates` / `::test_run_gate_tests_marks_failed_gate` / `::test_run_gate_tests_runner_exception_fails_closed` / `::test_default_validator_denies` / `::test_validator_denies_when_only_one_producer_injected` / `::test_validator_passes_when_both_judgments_pass` / `::test_validator_denies_when_review_rejects` / `::test_validator_denies_when_a_gate_fails` / `::test_validator_denies_on_empty_test_set`） |
| TC-EVGJ-04 | evolution/spec.md「验证门」（change `0120`，G5 锚点） | 装真判据（真 `review_with` + 真 `run_gate_tests`）后 `run_cycle`：未过门 / 过门；`GATE_CALIBER` 读数 | 未过门 ⇒ `status="rejected"`（**生产可达**，不再恒 pending）；门过 ⇒ 进留出评测（无基准 ⇒ `frozen`，非 `rejected`）；`GATE_CALIBER >= 2`（判定面真实化已递增口径）（锚点：`::test_run_cycle_reports_rejected_on_failed_gate` / `::test_run_cycle_reaches_eval_when_gate_passes` / `::test_gate_caliber_bumped_for_judgment_face`） |
| TC-EVGJ-05 | evolution/spec.md「验证门」（change `0120`，装配级 + 回归改判） | 真 `build_runtime` 下 `run_cycle`（模型提供者与门禁子进程两外部面打桩）：审查者判过 / 模型端点不可用；既有依赖「缺省 `Validator()` 即通过」的测试文件显式注入过门替身 | 生产装配**真的走**真 review + 真门禁子集（实际跑 `["lint", "test"]`）⇒ 全过进留出评测 ⇒ `frozen`；模型不可用 ⇒ `rejected` 且门禁**零调用**（fail-fast）；既有用例改**显式注入**判据后仍**真实过门**（读数器仍是真 `Validator`，汇总逻辑不打折 —— 改判理由见 ADR-0113）（锚点：`tests/test_evolution_gate_judgment.py::test_runtime_runs_real_review_and_marked_gates` / `::test_runtime_denies_when_review_unavailable` / `tests/test_evolution_gate_data.py::test_runtime_evaluator_is_a_real_gate` / `tests/test_evolution.py`（46 例）/ `tests/test_evolution_attribution.py` / `tests/test_evolution_pending.py` / `tests/test_phase14.py` / `tests/test_phase15.py`） |

---

## 37. 子任务运行态实时回流（TC-OSP，change `0121`／ADR-0114，账本 E51）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-OSP-01 | orchestration/spec.md「任务入口与进度事件」（子任务运行态回流） | 真 `TaskScheduler` + 真 `DefaultLoop`（planner 先调 `tools.echo` 再终止）执行单子任务，收集 `astream` 事件 | 里程碑依序外发为 `subtask_progress`（`action_started` / `action_completed` / `step_completed` ×2），每条带 `task_id` / `subtask_id` / `float ts`；且 `subtask_progress` 索引 **<** `subtask_completed`（**实时**而非收尾补发）（锚点：`tests/test_orchestration_progress.py::test_milestone_events_relayed_as_subtask_progress`） |
| TC-OSP-02 | 同上（回流粒度） | 流式 planner 逐 delta 外发自然语言后给终 Action | 里程碑**仍**回流，但 `reply_delta` **绝不出现在** `subtask_progress` 中，正文不外泄（洪泛 + 未定稿原文双重排除）（锚点：`::test_reply_delta_never_relayed`） |
| TC-OSP-03 | 同上（载荷白名单） | 内层事件载荷**多带**字段（`args` 旁挂 `api_key`、`output` 旁挂 `secret`） | 每条 `subtask_progress.data` 的键集 **⊆** 该事件类型的白名单（`action_started` → round/tool_id/args；`action_completed` → round/tool_id/ok/duration_ms/output；`step_completed` → round/failed）；疑似凭据**不外发**（锚点：`::test_payload_is_whitelisted_per_event_type`） |
| TC-OSP-04 | 同上（表外类型不外发） | 内层流含 `custom_event` / `loop_started` | **零** `subtask_progress`（白名单外类型含未来新增一律静默丢弃）（锚点：`::test_unknown_event_type_not_relayed`） |
| TC-OSP-05 | 同上（附加通道、终态不变）+ loop-interface §2.1 | 有里程碑 / 无里程碑两次运行比对 `SubtaskOutcome`；`arun` 与 `collect_result(astream)` 同轮比对（成功轮 / `loop_failed` 轮） | 终态 `(ok, trace_id, reply)` **逐字一致**（回流不改判定）；`arun` 即 `collect_result·astream` 薄壳 ⇒ 成功/失败两态回复与 `failed` 逐字一致（终态归一单一真源）（锚点：`::test_progress_is_additive_terminal_outcome_unchanged` / `::test_collect_result_matches_arun_on_success` / `::test_collect_result_normalizes_loop_failed`） |

---

## 38. 编排任务的 HTTP 面与 Web 任务区（TC-TASKHTTP，change `0122`／ADR-0115，账本 E53）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-TASKHTTP-01 | ui/spec.md「任务编排的 HTTP 面与 Web 任务区」（HTTP 派发任务并流式呈现进度） | 真 `TaskScheduler`（单子任务 + 假子 Agent loop：`action_started` / `step_completed` / `loop_finished`）经 `UIAPILayer(orchestrator=…)`，`POST /task` 流式读取 | SSE 帧序 **首 `task.task_started`、末 `task.task_finished`**，且 `task_started` < `subtask_started` < **`subtask_progress`** < `subtask_completed` < `task_finished`（change `0121` 的回流事件经**未改动**转发层到达 HTTP 面）；`subtask_started` 载荷带 `subtask_id`/`goal`（任务区标题面）；`subtask_progress` 的 `event` 依序 `action_started`/`step_completed`、`data` 白名单字段逐字（锚点：`tests/test_serve.py::test_task_sse_streams_progress`） |
| TC-TASKHTTP-02 | 同上（未登记会话标识被拒绝） | 未登记 `session_id` 经 `POST /task` | body 含 `UI_SESSION_NOT_FOUND` 错误帧（fail-closed，不放宽既有会话校验）（锚点：`::test_task_unknown_session_sse_error`） |
| TC-TASKHTTP-03 | 同上（编排器未注入时报结构化错误） | 未注入编排器的 `UIAPILayer` 经 `POST /task` | body 含 `UI_ORCHESTRATOR_UNSET` 错误帧（不裸抛、不静默成功）（锚点：`::test_task_without_orchestrator_sse_error`） |
| TC-TASKHTTP-04 | 同上（静态挂载不遮蔽端点，change `0100` 契约延伸） | 挂载 SPA 产物后 `POST /task` | 得 **200**（`StaticFiles` 对 POST 会给 405 ⇒ 200 即已路由到处理器），与既有 11 端点同序注册（锚点：`::test_with_dist_serves_spa_without_shadowing_endpoints`） |

> **Web 任务区**（并列不混池 / 子任务标题·状态·详情 / 收尾回落）无 JS 测试基建 ⇒ 以 `npm run build`
> + 手工冒烟验收（**如实登记为已知局限**，见 ADR-0115）。

---

## 39. 难易度感知的同波次调度策略（TC-DIFF，change `0123`／ADR-0116，账本 E50）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-DIFF-01 | orchestration/spec.md「难易度感知的调度策略」（缺省策略维持既有并发） | 真 `TaskScheduler`（`difficulty_policy` 取缺省）+ 4 个无依赖子任务 + 记录入/出时间线的子 Agent loop，`max_concurrency=2` | 并发峰值 **= 2**（= 上限），与引入本策略前逐字一致（锚点：`tests/test_orchestration_difficulty.py::test_default_policy_keeps_topology_concurrency`） |
| TC-DIFF-02 | 同上（难易度策略下含 hard 的波次串行） | `difficulty_policy="difficulty"` + 同波次混编 `easy` / `medium` / **`hard`**（优先级 0 / 5 / 10） | 并发峰值 **1**，时间线 **严格不重叠**且按优先级降序（`+hard,-hard,+medium,-medium,+easy,-easy`）（锚点：`::test_difficulty_policy_serializes_wave_containing_hard`） |
| TC-DIFF-03 | 同上（难易度策略下无 hard 的波次并发） | `difficulty_policy="difficulty"` + 同波次全为 `easy` / `medium` | 并发峰值 **= `max_concurrency`**（策略**只收窄不放大**，不把无 hard 波次也降级）（锚点：`::test_difficulty_policy_keeps_concurrency_without_hard`） |
| TC-DIFF-04 | 同上（粒度 = 波次 + 依赖拓扑硬约束） | `difficulty_policy="difficulty"`，`e1`/`e2`（easy，无依赖）为波次 1、`h1`/`h2`（hard，`depends_on=["e1"]`）为波次 2 | 波次 1 **并发**（两者先入，窗口重叠）；波次 2 **串行不重叠**；依赖拓扑**未变**（hard 与 easy 仍分属不同波次）（锚点：`::test_only_hard_wave_is_serialized_across_waves`） |
| TC-DIFF-05 | 同上（难易度缺省与非法值归一） | 未声明 / `"urgent"` / `"1"` / `""` / `"very hard"` / `"HARD!"` / `"中"` / 非字符串（`1` / `None` / `1.5` / `["hard"]` / `{"level":"hard"}`） | `difficulty` 全部**归一**为 `medium`（不抛裸异常、不剔除子任务）（锚点：`::test_illegal_difficulty_normalized_to_medium` / `::test_non_string_difficulty_normalized_to_medium`） |
| TC-DIFF-06 | 同上（大小写与空白归一） | `"HARD"` / `" hard "` / `"Easy"` / `" Medium"` | 归一为对应小写档位（`hard` / `easy` / `medium`）——**不**因字面不等降级为 `medium`（锚点：`::test_difficulty_case_and_whitespace_normalized`） |
| TC-DIFF-07 | 同上（难易度随计划持久化往返） | `plan_to_dict` → `plan_from_dict` 往返；以及**缺键**的旧检查点 dict | 往返后 `difficulty` 逐字保留；旧检查点缺键回落 `medium`（**不静默丢字段**；`models.py` 两处枚举同改是其前提）（锚点：`::test_plan_roundtrip_preserves_difficulty` / `::test_plan_from_dict_missing_difficulty_falls_back`） |
| TC-DIFF-08 | 同上（LLM 拆解自报难易度） | 打桩 `LLMProvider`：拆解输出含 `"difficulty": "hard"` | planner 解析后 `Subtask.difficulty == "hard"`（弱信号经 prompt + `_parse` 进入 DAG）（锚点：`::test_planner_parses_difficulty`） |
| TC-DIFF-09 | 同上（构造器取值校验） | `TaskScheduler(difficulty_policy="fast")` | 抛 `OrchestrationError`，`code == INVALID_DISPATCH_POLICY`（fail-fast）（锚点：`::test_invalid_policy_rejected_at_construction`） |
| TC-DIFF-10 | configuration/spec.md「编排调度配置」（三面无第二真源） | `config_specs()` 中两键的 `cli_flag` / `env_var` / `map_to` / `default` | 逐字等于 `--orchestration.difficulty-policy` / `CORE_ORCHESTRATION_DIFFICULTY_POLICY` / `orchestration.difficulty_policy` / `off`，与 `--orchestration.max-concurrency` / `CORE_ORCHESTRATION_MAX_CONCURRENCY` / `orchestration.max_concurrency` / `4`（锚点：`tests/test_orchestration_config.py::test_specs_declare_orchestration_keys`） |
| TC-DIFF-11 | 同上（缺省 / 优先级链 / 段白名单） | 未配置段；yaml 取值；env 覆盖 yaml；CLI 覆盖 env+yaml | 缺省回落 `off` / `4`（与代码缺省一致）；优先级链 CLI > env > yaml 成立；声明段**不**触发「未知配置段」告警（锚点：`::test_defaults_match_code_defaults` / `::test_values_from_yaml` / `::test_env_overrides_yaml` / `::test_cli_overrides_env_and_yaml` / `::test_orchestration_section_is_not_reported_unknown`） |
| TC-DIFF-12 | 同上（非法取值校验期拒绝） | `max_concurrency` ∈ `0` / `-1` / `2.5` / `abc` / `true`；`difficulty_policy` ∈ `fast` / `parallel` / `OFF` / `1` | `ConfigurationError`，报文分别含「非法波次并发上限」/「非法编排调度策略」——**阻断启动**、不静默退化（与 `difficulty` **归一**口径有意不同）（锚点：`::test_invalid_max_concurrency_blocks_startup` / `::test_invalid_policy_blocks_startup`） |
| TC-DIFF-13 | 同上（组合根注入，不得依赖构造缺省） | `build_runtime` 读配置 `difficulty` / `2`；以及未配置时 | `runtime.orchestrator` 的 `_difficulty_policy` / `_max_concurrency` 等于**配置值**（`difficulty` / `2`）；未配置时等于代码缺省 `off` / `4` —— **仍走组合根**（构造缺省 `4` 与既有行为同值，不接线不会暴露）（锚点：`::test_build_runtime_injects_policy_and_limit` / `::test_build_runtime_defaults_unchanged`） |

> **端到端（离线，不触网）**：临时 `config.yaml` 置 `orchestration.difficulty_policy=difficulty` 经
> `build_runtime` 装配真 runtime，打桩拆解器产出「1 hard + 2 easy」同波次子任务 + 记录并发的子 Agent loop
> ⇒ 时间线 `+hard,-hard,+easy1,-easy1,+easy2,-easy2`、峰值 **1**、三子任务全 `ok`（已在 change 落地时
> 手工冒烟，未固化为用例）。

---

## 40. TUI 子任务运行态与里程碑详情（TC-TUI，change `0124`／ADR-0117，账本 E52）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-TUI-01 | ui/spec.md「TUI 子任务运行态与详情」（里程碑事件展开可见） | 编排桩依序回放 `subtask_started` + 三条 `subtask_progress`（`action_started` / `action_completed` / `step_completed`）+ `subtask_completed`；headless TUI 经 `/task` 驱动 | 展开区依序为「验收 → `⏺ Bash` → `⏺ Bash ✓ (1.5s)` → `· 第 1 轮完成` → 判定 → 结果节选」；工具类经**友好名**（`tools.code_run` ⇒ `Bash`）+ 耗时，轮次级落轮次与成败（锚点：`tests/test_repl.py::test_subtask_milestones_render_in_collapsible_detail`） |
| TC-TUI-02 | 同上 + `ui-interface.md` §1.1 注（不暴露内部 id 与原始参数） | 同 TC-TUI-01 的载荷（`tool_id="tools.code_run"`、`args={"code": "print(1)"}`、`output="1"`）；真 `TaskScheduler` 端到端（含 `reply_delta` 模型流式原文） | 时间线文本**不含** `tools.code_run`（内部 id）、**不含** `print(1)`（原始参数）、**不含** `reply_delta` 原文（白名单外）；端到端同断（锚点：TC-TUI-01 同用例 + 端到端冒烟；白名单侧由 `tests/test_orchestration_progress.py` 守门） |
| TC-TUI-03 | 同上（子任务运行中可见状态徽标） | 阻塞式编排器：`subtask_started` 后挂起，`release` 才收尾；运行态中读折叠块标题、收尾后再读 | 运行态标题含 `⟳` 且**不含** `✓`；以 `▸ 子任务 1` 开头（主题与 sid 仍在）；收尾后标题为 `▸ 子任务 1  ✓ 查资料`（**替换**，不并存）（锚点：`::test_subtask_title_shows_running_mark_until_completion`） |
| TC-TUI-04 | 同上（里程碑先于折叠块到达时静默忽略） | 回放「子任务 1 开工 + 子任务 **9**（无对应折叠块）的里程碑 + 子任务 1 的里程碑」；同时数折叠块个数 | `⏺ Read` 只出现 **1** 次（未知 id 的里程碑被忽略）；折叠块个数 **= 1**（未新建块、不抛裸异常）（锚点：`::test_progress_for_unknown_subtask_is_ignored`） |
| TC-TUI-05 | 同上（表外事件不呈现） | 回放表外类型（`event="reason_started"`）与**非字典** `data` 的里程碑，再回放一条合法 `action_completed` | 验收后**紧跟**合法里程碑（表外/异常载荷**不留空行与占位**）；文本不含 `reason_started`（锚点：`::test_non_action_progress_renders_no_line`） |

> **端到端（离线，不触网）**：真 `TaskScheduler`（打桩拆解器 + 打桩子 Agent loop，产出
> `action_started` / `action_completed` / `step_completed` / `reply_delta` / `loop_finished`）经
> `UIAPILayer.run_task` 驱动 headless TUI ⇒ 时间线含 `⏺ Bash` / `⏺ Bash ✓ (1.5s)` / `· 第 1 轮完成`、
> 收尾标题 `▸ 子任务 s1  ✓ 查资料`，且**不含** `tools.code_run` / `print(1)` / 流式原文（8 项断言全绿；
> 已在 change 落地时手工冒烟，未固化为用例）。
> **非交互 CLI（`core-agent task`）不在本 TC 范围**：其单行输出粒度**有意**不变（ADR-0117 决策⑤）。

---

## 41. TUI 子 Agent 焦点视图（TC-FOCUS，change `0125`／ADR-0118，账本 E61）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-FOCUS-01 | ui/spec.md「TUI 子 Agent 焦点视图」（聚焦显示子任务框且主时间线不可见） | 门控编排器：`subtask_started` 后挂起；`/task` 起任务 → `/focus 1` 逐字符输入 + 回车；读 `#panel` / `#timeline` 的 `display` 与面板文本 | `#panel.display is True` / `#timeline.display is False`；面板标题含 `▸ 子任务 1` 与运行态徽标 `⟳`、正文含 `验收：`；**焦点命令不进推理**（`loop.inputs == []`）（锚点：`tests/test_repl.py::test_focus_shows_subtask_panel_and_hides_timeline`） |
| TC-FOCUS-02 | 同上（聚焦期间随里程碑与收尾实时刷新） | 聚焦态下放行里程碑事件（`action_completed`，`tools.code_run` / 1500ms），再放行 `subtask_completed`（`reason` / `reply`） | 里程碑后正文出现 `⏺ Bash ✓ (1.5s)`（复用动作行**友好名**口径）；收尾后标题含 `✓` 且**不含** `⟳`（替换）、正文含 `判定：验收通过` 与结果节选（锚点：`::test_focus_panel_refreshes_on_milestone_and_completion`） |
| TC-FOCUS-03 | 同上（返回主视图后主时间线内容逐字不变） | 记录聚焦前 `_timeline_text`；`/focus 1` → `/main`；比对文本 | 时间线重新可见，且文本与聚焦前**逐字一致**（成功切换**零时间线写入** ⇒ presentation-only）（锚点：`::test_returning_to_main_view_leaves_timeline_unchanged`） |
| TC-FOCUS-04 | 同上（焦点命令在任务运行中可用） | 任务运行中（忙态，普通输入会被拒）按 `F2`（`focus_main` 绑定） | 回主视图（`#timeline.display is True`）且 `_turn_busy` **仍真**（焦点命令不被忙态拒绝、也不复位忙态）（锚点：`::test_focus_command_bypasses_busy_rejection`） |
| TC-FOCUS-05 | 同上（未知子任务标识不切换视图） | ① 未开工即 `/focus 1`；② 子任务 1 存在时 `/focus 99` | 两种情形 `#panel.display` 均 **False**（主视图仍在）、提示「未找到子任务 99」；无「延迟聚焦」半开态（锚点：`::test_focus_unknown_subtask_keeps_main_view`） |
| TC-FOCUS-06 | 同上 + `ui-interface.md` §1.1 注（焦点面板不泄露内部标识与原始参数） | 里程碑载荷含 `tool_id="tools.code_run"`、`args={"code": "print(1)"}`；聚焦后读面板文本 | 面板含**友好名** `Bash`，**不含** `tools.code_run`（内部 id）与 `print(1)`（原始参数）（锚点：`::test_focus_panel_does_not_leak_tool_id_or_args`） |

> **端到端（离线，不触网）**：真 `TaskScheduler`（打桩 `planner` 拆解器 + 打桩子 Agent loop，产出
> `action_started` / `action_completed` / `step_completed` / `loop_finished`）经 `UIAPILayer.run_task`
> 驱动 headless TUI ⇒ **10/10** 断言全绿（面板可见 / 时间线隐藏 / 标题含 `▸ 子任务 1` 与 `⟳` / 正文含验收 /
> 里程碑 `⏺ Bash ✓ (1.5s)` / 判定 / 结果节选 / **不含** `tools.code_run` 与 `print(1)` / `F2` 回主视图；
> 已在 change 落地时手工冒烟，未固化为用例）。
> **非交互 CLI（`core-agent task`）与 Web 不在本 TC 范围**：前者的单行输出粒度与后者（`TaskPanel`）均**有意**不变（ADR-0118 决策⑥）。

---

## 42. 子任务失败态传播（TC-SUBFAIL，change `0126`／ADR-0119，账本 E63）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SUBFAIL-01 | orchestration/spec.md「子任务验收门」（执行失败态不因非空合成回复通过） | 打桩子 Agent loop 产出 `loop_finished`（`reply` 非空、`failed=True`）；子任务**无**验收标准（离线判定本会通过） | `subtask_completed.ok is False`（假成功收口）、`task_failed` 收口、`tracker.completed == set()`、状态机转 `RECOVERING`（锚点：`tests/test_orchestration.py::test_failed_execution_without_acceptance_does_not_pass`） |
| TC-SUBFAIL-02 | 同上（验收门本会通过仍 fail-closed） | 同上 + 子任务有验收标准且注入 verifier 判通过 | 仍 `ok is False`、`task_failed`（验收通过不豁免执行失败）（锚点：`::test_failed_execution_with_acceptance_fails_closed`） |
| TC-SUBFAIL-03 | 同上（回归：成功路径逐字不变） | 正常成功 loop（`failed=False`、非空回复、无验收标准） | `ok is True`、`task_finished`、`tracker.completed == {"1"}`、状态机 `DONE`（锚点：`::test_successful_execution_still_passes`） |

---

## 43. 落地只认门禁全过的制品（TC-GATED，change `0127`／ADR-0120，账本 E69）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-GATED-01 | evolution/spec.md「架构级候选的原生实施（可选）」（未过门的残留制品不被放行落地） | 假门禁执行器在 `typecheck` **抛异常**中断筹备 ⇒ 台账留下 `gated=False` 残留、工作树已回退；随后携带**合格**复核单落地 | 抛 `IMPLEMENT_REJECTED`、工作区逐字不变、`candidate.status == "confirmed"`（锚点：`tests/test_evolution_executor.py::test_commit_rejects_artifact_left_by_an_interrupted_prepare`） |
| TC-GATED-02 | 同上（待复核定义收窄） | 同上的中断筹备后查 `executor.staged()` / `staged_all()` / `queue.implementation_of()` | 前两者**不列出**该残留；后者**仍可见**（留痕，不静默抹掉）（锚点：`::test_ungated_artifact_is_not_staged`） |
| TC-GATED-03 | 同上（回归：门禁全过路径逐字不变） | 正常筹备（四门全过）后查 `staged_all()` | 恰一条、`gated is True`，且 `staged(id) is staged_all()[0]`（锚点：`::test_staged_lists_gated_artifacts_after_successful_prepare`） |

---

## 44. 可逆效应账的清账与幂等（TC-EFFECT，change `0128`／ADR-0121，账本 E67）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-EFFECT-01 | plugin-registry/spec.md「可逆效应追踪（清账与幂等）」（撤销成功后出账且重复回滚不二次撤销） | 同一 trace 记两条可逆效应，**连滚两次** | 首次逆序各调一次 undo、二者均入 `reverted`；第二次 `reverted` / `undo_failed` **均空**且 undo **不再被调用**（锚点：`tests/test_plugin_registry.py::test_rollback_clears_ledger_and_is_idempotent`） |
| TC-EFFECT-02 | 同上（回滚后账目清空且不越界） | 记 `t1` / `t2` 两轮效应，回滚 `t1`；再对全局回滚 | `audit("t1") == []` 而 `t2` 逐条不受影响；全局回滚后两轮皆空（锚点：`::test_rollback_is_trace_scoped`、`::test_rollback_clears_all_traces_globally`） |
| TC-EFFECT-03 | 同上（撤销失败者留账隔离） | 同一 trace 一条 undo 抛异常、另一条正常，回滚该 trace | 失败者入 `undo_failed` 且**仍在账**（`audit` 可见），正常者出账，回滚**不抛**异常（锚点：`::test_effect_tracker_undo_failed_stays_in_ledger`） |
| TC-EFFECT-04 | 同上（不可逆效应不参与撤销、随清账出账） | 记一条 `reversible=False` 效应后回滚 | undo **未被调用**、`reverted` / `undo_failed` 均空、`audit` 为空（锚点：`::test_irreversible_effect_is_cleared_without_undo`） |
| TC-EFFECT-05 | 同上（显式清账不触发撤销） | `clear("t1")` 后 `clear()` | 两轮账目均移除且**未调用任何 undo**（锚点：`::test_clear_removes_ledger_without_undo`） |
| TC-EFFECT-06 | 同上（回归：筹备的临时应用仍在 finally 内回退并清账） | 进化筹备（四门全过）后对 `prepare` trace 再滚一次 | `reverted` / `undo_failed` 均空、`audit` 为空（筹备已清账 ⇒ 幂等）（锚点：`tests/test_evolution_executor.py::test_prepare_restores_worktree_and_stages_artifact`） |

---

## 45. 写类工具的按次快照（TC-SNAP，change `0129`／ADR-0122，账本 E64）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SNAP-01 | tool-use/spec.md「撤销与时间旅行回滚」（同一工具多次写入各自独立回滚） | **同一个** `file_write` 实例先写已存在的 A、再写原先不存在的 B；逆序撤销两次 | 先撤销 B ⇒ B 被删除（原本不存在）；再撤销 A ⇒ A 恢复原内容。第二次撤销**不被** B 的快照覆写（锚点：`tests/test_tool_use.py::test_same_tool_keeps_per_call_snapshots`） |
| TC-SNAP-02 | 同上 | 同一实例 `file_write("alpha")` → `file_patch(alpha→beta)` → `file_write("gamma")`，再回滚该 trace | 沿 LIFO 逆序各归各位 ⇒ 文件恢复为最初内容（write/patch 交错亦各持独立快照）（锚点：`::test_interleaved_write_and_patch_restore_in_lifo_order`） |
| TC-SNAP-03 | 同上（跨 trace 不串） | 同一实例在 `t1` 写 A、在 `t2` 写 B；**只**回滚 `t1` | A 恢复为 `t1` 写入前内容，B **逐字不变**（`t2` 的效应不被 `t1` 回滚触及）（锚点：`::test_snapshots_do_not_leak_across_traces`） |
| TC-SNAP-04 | 同上 | 未执行任何写入即取 `tool.undo()` 并调用所得闭包 | no-op、不抛异常（空栈 ⇒ 工厂返回 no-op 闭包）（锚点：`::test_undo_without_prior_write_is_noop`） |
| TC-SNAP-05 | 同上（回归：单次写的撤销语义不变） | 单次 `file_write` 覆盖已存在文件后回滚 | 原内容复现（既有 `file_write`/`file_patch` 撤销语义零回归）（锚点：`::test_reversible_write_rollback`） |

---

## 46. 配置写回的可逆效应（TC-CFGREV，change `0130`／ADR-0123，账本 E68）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-CFGREV-01 | configuration/spec.md「配置校验与生效」（写回可逆：回滚恢复磁盘原文） | `write_patch` 写回后回滚 `config` trace | config.yaml 恢复为**写盘前的原文字节**（含注释，非重 dump 的等价内容）（锚点：`tests/test_configuration.py::test_write_patch_rollback_restores_yaml_bytes`） |
| TC-CFGREV-02 | 同上 | `apply_change` + `write_patch` 后查账、再回滚一次 | 账上两条 `op` = {`config_apply`, `config_write_patch`}（**同 trace**）；一次回滚后**内存**（`is_enabled`）与**磁盘**同时回退（锚点：`::test_write_patch_and_apply_change_share_config_trace`） |
| TC-CFGREV-03 | 同上（记账先于替换 ⇒ 幂等） | 令 `os.replace` 抛 `OSError` 后调用 `write_patch` | 替换失败 ⇒ yaml 仍为旧值；记账**已发生**（`config_write_patch` 在账上），回滚 `undo_failed` 为空（写回旧值即 no-op）（锚点：`::test_write_patch_records_before_replace`） |
| TC-CFGREV-04 | 同上（回归：写回内容与原子性不变） | 既有 `write_patch` 往返用例 | 新进程读回 model 已更新、api_key 引用与未触及键原样保留（锚点：`::test_write_patch_round_trips`） |

---

## 47. 压实按会话收窄 + 分档口径两档（TC-SCOPECMP，change `0131`／ADR-0124，账本 E66 + E78）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SCOPECMP-01 | memory/spec.md「记忆压实」（压实按会话收窄，不触他会话） | 会话 A、B 各写 L2 episodic，`compact(session_id="A")` | A 的条目迁 L4、产出 `compaction.summary.A`；**B 的条目层级逐字不变**、无 B 的摘要（锚点：`tests/test_memory.py::test_compact_scoped_to_session_leaves_others_intact`） |
| TC-SCOPECMP-02 | 同上（空串=全量，逐字不变） | 同上两会话，`compact()`（缺省 `session_id=""`） | A、B **都**被提炼归档（节拍压实语义不变）（锚点：`::test_compact_default_session_id_keeps_full_store_semantics`） |
| TC-SCOPECMP-03 | 同上（收窄覆盖打分写回） | 注入假 scorer（A、B 条目各有分值），`compact(session_id="A")` | A 条目 `importance` 写回 0.9；**B 条目保持 `0.0`**（未被本轮触及）（锚点：`::test_compact_scoped_session_scores_only_that_session`） |
| TC-SCOPECMP-04 | ui/spec.md「Web 界面访问」（压缩本会话） | 经 UI 层 `compact(session_id)` 触发存储层压实 | 存储层收到**关键字** `session_id`（而非把它当 `query`）（锚点：`tests/test_ui.py::test_compact_triggers_store_compaction`，spy 断言 `compacted == [("", session_id)]`） |
| TC-SCOPECMP-05 | memory/spec.md「温度分层检索」（两档） | 规格文本核对 | 规格为**热/冷两档**（无「温」层条文），与实现（`core/memory/__init__.py` 自述热/冷）同构（文档项） |

---

## 48. 流式增量帧专类型（TC-DELTA，change `0132`／ADR-0125，账本 E65）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-DELTA-01 | ui/spec.md「Web 界面访问」（增量帧与终态帧不共型） | loop 产 `reply_delta`×2 + `loop_finished`，经 `UIAPILayer.run_loop` 收集 | 事件类型序 = [`session.created`, **`loop.delta`**, **`loop.delta`**, `loop.result`]；增量载荷恒 `{"text": …}`，终态载荷非 dict（锚点：`tests/test_ui.py::test_reply_delta_maps_to_dedicated_type`） |
| TC-DELTA-02 | 同上（分流只看类型） | `_event_delta` 喂 `loop.delta` / `loop.result`（dict 载荷）/ 空文本 / 非 dict 载荷 | 仅 `loop.delta` 取 `text`；`loop.result` 即便载荷为 dict 也**不是**增量（旧共型正是 Web 破碎根因）（锚点：`tests/test_repl.py::test_event_delta_only_accepts_dedicated_type`） |
| TC-DELTA-03 | 同上（REPL 只回显增量与错误） | `_format_event` 喂 `loop.delta` / 终态 `LoopResult` | 增量 → 文本；终态对象 → `None`（脚手架不外显）（锚点：`tests/test_repl.py::test_format_event_strips_scaffolding`） |
| TC-DELTA-04 | 同上（SSE 线上帧类型） | `POST /run` 走 SSE（loop 产增量 + 终态） | 响应体同时含 `loop.delta` 与 `loop.result` 两类帧（锚点：`tests/test_serve.py::test_run_sse_streams_result`） |
| TC-DELTA-05 | 同上（**手工验收**，前端无 JS 测试） | 浏览器打开 SPA 发一轮对话（后端流式分片） | 增量**逐段追加在同一条回复**中（不逐帧新建行、不出现 `{"text":…}` 字面量），终态收口为完整回复（`frontend/src/views/Chat.svelte`；无自动化门禁） |

---

## 49. 技能 draft → active 启用路径（TC-SKACT，change `0133`／ADR-0126，账本 E72）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SKACT-01 | skills/spec.md「技能启用」（draft 不进入路由 / 启用后进入路由） | 注册一条 `draft` 技能（`task_types` 与任务词法命中），先路由再启用后路由 | 启用**前** `match` 返回空（放行集仍 `active`/`gray`）；启用**后**命中该技能（锚点：`tests/test_skills.py::test_draft_not_routed_until_activated`） |
| TC-SKACT-02 | 同上（重复启用幂等） | 对同一技能连续两次 `activate(effect_tracker=…)` | 状态 `active`；该 trace 账上**只有一条**启用效应（锚点：`::test_activate_is_idempotent_and_tracks_once`） |
| TC-SKACT-03 | 同上（未知 id 拒绝） | `activate("skills.demo.nope")` | 抛 `KeyError`，且技能库**不**新增技能（锚点：`::test_activate_unknown_skill_raises_key_error`） |
| TC-SKACT-04 | 同上（启用落盘） | 注入 `path` 启用后以同路径新建技能库 | 新实例读回 `status="active"`（锚点：`::test_activate_persists_across_instances`） |
| TC-SKACT-05 | 同上（启用效应可回滚） | 注入 tracker 启用 → 回滚该 trace | 状态恢复为 `draft`（重复回滚不报错）（锚点：`::test_activate_effect_rollback_restores_draft`） |
| TC-SKACT-06 | skillhub/spec.md「签名校验与可信下载」（下载恒 draft，须显式启用方可路由） | CLI `skill install`（落 draft）→ `skill activate`，每步经**重开落盘库**断言 | install 后另一进程见 `draft`；activate 后另一进程见 `active`（锚点：`tests/test_skillhub_cli.py::test_skill_activate_makes_draft_routable_across_processes`） |
| TC-SKACT-07 | 同上（未注册技能拒绝） | CLI `skill activate <未注册 id>` | 退出码非零、stderr 含「技能未注册」，且未因此创建技能（锚点：`::test_skill_activate_unregistered_skill_reports_error`） |

---

## 50. skillhub 源不健康回退官方源（TC-SHFB，change `0134`／ADR-0127，账本 E80）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SHFB-01 | skillhub/spec.md「多源路由与健康回退」（源不健康 ⇒ 回退官方源取结果） | 非官方源 `bad` 不健康、官方源健康且有其目录，对 `bad` 调 `list` / `route` | `list(source="bad")` 返回**官方源**目录条目；`route("bad").name == "official"`；`health("bad").healthy is False`（回退被标记，非静默）（锚点：`tests/test_skillhub.py::test_index_unhealthy_source_falls_back_to_official`） |
| TC-SHFB-02 | 同上（回退目标亦不可用 ⇒ 无可用源） | `bad` 与官方源**均**不可达，对 `bad` 调 `list` | 抛 `SOURCE_UNHEALTHY`（锚点：`::test_index_fallback_target_unhealthy_raises`） |
| TC-SHFB-03 | 同上（官方源自身不可达：无回退目标） | 官方源不可达，`route("official")` | 抛 `SOURCE_UNHEALTHY`（锚点：`::test_index_official_unhealthy_has_no_fallback`） |
| TC-SHFB-04 | 同上（消费面回退） | 源 `third` 不健康、官方源含命中技能，`SkillHubClient.search("greet", source="third")` | 返回**官方源**的命中条目（不再「搜索失败」）（锚点：`::test_search_falls_back_to_official_source`） |
| TC-SHFB-05 | 同上（源不存在不 fallback / 回归） | `route("missing")`；官方源不健康时 CLI `skill search` | 前者 `SOURCE_NOT_FOUND`；后者退出码 1 + stderr「搜索失败」（无可用源仍是错误）（锚点：`::test_index_route_source_not_found`、`tests/test_skillhub_cli.py::test_skill_search_unhealthy_source_reports_error`） |

---

## 51. 分级按词元 + 高危审批码（TC-PERMTOK，change `0135`／ADR-0128，账本 E76）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PERMTOK-01 | permission/spec.md 分级权限体系（语义分词；命名空间 / 无关子串 SHALL NOT 影响等级） | `classify("tools.target")`（含子串 `get`）、`classify("tools.category_sync")`（含 `cat`）、`classify("tools.whatever", "/var/log/target")`（**目标侧**含 `get`） | 一律 `HIGH_RISK`（deny-by-default），SHALL NOT 判 `read`（锚点：`tests/test_permission.py::test_classify_substring_trap_not_read`） |
| TC-PERMTOK-02 | 同上（切词不误伤：整词元照旧命中） | `classify("fs.list")`、`classify("tools.file_read")` | `READ`（词元 `list` / `read` 命中）（锚点：`::test_classify_whole_token_still_matches`） |
| TC-PERMTOK-03 | 同上（命名空间前缀子串反例，既有回归） | `classify("tools.whatever")` / `classify("tools.file_write", coeffect=["filesystem:write"])` | 前者 `HIGH_RISK`；后者 `DATA_EDIT`（锚点：`::test_classify_namespace_substring_not_read`） |
| TC-PERMTOK-04 | permission/spec.md 人工审批流（高危须审批）+ permission 错误码表（`APPROVAL_REQUIRED` = 高危需人工审批） | `GitClient(approval=lambda op: False).push(force=True)` | 抛 `AccessControlError` 且 `code is APPROVAL_REQUIRED`（非 `PERMISSION_DENIED`），后端**未被调用**（fail-closed 且未执行）（锚点：`tests/test_git.py::test_force_push_requires_approval`） |
| TC-PERMTOK-05 | 同上（批准即放行，既有回归） | `GitClient(approval=lambda op: True).push(force=True)` | 后端收到 `("origin", None, True)`（锚点：`::test_force_push_approved`） |

---

## 52. composition 覆盖可回退 + 拒布尔覆盖值（TC-COMPREV，change `0136`／ADR-0129，账本 E75 + E70）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-COMPREV-01 | composition/spec.md「层叠解析」（SHALL 保留覆盖前分层结果；SHALL 提供回退恢复至覆盖前 `ResolvedSet`） | profile 层叠 `core`（`a=1,b=1`）且 patch 覆盖 `b=9`；`resolve` 后 `revert` | `resolved.layered` == `{a:1,b:1}`；`revert(resolved).plugins` == `{a:1,b:1}` 且 `overrides == {}`；**原结果不变**（仍 `b=9`，纯函数）（锚点：`tests/test_composition.py::test_revert_restores_pre_patch_layering`） |
| TC-COMPREV-02 | 同上（回退 SHALL 幂等） | 对 `revert` 结果**再** `revert` | 结果与首次回退**相等**（锚点：`::test_revert_is_idempotent`） |
| TC-COMPREV-03 | 同上（无覆盖时回退为恒等） | profile 无 patch：`resolve` → `revert` | `revert(resolved).plugins == resolved.plugins` 且 `overrides == {}`（锚点：`::test_revert_without_patch_is_noop`） |
| TC-COMPREV-04 | composition-interface.md §3（门面透出 revert） | `CompositionEngine.resolve` → `engine.revert` | 回到覆盖前分层值（锚点：`::test_engine_facade_exposes_revert`） |
| TC-COMPREV-05 | composition/spec.md「层叠解析」（覆盖值 SHALL 为整数 generation；布尔按 `PATCH_CONFLICT` 拒绝）+「patch.yml 用户覆盖」覆盖冲突兜底 | `PatchSpec({"a": True})`（YAML `true`）解析 | 抛 `CompositionError` 且 `code is PATCH_CONFLICT`，SHALL NOT 静默落为 generation `1`（锚点：`::test_patch_override_bool_rejected`） |

---

## 53. beast 三入口接线（TC-BEAST3，change `0137`／ADR-0130，账本 E74）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-BEAST3-01 | beast-mode/spec.md「Three-Entry Activation」（三入口 SHALL 落到同一生命周期）；beast-mode-interface.md §7.1 | 未注入激活器：`UIAPILayer().beast_command(...)` / `activate_beast(...)` | 抛 `UiError` 且 `code is UI_BEAST_UNSET`（fail-explicit，不静默）（锚点：`tests/test_ui.py::test_ui_beast_command_without_activator_raises`、`::test_ui_activate_beast_without_activator_raises`） |
| TC-BEAST3-02 | ui-interface.md §1（`beast_command` 动词面）/ §5 错误码 | `beast_command("banish", …)` | `code is UI_BEAST_UNKNOWN_VERB`（锚点：`::test_ui_beast_command_unknown_verb_raises`） |
| TC-BEAST3-03 | 同上（领域错误在 UI 边界归一） | 真实 `BeastActivator()`：`summon "没有这只兽"`；`recall "青龙"`（无在岗） | 无匹配神兽 ⇒ `UI_BEAST_NOT_FOUND`；状态冲突 ⇒ `UI_BEAST_STATE_INVALID`（两码**不并**）（锚点：`::test_ui_beast_command_unknown_beast_reports_ui_error`、`::test_ui_beast_command_dormant_recall_reports_ui_error`） |
| TC-BEAST3-04 | beast-mode/spec.md「Task Result Visibility」（结果只经只读查询面） | 替身 activator：`summon`（带 task）/ `recall` | verb 落到 `activate_from_slash("青龙","架构设计")` / `recall_from_slash("青龙")`；返回摘要含 `agent_id` / `state` / `result_summary` 字段；**召回不编造结果正文**（`has_result is False`）（锚点：`::test_ui_beast_command_delegates_to_activator`） |
| TC-BEAST3-05 | beast-mode-interface.md §7.1（NL 入口） | `activate_beast("召唤青龙 架构设计")`（替身） | 落到 `activate_from_nl` 且返回 `agent_id`（锚点：`::test_ui_activate_beast_returns_session_id`） |
| TC-BEAST3-06 | ui-interface.md「TUI 神兽斜杠命令」 | TUI：`/summon qinglong 架构设计` → `/recall qinglong` | 时间线含状态行（`已召唤神兽 beast.qinglong（状态 recalled）`）+ **有结果才打印**的结果行 + 召回状态行（锚点：`::test_tui_summon_and_recall_slash_commands`） |
| TC-BEAST3-07 | 同上（缺目标不发起激活） | TUI：`/summon`（无目标） | 只落用法提示，激活器**零调用**（锚点：`::test_tui_summon_usage_hint_on_missing_target`） |
| TC-BEAST3-08 | `_parse_beast_command` 纯函数面 | `/summon qinglong 架构设计`、`/summon qinglong`、`/recall 青龙`、`/summon`、`/summon   `、`/recall`、`你好`、`/focus s1` | 合法形态 ⇒ `("summon","qinglong","架构设计")` / `("summon","qinglong","")` / `("recall","青龙","")`；缺目标与非本命令 ⇒ `None`（锚点：`tests/test_repl.py::test_parse_beast_command_forms`） |
| TC-BEAST3-09 | 组合根装配（`entry.py` 注入 `Runtime.beast_activator`，门控同 pet） | 生产 `build_runtime`：`UIAPILayer(beast_activator=runtime.beast_activator)` + `activate_beast` | 会话登记进**同一** `runtime.beast_manager`（锚点：`tests/test_beast_wiring.py::test_ui_layer_activate_beast_registers_session`） |
| TC-BEAST3-10 | 同上（斜杠端到端） | 同上：`beast_command("summon","青龙",task="架构设计")` 离线桩 LLM | 真实 loop 跑通：`agent_id == "beast.qinglong"`、`reply` 为桩回复、`state == "recalled"`（任务完成自动回归）；此后再 `recall` ⇒ `UI_BEAST_STATE_INVALID`（锚点：`::test_ui_layer_beast_command_summon_and_recall`） |

---

## 54. git 远程断线重试 + 高危原语（TC-GITREL，change `0138`／ADR-0131，账本 E79）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-GITREL-01 | git/spec.md「远程操作可靠性」Scenario「断线重试」（SHALL 按指数退避自动重试，达上限后失败并保持工作区一致） | 桩 `_invoke`：瞬态失败 2 次后成功；`SubprocessGitBackend(sleep=记录, attempts=3, backoff=0.5).pull()` | 返回成功；`_invoke` 调用 **3** 次；退避序列 `[0.5, 1.0]`（锚点：`tests/test_git_subprocess.py::test_remote_transient_jitter_retries_with_exponential_backoff`） |
| TC-GITREL-02 | 同上（达上限后失败，不无限重试） | 桩 `_invoke` 恒瞬态失败：`push()` | 抛 `GitError(GIT_COMMAND_FAILED)`；调用 **3** 次；退避 `[0.5, 1.0]`（末次不再睡）（锚点：`::test_remote_retry_gives_up_at_attempt_limit`） |
| TC-GITREL-03 | git/spec.md「远程操作可靠性」Scenario「认证失败」（SHALL 明确报错，不泄露凭据） | 桩 stderr = `fatal: Authentication failed for '…'` | 抛 `GIT_AUTH_FAILED` 且 `_invoke` **仅 1 次**（凭据不会自愈 ⇒ 不重试）（锚点：`::test_remote_auth_failure_not_retried`） |
| TC-GITREL-04 | git-interface.md §4「可重试分类」（确定性失败不重试） | 桩 stderr = `fatal: not a git repository` | 抛 `GIT_COMMAND_FAILED` 且 `_invoke` **仅 1 次**（锚点：`::test_remote_deterministic_failure_not_retried`） |
| TC-GITREL-05 | git/spec.md「远程操作可靠性」Scenario「远程超时」（SHALL 中止该操作并返回超时错误，不无限挂起） | `subprocess.run` 抛 `TimeoutExpired`：`pull()` | 抛 `GIT_REMOTE_TIMEOUT` 且 `_invoke` **仅 1 次**（超时优先中止，不重试）（锚点：`::test_remote_timeout_not_retried`） |
| TC-GITREL-06 | git/spec.md「与 permission 沙箱协作」（SHALL 删除远程分支走审批链，非交互默认拒绝）+ Scenario「高危操作审批」 | `GitClient(approval=lambda op: False).delete_remote_branch("feature")` | 抛 `AccessControlError(APPROVAL_REQUIRED)`；后端**零调用**（触碰后端前阻断）（锚点：`tests/test_git.py::test_delete_remote_branch_requires_approval`） |
| TC-GITREL-07 | 同上（历史改写走审批链） | `GitClient(approval=lambda op: False).rewrite_history("fix: reword")` | 抛 `APPROVAL_REQUIRED`；后端零调用（锚点：`::test_rewrite_history_requires_approval`） |
| TC-GITREL-08 | 同上（批准即放行） | `approval=lambda op: True`：`delete_remote_branch` / `rewrite_history` | 后端收到 `("origin","feature")` / `amend("fix: reword") == "a1"`（锚点：`::test_delete_remote_branch_approved`、`::test_rewrite_history_approved`） |
| TC-GITREL-09 | git-interface.md §1（三处高危 op id 互异） | `approval` 记录 op 序列：force-push → 删远程分支 → 改写历史 | `["git.push(force)", "git.delete_remote_branch", "git.rewrite_history"]`（锚点：`::test_high_risk_ops_use_distinct_approval_ids`） |
| TC-GITREL-10 | git/spec.md「与 permission 沙箱协作」（非交互默认拒绝） | `GitClient(backend=…)`（**无** `approval` 回调）：两新原语 | 均抛 `AccessControlError`；后端零调用（锚点：`::test_non_interactive_high_risk_defaults_to_denied`） |

---

## 55. Harness Host 心跳 + Desktop 交付面（TC-DEPLOY，change `0139`／ADR-0132，账本 E81 + E83）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-DEPLOY-01 | deployment/spec.md「客户端断线与会话清理」Scenario「连接超时回收」（客户端**长时间无活动**才回收）+ `:60`（检测断线**含心跳**判定） | 注入时钟：`accept` → 推进 100s → `touch` ⇒ `reap(timeout=10)`；再推进 100s（期间无 touch）⇒ `reap` | 首次 `touch` 返 `True` 且 `reap` 返 `[]`、会话仍在；此后 100s 无活动 ⇒ 照旧回收（锚点：`tests/test_deployment.py::test_host_touch_keeps_active_session_alive`） |
| TC-DEPLOY-02 | 同上（心跳是保活、**非复活**） | `touch("session-999")`（未知）/ 断线后 `touch` / 回收后 `touch` | 三者皆 `False`，且会话状态**不变**（不复活）（锚点：`::test_host_touch_ignores_unknown_and_dead_sessions`） |
| TC-DEPLOY-03 | deployment-interface.md §6（刷新成功即持久化，与 `accept`/`disconnect`/`reap` 同口径） | `path` 落盘：`accept` → 推进 100s → `touch` → 新实例（时钟再 +5s）`reap(timeout=10)` | 返 `[]`（心跳后仅过 5s）；活跃会话仍在（不按陈旧 `last_seen` 误回收）（锚点：`::test_host_touch_persists_last_seen`） |
| TC-DEPLOY-04 | ui/spec.md「桌面打包」（SHALL 打包为可执行安装文件；SHALL 复用同一 SPA 产物） | **手工验收**（本仓四门禁无 Rust/打包面）：`src-tauri/tauri.conf.json` `bundle.active=true` + `targets="all"`；`app.windows` 空 ⇒ 端口不落配置 | `cargo check`（`src-tauri/`）为拟用的额外验证手段（非门禁），**本轮未跑通**（缓存依赖树与 `Cargo.lock` 版本不一致 + 联网取包未成功）⇒ **壳编译未经自动验证**；壳经 `resolve_port()`（`CORE_PORT`，缺省 8000）**与 sidecar 同源端口**程序化开窗；实际安装包产出随平台工具链，属手工验收 |
| TC-DEPLOY-05 | 同上（端口不得漂移 —— 内核换端口而壳指向空地址 ⇒ 白屏） | 静态检查：`grep -n "127.0.0.1:" src-tauri/tauri.conf.json` | 无命中（硬编码端口已移入 `main.rs` 单点 `resolve_port()`；`tauri.conf.json` 只留 `frontendDist`） |

---

## 56. 信息地图装配接线（TC-INFOMAP，change `0140`／ADR-0133，账本 E77）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-INFOMAP-01 | context/spec.md「信息地图」（系统 SHALL 把长文档转为轻量化目录索引） | `InfoMap.index("doc", "# 章节\n内容")` → `DynamicAssembler(info_map=...).build("章节", "reason", budget=2048)` | `pack.pointers == [{"doc_id": "doc", "section": "章节", "summary": "章节", "pointer": "doc#章节"}]`（目录层进装配包）（锚点：`tests/test_context.py::test_assembler_build_injects_pointer_catalog`） |
| TC-INFOMAP-02 | 同上 Scenario「地图定位与按需取详情」（先用地图定位指针，再 fetch 片段，**而非加载全文**） | `build_runtime`（Core.md 带「## 项目信息」段）；`planner._system_prompt(LoopContext(...))` | 提示词含「文档目录（按需取详情，勿请求全文）：」且含 `- core-profile#项目信息`（锚点：`tests/test_infomap_wiring.py::test_core_profile_indexed_and_pointers_reach_the_prompt`） |
| TC-INFOMAP-03 | 同上（模型**有通道**取详情 —— `fetch_detail` 不再零生产调用点） | `runtime.tools.invoke("tools.context_read", {"pointer": "core-profile#项目信息"})` | `ok=True` 且 `data == {"pointer": ..., "detail": "项目信息"}`（避开全文加载）（锚点：`::test_context_read_tool_fetches_pointer_payload`） |
| TC-INFOMAP-04 | 同上（指针失效**不得**中断任务） | `tools.context_read` 传 `absent#nope` | `ok=True` 且 `detail == ""`（空串**非**报错）（锚点：`::test_context_read_unknown_pointer_is_empty_not_error`） |
| TC-INFOMAP-05 | 同上 Scenario「重建失败二阶兜底」（**受控**分段线性扫描并逐段命中，任务不中断） | `InfoMap.register("doc", 原文)`（仅原文、不建索引）→ `lookup("doc", "目标")`；100 行原文 → `lookup("doc", "line")` | 逐段命中（`seg-1` 携该段原文）；段数**上界** `_MAX_SCAN_SEGMENTS = 20`（锚点：`tests/test_context.py::test_info_map_register_raw_only_falls_back_to_linear_scan` / `::test_info_map_linear_scan_is_bounded`） |
| TC-INFOMAP-06 | 零回归（未接地图 ⇒ 装配行为逐字不变） | `DynamicAssembler(info_map=InfoMap()).build(...)` | `pack.pointers == []`（缺省空目录层）（锚点：`::test_assembler_build_pointers_empty_without_documents`） |
| TC-INFOMAP-07 | 生产工具面（context_read 可达，权限分级按完整词元判**只读**放行） | `build_runtime` 后枚举 `runtime.tools.active_tools()` | 含 `tools.context_read`；`invoke` 不落 `APPROVAL_REQUIRED` / `IRREVERSIBLE_BLOCKED`（锚点：`tests/test_infomap_wiring.py::test_context_read_registered_on_main_tool_face`、`tests/test_phase13.py` 工具面清单） |

---

## 57. 账目校准（TC-LEDGER，change `0141`／**无 ADR**，账本 E86 + E82 + E87 + E71 + E84-b）

> **本 change 无新增测试用例**：零代码、零规格、零测试变更（四门禁与用例基线逐字不动）。
> 下表只登记**台账订正的证据锚点**——每条注记均以行号 / grep **实测**坐实，便于日后复查。

| 项 | 规格 / 事实锚点 | 证据（实测） | 订正结论 |
|---|---|---|---|
| TC-LEDGER-01 | `doc/openspec/specs/ui/spec.md` 全文（**无** pet/beast 专有端点要求） | `grep -rn "reconnect|retry|Last-Event-ID" frontend/src/ src/core/ui/` **零命中**；`frontend/src/lib/api.js:55-63` 用 `fetch` + `ReadableStream`（**非** `EventSource`） | **E86 假绿订正**：`phase-9.md:114`「断线重连」拆为 `[ ]`（真绿三项保持 `[x]`） |
| TC-LEDGER-02 | `ui/spec.md` + `ui/api.py:231/237`（宠物）、`:263/276`（神兽，change `0137` 接线） | REST 面 12 端点为 `fastapi_serve.py:194-206` 既有全集；Web 面**消息驱动**（复用 `/run`） | **E82 证伪**：规格未要求专有端点 ⇒「Web 面缺失」不成立 |
| TC-LEDGER-03 | `doc/10-codebase-engine/integration-plan.md:11`、`codebase-engine-evaluation.md:71`（自述「走 MCP 接入 / **不新增** `codebase` capability」） | 文档自述交付形态；`src/` 无对应模块系**设计形态** | **E87 证伪**：「有文档无实现」为形态误读（MCP 接入是否已接线**未核**，留口） |
| TC-LEDGER-04 | `doc/openspec/specs/memory/spec.md:26-29`（跨层检索）与 `:49-52`（检索失败降级）**并存**；正文 SHALL `:31-37` | `src/core/memory/store.py:110-115` `read()` 恒 `backend.search(query)` + `_hot`（常驻降级态） | **E71 定性订正**：**非**代码违约 ⇒ 性能面优化缺口（§4 取舍） |
| TC-LEDGER-05 | 规格 `composition/spec.md`（哈希口径 SHALL 在此）vs deployment 侧 | `src/core/entry.py:1014-1016` 退化哈希；deployment 侧**无** bundle 哈希 SHALL | **E84 拆二**：E84-a ⇒ change `0143`；E84-b ⇒ 已知取舍 |

---

## 58. core-profile 题词模板骨架（TC-PROFILE，change `0142`／ADR-0134，账本 E85）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PROFILE-01 | core-profile/spec.md「题词模板」（骨架产出物具名：`templates/Core.global.md` / `templates/Core.project.md`） | 检查两文件存在 | 均为文件（锚点：`::test_both_template_skeletons_exist`） |
| TC-PROFILE-02 | 同上（全局级模板含「宪法与全局规则」「人格」两分区；「项目信息」属项目级） | 读 `templates/Core.global.md` 原文 | 含 `## 宪法与全局规则` 与 `## 人格`，**不含** `## 项目信息`（锚点：`::test_global_skeleton_carries_two_sections_only`） |
| TC-PROFILE-03 | 同上 Scenario「骨架复制即被解析器接受」（标题逐字、分区非空 ⇒ 零 `SECTION_INVALID`） | `SectionParser().parse(全局骨架原文)` → `Validator().validate` | `["constitution","personality"]` 且 `warnings == []`（锚点：`::test_global_skeleton_round_trips_clean_through_parser`） |
| TC-PROFILE-04 | 同上 Scenario「项目级模板产出」+「复制即被接受」 | 同上，`templates/Core.project.md` | `["project_info"]` 且零告警（锚点：`::test_project_skeleton_round_trips_clean_through_parser`） |
| TC-PROFILE-05 | 同上（模板附分区注入说明注释，注明落向的运行时通道） | 读两骨架原文 | 全局含 `constitution:v1` 与 `L0`；项目含 `ContextEngine`（锚点：`::test_skeletons_note_runtime_injection_channels`） |
| TC-PROFILE-06 | core-profile/spec.md「题词规范」（篇幅受控：建议不超过 50 行） | 读两骨架行数 | 各 ≤ 50 行（锚点：`::test_skeletons_are_bounded_in_length`） |

---

## 59. bundle 内容哈希口径（TC-BUNDLE，change `0143`／ADR-0135，账本 E84-a）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-BUNDLE-01 | composition/spec.md「bundle 分发格式」（哈希 SHALL 由制品内容派生，元信息不参与） | 两份清单**内容相同**、清单名与 `name` 皆不同 ⇒ `load_manifest` | 两者 `hash` 相同，且等于 `pack(同内容)` 的哈希（锚点：`test_composition.py::test_load_manifest_hash_derives_from_content_not_meta`） |
| TC-BUNDLE-02 | 同上（**内容不同 ⇒ 哈希不同**；规范形为**有序**拼接） | 改任一 `generation`；以及同项换序 | 哈希改变（锚点：`::test_load_manifest_hash_changes_with_content` / `::test_load_manifest_order_is_significant`） |
| TC-BUNDLE-03 | 同上（清单缺失 / 非法 ⇒ 结构化拒绝，SHALL NOT 退化） | 路径不存在 / 非法 JSON / 顶层非对象 / `plugin_refs` 非列表 / 引用项缺 `plugin_id`·`generation`（6 例参数化） | `CompositionError` 且 `code is BUNDLE_INVALID`（锚点：`::test_load_manifest_invalid_rejected`） |
| TC-BUNDLE-04 | 同上 + 规格「发布入口」（CLI 读制品清单） | `main(["release","publish", <清单路径>])` | 退出码 0 + 输出「已发布版本 <bundle 名>」（锚点：`test_entry.py::test_release_publish`） |
| TC-BUNDLE-05 | Scenario「同内容同哈希、异内容异哈希」 | 连发三条清单（两条同内容异名、一条异内容）后读 `releases.json` | 同内容两条 `hash` 相等；异内容 `hash` 不同（锚点：`::test_release_publish_hash_is_content_addressed`） |
| TC-BUNDLE-06 | Scenario「制品清单缺失不产假账」 | 缺清单发布；以及先成功一条再用坏清单撞 | 退出码 1 + stderr 含「发布失败」；`releases.json` **不存在 / 逐条不变**（锚点：`::test_release_publish_missing_manifest_rejected` / `::test_release_publish_invalid_manifest_keeps_history`） |
| TC-BUNDLE-07 | 同上（清单可选 `name`；元信息不参与哈希） | 清单不声明 `name` | 取清单文件名的 stem（锚点：`::test_load_manifest_name_defaults_to_file_stem`） |

---

## 60. 时间旅行回滚生产入口（TC-TIMETRAVEL，change `0144`／ADR-0136，账本 E73）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-TIMETRAVEL-01 | durability/spec.md「时间旅行」Scenario「回滚到历史检查点」（**上层请求**） | `main(["time-travel", "<cp>"])`（runtime 桩） | 退出码 0 且**委派到** `runtime.time_travel.rollback`（记录入参 = cp）；回执含检查点 id 与撤销集条数（锚点：`test_entry.py::test_time_travel_delegates_to_runtime`） |
| TC-TIMETRAVEL-02 | 同上（检查点不存在 ⇒ 结构化失败，不伪造成功） | 桩 `rollback` 抛 `CHECKPOINT_NOT_FOUND` | 退出码 1 + stderr 含「回滚失败」（锚点：`::test_time_travel_unknown_checkpoint_exits_1`） |
| TC-TIMETRAVEL-03 | 同上 + Scenario「与副作用级回滚协同」（撤销集取快照 `state["trace_ids"]`） | 真子进程 `python -m core.entry time-travel <cp>`（cp 经生产口径落盘 `$CORE_STATE_DIR/checkpoints.jsonl`） | 退出码 0 + stdout 含该检查点 id（锚点：`::test_time_travel_rolls_back_persisted_checkpoint`） |
| TC-TIMETRAVEL-04 | durability/spec.md「时间旅行」（回滚未知检查点） | `TimeTravel.rollback("ghost")`（空 store） | `DurabilityError` 且 `code is CHECKPOINT_NOT_FOUND`（锚点：`test_durability.py::test_time_travel_missing_checkpoint_raises`） |
| TC-TIMETRAVEL-05 | 同上（撤销协同：undo 复用 tool-use 栈，**不新建机制**） | 记可逆效应 `t1` → 建含 `trace_ids=["t1"]` 的检查点 → `rollback` | undo 回调被执行、快照 state 原样返回（锚点：`test_durability.py::test_time_travel_rolls_back_effects`，既有用例） |

> **手工验收项（无自动门禁）**：跨进程撤销协同 —— `Effect.undo` 为进程内闭包、不可持久化，
> 一次性 CLI 进程内撤销循环**空转**（快照恢复与失败语义仍生效）；同进程入口（`serve` / REPL /
> 同一 runtime 内的 `task`）的撤销协同由 TC-TIMETRAVEL-05 覆盖（见 ADR-0136 已知局限②）。

---

## 61. Think 思考过程回显链路（TC-THINK，change `0145`／ADR-0137，账本 E56~E60）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-THINK-01 | llm-provider/spec.md「默认实现与配置归一化」（E56） | 响应体 `message.reasoning_content="想"` | `LLMResponse.thinking == "想"` 且 `content` 不含该文本（锚点：`test_llm_provider.py::test_response_maps_thinking_from_reasoning_content`） |
| TC-THINK-02 | 同上（OpenAI o 系 `reasoning` 兜底） | 响应体 `message.reasoning="想"`（无 `reasoning_content`） | `LLMResponse.thinking == "想"`（锚点：`::test_response_maps_thinking_from_openai_reasoning`） |
| TC-THINK-03 | 同上（流式增量归一） | SSE `delta.reasoning_content` = `想` / `一下` / `好` | 逐 chunk `LLMChunk.thinking` 依次为三段（锚点：`::test_chunk_maps_thinking_delta`） |
| TC-THINK-04 | 同上（字段缺失 ⇒ 空串，零回归） | 响应/增量均无思考字段 | `thinking == ""`，既有字段逐字不变（锚点：`::test_thinking_empty_when_absent`） |
| TC-THINK-05 | loop/spec.md「异步流式执行」Scenario「开启时逐段产出 loop.reasoning」（E57） | `LLMPlanner(show_thinking=True)` + 桩 provider 产 `thinking` 三段 + `content="好"` | 产出序 `[Thinking("想"), Thinking("一下"), "好", Action(reply="好")]`（锚点：`test_phase13.py::test_planner_astream_emits_thinking_when_enabled`） |
| TC-THINK-06 | 同上 Scenario「关闭时不产」（开关缺省关） | `LLMPlanner(show_thinking=False)` + 同上桩 | 产出序零 `Thinking`，与既有缺省逐字一致（锚点：`::test_planner_astream_no_thinking_when_disabled`） |
| TC-THINK-07 | 同上 Scenario「非流式路径支持终态思考」（降级分支） | 无 `astream` 的 completion-only 桩 + `show_thinking=True` | 先 `Thinking(全文)` 后 `Action`（锚点：`::test_planner_degraded_stream_emits_terminal_thinking`） |
| TC-THINK-08 | 同上 Scenario「关闭时不产」（降级分支） | 同上桩 + `show_thinking=False` | 零 `Thinking`（锚点：`::test_planner_degraded_stream_no_thinking_when_disabled`） |
| TC-THINK-09 | loop/spec.md「异步流式执行」（E58：`Thinking` ⇒ `loop.reasoning`） | `DefaultLoop.astream` + `Thinking` 桩 planner | 事件序含 `("loop.reasoning", {"text": "想"})` / `{"text": "一下"}`（锚点：`test_loop.py::test_astream_thinking_planner_emits_loop_reasoning`） |
| TC-THINK-10 | 同上（思考事件**不吞**终态全文补发） | 思考事件 + `reply_delta` 混合 | 终态回复仍完整外发（`streamed` 判据只认 `reply_delta`）（锚点：`::test_astream_thinking_events_do_not_suppress_terminal_reply`） |
| TC-THINK-11 | 同上（红线：纯呈现层） | 思考原文经 `loop.reasoning` 外发 | 思考文本**仅**出现在 `loop.reasoning` 载荷；`_RecordingMemory.written` / 其余事件面**均不含**（锚点：`::test_thinking_only_visible_through_reasoning_event`） |
| TC-THINK-12 | ui/spec.md「思考过程回显（Think）」（E59：映射） | 断言 `_EVENT_MAP["loop.reasoning"]` | 恒等映射；SSE 类型序 `["session.created", "loop.reasoning", "loop.delta", "loop.result"]`，载荷 `{"text": "想"}`（锚点：`test_ui.py::test_loop_reasoning_maps_to_identity_type`） |
| TC-THINK-13 | ui/spec.md 同上 Scenario「TUI 折叠块默认收起 + 同轮归并」（E60） | TUI 消费两段 `loop.reasoning` + `reply_delta` + 终态 | **单个** 折叠块、`display is False`（缺省收起）、块内含两段思考全文、主回复不受影响（锚点：`test_repl.py::test_tui_thinking_renders_in_single_collapsed_block`） |
| TC-THINK-14 | loop/spec.md 红线（思考**不**上子任务回流通道） | 子任务 `_ThinkingPlanner` 产 `Thinking` | 回流进度 `event` 集**不含** `loop.reasoning`；其余里程碑照常回流（锚点：`test_orchestration_progress.py::test_loop_reasoning_never_relayed`） |
| TC-THINK-15 | 同上（白名单第二道防线） | 断言 `scheduler._PROGRESS_FIELDS` | `"loop.reasoning"` **不在**白名单内（锚点：`::test_progress_whitelist_excludes_loop_reasoning`） |
| TC-THINK-16 | configuration/spec.md「LLM 提供商配置（必选）」子项 `show_thinking` | `llm.show_thinking` 缺省 / 原生 bool / `true·yes·on·1·TRUE·" On "` / `false·no·off·0·OFF` / 非法 `maybe·""·{}` | 缺省 `False`；真值集归一为开、假值集归一为关；非法值 `ConfigurationError` **阻断启动**（锚点：`test_configuration.py::test_show_thinking_default_off` / `_native_bool` / `_truthy_set` / `_falsy_set` / `_invalid_blocks_startup`） |
| TC-THINK-17 | ui/spec.md（非交互 `run` 不刷屏） | `core-agent run` 消费 `loop.delta` / `loop.reasoning` / `loop.result` | 思考与增量帧**均不**逐段打印；终态回复照常打印（锚点：`test_entry.py::test_run_stream_skips_reasoning_frames`） |

> **手工验收项（无自动门禁）**：
> 1. **真端点字段取证**（ADR-0137 已知局限①）—— 「实测 glm-5.3 流式思考字段名」被**凭据物化**阻断
>    （`config.yaml` 密钥只引用不读取、绝不回显），双键归一按公开口径（`reasoning_content` 优先 /
>    `reasoning` 兜底）落地。**须**在具备密钥的环境下对 `provider=zai / model=glm-5.3` 跑一次真实
>    流式请求，确认 `delta` 的思考字段落于两键之内；若落在两键之外，仅需扩 `_thinking_text` 的键位
>    （单点）而无涉链路。
> 2. **Web (Svelte) 渲染** —— 前端无 JS 测试面，`Chat.svelte` 的 `<details>` 折叠块（增量追加、
>    缺省收起、终态不改写）**须**浏览器手工验收：开启 `llm.show_thinking` 后发一条触发思考的消息，
>    确认折叠块出现且缺省收起、展开见全文、会话切换后清空。
> 3. **APP 同构面** —— 复用同一 SPA 产物（§4 约束 1），随 Web 面验收。

---

## 62. TUI 流式 Markdown 表格整块解析（TC-TABLE，change `0146`／ADR-0138，账本 E88）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-TABLE-01 | ui/spec.md「CLI 友好交互」Scenario「流式结构化块整体解析」（判据纯函数） | 尾段为 `"| 水果 | 产地 |\n"`（表头后半开）/ 完整三行表格 / 表格后接**空行** / 表格后**紧接散文行** / 散文行仅含**单个** `|`（`"见 foo|bar\n"`）/ **代码围栏内含 `|`** | 表头后与完整表格 ⇒ `True`；空行闭合 / 散文尾随 / 单竖线散文 ⇒ `False`；围栏先判 ⇒ 表格判据**不误判**（锚点：`test_repl.py::test_in_open_table_predicate`） |
| TC-TABLE-02 | 同上 Scenario「流式结构化块整体解析」（整块落入同一渲染块） | 桩 loop 逐行 emit `LoopEvent("loop.delta", {"text": row})`（表头 / 分隔行 / 3 数据行）后收尾 | `#timeline` 内该回复为**单个** `Markdown` 块（**修复前为 3+ 块 ⇒ 红**），子块含 `MarkdownTable`，`.source` 含完整表头 + 分隔 + 数据行（锚点：`test_repl.py::test_streamed_table_renders_in_single_block`） |

> **手工验收项（无自动门禁）**：
> 1. **真 TUI 目视表格渲染** —— 在真终端跑一次流式产出 Markdown 表格的对话（或桩 provider 逐行
>    流式一张表格），目视确认 `#timeline` 出现**一个**表格块（**非**逐行竖线原文）；并回归确认
>    **代码围栏**流式仍渲染为代码块（分支优先序：围栏先判）。
> 2. **Web 端（非本 change 面）** —— `Chat.svelte` 无 Markdown 渲染器，表格恒显竖线原文；
>    若后续要 Web 表格渲染，须另立 change（ADR-0138 已知局限②）。

---

## 63. TUI 流式回显合帧节流 + 表格整块延后渲染（TC-SMOOTH，change `0147`／ADR-0139，账本 E89）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SMOOTH-01 | ui/spec.md「CLI 友好交互」Scenario「流式回显合帧与表格延后渲染」（合帧节流） | 直接驱动 `_show_delta("你")` + `_show_delta("好")`；查状态；再 `_flush_tail()` | 合帧前 `_tail_widget is None`（**旧实现逐 delta 立即建 widget ⇒ 红**）、`"".join(_tail_buf) == "你好"`（增量在缓冲、不丢字）；合帧后尾块建立、`#timeline` 恰 **1** 个 `Markdown`（锚点：`test_repl.py::test_show_delta_defers_until_flush`） |
| TC-SMOOTH-02 | 同 Scenario（表格整块延后渲染） | 逐行 `_show_delta` 表格三行（表头 / 分隔 / 数据行）+ `_flush_tail()`；再 `_show_delta("\n")`（空行闭合）+ `_flush_tail()` | 未闭合 flush 后 `_tail_widget is None`（**旧实现已挂 Markdown ⇒ 红**）、缓冲非空；闭合后恰 **1** 个 `Markdown` 块且子块含 `MarkdownTable`（锚点：`test_repl.py::test_open_table_not_rendered_until_closed`） |
| TC-SMOOTH-03 | 同 Scenario（**围栏维持流式可见**） | `_show_delta("```python\n")` + `_show_delta("print(1)\n")` + `_flush_tail()` | 未闭合围栏合帧后**仍渲染**（`_tail_widget is not None`）—— 表格延后**不得误伤围栏**（锚点：`test_repl.py::test_open_fence_still_streams`） |

> **手工验收项（无自动门禁）**：
> 1. **高速流式目视「不再阶梯」** —— 真终端跑一次逐词高速流式回复，目视确认回显**不再一卡一卡**
>    （渲染次数 ≪ delta 数）；可用桩 provider 逐字符流式放大观察。
> 2. **表格一次成型 + 围栏回归** —— 流式产出表格时，目视确认**自表头到达至闭合之间不出现该表**、
>    闭合后**一次整块成型**（不逐行抽动）；同时回归确认**代码围栏**流式仍逐行可见。
> 3. **时序不乱** —— 流式进行中触发 **Ctrl+B 打断** / 命中**审批门**，目视确认打断行 / 审批提示出现
>    在**已回显文本之下**（挂起尾段先提交，`_add` 时序闸）。

---

## 64. 记忆压实增量滚动摘要（TC-ROLLSUM，change `0148`／ADR-0140，账本 E90）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-ROLLSUM-01 | memory/spec.md「记忆压实」Scenario「滚动合并既有摘要（不丢失）」（槽位渲染） | `build_prompt([既有摘要条目, 新增条目])`；对照 `build_prompt([新增条目])` | 有既有摘要 ⇒ prompt 含「现有摘要」槽**与既有摘要原文**（**旧实现一律逐条渲染 ⇒ 无槽、红**）；无既有摘要 ⇒ **不含**该槽（锚点：`test_memory.py::test_build_prompt_renders_existing_summary_slot`） |
| TC-ROLLSUM-02 | 同 Scenario（材料含既有摘要） | 假摘要器记录输入；写 e0(s1)→`compact()`→写 e1(s1)→`compact()` | 首次材料 `[["e0"]]`（无既有摘要）；第二次材料**首元素为** `compaction.summary.s1` 且含 `e1`（**旧实现第二次仅 `["e1"]` ⇒ 红**）（锚点：`test_memory.py::test_compact_feeds_existing_summary_back_to_summarizer`） |
| TC-ROLLSUM-03 | 同 Scenario（**早期结论不丢**，核心） | 摘要器 `"="; join(contents)`：轮 1 压实得摘要；再写 e1 后二次压实 | 二次摘要内容**仍含**轮 1 结论「事实零」且含「事实一」（**旧实现被覆盖为 `事实一` ⇒ 红**）（锚点：`test_memory.py::test_compact_rolling_merge_preserves_prior_conclusions`） |
| TC-ROLLSUM-04 | 同 Scenario（**条目不增长**） | 同会话连续两次 `compact()` | 该会话摘要条目**恰 1 条**、`id` 不变（`compaction.summary.s1`）、`tags` 携带本轮原条目出处（锚点：`test_memory.py::test_compact_keeps_single_summary_entry_per_session`） |
| TC-ROLLSUM-05 | memory/spec.md「记忆压实」Scenario「压实可撤销」／「摘要提炼并归档」（**回归护栏**） | 既有 `tests/test_memory.py` 压实/固化/遗忘全量用例 | 逐字不动全绿——尤其三条 `seen ==` 断言（首次压实无既有摘要 ⇒ 材料逐字等于原始条目）、`test_compact_is_reversible_by_trace`（回滚 ⇒ 原条目迁回 L2、摘要移除、`undo_failed == []`） |

> **无手工验收项**：纯库内行为（`memory` 层），全自动门禁（pytest）覆盖；无前端 / Rust / 真端点面。

## 65. 常驻（pinned）笔记：任务级硬约束锚（TC-PIN，change `0149`／ADR-0141，账本 E93）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PIN-01 | notes/spec.md「常驻（pinned）笔记（任务级硬约束锚）」标记往返（**零回归护栏**） | `render_note(NoteEntry(pinned=False))`；对照 `pinned=True` | False ⇒ 输出**逐字不含** `- pinned`（与改前逐字一致）；True ⇒ 含 `- pinned: true`（锚点：`test_notes.py::test_render_note_omits_pinned_line_when_false` / `::test_render_parse_roundtrip_with_pinned`） |
| TC-PIN-02 | 同 Requirement（解析宽容 + fail-closed） | `parse_note` 喂 `pinned` 取 `true/yes/1/on`（含大小写变体）/ 其他拼写 / 缺行 | 前三类 ⇒ True；其他拼写与缺行 ⇒ False（手误**绝不**意外置常驻）（锚点：`::test_parse_note_pinned_truthy_spellings` / `::test_parse_note_pinned_falsey_spellings`） |
| TC-PIN-03 | 同 Requirement（标记往返持久化 + 幂等） | `set_pinned(id, True)` 后**新实例**读回；再同值 `set_pinned` | 新实例 `pinned is True`（落盘真源）；同值重置 ⇒ **不写盘、不 bump** `updated_at`（锚点：`::test_store_set_pinned_persists_and_is_idempotent`） |
| TC-PIN-04 | 同 Requirement（未知 id 结构化错误） | `set_pinned("missing", ...)` | `NoteError(NOTE_NOT_FOUND)`（锚点：`::test_store_set_pinned_missing_raises`） |
| TC-PIN-05 | 同 Requirement（注入**全文**而非节选） | 常驻笔记正文 > `_MAX_EXCERPT_CHARS`(200)；另有非常驻笔记 | `pinned_digest()` 含常驻正文**全文**；非常驻正文**不出现**（锚点：`::test_store_pinned_digest_carries_full_body`） |
| TC-PIN-06 | 同 Requirement（无常驻 ⇒ 空块；确定性 + 有界） | 无常驻笔记；多篇超长常驻正文 | 前者 ⇒ `""`（不注入空块）；后者 ⇒ 长度 ≤ `_MAX_PINNED_CHARS`(4000) 且按 `note_id` 升序**确定**（跨轮字节稳定）（锚点：`::test_store_pinned_digest_empty_without_pins` / `::test_store_pinned_digest_is_deterministic_and_capped`） |
| TC-PIN-07 | 同 Requirement（逐轮写回不抹除常驻） | 先 `set_pinned`，再 `observe_turn` 同一主题（slug 命中该 id） | 写回后 `pinned` **仍为 True**（`observe_turn` 原样携带既有标记）（锚点：`::test_store_observe_turn_preserves_pinned`） |
| TC-PIN-08 | 同 Requirement Scenario「每轮无条件注入（不依赖 query 命中）」 | 注入**零参** `pinned_notes_consult` 闭包；跑一轮与约束**完全无关**的任务 | 闭包被调**恰一次**、`ctx.pinned_notes` 即其返回值（零参闭包在误传任务文本时会 TypeError ⇒ 有内容即证零参调用）；缺省未注入 ⇒ `""`（锚点：`test_notes_loop.py::test_loop_pinned_hook_populates_context_without_task_arg` / `::test_loop_without_pinned_hook_leaves_pinned_notes_empty`） |
| TC-PIN-09 | 同 Requirement Scenario「源失败降级不阻断」 | 常驻钩子抛错；对照正常轮 | 降级 ⇒ `ctx.pinned_notes` 置空 + `pinned_notes_consult_failed` 留痕、本轮结局**不变**（锚点：`::test_loop_pinned_consult_failure_degrades`） |
| TC-PIN-10 | 同 Requirement Scenario「独立块且位置在最前」 | `LLMPlanner` 在 `pinned_notes` 与 `notes` **同时非空** / 缺省两种上下文装配 prompt | 同时非空 ⇒ 两**独立**块分列且「常驻笔记」**先于**「相关笔记」（`index` 序）；缺省 ⇒ **无**「常驻笔记」块（锚点：`::test_planner_injects_pinned_block_before_related_notes` / `::test_planner_omits_pinned_block_when_empty`） |
| TC-PIN-11 | 同 Requirement CLI + Scenario「pin/unpin 持久化往返」 | 跨实例：`core-agent notes pin <id>` → `notes show` → `notes unpin`；未知 id | 落盘真源读回 `pinned is True`；`show` 输出含 `- pinned: true`；`unpin` 后 `False`；未知 id ⇒ 退出码 1 + stderr `NOTE_NOT_FOUND`（锚点：`test_entry.py::test_notes_pin_then_show_marks_pinned` / `::test_notes_pin_missing_note_returns_nonzero` / `::test_notes_pin_is_idempotent` / `::test_notes_list_marks_pinned` / `::test_notes_usage_lists_pin_verbs`） |
| TC-PIN-12 | 同 Requirement（全局文档层，不参与会话隔离） | 内省 `pinned`/`pinned_digest`/`set_pinned` 参数名；两会话下同一常驻源注入 | 均**无** `session` 维度；两处注入块**相同** —— 常驻层与 Consult 同为全局刻意知识（锚点：`test_session_isolation.py::test_notes_pinned_is_not_session_scoped` + `::test_notes_api_has_no_session_dimension[pin/pinned/pinned_digest/set_pinned]`） |
| TC-PIN-13 | 同 Requirement（**消歧**：不改变未标记笔记口径 + 零回归） | 既有 `tests/test_notes.py`（含 `digest` 三例）/ `tests/test_notes_loop.py`（含「相关笔记」两例）/ `tests/test_session_isolation.py` 全量用例 | 逐字不动全绿 —— 「不自动全量注入」口径只约束 Consult 命中路径；未标记笔记行为**逐字不变**（回归护栏） |

> **无手工验收项**：纯库内行为（`notes` + loop 注入 + CLI），全自动门禁（pytest）覆盖；无前端 / Rust / 真端点面。
> ⚠️ **使用红线（入 proposal 风险节）**：常驻笔记正文**每轮进模型上下文** ⇒ **绝不**把密钥 / 凭据写进常驻笔记。

---

## 66. 会话摘要提升（TC-PROMOTE，change `0150`／ADR-0142，账本 E94）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PROMOTE-01 | memory/spec.md「记忆压实」只读访问器 | 注入 summarizer 压实某会话后 `summary_for(<该会话>)`；`summary_for(<他会话>)`；`summary_for("")` | 命中条目 `id == "compaction.summary.<sid>"`、`kind=="semantic"`、`tags` 含 `summary`；他会话 ⇒ `None`；空串命中 `compaction.summary.default`（锚点：`test_memory.py::test_summary_for_returns_session_summary_entry` / `::test_summary_for_default_session_key`） |
| TC-PROMOTE-02 | 同 Requirement（只读：零写入 / 零效应） | 压实后连续两次 `summary_for(sid)`；比对前后 `audit()` 快照与 `EffectTracker.audit("compaction.<sid>")` 条数 | 条目 `(id, layer, reuse_count, importance)` **逐字不变**、效应面**不增**（锚点：`::test_summary_for_is_read_only`） |
| TC-PROMOTE-03 | 同 Requirement（未注入摘要器 ⇒ 无摘要） | 裸 `MemoryStore()` 压实后 `summary_for(sid)` | `None`（未写摘要）（锚点：`::test_summary_for_none_without_summarizer`） |
| TC-PROMOTE-04 | notes/spec.md「会话摘要提升（promotion）」Scenario「提升落 canonical 且可读回」 | `promote_session_summary(store, 摘要, session_id=…)`；**新实例**读回 | 正文含摘要内容、`source == "notes.promote"`、`pinned is True`（锚点：`test_notes_promote.py::test_promote_writes_canonical_from_summary`） |
| TC-PROMOTE-05 | 同 Requirement Scenario「幂等：重复提升单条覆盖」 | 同会话提升两次（第二次摘要内容不同） | 命中**同一** `note_id`；canonical 仅**一条** `session-*`；内容为第二次（覆盖式）（锚点：`::test_promote_is_idempotent_single_note_per_session`） |
| TC-PROMOTE-06 | 同 Requirement Scenario「note_id 确定性派生」+ CLI | 同 `session_id` 两次提升；跨进程两次 `core-agent notes promote <sid>` | 落同一 `note_id == "session-<slug>"`；跨进程仍**单条**、内容为第二次（锚点：`::test_promote_note_id_derived_deterministically` ＋ `test_entry.py::test_notes_promote_idempotent_across_processes`） |
| TC-PROMOTE-07 | 同 Requirement（显式 `--as` 覆盖 + 标题） | `promote_session_summary(..., as_note_id="my-topic", title="我的主题")` | 落 `my-topic` 且 `title == "我的主题"`（锚点：`::test_promote_as_overrides_note_id`） |
| TC-PROMOTE-08 | 同 Requirement（来源标注） | 提升后读 `note.tags` | 含 `session:<sid>` 与 `summary`（锚点：`::test_promote_tags_carry_session_provenance`） |
| TC-PROMOTE-09 | 同 Requirement Scenario「无摘要 / 空 slug ⇒ 不写盘 + 非零退出」 | `session_id="..."`（不可 slug）且无显式 id；CLI `notes promote <无摘要会话>` | 函数 ⇒ `None` 且目录无 `.md`；CLI ⇒ 退出码 1 + stderr 非空、**不写任何文件**、**不新增**错误码（锚点：`::test_promote_empty_slug_returns_none_and_writes_nothing` ＋ `test_entry.py::test_notes_promote_missing_summary_returns_nonzero`） |
| TC-PROMOTE-10 | 同 Requirement CLI 面 | 跨进程：播种摘要 → `notes promote` → `notes show` / `notes list`；`notes`（无子命令） | `show` 含摘要正文、`source == "notes.promote"`、`- pinned: true`；`list` 该行尾 `\t[pinned]`；usage 列出 `promote <session-id>`（锚点：`test_entry.py::test_notes_promote_writes_note_and_show_reads_it` / `::test_notes_promote_marks_pinned` / `::test_notes_usage_lists_promote_verb`） |
| TC-PROMOTE-11 | 同 Requirement Scenario「提升后对任意会话可见（全局层护栏）」 | 提升后在**不同** `session_id` 上下文 `_consult_notes` | 两会话命中集**相同**（非会话私有）（锚点：`test_session_isolation.py::test_notes_promoted_note_is_global_layer`） |
| TC-PROMOTE-12 | 同 Requirement Scenario「不自动触发（设计裁决护栏）」 | 跑一轮触发压实的 loop（注入 memory+summarizer+notes 钩子） | 压实确已产摘要；canonical 目录**无**任何 `session-*` note（锚点：`test_notes_loop.py::test_loop_compaction_does_not_auto_promote`） |
| TC-PROMOTE-13 | 同 Requirement（**零回归护栏**） | 既有 `tests/test_notes.py` / `test_memory.py` / `test_notes_loop.py` / `test_entry.py` / `test_session_isolation.py` 全量 | 逐字不动全绿 —— `notes` 既有 4 条 Requirement 的 Scenario**逐字不变**（本 change 对 notes **纯 ADDED**；memory 仅追加只读条款） |

> **无手工验收项**：纯库内行为（`notes` 提升 + `memory` 只读访问器 + CLI），全自动门禁（pytest）覆盖；无前端 / Rust / 真端点面。
> ⚠️ **使用红线（入 proposal 风险节与 ADR-0142 局限）**：提升产出**自动置常驻** ⇒ 摘要正文**每轮进模型上下文**，
> 操作者须在提升前 **review 摘要**，**绝不**提升含密钥 / 凭据的摘要。

---

## 67. 笔记写入来源守护（TC-WRITESAFE，change `0151`／ADR-0143，账本 E95）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-WRITESAFE-01 | notes/spec.md「Consult → Build → Update 循环纪律」Scenario「逐轮写回不覆写外来源笔记」 | 先落一篇 `source="notes"` 的人工笔记（`note_id == slug_topic(task)`），再跑成功轮 `observe_turn(task, …)` | 人工笔记正文与标题**逐字不变**；返回 note 落**派生主题** `<topic>-2` 且含本轮步骤（锚点：`test_notes.py::test_observe_turn_does_not_clobber_foreign_source_note`） |
| TC-WRITESAFE-02 | 同 Requirement（同来源覆盖式，**零回归**） | 连续两轮 `observe_turn` 同一 task（既有笔记来源 `notes.turn`） | 仍覆盖**同一** `note_id`；文件为第二次内容、不含第一次（锚点：`::test_observe_turn_overwrites_own_source_same_topic`） |
| TC-WRITESAFE-03 | 同 Requirement（派生主题**复用**、不增长） | 外来源占据主题下连续两轮 `observe_turn` | 两轮落**同一**派生主题 `k-2`；目录仅 `k.md` + `k-2.md`（锚点：`::test_observe_turn_derived_topic_reuses_own_across_rounds`） |
| TC-WRITESAFE-04 | 同 Requirement（**常驻**外来源不被污染） | 外来源 **常驻**笔记（`source="notes"`、`pinned=True`）撞 task slug，跑 `observe_turn` | 常驻笔记正文/标题逐字不变、`pinned` 保留；沉淀落 `<topic>-2`（锚点：`::test_observe_turn_does_not_clobber_pinned_foreign_note`） |
| TC-WRITESAFE-05 | notes/spec.md「会话摘要提升（promotion）」Scenario「撞非 promotion 来源 ⇒ 拒绝且不写盘」 | 先落人工笔记 `note_id == "session-<slug>"`，再 `promote_session_summary(store, 摘要, session_id=…)`（不给 `--as`） | 函数返回 `None`、人工笔记**逐字不变**（锚点：`test_notes_promote.py::test_promote_refuses_to_clobber_foreign_source_note`） |
| TC-WRITESAFE-06 | 同 Requirement（显式 `--as` = 授权覆写） | `promote_session_summary(..., as_note_id="manual")`（撞人工笔记） | 照常覆写：`source == "notes.promote"`、`pinned`、正文含摘要（锚点：`::test_promote_explicit_as_is_authorized_to_overwrite`） |
| TC-WRITESAFE-07 | 同 Requirement CLI 面（撞车非零退出） | 播种摘要 + 手写 canonical 人工笔记 `session-s1.md`；跨进程 `notes promote s1` | 退出码非零 + stderr 非空；文件**逐字不变**、`session-*.md` 仅一条（锚点：`test_entry.py::test_notes_promote_refuses_foreign_source_note`） |

> **无手工验收项**：纯库内行为（`observe_turn` 来源守护 + `promote` 撞车拒绝 + CLI），全自动门禁（pytest）覆盖。
> 语义：**一条主题只由产生它的写路径覆写**（provenance guard）；不推翻「覆盖式（最新即权威）」，只约束**跨来源**覆写；**不删除**任何笔记。

---

## 68. loop token 记账口径（TC-TOKACC，change `0152`／ADR-0144，账本 E96）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-TOKACC-01 | loop/spec.md「错误与预算控制」记账口径 + Scenario「provider 实报为记账下界」 | planner 探针报出 10000 提示 token；本轮 user 仅 `"hi"`；`token_budget=100` | 本轮**终止**且 `TOKEN_BUDGET_EXCEEDED`、`failed` 为真 —— 旧口径只记 0～3 token ⇒ 闸门看不见真实提示词大小（锚点：`test_loop_token_accounting.py::test_gate_uses_planner_reported_prompt_tokens`） |
| TC-TOKACC-02 | 同 Requirement（**零回归**：无探针 ⇒ 退化估算） | 既有形态 planner 替身（无 `last_prompt_tokens`）；`token_budget=100` | 本轮照常完成（`reply == "ok"`、`failed` 假）—— 探针缺失不改变既有 planner 行为（锚点：`::test_no_probe_degrades_to_estimate`） |
| TC-TOKACC-03 | 同 Requirement（探针降级不阻断） | planner 暴露的探针**抛错** | 当作「无观测」降级：本轮照常完成、**不抛裸异常**（锚点：`::test_broken_probe_degrades_without_raising`） |
| TC-TOKACC-04 | 同 Requirement Scenario「记账计入系统提示与工具 schema」 | `LLMPlanner.last_prompt_tokens()`：provider **未报用量**（0）；对照上下文含 / 不含 `pinned_notes` 前缀 | 两者均 > 0 且**含前缀者更大** —— 装配全量估算（含系统提示块）计入（锚点：`::test_planner_probe_estimates_full_assembly_without_usage`） |
| TC-TOKACC-05 | 同 Requirement Scenario「provider 实报为记账下界」 | 同一上下文：provider 报 999 vs 报 0 | 报 999 时探针值 **≥ 999**，且 **≥** 报 0 时的纯估算值（实测抬升下界）（锚点：`::test_planner_probe_takes_reported_usage_as_lower_bound`） |
| TC-TOKACC-06 | 同 Requirement（工具 schema 计入） | 同上下文：注入 `tools.echo` 工具提供者 vs 不注入 | 有工具 ⇒ 探针值**更大**（工具 schema 序列化计入装配估算）（锚点：`::test_planner_probe_counts_tool_schemas`） |
| TC-TOKACC-07 | 同 Requirement（**零回归护栏**） | 既有 `tests/test_loop.py` / `test_history_replay.py` / `test_context_compaction.py` / `test_loop_budget_config.py` 全量 | 逐字不动全绿 —— 阈值数字（`token_budget`）与窗口派生规则**不变**，仅记账口径覆盖全量（`test_history_replay.py::test_history_tokens_counted_into_budget` 断言值 210 不变）（锚点：`::test_history_tokens_counted_into_budget`） |

> **无手工验收项**：纯库内行为（loop 记账 + planner 探针），全自动门禁（pytest）覆盖；无前端 / Rust / 真端点面。
> 语义：记账口径**只改记账**，不改阈值与派生规则；口径缺陷的**真实后果**是预算闸门偏晚 ⇒ 撞厂商
> `context_length_exceeded` 400，而非优雅的 `TOKEN_BUDGET_EXCEEDED`。

---

## 69. 会话摘要「首次越界」半自动提升（TC-SEMIAUTO，change `0153`／ADR-0145／路线图 G3）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-SEMIAUTO-01 | memory/spec.md「记忆压实」Scenario「摘要首次越过上界交付提升钩子一次」 | 会话 `s1` 注摘要器（产出 > `MAX_SUMMARY_CHARS`）+ 提升钩子替身；首次 `compact(session_id="s1")`；再添条目、二次压实 | 首次**恰一次**交付、收到 `(s1, 该摘要条目)`；**已越界**二次压实**不再**交付（锚点：`test_memory_summary_promotion.py::test_summary_crossing_bound_delivers_promotion_once`） |
| TC-SEMIAUTO-02 | 同 Requirement Scenario「未越界或未注入钩子 ⇒ 不交付」 | 摘要器产出 ≤ 上界（`"结论：短"`）；注入钩子 | 钩子**从不**被调用（边界护栏）（锚点：`::test_summary_below_bound_never_delivers`） |
| TC-SEMIAUTO-03 | 同 Requirement（**零回归护栏**） | 注摘要器（产出越界）、**不**注提升钩子 | 不交付、**不抛**；摘要照写（``summary_for`` 非空）——缺省 UNWIRED 逐字不变（锚点：`::test_promoter_unwired_is_noop`） |
| TC-SEMIAUTO-04 | 同 Requirement Scenario「提升钩子抛错降级不牵连压实」 | 钩子**抛错**；摘要越界 | `warnings.warn`（`RuntimeWarning`）留痕；摘要**仍**写回、原条目**仍**迁 L4（压实不中断）（锚点：`::test_promoter_exception_degrades_without_aborting_compaction`） |
| TC-SEMIAUTO-05 | 同 Requirement（`session_id` 空串不交付） | 条目会话为空串、摘要越界、`compact()`（全量） | 钩子**不**被调用；摘要照写（key 归 `default`）（锚点：`::test_empty_session_id_not_delivered`） |
| TC-SEMIAUTO-06 | notes/spec.md Scenario「首次越界 ⇒ 半自动提升且不自动 pin」+「已越界不再重复交付」 | 端到端：`MemoryStore` + `NoteStore` + 真实闭包（`pin=False`）；越界后二次压实 | canonical 落**一篇** `session-s1`（`source=notes.promote`、正文含摘要、`pinned is False`）；二次压实仍**单条**且 `pinned` 仍 `False`（幂等）（锚点：`::test_end_to_end_semi_auto_promotion_lands_canonical_not_pinned`） |
| TC-SEMIAUTO-07 | notes/spec.md Scenario「不自动触发（设计裁决护栏）」 | 跑一轮触发压实的 loop，其会话摘要**未越界**（短摘要）+ 注入钩子替身 | 钩子 `delivered == []`；canonical 目录**无** `session-*.md` —— 半自动提升**仅**由「首次越过」触发（锚点：`test_notes_loop.py::test_loop_compaction_below_bound_does_not_promote`） |
| TC-SEMIAUTO-08 | notes/spec.md「会话摘要提升」置常驻分路径 | `promote_session_summary(..., pin=False)`（半自动）；对照缺省 `pin=True`（显式） | `pin=False` ⇒ 产出 `pinned is False`（落盘真源亦然）；缺省仍 `True`（显式路径逐字不变）（锚点：`test_notes_promote.py::test_promote_pin_false_leaves_note_not_pinned`） |
| TC-SEMIAUTO-09 | 全 Requirement（**零回归护栏**） | 既有 `tests/test_notes.py` / `test_notes_loop.py`（其余用例）/ `test_notes_promote.py`（其余用例）/ `test_memory.py` / `test_session_isolation.py` 全量 | 逐字不动全绿 —— 缺省 UNWIRED ⇒ 约 60 处 `MemoryStore(...)` 调用点与既有提升行为**逐字不变**（锚点：全量 `pytest -q`） |

> **无手工验收项**：纯库内行为（memory 交付钩子 + notes 落 canonical），全自动门禁（pytest）覆盖；
> 无前端 / Rust / 真端点面。语义：**越界即滚合并开始截断既有内容**（信息不可逆销毁）⇒ 首次越界时
> 止损落 canonical；**一次语义**杜绝以已稀释的后继摘要覆写完整内容；半自动产出**不自动 pin**（承
> ADR-0142 局限①，不以硬约束身份逐轮占据常驻预算）。

---

## 70. 常驻笔记预算：显式优先级 + 整篇纳入 + 超限可见（TC-PINBUDGET，change `0154`／ADR-0146／路线图 G1）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PINBUDGET-01 | notes/spec.md「常驻（pinned）笔记」Scenario「优先级往返 + 幂等 + 逐轮写回不抹除」 | `render_note` / `parse_note`：`pin_priority=5`；缺省 0；`- pin_priority: abc` | 往返得 5；缺省**不含**该行（既有渲染逐字不变）；`abc` ⇒ **0**（fail-closed）（锚点：`test_notes_pinned_budget.py::test_render_parse_pin_priority_roundtrip` / `::test_render_omits_pin_priority_at_zero` / `::test_parse_pin_priority_unparseable_is_zero`） |
| TC-PINBUDGET-02 | 同 Requirement Scenario「优先级决定在场（预算紧张时高优先级优先）」 | 三篇常驻：`c`/`a` 优先级 5、`b` 优先级 1 | `pinned()` 次序 `[a, c, b]`（优先级降序、同优先级 `note_id` 升序）（锚点：`::test_pinned_orders_by_priority_desc_then_note_id`） |
| TC-PINBUDGET-03 | 同 Requirement Scenario「整篇纳入，绝不半篇」 | `a` 短、`b` 4000 字（整篇即超）、`c` 短（次序在 `b` 后） | 块含**整篇** `a`；`b` 一段都**不在**（绝不半篇）；`c` **不**越位挤入（在场集合＝优先级次序前缀）（锚点：`::test_digest_includes_whole_notes_and_excludes_overflow_whole`） |
| TC-PINBUDGET-04 | 同 Requirement Scenario「超限可见（留痕 + 未进场篇目可查）」 | 如上发生排除；对照合计未超预算 | 排除 ⇒ `warnings.warn`（`RuntimeWarning`）+ `pinned_overflow() == ["b","c"]`；未超 ⇒ **不**告警（`simplefilter("error")`）+ 空列表（锚点：`::test_digest_without_overflow_neither_warns_nor_reports`） |
| TC-PINBUDGET-05 | 同 Requirement Scenario「单篇超限仍整篇纳入（不空块）」 | 唯一常驻篇自身 > `_MAX_PINNED_CHARS` | 该篇**整篇**在场（块非空）、留痕；`pinned_overflow()` **不含**它（锚点：`::test_digest_single_oversized_note_is_included_whole`） |
| TC-PINBUDGET-06 | 同 Requirement（空正文不占块、不计未进场） | 一篇空正文常驻 + 一篇正常常驻 | 块只含正常篇；不告警；`pinned_overflow() == []`（锚点：`::test_digest_empty_body_notes_neither_occupy_nor_overflow`） |
| TC-PINBUDGET-07 | 同 Requirement Scenario「优先级往返 + 幂等 + 逐轮写回不抹除」 | `set_pinned(priority=5)` 落盘 / 同值再置 / `unpin` / 逐轮写回（同来源） | 落盘含 `- pin_priority: 5`、新实例读回 5；同值不写盘不 bump；`unpin` 归零且行消失；`observe_turn` 保留优先级（锚点：`::test_set_pinned_priority_roundtrip_and_idempotent` / `::test_unpin_zeroes_priority` / `::test_observe_turn_preserves_pin_priority`） |
| TC-PINBUDGET-08 | CLI 面（`notes pin --priority` / `notes pinned`） | `notes pin 约束 --priority 5`；两篇常驻（高优先级短篇 + 超预算长篇）后 `notes pinned` | 落盘含 `- pin_priority: 5`、`unpin` 归零；`notes pinned` 报「`[在场]` / `[未进场]`」并含两篇 id（锚点：`test_entry.py::test_notes_pin_with_priority_persists` / `::test_notes_pinned_reports_in_context_and_overflow`） |
| TC-PINBUDGET-09 | 同 Requirement（**零回归护栏**） | 既有 `test_notes.py::test_store_pinned_digest_is_deterministic_and_capped`（按新契约改写：整篇排除替代字符切片）/ `test_session_isolation.py`（`pinned_overflow` 纳入全局层钉住）/ 其余 `test_notes*.py` / `test_entry.py` 全量 | 逐字不动全绿 —— `pin_priority` 缺省 0 且排序回落到 `note_id` ⇒ 未设优先级的既有常驻笔记行为**逐字不变**（锚点：全量 `pytest -q`） |

> **无手工验收项**：纯库内行为（canonical 追加可选行 + 整篇装配 + CLI 报出），全自动门禁（pytest）覆盖。
> 语义：**在场判据＝显式优先级**（操作者的决定，不踩 `note_id` 字典序）；**整篇纳入**杜绝半截硬约束
> （可能语义反转）；**超限可见**（warn + `pinned_overflow` + `notes pinned`）杜绝静默缺席。

---

## 71. 结构化实体抽取（关键事实）：密钥引用式 + fail-closed 脱敏（TC-KEYFACT，change `0155`／ADR-0147／路线图 G4）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-KEYFACT-01 | memory/spec.md「结构化实体抽取（关键事实）」密钥红线条款 | `scrub_key_fact`：`value` 为已知前缀族（`sk-` / `sk-ant-` / `ghp_` / `AKIA` / `xoxb-`）、PEM 私钥块、`password: …` 赋值式；以及 38 字符长随机串；均带 `ref` | 一律 **强制** `<redacted>`（`ref` 原样保留）（锚点：`test_memory_key_facts.py::test_scrub_redacts_secret_shaped_values` / `::test_scrub_redacts_long_random_string`） |
| TC-KEYFACT-02 | 同 Requirement（引用式取值一律脱敏） | `value="生产集群 A"`（看似正常）+ `ref="coeffect:env"` | `value` **一律** `<redacted>`（有引用即不留明文）；`ref` 进 `tags`（锚点：`::test_scrub_forces_redacted_when_ref_present`） |
| TC-KEYFACT-03 | 同 Requirement Scenario「fail-closed —— 裸密钥无引用则整条丢弃」 | `value` 为密钥形态、`ref` 为空；同批另一条合规事实 | 该条 `scrub_key_fact` ⇒ `None`、**不落库**；`warnings.warn` 留痕**含实体名、不含取值**；同批合规条照常落库（锚点：`::test_scrub_drops_bare_secret_without_ref` / `::test_secret_without_ref_is_dropped_with_warning` / `::test_mixed_batch_keeps_compliant_facts`） |
| TC-KEYFACT-04 | 同 Requirement Scenario「抽取落库 + 同实体幂等覆盖」 | 抽取器返回「部署环境 → 生产集群 A」 | `id="keyfact.部署环境"`、`kind="semantic"`、`source="extraction"`、`trace_id="compaction.s1"`、`tags` 含 `key_fact`/`entity:部署环境`/`session:s1`、`session_id=""`（全局层）；再次同实体不同取值 ⇒ 仍**单条**（覆盖式不增长）（锚点：`::test_extracted_key_fact_lands_with_expected_shape` / `::test_same_entity_is_idempotent_overwrite`） |
| TC-KEYFACT-05 | 同 Requirement（属全局层 ⇒ 跨会话可见） | 会话 `s1` 抽出的关键事实；以 `session_id="s2"` 检索 | 仍可召回（关键事实不参与会话隔离）（锚点：`::test_key_fact_is_global_so_visible_across_sessions`） |
| TC-KEYFACT-06 | 同 Requirement Scenario「未注入抽取器 ⇒ 零抽取、逐字不变」 | `MemoryStore` 未注入 `key_fact_extractor`；对照仅注入抽取器（未注入摘要器） | 未注入 ⇒ 无 `key_fact` 条目、摘要与迁移逐字不变；仅抽取器 ⇒ 抽取生效、不写摘要条目（两者**互不依赖**）（锚点：`::test_unwired_extractor_changes_nothing` / `::test_extraction_runs_without_summarizer`） |
| TC-KEYFACT-07 | 同 Requirement Scenario「抽取器抛错或返回不可解析 ⇒ 降级不抽取」 | 抽取器抛错 | 不落库、`warnings.warn` 留痕；摘要**仍**写回、原条目**仍**迁 L4（压实不中断）（锚点：`::test_extractor_exception_degrades_without_aborting_compaction`） |
| TC-KEYFACT-08 | 同 Requirement Scenario「关键事实条目随压实一并可撤销」 | 触发带抽取的压实后按 `compaction.s1` 回滚 | 关键事实条目与摘要一并移除、原条目迁回原层（锚点：`::test_key_facts_are_reverted_with_compaction`） |
| TC-KEYFACT-09 | 同 Requirement（条数与长度有界，先脱敏后截断） | 一次返回 `MAX_KEY_FACTS_PER_COMPACT+4` 条；`entity`/`value` 各 400 字；超长密钥 | 落库恰 `MAX_KEY_FACTS_PER_COMPACT` 条；长度 ≤ `_MAX_FACT_CHARS`；先脱敏后截断（不残留明文片段）（锚点：`::test_fact_count_is_bounded` / `::test_fact_length_is_bounded` / `::test_scrub_redacts_before_truncating`） |
| TC-KEYFACT-10 | 同 Requirement（解析容错）+「无行动不记忆」 | `parse_key_facts`：代码围栏 / 非 JSON / 非数组 / 元素非对象 / 缺字段；无 episodic 条目时压实 | 围栏可解析；不可解析 ⇒ `[]`；畸形元素跳过；**无 episodic 条目 ⇒ 不抽取**（锚点：`::test_parse_tolerates_code_fence_and_surrounding_text` / `::test_parse_returns_empty_on_unparseable` / `::test_parse_skips_malformed_items` / `::test_no_episodic_entries_no_extraction`） |

> **无手工验收项**：纯库内行为（抽取接缝 + 脱敏原语 + 落库形态），全自动门禁（pytest）覆盖。
> 语义：**信任边界在 store**（注入的抽取器不构成信任边界，脱敏无条件执行）；**over-redact**（拿不准
> 即多脱敏，落在安全侧）；**fail-closed**（记不住引用就不记）；**与摘要互不依赖**、**与压实同 trace 可撤销**。

---

## 72. TUI 续聊转录按 Markdown 渲染（TC-RESUMEMD，change `0157`／ADR-0149，账本 E98）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-RESUMEMD-01 | ui/spec.md「CLI 友好交互」Scenario「续聊转录按同格式渲染（回复不退化为明文）」 | 真 `TranscriptStore` 会话，一轮 `user="给我个 demo"` / `assistant="示例：\n\n```python\nprint('hi')\n```\n"`；`build_app(api, session_id)` 挂载后驱动 `run_test` | 时间线内出现 **`MarkdownFence`**（≥1）且 `Markdown` 源含 ` ```python ` —— 即 agent 回复按 Markdown 渲染、围栏成代码块（锚点：`tests/test_repl.py::test_resumed_agent_reply_renders_as_markdown`） |
| TC-RESUMEMD-02 | 同 Requirement（**零回归护栏**：内容仍在时间线、`❯` 回显不变、复用不新建） | 同会话含 `user="早前的问题"` / `assistant="早前的回答"`；`create_session` 被 `monkeypatch` 为 `pytest.fail` | 时间线文本同时含「早前的问题」与「早前的回答」（回复改落 `Markdown.source`，内容**仍在**）；**不**新建会话（锚点：`::test_build_app_resumes_existing_session`，取文本助手 `_timeline_texts` 已下沉为同收 `Static` + `Markdown`） |

> **无手工验收项**：纯库内行为（TUI 回放渲染格式），全自动门禁（pytest headless `run_test`）覆盖。
> 语义：**单一渲染口径** ——「agent 回复」无论从实时流式还是续聊铺入进入时间线，都以**同一** Markdown
> 格式呈现（围栏成代码块、表格成表格）；用户消息仍为 `❯` 逐字转义行；既有转录**内容**不被改写。
> **已知局限**：Web/Desktop SPA 仍无 Markdown 渲染（另一端，承 E88 局限②）。

---

## 73. TUI 代码块背景可辨识（TC-CODEBG，change `0158`／ADR-0150，账本 E98 后续）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-CODEBG-01 | ui/spec.md「CLI 友好交互」Scenario「代码块与正文可辨识（深色主题下不成透明块）」 | 真 `TranscriptStore` 会话，一轮 `assistant="示例：\n\n```python\nprint('hi')\n```\n"`；`build_app` 挂载后驱动 `run_test`，取时间线内首个 `MarkdownFence` 的**运行时解析**背景 | 背景 **alpha == 1.0**（不透明）**且**叠加到主背景（`$background`）后的 **WCAG 对比度 ≥ 2.0**（锚点：`tests/test_repl.py::test_code_block_background_is_distinguishable`） |

> **无手工验收项**：纯样式，但以**运行时解析的样式**为断言面（CSS 变量 → 具体色值 → 叠加到主背景 → WCAG 比值），
> 全自动门禁覆盖；**修复前**该用例红（Textual 默认 `black 10%` ⇒ alpha=0.1 ⇒ 对比度 ≈ 1.02）。
> 语义：**「围栏渲染为代码块」含视觉可辨识** —— 语法层（走 `Markdown`）之外，块还须**看得见**：
> 背景不透明 + 与主背景对比度 ≥ 2.0。取**深灰**（`$surface-lighten-3`）而非浅灰，是为保住亮色 token 高亮。
> **已知局限**：颜色偏暗的观感风险（一处 CSS 可调）；对比度按 `$background` 计算（主题改色须重估，测试会先红）；
> 未覆盖 `:ansi` 分支（本主题 `ansi=False`）；Web/Desktop SPA 的代码块视觉属另一端。

---

## 74. TUI 斜杠命令浮层与补全（TC-CMDPAL，change `0159`／ADR-0151）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-CMDPAL-01 | ui/spec.md「CLI 友好交互」Scenario「斜杠唤起命令浮层并按前缀收窄」 | 纯函数 `_palette_options("/")` / `("/ta")` | 一级候选＝**全部**登记命令；`"/ta"` 收窄为 `/task`（锚点：`tests/test_repl.py::test_palette_options_lists_all_commands_on_slash`、`..._filters_by_command_prefix`） |
| TC-CMDPAL-02 | 同上 Scenario | 纯函数 `_palette_options` 未知前缀 `/zzz`、普通文本 `hello`、注册命令加空格后参数含空格 `/focus a b`；非枚举参数命令 `/task ` | 一律返回 `[]`（不呈现浮层）（锚点：`..._closed_for_unknown_or_plain_input`、`..._closed_when_arg_has_space`、`..._no_second_level_for_non_enum_arg`） |
| TC-CMDPAL-03 | ui/spec.md「CLI 友好交互」Scenario「二级参数候选取自既有面」 | 纯函数 `_palette_options("/focus ", subtask_ids=("1","12","2"))` | 二级候选**取自传入的在途子任务**，按已输入前缀收窄（锚点：`..._second_level_lists_and_narrows_subtasks`） |
| TC-CMDPAL-04 | ui/spec.md「CLI 友好交互」Scenario「斜杠唤起命令浮层并按前缀收窄」 | 真 TUI：`#input` 值置 `"/"` 后驱动 `run_test` | `#palette` **`display` 为真**（可见）且选项 id 含既有 5 命令；清空输入后 **`display` 为假**（锚点：`tests/test_repl.py::test_palette_opens_on_slash_and_lists_registered_commands`、`..._closes_when_input_cleared`） |
| TC-CMDPAL-05 | ui/spec.md「CLI 友好交互」Scenario「键盘移动高亮并采纳（只改写输入框、不提交）」 | 真 TUI：浮层开，按 `down`/`up`；再按 `tab` | 高亮随 `↓`/`↑` 移动且**焦点仍在 `#input`**；`tab` 把候选写回 `#input` 且 `RecordingLoop.inputs` **不增长**（锚点：`..._arrows_move_highlight_keeping_focus_in_input`、`..._tab_accepts_highlighted_command_without_submitting`） |
| TC-CMDPAL-06 | ui/spec.md「CLI 友好交互」Scenario「采纳不改变既有命令的语义与分发次序」 | 真 TUI：浮层开且输入为**完整命令**（如 `/main`）时回车；未知前缀 `/zzz` 回车；`escape` 关浮层 | 前缀被补全但**不提交**（`loop.inputs` 不增）；`/zzz` **不被浮层劫持**、按既有路径当普通消息；`escape` 收起且**输入值不变**（锚点：`..._enter_completes_prefix_without_submitting`、`..._does_not_hijack_unknown_slash_input`、`..._escape_closes_without_touching_input`） |
| TC-CMDPAL-07 | ui/spec.md「CLI 友好交互」Scenario「审批挂起期间不呈现浮层」 | 真 TUI：审批挂起中把 `#input` 置 `"/"` | `#palette` **不呈现**（`display` 为假）（锚点：`..._suppressed_while_approval_pending`） |
| TC-CMDPAL-08 | ui/spec.md「CLI 友好交互」Scenario「命令幽灵补全与 `→` 采纳」 | 真 TUI：`#input` 值置 `"/re"`；再按 `→` | `Input` 原生补全位给出 `/recall`（幽灵补全与浮层**同源**）；`→` 采纳后值变为 `/recall`（锚点：`..._ghost_completion_shows_and_accepts_remainder`） |
| TC-CMDPAL-09 | ui/spec.md「CLI 友好交互」（**单一真源**：真源内每条命令 SHALL 可由分发链实际执行） | 真 TUI：逐条驱动真源内命令的**规范形态**（`/task 目标` / `/focus 1` / `/main` / `/summon qinglong` / `/recall qinglong`） | 每条均落**既有分发链**（`RecordingLoop.inputs` **不增长**）；「只登记、未接线」⇒ 本用例**必红**（锚点：`tests/test_repl.py::test_registry_commands_are_all_dispatchable`） |
| TC-CMDPAL-10 | —（**零回归**） | 真 TUI：浮层**关闭**时按 `↑`/`↓`/`escape` | 三键**一律放行**、不改变输入框与时间线（浮层关闭时既有按键逐字不变）（锚点：`..._palette_absent_keeps_arrows_and_escape_inert`） |

> **无手工验收项**：键盘面、呈现面、采纳面与**单一真源守护**全部以 headless `run_test` 驱动 + 纯函数直测覆盖；
> 浮层「存在/可见」以 `#palette` 的**运行时 `display`** 断言（非 `visible` 链，避免父级不可见干扰）。
> 语义：命令清单**单一真源**（`_COMMANDS`）由**可执行守护**绑定到分发链 —— 登记后未接线即红；
> **采纳是纯呈现层**（只改写输入框、不提交），完整命令 / 未知前缀 / 审批 y / n 的既有分发次序**逐字不变**。
> **已知局限**：命令浮层的二级参数目前仅 `/focus`（`self._open` 键）可枚举，`/resume` 待 0160 进表（避免「登记即无反应」）；
> 浮层沿 `#panel` 的 `display` 翻转惯用法（不引 `Screen`/`layers`）；`OptionList` 高亮在**未聚焦**时的可见性依赖主题样式（本 change 未另加覆盖规则）。

---

## 75. TUI 会话切换（TC-RESUME，change `0160`／ADR-0152）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-RESUME-01 | ui/spec.md「TUI 会话切换（`/resume`）」Scenario「切换会话并还原其内容」 | 纯函数 `_palette_options("/resume ", subtask_ids=["1"], sessions=(("s-alpha","部署脚本 · s-alpha"),…))` | 二级候选**只**取会话面（不吃子任务面）：`/resume s-alpha`、`/resume s-beta`，显示行取会话标题（锚点：`tests/test_repl.py::test_palette_options_second_level_lists_sessions`） |
| TC-RESUME-02 | 同上 Scenario | 纯函数 `/resume 重构`（显示行前缀）、`/resume s-a`（标识前缀）、`/resume zzz`（无匹配） | 前缀收窄：命中对应会话 / 无候选（锚点：`..._session_narrows_by_label_or_id`） |
| TC-RESUME-03 | 同上 Scenario | 真 TUI（会话 A，目标 B 含用户消息 + 带围栏的 agent 回复）：提交 `/resume <B>` | 时间线清空并铺入 B：出现 `↻ 续接会话 <B>（2 条历史已载入）`、用户消息按 `❯` 回显行、agent 回复为 **Markdown** 源文本、**`MarkdownFence` == 1**（锚点：`test_resume_switches_session_and_replays_markdown`） |
| TC-RESUME-04 | 同上 Scenario（「后续轮次落目标会话」） | 同上，切换后再发一条普通消息 | `RecordingLoop.sessions[-1] == B`（`run_loop` 收到新标识）（锚点：同上） |
| TC-RESUME-05 | 同上 Scenario「未登记会话 fail-closed（当前会话逐字不变）」 | 真 TUI：提交 `/resume nope`，随后发一条消息 | 时间线**只多一行**（`[UI_SESSION_NOT_FOUND] …`）、既有内容逐字不变；`RecordingLoop.sessions[-1] == A`（未切换）（锚点：`test_resume_unknown_session_fails_closed_without_touching_state`） |
| TC-RESUME-06 | 同上 Scenario「`/resume` 无参数只提示用法」 | 真 TUI：提交 `/resume` | 仅多一行 `用法：/resume <会话标识>`、不切换（锚点：`test_resume_without_arg_prints_usage_only`） |
| TC-RESUME-07 | 同上 Scenario「本轮执行期间拒绝切换」 | 真 TUI（门控编排器挂起在途任务）：提交 `/resume <B>` | 落「处理中」提示、**无**「续接会话」落痕（未切换）（锚点：`test_resume_rejected_while_busy`） |
| TC-RESUME-08 | 同上（「切换 SHALL 复位跨会话无意义的呈现态」） | 真 TUI：跑一轮任务 → `/focus 1`（进焦点视图）→ `/resume <B>` | 切换前焦点视图可见（前置）；切换后 `_open == {}`、`#panel` 隐藏、`#timeline` 可见（锚点：`test_resume_resets_previous_session_view_state`） |
| TC-RESUME-09 | ui/spec.md「CLI 友好交互」（**单一真源**可执行守护，承 0159） | 真 TUI：逐条驱动真源内命令的规范形态，含 `/resume <已登记标识>` | 每条均落既有分发链（`RecordingLoop.inputs` 不增长）；`/resume` **登记即接线**（锚点：`tests/test_repl.py::test_registry_commands_are_all_dispatchable`） |

> **无手工验收项**：候选面（纯函数）、切换面（时间线快照 + `MarkdownFence` 计数）、fail-closed 面
> （既有内容逐字比对 + 错误行）、会话标识落点（loop 收到的 `session_id`）、忙态拒绝与呈现态复位
> 全部以 headless `run_test` 驱动覆盖。
> 语义：**先验证后落地**（fail-closed 的关键形态 —— 不留「空时间线 + 旧会话」半切换态）；
> **切换与启动续聊共用同一铺入路径**（`_replay_history`），使「回复入口无关、格式同一」只有一处实现；
> 切换排在**忙态检查之后**（与在途轮次互斥）、**回显之前**（不产生 `/resume` 回显行）。
> **已知局限**：只切既有会话（不新建 / 删除 / 重命名）；切换即清时间线（含欢迎行，滚动位置不保留）；
> 呈现态**全局单份**、切走即清（切回不恢复展开状态）；会话清单无裁剪；未改 Web / Desktop；
> 更新时间为本地时区分钟粒度；不做「切换即续跑」（不恢复目标会话的在途编排视图）。

---

## 76. 只读诊断源（TC-DIAG，change `0162`／ADR-0153，账本 E100）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-DIAG-01 | cli-ops/spec.md「自检诊断（`doctor`）与运行状态（`status`）」Scenario「自检全绿」 | 纯函数 `collect_doctor(deps)`（配置有效 + 引用可解析 + 状态目录可写 + 注册表可读） | 无 `fail` 项；`配置`/`密钥`/`状态目录`/`工具`/`笔记`/`MCP`/`资产`/`技能` 逐项在场（锚点：`tests/test_diagnostics.py::test_doctor_all_green`） |
| TC-DIAG-02 | 同上 Scenario「存在失败项时非零退出」的纯函数面 | `collect_doctor`（`environ={}` ⇒ `${CORE_DIAG_KEY}` 不可解析） | `ok=False`；**不抛**；该项 `detail` 写明**配置键名**（`llm.api_key`）而非取值；其余项未被吞掉（锚点：`..._unresolvable_ref_fails_without_raising`） |
| TC-DIAG-03 | 同上（诊断的职责是**报告**不可用） | `collect_doctor`（config 缺 `api_key` 段） | 落成一条 `fail` 项、`detail` 非空，**不向上抛**（锚点：`..._missing_config_is_a_fail_not_a_crash`） |
| TC-DIAG-04 | 同上（能力面缺失 ≠ 系统不可用） | `collect_doctor(Deps(config=...))`（句柄全缺） | 无 `fail`、**有** `warn`（锚点：`..._warns_on_missing_handles`） |
| TC-DIAG-05 | 同上（零副作用） | `collect_doctor(state_dir=<0o500 目录>)` | 「状态目录」`fail`；探测**不新建目录**（锚点：`..._unwritable_state_dir_fails`；root 下跳过） |
| TC-DIAG-06 | 同上 Scenario「诊断输出不含密钥值」（**红线**） | 注入哨兵值 `sk-DIAG-CANARY-9f3a` 为 `${CORE_DIAG_KEY}` 的解析结果，跑 `doctor` / `status` / 五张列表视图 | 输出含**引用名** `${CORE_DIAG_KEY}`、**逐字不含**哨兵值（锚点：`..._reports_secret_ref_name_only`、`..._never_leaks_secret`、`..._render_config_masks_secret_value`） |
| TC-DIAG-07 | 同上 Scenario「运行状态概览」 | `collect_status(deps)` | 六项字段齐备（`会话数`/`内置工具`/`已安装资产`/`MCP 端点`/`模型`/`循环预算`）+ 模型名在场；配置坏时**照常出**（锚点：`..._overview_fields`、`..._survives_broken_config`） |
| TC-DIAG-08 | 同上 Scenario「存在失败项时非零退出」（**端到端**） | CLI `doctor`：全绿配置 ⇒ `0`；`${VAR}` 不可解析 ⇒ `1` | 退出码与输出同源：非零时含 `✗ 配置` 与 `llm.api_key`、不含密钥值（锚点：`tests/test_entry.py::test_doctor_exits_zero_when_all_green`、`..._exits_nonzero_on_unresolvable_secret`） |
| TC-DIAG-09 | 同上（`status` 是信息面） | CLI `status`：正常 / 配置不可读 | 两种情况**均恒 0**、六项字段在场（锚点：`tests/test_entry.py::test_status_overview_exits_zero`、`..._with_unreadable_config_still_exits_zero`） |
| TC-DIAG-10 | 同上 Scenario「诊断输出不含密钥值」（列表视图侧） | `render_mcp`（端点 `args=["--token", <哨兵>]`） | 出 `name`、**不出** `--token` 与哨兵值（锚点：`..._render_mcp_omits_args`） |
| TC-DIAG-11 | 同上（包边界，**硬红线**） | AST 扫 `src/core/diagnostics/**` 的 import 节点 | **零** `core.runtime` / `core.ui` 引用（锚点：`..._never_imports_runtime_or_ui`；红态由临时植入 probe 验证） |
| TC-DIAG-12 | 同上（句柄缺失的呈现面） | 五张列表视图各喂 `Deps()`（空） | 各出**用法提示**而非崩（TUI 里点开空表的体验）（锚点：`..._views_degrade_without_handles`） |

> **无手工验收项**：退出码、逐项状态、密钥零泄漏、视图降级、包边界全部以纯函数 + CLI 端到端覆盖；
> 唯一需**目视**的是真实 `config.yaml` 下的 `/config` 与 `doctor` 输出（自动测试只覆盖注入样本）。
> 语义：**实现追上规格**（`cli-ops` spec「状态查询命令」早已承诺健康诊断，此前 `dispatcher` 恒返回 `"ok"`）；
> **只读源与呈现面分离**（`collect_*` 产 `Report`、`render` 产行 ⇒ TUI 复用同一份，不各写一份检查逻辑）。
> **已知局限**：只判「可读 / 存在」**不探活性**（不建 MCP 连接、不真调 LLM）；资产 / 端点数取自各自落盘账本；
> 本 change 只接 **CLI**（TUI 浮层命令属 change `0163`）；`doctor` 退出码语义**有意**由「恒 0」改为「有 fail 项非零」；
> `cli_ops/dispatcher.py` 的 `status()` 分支自此不可达（不改不删）；其余运维动词仍未注册（台账 E100）。

## 77. TUI 只读命令族（TC-READONLY，change `0163`／ADR-0154）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-READONLY-01 | ui/spec.md「TUI 只读诊断命令」Scenario「浮层列出只读命令并可采纳」 | `_palette_options("/")`；`_COMMANDS` 全量 | 一级候选 **13 条**（顺序即真源顺序，含 7 条只读），采纳**只改写输入框不提交**（锚点：`tests/test_repl.py::test_palette_options_lists_all_commands_on_slash`、`..._palette_opens_on_slash_and_lists_registered_commands`、`..._palette_tab_accepts_highlighted_command_without_submitting`） |
| TC-READONLY-02 | 同上 Scenario「执行命令落结果块且不进对话」 | 7 条命令各提交一次（诊断源已接线） | 各**新增一条**结果块、**无** `❯` 回显；`loop.inputs == []` 且 `loop.sessions == []`（**零**对话轮次）（锚点：`..._readonly_commands_render_result_block_without_touching_conversation`） |
| TC-READONLY-03 | 同上 Scenario「只读命令零副作用」 | 同一会话先跑一轮普通消息（攒既有内容）再提交 `/status` | 会话标识**不变**、会话数**不变**、转录条数**不变**；时间线既有三面（Static 文本 / Markdown 源 / 围栏数）**逐字不变**、恰好**多一条**（锚点：`..._readonly_commands_have_zero_side_effects`） |
| TC-READONLY-04 | 同上 Scenario「本轮执行期间拒绝只读命令」 | `/task slow`（阻塞编排器，忙态窗口确定）后提交 `/doctor` | 落「处理中」拒绝提示、**无**结果块、`loop.inputs == []`（锚点：`..._readonly_command_rejected_while_busy`） |
| TC-READONLY-05 | 同上 Scenario「只读输出不含密钥值」（**红线**） | 注入哨兵 `sk-READONLY-CANARY-7c21` 为 `${CORE_READONLY_KEY}` 的解析结果，提交 `/config` 与 `/doctor` | 时间线含**引用名** `${CORE_READONLY_KEY}`、**逐字不含**哨兵值（锚点：`..._readonly_commands_leak_no_secret`） |
| TC-READONLY-06 | 同上 Scenario「带参数与未登记前缀走既有路径」 | 提交 `/doctor 额外参数` | 只落用法提示、**不执行**（无结果块）、`loop.inputs == []`（锚点：`..._readonly_command_with_arg_prints_hint_only`；未登记前缀 `/zzz` 的零回归由 `..._palette_does_not_hijack_unknown_slash_input` 与 `..._registry_commands_are_all_dispatchable` 分担） |
| TC-READONLY-07 | 同上（**接线守护**，防「只登记、未接线」） | `_COMMANDS` 每条命令的**规范形态**分别驱动一次；每条 `handler` 在 app 上解析 | 无一落进普通对话（`loop.inputs` 不增长）；`getattr(app, handler)` 全部可调用（锚点：`..._registry_commands_are_all_dispatchable`、`..._registry_handlers_resolve`） |

> **无手工验收项**：浮层候选、结果块、零副作用、忙态拒绝、密钥零泄漏、接线守护全部以 `run_test` 无头驱动覆盖；
> 唯一需**目视**的是真实 `config.yaml` 下的 `/config` 与 `/doctor` 输出（自动测试只覆盖注入样本）。
> 语义：**与 CLI 同源**（`/doctor` `/status` 经 `UIAPILayer.diagnostics()` 取 `core.diagnostics` 的同一份
> `collect_*` / `render_*`，**不**另写检查逻辑）；**结果不进对话**（只读 ⇒ 无轮次、无回显、零副作用）；
> **忙态不豁免**（排在 `on_input_submitted` 的忙态检查之后，与 `/resume` 同侧 ⇒ 不在流式写时间线时插块）。
> **已知局限**：`/sessions` 与 CLI `sessions` **同名异义**（前者列会话注册表，后者列 Harness Host 连接记录）；
> **只读**（写操作命令不在其内）；TUI 的工具面计数按**全量** `runtime.tools`（与 CLI 的 builtin-only 面**有意不同**）；
> 未接线诊断源 ⇒ 落一行提示（不崩）；命令清单仍是**内存真源**（配置驱动 / 插件注册命令面另立 change）。

## 78. 推理输出协议容错与失败可见（TC-PARSE，change `0166`／ADR-0156）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-PARSE-01 | loop/spec.md「推理动作解析与失败可见」形态 3 Scenario「混写正文的动作 JSON 被识别」 | `_parse("执行提交…：\n\n" + '{"tool_id": "tools.echo", "args": {"text": "hi"}}')` | `tool_id == "tools.echo"`、`args == {"text": "hi"}`、非终止动作；**不进回复**（锚点：`tests/test_loop_output_protocol.py::test_trailing_action_json_after_prose_is_tool_call`） |
| TC-PARSE-02 | 同上 Scenario「围栏包裹的尾部动作 JSON 被识别」 | `_parse(正文 + "```json\n" + 动作 JSON + "\n```")` | 同样得到工具动作（`tool_id`/`args` 正确）（锚点：`..._fenced_trailing_action_json_is_tool_call`） |
| TC-PARSE-03 | 同上 Scenario「非动作 JSON 的自然语言回复不被误判」（正文**中间**夹带） | `_parse("输出格式二选一：… " + 动作 JSON + " —— 就这样。")` | 终止动作、`reply` 为原文整段、`failed is False`（锚点：`..._action_json_mid_text_stays_reply`） |
| TC-PARSE-04 | 同上 Scenario「非动作 JSON 的自然语言回复不被误判」（文末示例**无** `tool_id`） | `_parse('建议把上限调成这样：\n\n{"max_rounds": 3, "token_budget": 8000}')` | 终止动作、`reply` 为原文、`failed is False`（锚点：`..._trailing_json_without_tool_id_stays_reply`） |
| TC-PARSE-05 | 同上 Scenario「纯 JSON 与原生工具调用路径零回归」（纯文本 / 纯 JSON） | `_parse("直接回复文本")`；`_parse(动作 JSON)` | 文本 ⇒ `{"reply": …}` 且 `failed is False`；纯 JSON ⇒ 工具动作、`failed is False`（锚点：`..._plain_text_reply_unchanged`、`..._pure_json_action_path_unchanged`） |
| TC-PARSE-06 | 同上（失败面各分支，**逐条**置位） | `_parse` 截断 JSON / 空响应 / 无 `tool_id` 与 `reply` 的对象；`LLMPlanner(_BoomLLM())` 调用抛 `LLMError` | 四者均含 `LLM_PLAN_PARSE_FAILED`（或 `LLM 调用失败`）且 `action.failed is True`（锚点：`..._truncated_json_marks_action_failed`、`..._empty_content_marks_action_failed`、`..._object_without_tool_id_or_reply_marks_action_failed`、`..._llm_error_marks_action_failed`） |
| TC-PARSE-07 | 同上 Scenario「解析失败使本轮失败」（**端到端**） | `DefaultLoop(planner=LLMPlanner(_FakeLLM(截断 JSON)), tools=…)`，挂 `turn_observer` | `LoopResult.failed is True`、`reply` 含 `LLM_PLAN_PARSE_FAILED`、观察者收到 `[False]`（锚点：`..._test_parse_failure_marks_turn_failed`） |
| TC-PARSE-08 | 同上（正常轮零回归） | 同上但内容为普通文本 | `LoopResult.failed is False`、`reply` 逐字、观察者收到 `[True]`（锚点：`..._test_normal_turn_not_marked_failed`） |
| TC-PARSE-09 | 同上形态 3（**事故复刻的端到端**：真的执行） | 内容序列 `[正文 + 动作 JSON, "完成"]`，echo 工具记录入参 | 工具**确实被调用**（`calls == ["hi"]`，旧实现此处为空）、`result.reply == "完成"`、`failed is False`（锚点：`..._test_trailing_action_json_executes_in_loop`） |

> **无手工验收项**：三形态识别、误判边界、失败态置位与端到端成败核算全部以纯函数 + `DefaultLoop` 无头驱动覆盖。
> 语义：**只认尾部、不全文扫描**（模型解释协议时会引用动作 JSON 作示例，全篇扫描会把「解释」当「执行」
> ⇒ **宁可漏检，不可误判**）；**命中即复用既有动作协议**（参数校验的单一真源在工具调用链，解析层不写第二份）；
> **失败态只属终止动作**（工具动作失败走既有 ReAct 多轮自愈口径，本次**不动**）；**不改终止语义**
> （解析失败仍以回复收尾，`loop_failed` 仍只认 `limit_reason`，转录追加零改动）。
> **已知局限**：非尾部动作 JSON 仍按答复（漏检为已知取舍）；尾部 JSON 若**确为**「示例引用」会被执行
> （缓解面是既有授权/审批链 + 事件面可见 + 工具可逆）；解析失败的**合成文案仍进转录**（既有口径）；
> 审批拒绝 `decline()` 与 `pet/safety` 阻断**不置** `failed`（属审批语义，非「推理产出不可用」）。

## 79. 收尾与维护在工作线程上执行（TC-OFFLOAD，change `0167`／ADR-0157）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-OFFLOAD-01 | loop/spec.md「收尾与维护工作的执行线程」Scenario「收尾钩子在工作线程上执行」 | `DefaultLoop(turn_observer=…)` 跑一轮，钩子内探 `asyncio.get_running_loop()` 是否成功 | 钩子在**无运行中循环**的线程上被调用（观测值 `[False]`；旧实现为 `True`）（锚点：`tests/test_loop_offload_threads.py::test_turn_observer_runs_off_loop_thread`） |
| TC-OFFLOAD-02 | 同上 Scenario「冷路径回调在工作线程上执行」 | 时钟推进越过 `maintenance_interval`，`cold_path` 内探循环 | 冷路径在**无运行中循环**的线程上被调用（`[False]`）（锚点：`..._test_cold_path_runs_off_loop_thread`） |
| TC-OFFLOAD-03 | 同上 Scenario「轮内压实不阻塞事件循环」 | 压实替身以 `time.sleep(0.3)` 真阻塞；事件循环内并发 ticker 任务 | 压实落在工作线程（`on_loop is False`）且阻塞期间事件循环持续推进（`ticks >= 5`；旧实现下 `ticks ≈ 0`）（锚点：`..._test_event_loop_not_blocked_during_compaction`） |
| TC-OFFLOAD-04 | 同上 Scenario「含同步模型调用的压实产出真的落库」（**端到端**） | 会话摘要接缝以**同步模型桥接**（只实现异步入口 ⇒ 继承的 `completion()` = `asyncio.run`）注入，跑一轮触发压实 | `compaction.summary.*` **真的落库**且含桥接产出（旧实现：`RuntimeError` 被降级链吞掉、摘要恒缺）；同步桥接调用点观测为 `False`（工作线程）（锚点：`..._test_summary_written_with_sync_llm_bridge`） |
| TC-OFFLOAD-05 | 同上 Scenario「降级语义零回归」 | `turn_observer` 抛错 + 假 tracer | 仅降级留痕（`turn_observer_failed`）；`result.reply == "done"`、`result.failed is False`（锚点：`..._test_turn_observer_failure_still_degrades`） |

> **无手工验收项**：三处边界的执行线程以「工作线程上 `asyncio.get_running_loop()` 抛 `RuntimeError`」
> 为可执行判据钉住；端到端用例用**事故现场原样**的同步桥接（`completion()` = `asyncio.run`）复现旧缺陷。
> 语义：卸载的是**执行线程**，不变的是**接口与语义** —— 三段私有方法签名与内部降级链逐字不动，
> 四个注入接缝（`turn_observer` / `cold_path` / `summarizer` / `key_fact_extractor`）仍为同步 callable。
> **已知局限**：交叉会话并发写未加锁（竞态先于本 change 存在，不引入也不消除）；`to_thread` 无超时/取消
> （卡住时本轮收尾会等它，缓解面是既有 `timeout_s` 与失败降级链）；只覆盖三处已确认边界（无自动门禁）；
> 线程跳一次成本非零；不改 `completion()` 薄壳（从事件循环内直接调用仍是错误用法，未加防呆断言）。

## 80. 诊断视图列对齐（TC-NOTES-ALIGN，change `0165`／ADR-0158）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-NOTES-ALIGN-01 | cli-ops/spec.md「诊断视图列对齐」Scenario「笔记清单等宽列」 | 笔记库两条（`a`/`短`、`longer-id`/`一个较长的标题`）⇒ `render` 去标题行取全部行 | 恰两行；每行**不含 `\t`**（锚点：`tests/test_diagnostics.py::test_render_notes_columns_aligned`） |
| TC-NOTES-ALIGN-02 | 同上 Scenario「含中日韩字符的清单仍对齐」（**本 change 的核心**） | 同上 | 各行时间戳（末尾 10 位数字）起点的**显示列**相等 —— 按字符数补齐时中文行会整体右移 ⇒ 必红（锚点：同上；显示宽度由 `unicodedata.east_asian_width` 独立计算，**不复用被测代码**以免自证） |
| TC-NOTES-ALIGN-03 | 同上 Scenario「title 回退对齐」（回归） | 常驻项清单 ⇒ `render_notes` | 既有断言 `"alpha" in out` / `"常驻" in out` 在新格式下逐字仍成立（锚点：`...::test_render_notes_marks_pinned`） |

> **无手工验收项**：列对齐以**显示宽度**为判据（`east_asian_width` 的 `WF` 类按 2 列），
> 时间戳列起点一致即通过 —— 该判据在按字符数补齐的旧实现下必红（实测同字符长度 36 而显示宽 37/43/36）。
> **已知局限**：歧义宽（`A`）字符按 1 列（与多数终端默认一致）；超长 title 拉长整行（无截断）；
> 覆盖 `render_notes`（**其余列表型视图已由 §81 覆盖**）；未做 TUI 端列宽自适应。

## 81. 诊断视图列对齐：全部列表型视图（TC-ALIGN-ALL，change `0168`／ADR-0159）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-ALIGN-ALL-01 | cli-ops/spec.md「诊断视图列对齐」Scenario「会话与 MCP 端点清单等宽列」 | 会话两条（`s1`/`日常`、`sess-2-longer`/`a much longer title`） | 各行**更新时间列**起点的**显示列**相等，且逐行不含 `\t`（锚点：`tests/test_diagnostics.py::test_render_sessions_columns_aligned`） |
| TC-ALIGN-ALL-02 | 同上 Scenario | MCP 端点两条（`remote`/`sse`、`local-mcp`/空传输 ⇒ `自动`） | 各行**来源列**起点的显示列相等，且不含 `\t`（锚点：`...::test_render_mcp_columns_aligned`） |
| TC-ALIGN-ALL-03 | 同上 Scenario「键值型视图标签列对齐」 | 有效配置（`_VALID_YAML`）⇒ `render_config` | 各**值的起始显示列**相等、不含 `\t`；键值行数 ≥ 6（锚点：`...::test_render_config_labels_aligned`） |
| TC-ALIGN-ALL-04 | 同上 Scenario（**明细行豁免**） | 已装 1 条 + 市场目录 1 条 ⇒ `render_skills` | 两条**键值行**（非 `·` 开头）的值起点显示列相等；`· …` 明细行**原样透出**、不参与补齐（锚点：`...::test_render_skills_labels_aligned`） |
| TC-ALIGN-ALL-05 | 同上 Scenario | 全绿依赖 ⇒ `collect_status` | 8 行键值**值的起始显示列**相等、不含 `\t`（锚点：`...::test_collect_status_labels_aligned`） |
| TC-ALIGN-ALL-06 | 同上 Scenario「笔记清单等宽列」（回归） | 同 §80 的两条笔记 | 时间戳列起点相等（改用共用助手 `_assert_aligned`，判据不变；锚点：`...::test_render_notes_columns_aligned`） |

> **判据同 §80**：按**显示宽度**（非字符数）断言列起点一致；断言助手的显示宽度在**测试内独立实现**
> （不复用被测 `align.display_width`，以免自证）。**红态证据**：把 `src/core/diagnostics` 暂存回滚
> ⇒ 上述 5 条新增用例**全红**（`\t` 断言先命中），`render_notes` 用例仍绿（`0165` 已修）。
> **已知局限**：歧义宽（`A`）字符按 1 列（承 §80，ADR-0159 局限①）；超长字段拉长整行（无截断）；
> 值内含 2+ 空格时「2 空格分列」解析会拆格（值为单空格形态，无实例）。

## 82. TUI 步骤块：缩略 / 全文 / 收起（TC-STEP-BLOCK，change `0169`／ADR-0160，台账 E106）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-STEP-BLOCK-01 | ui/spec.md「TUI 步骤块（缩略 / 全文 / 收起）」Scenario「缩略窗口与剩余行数提示」 | 注入「一轮 `code_run` + 20 行输出」的事件流 | 步骤块**缺省展开**（`.step-body` 所在折叠区 `display` 非 `False`、`collapsed is False`）；正文恰 **8** 行（末尾窗口，含 `第 13 行`/`第 20 行`、不含 `第 12 行`）；提示行逐字 `⋯ 还有 12 行 · 点击展开全文`（锚点：`tests/test_repl.py::test_tui_step_block_truncates_tail_and_expands`） |
| TC-STEP-BLOCK-02 | 同上 Scenario「点正文展开全文并回缩」 | 同 01，`pilot.click(正文)` 一次 / 再一次 | 一次点击 ⇒ 正文 **20** 行（含 `第 1 行`）、提示改 `⋯ 点击正文收起`；再次点击 ⇒ 回到 **8** 行 + 原提示（锚点：同上） |
| TC-STEP-BLOCK-03 | 同上 Scenario「点标题收起与展开」 | 同 01，`pilot.click(CollapsibleTitle)` 一次 / 再一次 | 一次 ⇒ `collapsed is True` 且折叠区 `display is False`（正文隐藏）；再一次 ⇒ `collapsed is False`、正文回缩略 **8** 行（锚点：`...::test_tui_step_block_title_toggles_collapse`） |
| TC-STEP-BLOCK-04 | 同上 Scenario「标题带目标且不含正文参数」 | `code_run`（`script="echo hi"`）与 `file_read`（含 `content` 类正文参数） | 标题逐字 `⏺ Bash  echo hi ✓ (12ms)`（友好名 + 目标 + 完成标记）；**不含** `tools.code_run`（内部 `tool_id`）与 `{'script'`（原始参数容器）；工具输出落 `└ ` 缩略区（锚点：`...::test_tui_step_block_shows_target_but_not_raw_args`、`...::test_tui_action_widget_lifecycle`） |
| TC-STEP-BLOCK-05 | 同上 Scenario「超宽正文折行而非裁切」 | 单行 `"Z" * 200` 作工具输出 | 正文 `size.width` 与 `virtual_size.width` **均 ≤** 时间线宽度（`width: 1fr` 生效 ⇒ 折行）；**红态**：退回 `width: auto` 即超宽被裁（`virtual` 达 ~200）（锚点：`...::test_tui_step_block_body_wraps_wide_line`） |
| TC-STEP-BLOCK-06 | ui/spec.md「思考过程回显（Think）」Scenario「TUI 思考折叠回显」（MODIFIED 后的缩略口径） | 同一轮连喂两条 `loop.reasoning`（`先读文件` / `，再改配置`）+ 一条 `reply_delta` | 时间线**恰一个**步骤块（同轮归并、不逐段新建）；该块**缺省缩略**（折叠区可见）；正文含 `先读文件，再改配置`（增量按序拼接）；主回复终态 `好了` 不受影响（锚点：`...::test_tui_thinking_stream_merges_and_updates_in_place`） |
| TC-STEP-BLOCK-07 | 同上「标题带目标且不含正文参数」（取数判据） | `_tool_target` 表驱动 12 例：7 类白名单字段 / 白名单表外工具 / 缺字段 / 空白值 / 非字符串值 / `args` 为 str（事件面节选形态）；另 200 字符超长值 | 白名单字段取值、**多行只取首行**；其余一律 `""`（不解析 repr）；超长按 `_MAX_TARGET_CHARS`(60) 截断加 `…`（锚点：`...::test_tool_target_whitelist`、`...::test_tool_target_truncates_long_value`） |
| TC-STEP-BLOCK-08 | 同上（标题拼装口径） | `_action_title`：开工态 / 完成 ✓ / 失败 ✗ / 无目标 | `⏺ <友好名>  <目标>`；完成态**保留目标**只追加 `✓ (耗时)`、失败态 `✗`；无目标只留友好名（不落占位）（锚点：`...::test_action_title_keeps_target_across_completion`） |

> **红态证据**：实现落地前跑 `tests/test_repl.py` ⇒ 01~04、06 **行为全红**（既有实现 `collapsed=True`、
> 标题无目标、无 `└ ` 角标、`输出：` 前缀、无 `.step-body`）；07/08 属新落地的模块级纯函数，随其实现在同一步转绿。
> **手工验收**：`.venv/bin/python -m core.entry` 发一句触发工具调用的话 —— 思考**实时滚动**（末尾 8 行 +
> `└` 肘线）、每步一行标题（`⏺ Bash  <script 首行>` / `⏺ Read  <路径>`）、点正文 ⇒ 全文、点标题 ⇒ 收起、
> 长行折行；另以 `show_thinking: false` 复跑确认**不出现**思考块。
> **已知局限**：`file_write` / `file_patch` 标题**无目标**（其正文参数使事件面 `args` 超 400 字符上界而退化为
> 节选字符串，TUI 不解析 repr ⇒ 取不到 `path`；路径仍见于 `└` 输出摘录，根治需改 `loop` 节选口径 ⇒ 另立 change）；
> `code_run` 目标取 `script` 首行 ⇒ 操作者自填内联凭据与终端显示命令**同等**暴露（步骤块不落盘）；
> 缩略窗口恒**跟随最新**（不因用户上滚而冻结）；**不覆盖**子任务折叠块与 `/focus` 焦点视图；Web / APP 维持缺省收起。

## 83. 未闭合动作载荷：失败可见 + 原始产出可诊断（TC-UNPARSED-ACTION，change `0170`／ADR-0161，台账 E107）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-UNPARSED-ACTION-01 | loop/spec.md「推理动作解析与失败可见」Scenario「未闭合的动作载荷不再被当作正文」 | `解释文字 + 换行 + {"tool_id": "tools.file_write", "args": {"path": "a.md", "content": "未写完`（外层**未闭合**、文本止于内层字符串） | `_parse` ⇒ **失败态终止动作**（`failed is True`）；`reply` 含 `LLM_PLAN_PARSE_FAILED` 且**不含** `"tool_id"`；`raw_output` 非空且含 `tools.file_write`（锚点：`tests/test_loop_output_protocol.py::test_unclosed_action_payload_marks_failed`） |
| TC-UNPARSED-ACTION-02 | 同上 Scenario「未闭合载荷的原始产出有界且不进持久面」 | 超长输入（`甲` × 9000 追加其后） | `0 < len(raw_output) <= _RAW_OUTPUT_MAX`(4096)（上界**含**截断提示行 ⇒ 总长受约束）（锚点：`...::test_unclosed_action_payload_raw_output_is_bounded`） |
| TC-UNPARSED-ACTION-03 | 同上（形态 4 反面守护） | `建议这样调：\n\n{"tool_id": "tools.echo", "args": {"text": "hi"}} 就这样。`（尾部对象**闭合**，其后仍有正文） | **不命中**形态 4 ⇒ 整段原文为回复、`failed is False`、`raw_output == ""`（承 0166「只认尾部、宁漏勿误」）（锚点：`...::test_closed_tail_object_without_tool_id_stays_reply`） |
| TC-UNPARSED-ACTION-04 | 同上 Scenario「provider 报告截断时提示区分成因」 | 同一未闭合输入，`finish_reason="length"` vs 缺省 | `length` ⇒ 提示含 `截断`；缺省 ⇒ 提示为「未闭合」措辞（**不含** `finish_reason` 字样 ⇒ 不声称 provider 报告了截断）；两态 `failed is True`（锚点：`...::test_unclosed_payload_finish_reason_length_distinguishes_cause`） |
| TC-UNPARSED-ACTION-05 | 同上（端到端 + 红线） | `DefaultLoop` + 记录型 `MemoryStore`，模型回该未闭合载荷 | `LoopResult.failed is True`；`reply` **不含** `"tool_id"`；`raw_output` 含 `tools.file_write`；**记忆落库**不含 `"tool_id"`（原始产出不进转录 / 记忆 / 笔记）（锚点：`...::test_unclosed_action_payload_keeps_raw_out_of_persisted_surfaces`） |
| TC-UNPARSED-ACTION-06 | llm-provider/spec.md「流式增量携带终止原因」Scenario「末块终止原因透出」 | `_map_chunk` 依次喂 `delta.content="甲"`（无 `finish_reason`）与空 delta + `choices[0].finish_reason="length"` | `[c.finish_reason for c in chunks] == ["", "length"]`；`[c.content …] == ["甲", ""]`（缺省空洞零影响）（锚点：`tests/test_llm_provider.py::test_chunk_maps_finish_reason`） |
| TC-UNPARSED-ACTION-07 | ui/spec.md「TUI 折叠呈现未能解析的模型原始输出」Scenario「TUI 折叠呈现原始产出」 | 注入「`loop_finished` 携带非空 `raw_output`」的事件流 | 时间线**恰一个** `Collapsible` 且 `collapsed is True`（缺省收起、不遮蔽时间线）；展开后 `.step-body` 含 `tools.file_write`；块外时间线文本**不含** `"tool_id"`（锚点：`tests/test_repl.py::test_tui_raw_output_renders_collapsed_block`） |
| TC-UNPARSED-ACTION-08 | 同上 Scenario「正常轮不呈现」 | 同上，但 `raw_output=""` | 时间线**零**折叠块（与既有行为逐字一致）（锚点：`...::test_tui_no_raw_output_block_on_normal_turn`） |

> **红态证据**：实现落地前 `git stash push -u -- src/core/loop/planner.py …`（五处 src 改动）后跑取证脚本 ⇒
> 同一未闭合载荷在旧实现下 `is_terminal=True`（**零执行**）、`failed=False`、`reply` 含 `"tool_id"`、
> **无** `raw_output` 字段；`LLMChunk` 亦**无** `finish_reason` ⇒ 08 类断言全红（精确复刻事故：
> 「JSON 当正文 + 静默成功」）。
> **已知局限**：判据只认**最后一次** `"tool_id"` 标记（更早一处未闭合、最后闭合 ⇒ 按答复处理）；
> 未闭合是**结构**判据、信号不可用时不解释成因；原始产出上界 4096 字符（超长截断）；
> **不下发 `max_tokens`** ⇒ 端点缺省限额导致的截断**仍会发生**（本 change 只使其**可见、归得因**）；
> Web / APP 不呈现该折叠块（SPA 零改动）。

## 84. notes 逐轮写回：可读解决过程 + 有意义闸门（TC-NOTES-WRITEBACK，change `0171`／ADR-0162，台账 E108）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-NOTES-WRITEBACK-01 | notes/spec.md「Consult → Build → Update 循环纪律」Scenario「解决过程人类可读（不落原文）」 | `LoopContext.messages` = user + 助手动作 `json.dumps({"tool_id":…, "args":…})` + 工具观察 `json.dumps({"data":…})` | `_action_steps` 产出一行 `工具名（参数摘要） → 结果节选`；**不含** `{"tool_id"` / `{"data"` / `"args"` / 角色前缀 `assistant:` / `tool:`（锚点：`tests/test_action_steps.py::test_action_steps_renders_readable_line` + `::test_action_steps_has_no_raw_json_dump`） |
| TC-NOTES-WRITEBACK-02 | 同上 Scenario「纯文字回复轮不写回」（loop 侧判据） | `LoopContext.messages` = 仅 user（终止动作不产生行动消息） | `_action_steps(ctx) == []` ⇒ 写回侧闸门可判（锚点：`...::test_action_steps_empty_for_reply_only_turn`） |
| TC-NOTES-WRITEBACK-03 | 同上（有界） | 参数值 / 结果均 5000 字符 | 整行 `<= _MAX_STEP_LINE`(300)；原文（5000 字符）**不在**行内；截断留 `…`（锚点：`...::test_action_steps_bounds_long_arg_and_output`） |
| TC-NOTES-WRITEBACK-04 | 同上（容器不 dump） | `args={"script":…, "env":{"A":"1","B":"2"}}` | `env: <dict len=2>` 出现；`"A"` **不**出现（容器只报类型与规模）（锚点：`...::test_action_steps_reports_container_arg_by_type_and_size`） |
| TC-NOTES-WRITEBACK-05 | 同上（错误前缀 + 畸形跳过） | 工具观察 `{"error":"NOT_FOUND"}`；另一路：助手消息为纯文本 | 前者 ⇒ `… → 错误：NOT_FOUND`；后者 ⇒ 该消息**不**产行（静默跳过、不崩）（锚点：`...::test_action_steps_marks_tool_error` + `::test_action_steps_skips_message_without_action_shape`） |
| TC-NOTES-WRITEBACK-06 | 同上 Scenario「纯文字回复轮不写回」（存储侧） | `store.observe_turn("你好", [], ok=True)` | `is None` 且 canonical 目录**无新增文件**（锚点：`tests/test_notes.py::test_store_observe_turn_skips_empty_action_sequence`） |
| TC-NOTES-WRITEBACK-07 | 同上（空序列不改写既有） | 先 `observe_turn("部署流程", ["跑测试"])`，再 `observe_turn("部署流程", [])` | 第二次 `is None`；目录内文件**逐字不变**（锚点：`...::test_store_observe_turn_empty_steps_does_not_touch_existing`） |
| TC-NOTES-WRITEBACK-08 | 同上（端到端 + 红线） | `DefaultLoop` + 真 `NoteStore`，一轮含工具动作成功；另一轮纯文字回复 | 前者 canonical 文件正文含 `tools.echo` / `中间结论`、**不含** `{"tool_id"` / `{"data"`；后者**零文件**（锚点：`tests/test_notes_loop.py::test_loop_turn_observer_writes_canonical_note` + `::test_loop_reply_only_turn_does_not_write_note`） |

> **红态证据**：实现落地前跑两类取证 —— ① 存储侧 `pytest tests/test_notes.py tests/test_notes_loop.py`
> ⇒ **4 failed**（含 `test_notes_loop` 端到端用例证明旧实现为纯文字回复轮写下 `你好.md` —— 精确复刻
> 「琐碎轮入库」）；② 渲染侧自包含脚本对旧 `_action_steps` ⇒ 首行为 `assistant: {"tool_id": …}`
> （JSON 原文）、工具观察行 **1846 字符**（整篇输出无界）—— 精确复刻「JSON 转储进笔记」。
> **已知局限**：① 参数摘要对深层嵌套参数只报类型与规模（按工具语义字段白名单属展示层政策，不下沉
> loop）；② 工具名保留 `tools.` / `mcp.` 命名空间前缀（未美化）；③ 结果节选为 `str()` 形态
> （dict 结果呈 Python repr 而非 JSON）；④ 闸门以「有无工具动作」为判据、**不**判「有无新结论」⇒
> 无信息量的工具轮仍写回（覆盖式写同一主题、不增长）；⑤ 派生主题 `<topic>-N` 机制**逐字不变**
> （靠闸门减量，未做结构性收敛）。

## 85. 关键事实抽取端质量：同批归并 + 解析失败可观测 + 取值首尾保留（TC-EXTRACT-QUALITY，change `0172`／ADR-0163，台账 E109）

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-EXTRACT-QUALITY-01 | memory/spec.md「结构化实体抽取（关键事实）」Scenario「同批同 slug 归并（只留首条 + 留痕）」 | 同批两条 `KeyFact(entity="API Key", value="首值")` + `KeyFact(entity="api-key", value="次值")`（slug 折叠后同 slug） | 落库**单条** `keyfact.api-key`、取值为**首条** `API Key: 首值`；留痕含实体名、**不含**取值（锚点：`tests/test_memory_key_facts.py::test_same_batch_same_slug_is_merged_keeping_first`） |
| TC-EXTRACT-QUALITY-02 | 同上（归并后条数计额） | 1 条重复（同 slug）+ 7 条不同实体（共 8 实体唯一） | 落满 `MAX_KEY_FACTS_PER_COMPACT`(8) 条；第 8 个**不同**实体未被重复项挤出（锚点：`...::test_same_batch_merge_does_not_consume_extra_quota`） |
| TC-EXTRACT-QUALITY-03 | 同上 Scenario「解析失败留痕且不含模型输出正文」 | `extract_with(lambda prompt: f"我无法判断，参考 {sk-…} 好了")`（有输出、无 JSON 数组） | 不抽取 + `warnings.warn`；留痕**不含**输出正文（哨兵 `sk-…` 不在告警中）（锚点：`...::test_unparseable_output_warns_without_dumping_model_text`） |
| TC-EXTRACT-QUALITY-04 | 同上（合法空数组不告警） | `extract_with(lambda prompt: "[]")`（模型明确无可抽） | 不抽取、**无**「unparseable」告警（防误报）（锚点：`...::test_empty_json_array_does_not_warn`） |
| TC-EXTRACT-QUALITY-05 | 同上 Scenario「取值超长 ⇒ 首尾保留（总额度不变）」 | `value` = `"头"*10 + "甲"*300 + "尾"*10`（CJK 填充，不触发脱敏） | 落库取值 `<= _MAX_FACT_CHARS`(200)；`startswith("头"*10)` **且** `endswith("尾"*10)`；含 `…`（锚点：`...::test_long_value_keeps_head_and_tail`） |
| TC-EXTRACT-QUALITY-06 | 同上（`entity` / `ref` 维持头部截断） | 超长 `entity` 与长 `ref`（`coeffect:` + `ab.`×70，非密钥形态） | `entity == "长"*200` 且**无** `…`；`ref == long_ref[:200]` 且**无** `…`（首尾保留**只**用于 `value`）（锚点：`...::test_entity_and_ref_keep_head_only_truncation`） |

> **红态证据**：实现落地前（stash `src/core/memory` 改动）跑 `tests/test_memory_key_facts.py`
> ⇒ **4 failed / 39 passed** —— 4 条新增断言按预期变红（同批归并两条 + 解析失败留痕 + 取值首尾保留），
> 复刻三处缺口；`entity` / `ref` 头部截断用例在修复前后皆绿（守护「未误改形态」）。
> **已知局限**：① 首尾保留扩大截断后可见面 ⇒ 对脱敏完备性要求更高（不改脱敏启发式，方向仍 over-redact）；
> ② 归并只消**同批**重复，跨批仍靠 `id` 同实体幂等覆盖（不合并为「历史值」）；③ 归并丢弃的取值**不进**
> 任何记忆面（有损）；④ 解析失败留痕**不含**模型输出正文（排查须回看 trace，不以牺牲红线换可诊断性）；
> ⑤ 数组存在但元素**全**不合规时不告警；⑥ `MAX_KEY_FACTS_PER_COMPACT`(8) **未**放宽。

## 86. 记忆材料与引用语义：行动序列另立条目 + `ref` 只认 `coeffect:`（TC-MEM-REF，change `0173`／ADR-0164，台账 E110）

> **背景取证**（用户 2026-10-08）：复查生产 `memory.jsonl` 的 24 条 `key_fact` —— **8 正常 / 16 被抹成
> `<redacted>`**。两条根因：① 模型把「取自哪一句」当 `ref` 回填（`round1:热带水果有哪些` / `会话事件` /
> `证据链第1条` / `分析结论`），而 store 侧判据是「有 `ref` ⇒ `value` **一律** `<redacted>`」⇒ **纯自伤**
> （那些取值**不是**密钥）；② 逐会话回看抽取材料（`remember()` 写的 `round N ok` + **回复散文**）：
> **24/24** 条实体的来源**全是散文**、**无一条**来自工具调用或结果（实体名里出现 `round 5 执行结果`
> 即反证）。故本 change 双修：**引用判据**（D-B）+ **材料补厚**（D-A′，另立条目）。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-MEM-REF-01 | loop/spec.md「执行循环」Scenario「行动与结果另立一条 L2 条目」 | `remember("t1", [{"round":1,"ok":True},{"reply":"已回显"}], steps=_action_steps(ctx))`（ctx 含一次 `tools.echo`） | **两条并存**：`loop.t1` 内容 `"round 1 ok\n已回显"`（**逐字不变**）、`loop.steps.t1` 内容 `"tools.echo（text: 中间结论） → echo:中间结论"`（锚点：`tests/test_loop_memory_sequence.py::test_action_sequence_lands_as_separate_entry`） |
| TC-MEM-REF-02 | 同上（条目归属） | 同上有 `session_id="s1"` | 行动序列条目 `layer=="L2"`、`trace_id=="t2"`、`session_id=="s1"`、`source=="loop"` —— 与轨迹条目同口径（回滚/归组一致）（锚点：`...::test_sequence_entry_shares_trace_and_session`） |
| TC-MEM-REF-03 | 同上 Scenario「无工具调用不另立条目」 | `steps=_action_steps(纯文字 ctx)`（零工具动作） | **只**有 `loop.t3`；**不**出现 `loop.steps.t3`（无行动不记忆）（锚点：`...::test_reply_only_turn_does_not_add_sequence_entry`） |
| TC-MEM-REF-04 | 同上（缺省逐字一致） | `remember("t4", [{"reply":"结论"}])`（**不传** `steps`） | 只有 `loop.t4`，内容 `"结论"` —— 变更前后**逐字一致**（旧调用形态零回归）（锚点：`...::test_default_steps_keeps_trajectory_entry_only`） |
| TC-MEM-REF-05 | 同上 Scenario「行动序列条目脱敏且有界」（脱敏） | 观察含 `token: sk-abcdefgh12345678` | 条目**不含**该明文；含 `REDACTED`；`startswith("code_run（")` ⇒ **行内子串替换**（工具名/结构保留，非整行抹除）（锚点：`...::test_sequence_entry_redacts_secret_substrings`） |
| TC-MEM-REF-06 | 同上（有界） | 40 条超长 steps（每条 200 字符） | 条目长度 `<= _MAX_MEMORY_ENTRY`(2048)（token 有界）（锚点：`...::test_sequence_entry_is_bounded`） |
| TC-MEM-REF-07 | memory/spec.md「结构化实体抽取（关键事实）」Scenario「非 coeffect 形态的 ref 视为无引用」 | `scrub_key_fact(KeyFact(entity=…, value="正常取值", ref=r))`，`r` ∈ {`round1:热带水果有哪些`, `会话事件`, `证据链第1条`, `分析结论`}（参数化 4 例） | 返回条目的 `ref == ""`（该 `ref` **被弃用**）；`value` **保持明文**（不因自造引用而 `<redacted>`）（锚点：`tests/test_memory_key_facts.py::test_non_coeffect_ref_is_treated_as_absent`） |
| TC-MEM-REF-08 | 同上（fail-closed 不许自造引用背书） | 同上但 `ref="会话事件"`、`value="sk-abcdefgh12345678"`（密钥形态） | 返回 **`None`** ⇒ 整条丢弃（自造引用**不能**为明文密钥背书）（锚点：`...::test_non_coeffect_ref_cannot_vouch_for_secret_value`） |
| TC-MEM-REF-09 | 同上（端到端落库形态） | 经 `MemoryStore` 压实一条 `ref="分析结论"`、取值普通的 KeyFact | 落库 `content` 为**裸值**、**不**含 `ref:` 标签（锚点：`...::test_non_coeffect_ref_lands_plain_value_without_ref_tag`） |
| TC-MEM-REF-10 | 同上 Scenario「非 coeffect 形态 ref + 密钥形态取值 ⇒ 整条丢弃」 | 经 `MemoryStore` 压实 `ref="会话事件"` + 密钥形态取值 | **无** `key_fact` 落库 + `pytest.warns(RuntimeWarning)`（丢弃留痕）（锚点：`...::test_non_coeffect_ref_with_secret_is_dropped_with_warning`） |
| TC-MEM-REF-11 | memory/spec.md（判据提公开：一处定义、两处消费） | `looks_like_secret(s)`，`s` 遍历既有 `_SECRETS` 全集 + 一条长随机串（参数化） | 全部 `is True` ⇒ 公开判据与 `scrub_key_fact` **同源**（非第二份启发式）（锚点：`...::test_looks_like_secret_is_public`） |
| TC-MEM-REF-12 | 同上（行内脱敏语义） | ① `redact_secrets("prefix sk-… suffix")`；② 纯文本；③ 一行含两种密钥形态 | ① **只**替换命中子串、保留 `prefix`/`suffix` 结构；② 原样返回（无操作）；③ 两处**均**替换（锚点：`...::test_redact_secrets_replaces_only_matched_substrings` / `...::test_redact_secrets_is_noop_on_plain_text` / `...::test_redact_secrets_handles_multiple_patterns`） |

> **红态证据**：实现落地前跑两文件 ⇒ **收集期即失败**（预期，作为「新面确由本 change 引入」的证据）：
> `ImportError: cannot import name '_MAX_MEMORY_ENTRY' from 'core.loop.default'`、
> `cannot import name 'looks_like_secret' from 'core.memory'`（`redact_secrets` 同）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2003 passed**（基线 1979，**+24**）。
> **已知局限**：① 脱敏判据是**启发式** —— 不符合任何 `_SECRET_PATTERNS` 的内联凭据仍会入 L2 并**落盘**
> （根治需在工具侧打标 ⇒ 另立）；② `ref` **只认前缀** —— `coeffect:` 之外的真实引用源（如 `env:`）
> 一律视为无引用；③ 每轮多一条 L2 条目 ⇒ 压实材料条数与 token 成本上升（有界）；④ `_MAX_ENTRY_CHARS`(400)
> **未**放宽 —— 靠「另立条目」绕开窗口竞争（某轮行动序列超 400 字符时抽取器仍只看前 400）；⑤ 既有 16 条
> 错误条目不主动清理（靠同实体幂等覆盖自然刷新）；⑥ 非 `coeffect:` 引用**被弃用时不发** `warnings.warn`
> （规格只要求「整条丢弃」时留痕）。

## 87. 失效关键事实的运维修复：按会话重抽 + 删除 + 备份兜底（TC-KFREPAIR，change `0174`／ADR-0165，台账 E111）

> **背景取证**（用户 2026-10-08）：change `0173` 修好了**判据**，但**已写坏的条目仍在库里** —— 生产
> `memory.jsonl` 的 24 条 `key_fact` 里 **16 条**取值被抹成 `<redacted>`，`ref` 是模型自造的出处说明。
> 这些条目**已无任何可用信息**，却仍被检索命中（`keyfact.榴莲` 的 `reuse_count` 达 **36**）。
> 只读 dry-run 实证（`memory.jsonl` 前后 sha256 一致）：两来源会话材料仍在（episodic 原文已归档 **L4**，
> `_all_entries()` 读全层）、`build_runtime` 已注入 `extract_with(_llm_text)` ⇒ 同材料重抽即得**每会话
> 8 条明文**、零假 `ref`、无 `round N 执行结果` 类垃圾。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-KFREPAIR-01 | memory/spec.md「失效关键事实的运维修复」Scenario「识别失效条目」 | 库中并存：`coeffect:` 引用的 keyfact、无 `ref:` 的正常 keyfact、`ref:` 非 `coeffect:` 形态且取值 `<redacted>` 者 | **只**第三条被识别；`identified == ["keyfact.榴莲"]`（锚点：`tests/test_memory_keyfact_repair.py::test_identifies_only_stale_entries`） |
| TC-KFREPAIR-02 | 同上 Scenario「重抽成功后清理该会话旧条目」 | 会话 `s1` 有失效条目 `榴莲` / `山竹`；重抽产出 `榴莲` / `泰国` | 旧条目**全删**（含重抽**未**再产出的 `山竹`）、新条目落库；`backup_path` 非空（锚点：`...::test_successful_reextract_clears_all_old_entries_of_the_session`） |
| TC-KFREPAIR-03 | 同上 Scenario「同 slug 重抽不误删」 | 失效条目 `keyfact.榴莲`，重抽又产出实体 `榴莲`（slug 相同） | 该 id 上落**新**取值；该条目**不在** `deleted` 中（刚修好的条目不得被自己删掉）（锚点：`...::test_same_slug_rewrite_is_not_deleted`） |
| TC-KFREPAIR-04 | 同上（材料口径 = episodic **全层**） | 该会话的 episodic 原文已迁 **L4**（`_episodic_groups` 会取空） | `sessions == ["s1"]` 且重抽成功 ⇒ 证明材料取自**全层**（守护「去掉 L2 层过滤」）（锚点：`...::test_material_includes_archived_l4_entries`） |
| TC-KFREPAIR-05 | 同上 Scenario「重抽失败不删条目」（抽取器**未注入**） | `MemoryStore()`（无 `key_fact_extractor`）+ 一条失效条目 | 不删、无写入、`backup_path == ""`、`skipped["no_extractor"]` 标明（锚点：`...::test_no_extractor_means_no_deletion`） |
| TC-KFREPAIR-06 | 同上 Scenario「重抽失败不删条目」（抽取器**抛错**） | 抽取器 `raise RuntimeError` | 不删、条目原样、`skipped["extract_failed"]` 含该会话（fail-closed）（锚点：`...::test_extractor_failure_means_no_deletion`） |
| TC-KFREPAIR-07 | 同上 Scenario「备份文件先落且失败即不删」 | `CORE_STATE_DIR` 指向一个**文件** ⇒ 备份路径写入必失败 | 不删任何条目（旧条目留在原地）、`backup_path == ""`、`skipped["backup_failed"]` 标明（锚点：`...::test_backup_failure_means_no_deletion`） |
| TC-KFREPAIR-08 | 同上（备份文件口径） | 备份文件逐行 = 待删条目原文 | 每行可 `json.loads` 回条目；id 集合 == `deleted`；`content` == `榴莲: <redacted>`；`tags` 非空（锚点：`...::test_backup_file_keeps_original_entries`） |
| TC-KFREPAIR-09 | 同上 Scenario「幂等与只读预演」（幂等） | 库中**无**失效条目（正常 keyfact + 会话材料） | `identified` / `deleted` / `written` 全空、无备份文件、库内容逐字不变（锚点：`...::test_idempotent_when_no_stale_entries`） |
| TC-KFREPAIR-10 | 同上 Scenario「幂等与只读预演」（预演） | `repair_stale_key_facts(dry_run=True)` | `dry_run is True`、`identified` 非空而 `deleted` / `written` 空、`backup_path == ""`、库内容不变、无备份文件（锚点：`...::test_dry_run_reports_but_never_writes`） |
| TC-KFREPAIR-11 | 同上 Scenario「无会话出处的失效条目不删」 | 失效条目**不带** `session:` 标签 | 不删、`skipped["no_session"]` 含该 id、内容不变（无材料即无法重抽）（锚点：`...::test_stale_without_session_tag_is_not_deleted`） |
| TC-KFREPAIR-12 | design.md §3「抽样返回**合法空数组**」 | 抽取器返回 `[]`（模型明确无可抽） | 视为**重抽成功** ⇒ 旧条目**仍删**（它们已无信息）（锚点：`...::test_empty_reextract_result_still_clears_stale_entries`） |

> **红态证据**：实现落地前跑 `tests/test_memory_keyfact_repair.py` ⇒ **12 failed / 0 passed**，全部为
> `AttributeError: 'MemoryStore' object has no attribute 'repair_stale_key_facts'`（新面确由本 change 引入）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2015 passed**（基线 2003，**+12**）。
> **已知局限**：① 删除是**不可逆的持久动作**（备份文件是唯一回滚路径，且**不自动清理**）；② 重抽结果
> **不确定** —— 同一材料两次调用可能给出不同实体名与取值，产出的新事实**可能少于**旧条目数 ⇒ 修复后
> 信息面**不保证等量**；③ 备份文件含旧条目原文（与 `memory.jsonl` 同暴露度，承 ADR-0164 局限①）；
> ④ 无 `session:` 出处的失效条目**只报告不动作**，永远留在库里；⑤ 只覆盖 keyfact 这一面；⑥ **不做
> 实体名映射** ⇒ 命名漂移不可避免。

## 88. 修复备份「一次操作一份」：备份/删除提出会话循环（TC-KFBACKUP，change `0175`／ADR-0166，台账 E112）

> **背景取证**（change `0174` 首次**实跑**，生产 2 个会话）：备份/删除原在**每会话循环体**内 ⇒ 备份文件数
> = 会话数（实落 `memory.repair.20261008-234522.jsonl` 2 行 + `…234545.jsonl` 5 行）。`RepairReport.backup_path`
> 是**标量**，循环里**后写覆盖前写** ⇒ 报告只显示**最后一份**、第一份成**孤儿**（回滚会漏）；且与规格句
> 「落**一份**备份文件」不符。附带缺陷：备份失败只阻断**该会话** ⇒ 一次操作可能**部分删除**。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-KFBACKUP-01 | memory/spec.md「失效关键事实的运维修复」Scenario「待删条目跨会话合并为一份备份」 | 两个会话（`s1` / `s2`）各有一条失效条目 + 各自 episodic 材料；抽取器按会话给不同事实 | 备份文件**恰好 1 份**、`backup_path` 指向它、行 id 集合 = 两会话待删 id 的**并集**、`deleted` 与之相等（锚点：`tests/test_memory_keyfact_repair.py::test_two_sessions_share_one_backup`） |
| TC-KFBACKUP-02 | 同上 Scenario「备份文件先落且失败即不删」（多会话） | 同上布景，`CORE_STATE_DIR` 指向一个**文件** ⇒ 备份写入必失败 | `deleted == []`、`backup_path == ""`、`skipped["backup_failed"] == ["s1","s2"]`（**跨会话一并阻断**）、两会话旧条目**都在**、新条目已落（锚点：`...::test_backup_failure_blocks_every_session`） |
| TC-KFBACKUP-03 | 同上（**单**会话口径不变） | 单会话、有待删条目 | 恰好一份备份、旧条目删净、`skipped["backup_failed"]` 标明（锚点：`...::test_backup_file_keeps_original_entries` / `...::test_backup_failure_means_no_deletion`） |

> **红态证据**：实现落地前跑 `tests/test_memory_keyfact_repair.py` ⇒ **1 failed / 13 passed**
> （`test_two_sessions_share_one_backup`）。失败形态比预期更锋利：两次调用落在**同一秒** ⇒ **同一路径**
> ⇒ 第二会话的备份**静默覆盖**第一会话的（文件恰好 1 个但内容只有会话 2 的待删条目 ⇒ **会话 1 的回滚面
> 被覆盖清除**）。另一新增用例 `test_backup_failure_blocks_every_session` 是**等价守护**（「目录不可写」
> 对两会话**同时**生效 ⇒ 实现前后皆绿），诚实记之。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2017 passed**（基线 **2015**，**+2**）。
> **已知局限**：① 备份失败即**整次不删** ⇒ 一个坏目录（磁盘满 / 权限错）会让**所有**会话都修不成（以
> 「不修」换「不错删」）；② **已产生的历史多份备份不合并/不清理** ⇒ 本 change 只保证**此后**每次操作
> 恰好一份；③ 跨会话**同 slug** 时最后一个会话胜，报告里该 id 只出现一次、用户**看不出**发生了覆盖；
> ④ `doomed` 并集顺序不保证稳定（回滚按行不按序）；⑤ 承 §87 全部局限。

## 89. notes 写回效应闸门：纯读轮不落盘（TC-NOTES-EFFECT-GATE，change `0176`／ADR-0167，台账 E113）

> **背景取证**（用户 2026-10-09 实测）：逐轮写回仍把**纯读型工具轮**整篇塞进 canonical 知识库
> （`web_fetch` 抓的网页正文、`file_read` 的一次性排查产物）。change 0171 的闸门只看 `steps` 是否**为空**
> （`if not ok or not steps: return None`），而 `loop._action_steps` 对**所有**工具动作一律产出行 ⇒
> 「调过 `web_fetch`/`file_read`」即满足写回条件。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-NOTES-EFFECT-GATE-01 | notes/spec.md「Consult → Build → Update 循环纪律」Scenario「纯读轮不写回（效应闸门）」 | `observe_turn(task, [<纯读型行>], ok=True)`，参数化 `web_fetch` / `file_read` / `context_read` / `list` | 返回 `None`、canonical 目录**无新增文件**（锚点：`tests/test_notes.py::test_observe_turn_pure_read_step_skips`） |
| TC-NOTES-EFFECT-GATE-02 | 同上 Scenario「写效应失败不计入（效应闸门失败口径）」 | `observe_turn(task, ["tools.code_run（script=boom） → 错误：boom"], ok=True)` | 返回 `None`（失败执行不构成可沉淀效应）（锚点：`...::test_observe_turn_failed_write_effect_step_skips`） |
| TC-NOTES-EFFECT-GATE-03 | 同上 Scenario「含写效应轮正常写回」 | 参数化 `file_write` / `file_patch` / `code_run` / `gate_run` / `install` / `uninstall` 的成功行 | 返回非 `None`（照常覆盖式写回）（锚点：`...::test_observe_turn_write_effect_step_writes`） |
| TC-NOTES-EFFECT-GATE-04 | 同 design.md 决策③（非已知工具名 ⇒ 保守判无写效应） | `observe_turn(task, ["跑测试", "上线"], ok=True)` | 返回 `None`（锚点：`...::test_observe_turn_unrecognized_step_skips`） |
| TC-NOTES-EFFECT-GATE-05 | 同 design.md 决策①（读写混轮含写即写回） | 纯读行 + 一个成功写效应行 | 返回非 `None`（锚点：`...::test_observe_turn_mixed_read_and_write_writes`） |
| TC-NOTES-EFFECT-GATE-06 | notes/spec.md 同上（loop 接线） | 真 loop + 只读替身工具（`tools.echo`）跑一轮成功 | canonical 目录**无新增文件**（锚点：`tests/test_notes_loop.py::test_loop_pure_read_turn_does_not_write_note`） |

> **红态证据**：实现落地前跑 `tests/test_notes.py tests/test_notes_loop.py tests/test_notes_pinned_budget.py`
> ⇒ **7 failed / 79 passed**，失败者为 4 条纯读参数化用例 + 写效应失败 + 非工具行形态 + loop 侧纯读轮
> （loop 侧实落 `查一下资料.md`）；写效应正例同期全绿。绿后全量 `.venv/bin/pytest -q` ⇒ **2031 passed**
> （基线 **2017**，**+14**）。
> **连带调整**：闸门依赖 steps 的**工具行形态**，10 个既有用例的 steps 是散文占位 / 只读替身 ⇒ 改为
> 工具行形态的写效应 steps（断言不变量不变；`test_notes_loop.py` 新增 `_write_tool()` 替身）。
> **已知局限**：① 判据靠**解析 steps 行前缀**（渲染契约的隐式耦合）—— 行格式变更会让闸门静默退化为
> 「无写效应」（保守方向）；② 工具名为**白名单快照**，新增写效应型工具须同步 `_WRITE_EFFECT_TOOLS`
> （否则该类轮次静默不写回）；③ 只覆盖**持久化**效应；④ `错误：` 判据是行内子串匹配，参数摘要恰含该
> 子串会被误判为失败（方向保守）；⑤ memory 侧 keyfact 抽取**不受本闸门约束**（纯读素材按设计归其沉淀）。

## 90. 记忆质量闭环：写入侧闸门 + 复用强化衰减 + 自适应抽取上限（TC-MEM-QUALITY，change `0177`／ADR-0168，台账 E114）

> **背景取证**（用户 2026-10-09 三面复盘）：① `importance` 只在检索 / 遗忘评分被**消费**、**写入路径
> 从不生产它**（唯一产出点是压实固化对**存量**条目的**事后修正**）；② 抽取条数上界 `MAX_KEY_FACTS_PER_COMPACT`
> 是**死值 8**；③ 遗忘评分 `_decay_score` 的 freshness 项对**被复用过的条目**不设延缓 ⇒ 好条目与新条目
> **同速衰老**。三处构成同一「记忆质量闭环」缺口：**入口不筛、出口不保、容量不随规模伸缩**。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-MEM-QUALITY-01 | memory/spec.md「记忆遗忘」Scenario「未复用条目衰减不变」 | `reuse_count=0` 的 L2 episodic（冻结时钟） | 遗忘评分与改动前**逐字一致**（锚点：`tests/test_memory.py::test_decay_score_unchanged_when_never_reused`） |
| TC-MEM-QUALITY-02 | 同 Scenario「复用延缓新鲜度衰减」 | 同时间戳 / 同 importance，`reuse_count=3` vs `0` | 复用者评分**高于**未复用者（锚点：`...::test_decay_score_slows_freshness_decay_by_reuse`） |
| TC-MEM-QUALITY-03 | 同上（阈值判据） | 99 天龄，`reuse_count=1` | 新评分 ≥ 遗忘阈值（旧评分 < 阈值）⇒ 不被归档（锚点：`...::test_forget_spares_reused_entry_that_plain_decay_would_archive`） |
| TC-MEM-QUALITY-04 | 同 Scenario（检索排序不受影响） | `relevance.recency_decay` / `rank` | **逐字不变**（调制只落 `store._decay_score`）（锚点：既有 `test_rank_*` 全绿） |
| TC-MEM-QUALITY-05 | 关键事实「条数与长度有界」/「上限随会话长度自适应」 | `key_fact_cap(n)` 表驱动 `n∈{0,1,20,32,36,40,64,200}` | `8,8,8,8,9,10,16,16`（锚点：`tests/test_memory_key_facts.py::test_key_fact_cap_bounds_and_scaling`） |
| TC-MEM-QUALITY-06 | 同 Scenario「自适应上限不低于既有死值」 | `key_fact_cap(n)`，`n∈[0,300)` | 恒 `≥ 8`（既有死值）且单调不减（锚点：`...::test_key_fact_cap_never_tightens_below_legacy_value`） |
| TC-MEM-QUALITY-07 | 同 Scenario（端到端名额） | 36 条 L2 episodic、抽取器返回 50 条 | 落库恰 `key_fact_cap(36)=9` 条（锚点：`...::test_fact_count_cap_adapts_to_aggregated_episodic_count`） |
| TC-MEM-QUALITY-08 | memory/spec.md「写入侧重要度闸门」Scenario「未注入评分器时写入不变」 | `MemoryStore()`（UNWIRED）`write()` | 正常入库、`importance` 不动、**无留痕**（锚点：`tests/test_memory.py::test_gate_unwired_write_is_unchanged`） |
| TC-MEM-QUALITY-09 | 同 Scenario「低分条目拒收」 | scorer 返回 0.1（< FLOOR 0.2） | 返回 `None`、不落库、无效应、`warnings.warn` 留痕（锚点：`...::test_gate_rejects_low_score_entry`） |
| TC-MEM-QUALITY-10 | 同 Scenario「中间分降层写入」 | scorer 返回 0.3（`[0.2,0.4)`） | 落 **L4**；`rollback("gate.e1")` 后**迁回原意向层 L2**（锚点：`...::test_gate_middle_score_downgrades_to_l4_reversibly`） |
| TC-MEM-QUALITY-11 | 同 Scenario「高分正常入库并写回分值」 | scorer 返回 0.5（≥ AMBIT 0.4） | 落 L2 且 `importance==0.5`；回滚条目 trace ⇒ 两效应均撤销（锚点：`...::test_gate_high_score_keeps_layer_and_writes_back_importance`） |
| TC-MEM-QUALITY-12 | 同 Scenario「评分器抛错降级放行」 | scorer 抛 `RuntimeError` | 按意向层正常入库、留痕、不中断（锚点：`...::test_gate_scorer_error_degrades_to_normal_write`） |
| TC-MEM-QUALITY-13 | 同 design.md 决策②（界外值 ⇒ 降级放行） | scorer 返回 1.5 | 正常入库、留痕（锚点：`...::test_gate_out_of_range_score_degrades_to_normal_write`） |
| TC-MEM-QUALITY-14 | ADR-0045（memory 依赖方向红线） | `src/core/memory/` 无 LLM/rag import | 架构测试全绿（锚点：`tests/test_architecture.py::test_phase1_capability_no_reverse_dependency`） |

> **红态证据**：实现落地前 —— Layer A `ImportError: cannot import name 'KEY_FACTS_MAX'`；Layer B 两条判别性
> 用例在旧公式下红（99 天龄 + `reuse_count=1`：旧评分 ≈0.017 < 阈值 0.05、新评分 ≈0.11 ≥ 阈值）；
> Layer C `ImportError: cannot import name '_IMPORTANCE_AMBIT'`。绿后全量 `.venv/bin/pytest -q` ⇒ **2052 passed**
> （基线 **2031**，**+21**：A 10 用例 + B 5 + C 6）。
> **降层可撤销语义**：`EffectTracker.rollback` 按**逆序**撤销 ⇒ 降层**不得同 trace**（否则先迁回再**删除**）；
> 实现为「先按意向层 `write`（条目自身 trace）再 `migrate(→L4, trace_id=f"gate.<id>")`」两步**双 trace**。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0168 行（闸门不区分来源 / 抛错降级放行 / 阈值为常量
> 启发式 / 复用计数为进程内 / 上限 16 封顶 / 留痕只报 id）。

## 91. 三层会话滑窗：短 / 中 / 长 + 动态按比例压缩（TC-WINDOW，change `0178`／ADR-0169，台账 E115）

> **背景取证**（用户 2026-10-09「日常会话记忆，交互中/短/长滑窗动态按比例压缩」）：① 会话摘要
> `summary_for` 唯一调用者是 CLI ⇒ **摘要从不进任何 prompt**；② 日常会话路径**根本不产摘要**
> （`memory.compact()` 在无工具的日常聊天里从不触发）；③ `_load_history` 单层切片超限时**静默丢最旧、
> 无摘要替换**；④ 单条固定 `history_turns=20`、**无分层**。四者合成「日常会话越聊越失忆」。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-WINDOW-01 | context/spec.md「三层窗口比例分配」Scenario「非分层等价既有双重上界」 | `plan_window(turns, budget, tiered=False)` | 短层 = 全部 `turns` + 全部 `budget`、中层零 —— 与既有双重上界**逐字等价**（锚点：`tests/test_context_window.py::test_plan_window_untiered_equals_legacy_bounds`） |
| TC-WINDOW-02 | 同 Scenario「分层按固定份额切分」 | `plan_window(20, 32768, tiered=True)` | 短 10 / 中 6、短层 token = 16384（`0.5`）※（锚点：`...::test_plan_window_tiered_splits_by_ratio`） |
| TC-WINDOW-03 | 同 Scenario「关闭回灌的零守卫」 | 表驱动 `turns ≤ 0` 或 `budget ≤ 0` | 配额**全零**（锚点：`...::test_plan_window_recovers_zero_guards`） |
| TC-WINDOW-04 | 同 Scenario「短层恒不低于一轮且短中不超总量」 | 表驱动 `turns ∈ {1,2,3,20,100}` | `short ≥ 1` 且 `short + mid ≤ turns`（锚点：`...::test_plan_window_short_band_never_below_one_turn`、`...::test_plan_window_mid_never_exceeds_remaining`） |
| TC-WINDOW-05 | 同 Scenario「配额随总量单调」 | 逐值递增 `turns` | 短层与中层轮数**单调不减**（锚点：`...::test_plan_window_monotone_in_turns`） |
| TC-WINDOW-06 | memory/spec.md「对话转录持久化」Scenario「切分短带与中带且不重叠」 | `TranscriptStore.window(sid, short_turns=2, mid_turns=2, ...)` | 短带 = 末 2 轮、中带 = 其前 2 轮，两带无交集（锚点：`tests/test_transcript.py::test_window_splits_short_and_mid_bands`） |
| TC-WINDOW-07 | 同 Scenario「短带沿用 token 截断与孤儿行丢弃」 | 短带超 `short_tokens` / 截断后开头剩孤儿 assistant | 短带按 token 从新到旧截断 + 丢孤儿行；中带**不**截断（锚点：`...::test_window_short_band_truncated_by_short_tokens`、`...::test_window_short_band_drops_leading_orphan_assistant`） |
| TC-WINDOW-08 | 同 Scenario「轮数不足时中带为空」/「关闭短层时两带皆空」 | 会话轮数 < short+mid；`short_turns ≤ 0`（表驱动 0 / -1） | 中带空；短层非正 ⇒ `([], [])`（锚点：`...::test_window_insufficient_turns_leaves_mid_empty`、`...::test_window_zero_or_negative_short_turns_returns_empty`）；非分层等价锚 `window(N,0,B) ≡ tail(N,max_tokens=B)`（锚点：`...::test_window_untiered_equivalent_to_tail`） |
| TC-WINDOW-09 | memory/spec.md「记忆压实」Scenario「中期摘要滚动合并既有内容」/「按会话读取既有中期摘要（只读）」 | 已有 `compaction.mid.s1` + 新增桩；`mid_summary_for` 调用前后 `audit()` 快照 | 材料**首条**为既有中期摘要、产出仍为**唯一**一条；读取**只读**且按会话隔离（锚点：`tests/test_memory.py::test_summarize_slice_rolls_merge_prior_mid_summary`、`...::test_mid_summary_for_is_read_only`、`...::test_mid_summary_for_isolated_per_session`） |
| TC-WINDOW-10 | 同 Scenario「未注入摘要器时中期摘要零写入」 | 摘要器 UNWIRED / 桩为空 / `max_chars ∈ {0,-5}`（表驱动） | 返回 `None`、**零写入零效应**（锚点：`...::test_summarize_slice_unwired_summarizer_returns_none_and_writes_nothing`、`...::test_summarize_slice_nonpositive_max_chars_returns_none`、`...::test_summarize_slice_empty_entries_returns_none`） |
| TC-WINDOW-11 | 同 Scenario「中期摘要有界且脱敏且不迁移来源」 | 摘要器产出含明文密钥形态且超长；材料含**已在库**来源条目 | 落库**不含**明文（`<redacted>`）、长度 ≤ `max_chars`、来源条目层级**逐字不变**（锚点：`...::test_summarize_slice_bounded_by_max_chars_and_redacted`、`...::test_summarize_slice_does_not_migrate_source_entries`） |
| TC-WINDOW-12 | 同 Scenario「中期摘要可撤销」 | `rollback("compaction.mid.<key>")` | 中期摘要条目被移除（锚点：`...::test_summarize_slice_reversible_by_trace`） |
| TC-WINDOW-13 | loop/spec.md「执行循环」Scenario「冷会话退化为纯回灌」 | 无摘要 + 既有转录 + 真 loop | 请求**逐字 = 今天**（`["system","user","assistant","user"]`，**无**摘要块）（锚点：`tests/test_history_replay.py::test_cold_session_request_verbatim_without_summaries`） |
| TC-WINDOW-14 | 同 Scenario「分层摘要作为独立系统块注入」/「分层后短层收窄且更旧轮不再回灌原文」 | 预置长/中期摘要；`history_turns=4`、8 轮转录 | 两摘要各为**独立系统块**（次序：常驻笔记 → 长期 → 中期）；短带 = 末 2 轮原文、更旧轮**不进原文**（锚点：`...::test_layered_summaries_injected_as_system_blocks`、`...::test_long_before_mid_and_after_pinned_notes`、`...::test_tiered_short_band_narrows_and_drops_older_turns`） |
| TC-WINDOW-15 | 同 Scenario（独立字段不折入） | `perceive` 后检查 `history` / `messages` | 摘要**不折入** `history` / `messages`（锚点：`...::test_summaries_not_folded_into_history_or_messages`） |
| TC-WINDOW-16 | 同 Scenario（门控与回灌同形） | 表驱动 `turns=0` / `session_id=""` / 未注入转录 | 摘要亦**不读不注入**（锚点：`...::test_summaries_gated_like_history`） |
| TC-WINDOW-17 | 同 Scenario「维护节拍产出会话摘要与中期摘要」 | 冻结时钟 + 一次维护节拍（`_maintain("t-1","s1")`） | `summary_for` 与 `mid_summary_for` **均已产出**（锚点：`...::test_maintain_materializes_long_and_mid_summaries`） |
| TC-WINDOW-18 | 同 Scenario「摘要读取失败降级」/「维护节拍会话级两步失败不中断本轮」 | 替身 `summarize_slice` / `mid_summary_for` / `compact` 抛错 | 降级为空、留痕、**不抛**、本轮结局与事件序不变（锚点：`...::test_maintain_mid_failure_degrades_without_raising`、`...::test_load_summaries_failure_degrades_to_empty`） |
| TC-WINDOW-19 | loop/spec.md「错误与预算控制」记账口径（分层摘要计入） | 无探针 planner，对比「无摘要」与「两层摘要」两次运行 | `token_used` 增量 == `estimate_tokens(长期) + estimate_tokens(中期)`；**空字段零增量**（锚点：`tests/test_loop_token_accounting.py::test_layered_summary_tokens_counted_into_budget`、`...::test_empty_summary_fields_add_zero_tokens`） |

※ TC-WINDOW-02 断言值（10 / 6 / 16384）为 `# noqa: PLR2004` 标注的常量锚。

> **红态证据**：逐层先红后绿 —— Layer A `ImportError: cannot import name 'plan_window'`；Layer B
> `AttributeError: 'TranscriptStore' object has no attribute 'window'`；Layer C `AttributeError:
> 'MemoryStore' object has no attribute 'summarize_slice'`（**10 failed / 50 passed**）；Layer D 两条判别性
> 用例红（① 摘要未门控 ⇒ 未注入转录时仍注入；② 复用同一转录导致第二次运行回放首轮）。绿后全量
> `.venv/bin/pytest -q` ⇒ **2101 passed**（基线 **2052**，**+49** = A 19 用例 + B 7 + C 10 + D 13）。
> **逐字兼容不变量**（I1~I10）：关回灌 / 空标识 / 未注入转录 / 未注入记忆或摘要器 / 冷会话 ⇒ 请求与记账
> **逐字不变**；某轮维护失败 ⇒ 本轮结局、事件序、转录、终止语义不变；分层产物凭 `trace_id` 可整体回滚。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0169 行（每节拍额外模型调用成本 / 短层分层时收窄 /
> CJK 欠估不修 / 中带原文进 LLM 的密钥面 / 热路径两次全库扫描 / 中层产物与「相关事实」块可能重复暴露 /
> 节拍实例级会话无关 / `_should_compact` 轮数维度未修）。

## 92. 失败经验的独立沉淀面：轮级失败另立 L2 条目 + 压实材料排除（TC-FAILMEM，change `0179`／ADR-0170，台账 E116）

> **背景取证**（用户 2026-10-10 复盘四类记忆「会话滑窗 / 语义=notes / 程序=技能 / 情景=错误与成功经验」问
> 「是否有遗漏」）：① `remember()` 每轮只写两条（轨迹散文**含** `round N failed <error>` 行 + 行动序列），
> 全 `src/` **无任何** `fail*`/`error` 标签 ⇒ 失败无法作为**一类检索对象**；② `SopExtractor.observe` 对
> `ok=False` **直接丢弃**、docstring 自陈「教训沉淀走 memory/evolution 通道」，而该通道**从未存在**
> （`Crystallizer.dissolve` 的 `["dissolved","lesson"]` 在 `src/` 内无调用方；evolution 侧对 memory
> **只写不读**）；③ 压实材料唯一来源 `_episodic_groups()` **无 tags 判据** ⇒ 失败轮条目必被摘要吸收、
> 随即迁 L4（检索权重 0.6 → 0.2），失败证据被**摘成中性总结**。三者合成「情景记忆里的失败没有独立沉淀面」。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-FAILMEM-01 | loop/spec.md「执行循环」Scenario「失败轮另立一条 L2 条目」 | `failure_digest(轨迹, steps, reason=…, task=…)` | 行序 = **任务 → 失败：原因 → 失败轮行（`round N failed <error>`，复用 `_trajectory_line`）→ 失败步行（含 `错误：`）**；末条合成 `{"reply": …}`（**无 `ok` 键**）**不入**（判据 `ok is False` 而非 falsy）（锚点：`tests/test_loop_failure_memory.py::test_failure_digest_renders_task_reason_rounds_and_steps`） |
| TC-FAILMEM-02 | 同 Scenario（`reason` 缺省 / 无失败轮） | `failure_digest([], [], reason="", task="")` | 恒为**非空**、走恒定兜底文案 `失败：<兜底>`（锚点：`...::test_failure_digest_falls_back_when_reason_missing`） |
| TC-FAILMEM-03 | loop/spec.md「执行循环」Scenario「失败条目脱敏且有界」 | 任务 / 原因 / 失败轮 / 失败步**各含**明文密钥形态；100 条超长失败步；5000 字任务 | **逐行** `<redacted>`（四行各一）；整体 ≤ `_MAX_MEMORY_ENTRY`；任务首行 ≤ `_MAX_STEP_LINE`（锚点：`...::test_failure_digest_redacts_each_line`、`...::test_failure_digest_is_bounded`、`...::test_failure_digest_bounds_long_task`） |
| TC-FAILMEM-04 | 同 Scenario「失败轮另立一条 L2 条目」 | `remember(..., steps=[…], failed=True, reason=…, task=…)` | **三态并存**（`loop.t*` / `loop.steps.t*` / `loop.failure.t*`）；失败条目 `layer="L2"` / `kind="episodic"` / `tags=["loop","failure"]` / 同 `trace_id` / 同 `session_id` / `source` 取注入命名空间；内容含任务与原因（锚点：`...::test_failed_turn_writes_dedicated_failure_entry`） |
| TC-FAILMEM-05 | loop/spec.md「执行循环」Scenario「成功轮不写失败条目」 | 成功轮 `remember(..., steps=[…])`（`failed` 缺省） | **无** `loop.failure.*`；既有两条内容**逐字不变**（`{"loop.t2": "round 1 ok\n成了", "loop.steps.t2": …}`）（锚点：`...::test_success_turn_writes_no_failure_entry`） |
| TC-FAILMEM-06 | 同 Scenario（无 `steps` / 未注入 memory） | `failed=True` 且无工具动作；`DefaultLoop().remember(..., failed=True)` | 无行动序列条目但**仍有**失败条目（`{loop.t3, loop.failure.t3}`）；未注入 memory **不抛**（既有守卫）（锚点：`...::test_failure_entry_without_steps_still_written`、`...::test_no_memory_wired_is_a_noop`） |
| TC-FAILMEM-07 | 同 Scenario（可逆） | `EffectTracker` 注入 memory 后 `rollback("t4")` | 失败条目**消失**（`write` → `_persist` → `_tracker.record`，P2 可逆）（锚点：`...::test_failure_entry_is_reversible`） |
| TC-FAILMEM-08 | 同 Scenario（可检索） | `read("删除生产库 权限不足", session_id="s2")` | 失败条目**被命中**（注入面零改动 ⇒ 靠既有按相关度检索）（锚点：`...::test_failure_entry_is_retrievable`） |
| TC-FAILMEM-09 | 同 Scenario（`limit_reason` 两源） | 真 loop：`max_rounds=1`；`token_budget=1` | 失败条目内容分别含 `失败：LOOP_LIMIT_EXCEEDED` / `失败：TOKEN_BUDGET_EXCEEDED`（锚点：`...::test_round_limit_termination_writes_failure_entry`、`...::test_token_budget_termination_writes_failure_entry`） |
| TC-FAILMEM-10 | 同 Scenario（**轮级**口径，判别性） | 真 loop：第 0 轮工具 schema 不符（该步失败）、第 1 轮正常回复收尾 | 本轮**成功** ⇒ **无**失败条目（ReAct 自愈不记失败；轮内工具失败仍在 `loop.steps` 条目里）（锚点：`...::test_tool_failure_inside_turn_does_not_write_failure_entry`） |
| TC-FAILMEM-11 | 同 Scenario（`turn_failed` 另一源 + ADR-0161 禁入面） | 经**真实** `LLMPlanner._parse` 取「不可解析 ⇒ 失败态终止动作」后跑循环 | `result.failed is True`；写失败条目且兜底原因在内容；**`raw_output` 不入**（ADR-0161 明文禁入面，失败条目不得成为旁路）（锚点：`...::test_unparseable_output_writes_failure_entry_without_raw_output`） |
| TC-FAILMEM-12 | memory/spec.md「记忆压实」Scenario「失败条目不被压实吸收」 | 同会话一条普通条目 + 一条 `tags=["loop","failure"]`；`compact()` | 摘要材料**只见**普通条目；失败条目 `layer` **仍 L2**、普通条目**照常迁 L4**；摘要 `tags` **不含** `from:loop.failure.*`（锚点：`tests/test_memory.py::test_compact_skips_failure_entries_but_archives_plain_ones`） |
| TC-FAILMEM-13 | memory/spec.md「记忆压实」Scenario「失败条目仍可被遗忘」 | 失败条目回拨 30 天 + `forget()` | **仍被归档 L4**（豁免面＝压实，**不含**遗忘；有界性由既有衰减曲线承担）（锚点：`...::test_forget_does_not_spare_failure_entries`） |
| TC-FAILMEM-14 | 同 Scenario（零排序副作用） | 失败条目 + 无关条目；`read("终止动作未达成")` | 失败条目排首位（判据用 **tag**：`rank` / `_decay_score` **完全不看 tags** ⇒ 不触 `("beast.","pet")` 命名空间红线）（锚点：`...::test_failure_entry_is_readable`） |

> **红态证据**：逐层先红后绿 —— Layer A `ImportError: cannot import name 'failure_digest'`；
> Layer B 缺 `loop.failure.*` 条目；Layer C `test_compact_skips_failure_entries_but_archives_plain_ones`
> 在旧 `_episodic_groups` 下**红**（`seen == [['e0','loop.failure.t1']]`，判别性用例）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2119 passed**（基线 **2101**，**+18** = A 5 用例 + B 10 + C 3）。
> **逐字兼容不变量**（I1~I9）：成功轮 ⇒ 不写失败条目且既有两条**逐字不变**；三新形参缺省 ⇒ 行为与变更前
> 逐字一致；未注入 memory ⇒ 无写入无异常；未失败轮 / `beast.*`·`pet` 命名空间 ⇒ 既有封存语义与
> `exclude_source_prefixes` 排除项**逐字不动**（失败条目沿用 `source=self._source`）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0170 行（只覆盖轮级失败 / 记忆面→诊断面仍无桥 /
> 最终仍会被遗忘 / 任务原文首次进 L2 记忆面 / 注入评分器时仍受闸门约束 / 不进摘要 / 跨会话同类失败靠语义命中 /
> 运维修复的按会话重抽材料仍含失败条目）。

## 93. 语义记忆去重：提升产物退出 Consult 命中面（TC-ARCHIVE-DEDUP，change `0180`／ADR-0171，台账 E117）

> **背景取证**（用户 2026-10-10 复盘「语义记忆--笔记提取重要内容归档，这个和哪一个重复了?」）：同一份
> 会话摘要在同一次请求里经**两条通道**重复注入 —— 通道 A（记忆侧）：`loop.default` 每轮
> `summary_for(session_id)` 读 L2 `compaction.summary.<sid>` → `ctx.summary_long` → planner
> 「历史摘要（长期）」块（**全文**、滚动最新）；通道 B（笔记侧）：`runtime._promote_summary`（半自动
> 唯一生产接线）→ `promote_session_summary(..., pin=False)`（正文即会话摘要副本）→ canonical 笔记
> `session-<slug>`（`source="notes.promote"`）→ `NoteStore.digest()` 命中节选 → `ctx.notes` → planner
> 「相关笔记」块。⇒ 提升产物是摘要的**副本**，与记忆侧**当前滚动摘要**同场（重复 token + **陈旧冻结快照**
> 与**最新摘要**并列的语义噪声）。用户裁决 ① 让位方向＝**提升产物退出 Consult 命中面**（记忆侧长期摘要块
> 留任）、② 退出粒度＝**只退命中节选、清单标题保留**。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-ARCHIVE-DEDUP-01 | notes/spec.md「Consult → Build → Update 循环纪律」Scenario「命中面排除归档来源（提升产物以清单标题在场）」 | 一篇 `source="notes.promote"` 的提升产物（词法可命中）+ 一篇普通笔记，`digest(query)` | 提升产物**无**节选（正文**恰一次**在场，非两次）；普通笔记节选**照常**；提升产物仍在「笔记清单」标题（存在性可见）（锚点：`tests/test_notes.py::test_store_digest_excludes_archived_source_from_hits`） |
| TC-ARCHIVE-DEDUP-02 | notes/spec.md「会话摘要提升（promotion）」Scenario「提升产物置常驻也不进命中节选（通道分列）」 | 同一提升产物**置常驻**（`pinned=True`），`digest()` + `pinned_digest()` | 命中节选**仍不给**其正文；`pinned_digest()` **完整**含其正文（两通道分列、同篇不重复）（锚点：`tests/test_notes.py::test_store_digest_excludes_archived_source_even_when_pinned`） |
| TC-ARCHIVE-DEDUP-03 | notes/spec.md 两 Requirement（不变量 I4：排除仅落 `digest`） | 提升产物 + `consult` / `search` / `list` | 三者对提升产物**逐字不变**（检索语义不动 ⇒ CLI `notes search` 仍搜得到）（锚点：`tests/test_notes.py::test_store_consult_search_list_unchanged_for_archived_source`） |
| TC-ARCHIVE-DEDUP-04 | notes/spec.md「Consult → Build → Update 循环纪律」Scenario「命中面排除归档来源」+ 真实 loop 接线 | 真 `DefaultLoop`（`notes_consult=store.digest` / `pinned_notes_consult=store.pinned_digest`）+ 提升产物 + 普通笔记 | `ctx.notes` **不含**提升产物节选、**含**普通命中、仍以 `session-*` 标题在场；`ctx.pinned_notes == ""`（半自动不占常驻预算）（锚点：`tests/test_notes_loop.py::test_loop_notes_block_excludes_promoted_summary`） |
| TC-ARCHIVE-DEDUP-05 | notes/spec.md「会话摘要提升（promotion）」Scenario「提升产物置常驻也不进命中节选（通道分列）」+ 真实 loop 接线 | 真 `DefaultLoop` + **置常驻**提升产物 | `ctx.notes` 无其节选 **且** `ctx.pinned_notes` 含其**完整**正文（通道分列）（锚点：`tests/test_notes_loop.py::test_loop_promoted_note_pinned_stays_in_single_channel`） |
| TC-ARCHIVE-DEDUP-06 | notes/spec.md「会话摘要提升（promotion）」Scenario「半自动提升产物不进命中节选（只以清单标题在场）」+ 真实链路 | 真 `MemoryStore`（`_LONG` 摘要 + 提升钩子 → `NoteStore(pin=False)`）越界半自动提升后，以命中 query 取 `digest()` | `consult("会话摘要") == ["session-s1"]`（检索面**不变**）但 `digest` **含** `session-s1` 标题、**不含**摘要正文（锚点：`tests/test_memory_summary_promotion.py::test_semi_auto_promotion_leaves_digest_hit_surface`） |

> **红态证据**：逐层先红后绿 —— Layer A `test_store_digest_excludes_archived_source_from_hits` /
> `..._even_when_pinned` 在旧 `digest` 下**红**（命中节选仍含提升正文「先备份再滚动更新」）；
> Layer B 端到端 `test_loop_notes_block_excludes_promoted_summary` **红**（`ctx.notes` 含提升正文）；
> Layer C `test_semi_auto_promotion_leaves_digest_hit_surface` **红**。`..._consult_search_list_unchanged...`
> **生而绿**（守不变量 I4，非驱动变更）。绿后全量 `.venv/bin/pytest -q` ⇒ **2125 passed**
> （基线 **2119**，**+6** = A 3 用例 + B 2 + C 1）。
> **逐字兼容不变量**（I1~I7）：无提升笔记的语料 ⇒ `digest()` 输出**逐字不变**（零扰动）；`consult` /
> `search` / `list` / `pinned_digest` 口径**逐字不动**；`loop` / `memory` **零改动** ⇒「历史摘要（长期）」
> 块仍是该会话摘要的**唯一** prompt 通道；判据落 **source**（canonical 内持久、来源守护面）而非 tag。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0171 行（显式提升仍存在本会话内双在场 / 提升产物仍以
> 标题占 digest 预算 / 判据依赖 canonical `- source:` 行 / 未做同源去重的一般化）。

## 关联

- 测试计划：`doc/04-testing/test-plan.md`
- 需求：`doc/00-product/requirements.md`
- 规格：`doc/openspec/specs/*`

## 94. 写入侧重要度闸门的生产接线与内部产物豁免面（TC-MEM-GATE-WIRE，change `0181`／ADR-0172，台账 E118）

> **背景取证**：写入侧重要度闸门的契约与实现齐备（`ImportanceScorer` 契约 `memory/store.py:74`、构造形参
> `:173`/`:182`、闸门 `write()` 先评分再落库、`_gate_score` 三态降级全在），但 `runtime.py` 构造
> `MemoryStore` 时**无** `importance_scorer=` 实参 ⇒ 生产环境该闸门**永远**走「UNWIRED ⇒ 不评分」路径
> （同 `summarizer` / `key_fact_extractor` 早已组合根注入相对照 —— 唯一漏接的记忆接缝）。同一条 `write()`
> 上，**内部派生产物**亦过闸门：会话摘要与中层摘要（`source="compaction"`）、压实产物（`source="context"`）、
> 结构化关键事实（`source="extraction"`）—— 一经注入评分器，**由系统管道从已准入材料派生**的结论就可能
> 被判低价值而拒收/降层（ADR-0168 局限①由理论风险变为真实路径）。本 change：**补接**生产接线（新键
> `memory.importance_gate`，**缺省 false** ⇒ 行为逐字不变），并同时在闸门内加**内部派生产物豁免面**。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-MEM-GATE-WIRE-01 | memory/spec.md「写入侧重要度闸门」新条款「内部/派生产物豁免」Scenario「内部派生产物豁免评分」 | scorer 恒返 `_IMPORTANCE_FLOOR - 0.1`（低分）+ 来源∈豁免面（`compaction` / `context` / `extraction` 各一）的条目 | 条目**按意向层入库**、**不**降层、`importance` 保持 0.0、**无** `warnings` 留痕（派生结论不因评分而丢失）（锚点：`tests/test_memory.py::test_gate_exempts_internal_derived_sources`） |
| TC-MEM-GATE-WIRE-02 | 同新条款 + 不变式 I2（豁免面**不**覆盖有机写入） | 同一低分 scorer + 来源**非**豁免面（`source="loop"`）的条目 | 条目**被拒收**（`write` 返回 `None`、`audit()` 为空）+ `warnings.warn` 留痕（豁免面只覆盖系统派生产物）（锚点：`tests/test_memory.py::test_gate_exempt_face_does_not_cover_organic_writes`） |
| TC-MEM-GATE-WIRE-03 | 不变式「新增派生来源须同步登记」 | 断言 `_GATE_EXEMPT_SOURCES` 常量内容 | 恰为 `{"compaction", "context", "extraction"}` —— 常量变更即测试红（同步摩擦）（锚点：`tests/test_memory.py::test_gate_exempt_face_is_the_pipeline_sources`） |
| TC-MEM-GATE-WIRE-04 | memory/spec.md「写入侧重要度闸门」（评分器工厂接缝） | `score_with(λ→"0.8")` / 散文包裹 `0.35` / 无数值 / `1.7` | 依次：0.8；0.35（取**首个**数值）；抛 `ValueError`；**原样** 1.7（不 clamp）（锚点：`tests/test_memory_importance.py::test_score_with_*`） |
| TC-MEM-GATE-WIRE-05 | 不变式「失败方向恒为放行」+ 端到端接线 | `MemoryStore(importance_scorer=score_with(λ→无法解析))` / `score_with(λ→低分)` 各写一条 | 前者**降级放行**（入库 + `warnings` 留痕、`importance` 保持 0.0）；后者经闸门**拒收**（锚点：`tests/test_memory_importance.py::test_score_with_unparseable_output_degrades_gate_to_normal_write` / `..._low_score_rejects_via_gate`） |
| TC-MEM-GATE-WIRE-06 | 架构不变量（ADR-0045 单向依赖） | AST 走查 `src/core/memory/importance.py` 的 import | **无** `core.llm_provider` / `core.rag` 导入（工厂只吃 `str→str` 调用，prompt 文本属 memory 域）（锚点：`tests/test_memory_importance.py::test_importance_module_imports_no_llm_or_rag`） |
| TC-MEM-GATE-WIRE-07 | configuration（新键单一真源 + 段白名单） | `config_specs()` / yaml / env / 「未知配置段」告警 | 键 `memory.importance_gate` 三面齐备（`--memory-importance-gate` / `CORE_MEMORY_IMPORTANCE_GATE` / 缺省 `False`）；`memory:` 段**不**报未知段（声明段自动进白名单）（锚点：`tests/test_memory_config.py::test_spec_declares_importance_gate` / `..._section_is_not_reported_unknown`） |
| TC-MEM-GATE-WIRE-08 | 组合根接线（缺省零扰动 / 开启即注入） | `build_runtime` 缺省 / `memory.importance_gate: true` | 缺省 ⇒ `_importance_scorer is None`（写入逐字不变）；true ⇒ 注入 `score_with(_llm_text)` 产物（锚点：`tests/test_memory_config.py::test_build_runtime_default_wires_no_scorer` / `..._wires_scorer_when_enabled`） |

> **红态证据**：逐层先红后绿 —— Layer A `test_gate_exempts_internal_derived_sources`（3 参数）在旧
> `write()` 下**红**（恒低分 ⇒ 派生条目被拒收/降层）；Layer B `tests/test_memory_importance.py` 全文件
> **导入即红**（`memory/importance.py` 不存在）；Layer C `test_spec_declares_importance_gate` /
> `test_build_runtime_wires_scorer_when_enabled` **红**（`importance_gate` 属性缺失 / 组合根不注入）。
> `test_gate_exempt_face_does_not_cover_organic_writes` **生而绿**（守豁免面不覆盖有机写入，非驱动变更）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2146 passed**（基线 **2125**，**+21** = A 5 用例 + B 9 + C 7）。
> **逐字兼容不变量**：缺省 false ⇒ 组合根**不**注入评分器、`write()` 与变更前**逐字一致**（既有 6 个闸门
> 用例全绿，零回归）；豁免面**只缩小**评分面（不扩大）；`_gate_score` / 阈值常量 / 迁移与写回路径**逐字不动**
> （豁免在**调用点**短路）；`loop` / `context` / `notes` / `evolution` **零改动**。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0172 行（豁免面按 `source` 判据须同步登记 / 逐条目 LLM
> 调用开销 / `evolution` 直写不过闸门 / 生产缺省关属运行策略 / 宽松归一使笔误静默关闭）。

## 95. 压实触发的诚实化与配置注入（TC-COMPACT-TRIGGER，change `0182`／ADR-0173，台账 E119）

> **背景取证**：`Compactor.should_compact(self, rounds, token_used, budget)`（`context/compactor.py`）参数
> 写作 `rounds`、判据写作「轮数达到阈值」，但实参是 `ctx.rounds`（`loop/default.py` 触发点），而它是
> **本轮内已记账的工具动作步数**（`observe()` 内自增；`perceive()` 每用户轮重造 `LoopContext` ⇒ 每轮自 `0`
> 起算）。更实质：`_ROUND_THRESHOLD = 10` 与 `loop.max_rounds` 缺省 `10` **恰好相等**，而循环顶在
> `ctx.rounds >= max_rounds` 时先 `break` ⇒ 触发检查点**永远等不到** `rounds == 10`，**该维度事实上是死的**，
> 唯一活触发是 token 阀；且阈值是模块常量、**无配置键**（用户无法调到上限以下让它生效）。本 change：
> **诚实化**（形参/常量/kwarg/文案改口「工具步数」）＋ **配置注入**（新键 `loop.compact_steps`，缺省 `6`）
> ＋ **每轮至多一次**压实（步数阈值小于上限时 `步数 ≥ 阈值` 步步为真 ⇒ 无闸门则同轮多次模型调用）。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-COMPACT-TRIGGER-01 | context/spec.md「上下文自动压实」触发判据（工具步数维度） | `Compactor()` 缺省，`should_compact(5, 0, 大预算)` / `should_compact(6, 0, 大预算)` | 前者 `False`、后者 `True` —— 默认步数阈值 `6` 边界正确、该维度**活着**（锚点：`tests/test_context_compaction.py::test_default_step_threshold_boundary`） |
| TC-COMPACT-TRIGGER-02 | 缺省值单一真源（两地同值） | 断言 `configuration.manager._DEFAULT_COMPACT_STEPS` 与 `context.compactor._STEP_THRESHOLD` | **同值** —— `configuration` 不 import `context`（分层方向）⇒ 用测试把「两地」钉成**受门禁约束的两地**（锚点：`tests/test_context_compaction.py::test_config_default_matches_compactor_default`） |
| TC-COMPACT-TRIGGER-03 | 规格 Scenario「工具步数阈值可在本轮内触发且每轮至多一次」 | 阈值 `2`、`max_rounds=5`、非终止工具链；逐 `step_completed` 事件观察压实计数 | 第 1 步 `0`、**第 3 步时已为 `1`**（早于第 5 步终止）⇒ 提前触发**确已发生**（锚点：`tests/test_context_compaction.py::test_loop_step_threshold_triggers_before_limit`） |
| TC-COMPACT-TRIGGER-04 | 同 Scenario（**每轮至多一次**） | 阈值 `2`、`max_rounds=6`（阈值步后 `步数 ≥ 2` 步步为真） | `compacted == 1` —— 同轮多次满足判据**不重复**压实（改前为最多 5 次）（锚点：`tests/test_context_compaction.py::test_loop_compacts_at_most_once_per_turn`） |
| TC-COMPACT-TRIGGER-05 | 规格 Scenario「步数阈值达上限时不再重复压实」+ token 维度回归 | 缺省装配（阈值 `6`、上限 `10`）非终止动作连跑 | 压实恰 **1** 次且由 `LOOP_LIMIT_EXCEEDED` 终止（锚点：`tests/test_context_compaction.py::test_loop_default_wiring_compacts_exactly_once`）；`should_compact(0, 预算−1/预算, 预算)` ⇒ `False`/`True`（token 路径逐字不变，锚点：`...::test_default_token_budget_boundary`） |
| TC-COMPACT-TRIGGER-06 | configuration/spec.md「循环预算配置」第四键（单一真源） | `config_specs()` / yaml / env / CLI / 缺省 | 键 `loop.compact_steps` 三面齐备（`--loop.compact-steps` / `CORE_LOOP_COMPACT_STEPS` / 缺省 `6`），优先级链 CLI > env > yaml 生效，且 `loop_limits()` 仍为二元组（独立访问器）（锚点：`tests/test_loop_budget_config.py::test_compact_steps_*`） |
| TC-COMPACT-TRIGGER-07 | 同 Requirement Scenario「压实步数阈值经 ConfigSpec 声明且受校验」 | `loop.compact_steps` 取 `0` / `-1` / `2.5` / `abc` / `true` | 校验失败**阻断启动**，错误信息指明键名与合法取值（不静默兜底）（锚点：`tests/test_loop_budget_config.py::test_invalid_compact_steps_blocks_startup`） |
| TC-COMPACT-TRIGGER-08 | 组合根接线 | `build_runtime` 注入 `loop.compact_steps: 3` | 主 loop 的压实器 `_step_threshold == 3`（缺省 `6` ⇒ 与模块缺省同值、行为逐字一致）（锚点：`tests/test_loop_budget_config.py::test_build_runtime_injects_configured_compact_steps`） |

> **红态证据**：`tests/test_context_compaction.py` **导入即红**（`_DEFAULT_COMPACT_STEPS` 尚不存在）；
> `test_step_threshold_is_injectable` / `test_loop_compacts_at_most_once_per_turn` **红**
> （`step_threshold` 形参缺失 / 旧码同轮多次压实）；`test_compact_steps_*`
> **红**（`compact_steps` 访问器与 ConfigSpec 缺失）。绿后全量 `.venv/bin/pytest -q` ⇒ **2163 passed**
> （基线 **2146**，**+17** = 压实面 9 用例 + 配置面 8 用例）。
> **逐字兼容不变量**：`token` 触发路径与终止语义（`TOKEN_BUDGET_EXCEEDED` / `LOOP_LIMIT_EXCEEDED`）
> **逐字不变**；无压实器 ⇒ 永不压实；「每轮至多一次」标记为本轮**执行态**局部变量（随轮自然重置）；
> `exclude_source_prefixes=("beast.","pet")` 主方向封存红线（`runtime.py:603`）**逐字不动**。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0173 行（`LoopContext.rounds` 仍为历史名 / 缺省 `6`
> 为启发式 / 阈值 ≥ 上限时静默退化 / 「至多一次」为每用户轮粒度 / 仍只有轮级触发无内容判据）。

---

## 96. 流式令牌用量与请求侧输出上限（TC-LLM-USAGE，change `0183`／ADR-0174，台账 E120）

> **背景取证**：`LLMChunk`（`llm_provider/models.py`）**无** `usage` 字段、`_map_chunk`
> （`stdlib_provider.py`）从不解析顶层 `usage`；而**流式是默认推理路径**（`LLMPlanner.astream`
> 优先，非流式只在 provider 缺 `astream` 时退化）⇒ `_last_prompt_tokens` 在流式下**只有装配估算、
> 从不被端点实报抬升**，两路径记账口径不一致；流式请求体也不要求端点上报用量。同时
> `LLMRequest.max_tokens` 是**死字段**（`_build_body` 支持下发、无调用方填）⇒ 配置项
> `loop.output_reserve` 只是**记账假设**（预算派生 `窗口 − 预留`），模型侧无上界。
> **键位陷阱**：OpenAI 兼容端点在开启用量上报时把 `usage` 放在**末块**，而该末块 `choices` 是**空数组**
> ⇒ 必须在该早返分支**之前**取用量，否则数字永远丢失。本 change：用量字段 + 末块解析 + 请求侧
> `stream_options` + 消费方抬升下界 / 记录完成量 + `max_tokens` 构造期注入。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-LLM-USAGE-01 | llm-provider/spec.md「流式增量携带令牌用量」末块形态 | 流式一行 `{"choices":[],"usage":{"prompt_tokens":120,"completion_tokens":34}}` | 该块 `usage == TokenUsage(120, 34)` 且 `content == ""` —— **不因 `choices` 空而丢弃**（锚点：`tests/test_llm_provider.py::test_chunk_maps_usage_from_empty_choices_end_block`） |
| TC-LLM-USAGE-02 | 同 Requirement（未携带 ⇒ `None`） | 块不含 `usage` 键 / `usage: null` | `LLMChunk.usage is None`（不报错、**不以 `TokenUsage(0,0)` 冒充**），其余字段解析逐字一致（锚点：`...::test_chunk_usage_none_when_absent`） |
| TC-LLM-USAGE-03 | 同 Requirement Scenario「流式请求要求端点上报用量」 | 流式调用后读请求体 | `stream is True` 且 `stream_options == {"include_usage": True}`（锚点：`...::test_stream_body_requests_include_usage`） |
| TC-LLM-USAGE-04 | 同 Requirement（非流式不发该字段） | 非流式 `acompletion` 后读请求体 | **不含** `stream_options`、**不含** `stream`（既有形状逐字保留）（锚点：`...::test_body_omits_stream_options_when_non_streaming`） |
| TC-LLM-USAGE-05 | 同 Requirement Scenario「消费方以实报抬升提示词下界」 | 流式末块实报 `prompt_tokens = 999` | `last_prompt_tokens() == max(估算, 999)` —— 实报为**下界**、只抬升；消费在 `content` 空判**之前**故末块用量不被跳过（锚点：`tests/test_loop_token_accounting.py::test_planner_stream_raises_prompt_floor_from_usage`） |
| TC-LLM-USAGE-06 | 同 Requirement（完成量仅观测） | 末块 `completion_tokens = 7` / 未上报 | `last_completion_tokens() == 7` / `== 0`；**不**改终止语义与预算闸门（锚点：`...::test_planner_records_completion_tokens_as_observation`） |
| TC-LLM-USAGE-07 | llm-provider/spec.md「请求侧输出上限按预留注入」Scenario「注入正预留即下发」 | `LLMPlanner(max_tokens=8192)` | 请求 `max_tokens == 8192`（锚点：`...::test_planner_injects_max_tokens`） |
| TC-LLM-USAGE-08 | 同 Requirement Scenario「未注入或非正预留不下发」 | `max_tokens` 取 `None` / `0` / `-1` | 请求 `max_tokens is None` ⇒ body 无该键（既有形状逐字不变）（锚点：`...::test_planner_omits_max_tokens_when_non_positive`） |
| TC-LLM-USAGE-09 | 组合根接线（既有键、独立访问器） | `output_reserve()` 缺省 / yaml 配置 / `loop_limits()` arity | 缺省 `8192`；配置 `4096` ⇒ 访问器 `4096`；`loop_limits()` 仍为二元组（未配窗口时预算仍回落 `65536`）（锚点：`tests/test_loop_budget_config.py::test_output_reserve_accessor_*`） |
| TC-LLM-USAGE-10 | 端到端：预留从记账假设变为端点上界 | `build_runtime` 注入 `loop.output_reserve: 4096` | 主 loop planner 的 `_max_tokens == 4096`（四个 loop 的 planner 同源同参）（锚点：`tests/test_loop_budget_config.py::test_build_runtime_injects_output_reserve_as_max_tokens`） |

> **红态证据**：`test_chunk_maps_usage_from_empty_choices_end_block` / `test_chunk_usage_none_when_absent`
> **红**（`LLMChunk.usage` 不存在）；`test_stream_body_requests_include_usage` **红**（`KeyError:
> 'stream_options'`）；planner 面 4 组 **红**（`_max_tokens` / `last_completion_tokens` 不存在）；
> `test_output_reserve_accessor_*` / 组合根接线 **红**（访问器与注入点缺失）。绿后全量
> `.venv/bin/pytest -q` ⇒ **2176 passed**（基线 **2163**，**+13** = provider 面 4 + planner 面 6 + 配置与接线 3）。
> **逐字兼容不变量**：非流式 `LLMResponse.usage` 解析与请求体形状**逐字不变**；`max_tokens` 未注入 ⇒
> `LLMRequest.max_tokens is None` ⇒ body 无该键；`completion_tokens` 不入任何判定；`finish_reason`
> 既有 `getattr` 处置不变；`exclude_source_prefixes=("beast.","pet")` 主方向封存红线（`runtime.py:603`）**逐字不动**。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0174 行（拒绝 `stream_options` 的端点流式报错、无首轮探测
> 降级 / `max_tokens` 默认生效且未按模型推导输出上限 / `completion_tokens` 无消费者 / 只认末块用量 /
> 观测为单轮量无跨轮累计）。

---

## 97. 已知模型窗口表与 provider 审计标签（TC-MODEL-WINDOW，change `0184`／ADR-0175，台账 E121）

> **背景取证**：① `llm.context_window` 未配置（缺省 `0`）时 `loop_limits()`
> （`configuration/manager.py`）**直接回落常量 `65536`** ⇒ 不论跑 `gpt-4o`（128k）还是 `claude-*`（200k），
> token 预算恒为 `65536 − 8192`，用户不显式配窗口就永远拿不到模型真实窗口（闸门**偏早**，保守但白扔窗口）。
> ② `LLMResponse.provider` 在 `_map_response`（`llm_provider/stdlib_provider.py`）**硬编码 `"stdlib"`**、
> 组合根构造 `StdlibLLMProvider`（`runtime.py`）**不传** provider ⇒ 即便 `llm.provider: litellm`
> （该键**必填**、校验非空），响应上的审计标签仍是 `"stdlib"` —— 规格「模型调用审计」要求标注 provider，
> **标注与实际不符**（死标签）。本 change：内置有序窗口表 + 构造注入审计标签。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-MODEL-WINDOW-01 | configuration/spec.md「LLM 提供商配置（必选）」Scenario「未配置窗口时按模型推导」 | `known_window("gpt-4o-2024-08-06")` / `("anthropic/claude-sonnet-4")` / `("deepseek-chat")` / `("GPT-4O")` | 分别为 `128000` / `200000` / `65536` / `128000` —— **子串**匹配且**大小写不敏感**（锚点：`tests/test_loop_budget_config.py::test_known_window_matches_model_families`） |
| TC-MODEL-WINDOW-02 | 同 Requirement（未收录 ⇒ 不猜测） | `known_window("my-local-model")` / `known_window("")` | 均 `0`（=「不知道」的诚实表达，由调用方统一回落缺省）（锚点：`...::test_known_window_unknown_model_is_zero`） |
| TC-MODEL-WINDOW-03 | 同 Requirement Scenario「未配置窗口时按模型推导」 | `model: gpt-4o`、无 `context_window` ⇒ `loop_limits()` | `(10, 128000 − 8192)` —— 窗口取自表、**不再**恒 `65536`（锚点：`...::test_loop_limits_derives_window_from_model`） |
| TC-MODEL-WINDOW-04 | 同 Requirement Scenario「显式窗口优先于表推导」 | `context_window: 32768` + `model: gpt-4o` ⇒ `loop_limits()` | `(10, 32768 − 8192)` —— 显式值**胜出**（`gpt-4o` 表值 `128000` 被忽略）；**回归锚**（变更前后同值）（锚点：`...::test_loop_limits_explicit_window_wins`） |
| TC-MODEL-WINDOW-05 | 同 Requirement Scenario「未命中内置表回落缺省」 | `model: my-local-model`、无 `context_window` ⇒ `loop_limits()` | `(10, 65536)` —— 不做窗口派生、回落常量预算，**与变更前逐字一致**（回归锚）（锚点：`...::test_loop_limits_unknown_model_falls_back`） |
| TC-MODEL-WINDOW-06 | llm-provider/spec.md「模型调用审计」Scenario「审计标签反映配置的 provider」 | `StdlibLLMProvider(..., provider="litellm")` 完成一次补全 | `LLMResponse.provider == "litellm"`（配置面所见即响应面所见）（锚点：`tests/test_llm_provider.py::test_response_provider_label_reflects_configuration`） |
| TC-MODEL-WINDOW-07 | 同 Requirement（未注入 ⇒ 自身身份） | 裸构造（不传 `provider`）完成一次补全 | `LLMResponse.provider == "stdlib"` —— 与既有行为**逐字一致**（回归锚）（锚点：`...::test_response_provider_defaults_to_identity`） |
| TC-MODEL-WINDOW-08 | 同 Requirement（空标签自守） | `StdlibLLMProvider(..., provider="")` | `LLMResponse.provider == "stdlib"` —— 不把空串写进审计（锚点：`...::test_response_provider_blank_falls_back_to_identity`） |
| TC-MODEL-WINDOW-09 | 组合根接线（审计标签按配置注入） | `build_runtime`（`llm.provider: litellm`） | 主 loop planner 的 provider `_provider == "litellm"`（锚点：`tests/test_loop_budget_config.py::test_build_runtime_labels_provider_from_config`） |
| TC-MODEL-WINDOW-10 | 逐字兼容不变量（窗口减法一处） | 归一后统一 `window − output_reserve`；显式 / 表未命中两路径 | 显式路径与未命中路径的返回值与变更前**逐字相同**；`loop_limits()` arity 与 `(max_rounds, token_budget)` 解包断言不变（锚点：TC-MODEL-WINDOW-04/05 两条回归锚 + 既有预算用例全绿） |

> **红态证据**：`test_known_window_*` / `test_loop_limits_derives_window_from_model`
> **红**（`core.configuration.model_windows` 模块不存在）；`test_build_runtime_labels_provider_from_config`
> **红**（`StdlibLLMProvider.__init__() got an unexpected keyword argument 'provider'`）；
> `test_response_provider_label_reflects_configuration` / `test_response_provider_blank_falls_back_to_identity`
> **红**（同上 `TypeError`）。绿后全量 `.venv/bin/pytest -q` ⇒ **2185 passed**（基线 **2176**，**+9** =
> 表面 2 + 预算面 3 + provider 面 3 + 接线 1）。
> **逐字兼容不变量**：显式 `context_window > 0` ⇒ 预算派生与变更前**逐字相同**；表未命中 ⇒ 回落 `65536`，
> **逐字相同**；`provider` 未注入 ⇒ 标签仍 `"stdlib"`，**逐字相同**；表是**纯常量 + 纯函数**，
> **不**新增 ConfigSpec / CLI / env / yaml 面（**不是**第二真源）；无新第三方依赖、无 import 方向变化；
> `exclude_source_prefixes=("beast.","pet")` 主方向封存红线（`runtime.py`）**逐字不动**。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0175 行（静态表不自更新 / 子串无边界语义 /
> 表推导窗口**不过** `_window_reserve_errors` 闸门 ⇒ 荒谬大 `output_reserve` 可静默关闸 /
> 本 change **不**按模型推导**输出上限**（ADR-0174 局限②留坑仍在）/ 表只覆盖 `context_window` /
> 第三方 `LLMProvider` 自产硬编码标签管不到）。

---

## 98. 压缩产物退出事实注入面（TC-FACT-EXCLUDE，change `0185`／ADR-0176，台账 E122）

> **背景取证**：会话长期摘要（`source="compaction"`，`memory/store.py:655`）与中层摘要
> （`store.py:461`）的正文，**已由** `loop/default.py`（planner 侧「历史摘要（长期）/（中期）」块）
> **每轮专块注入一次**；但两者 `source` 不在装配器 `exclude_source_prefixes` 内 ⇒ `_gather_facts`
> 又经「相关事实」面**再注入一次**。① **预算浪费**（同一份正文吃两份配额）；② 更坏的 **虚假置信**
> —— 同一内容以两条独立条目出现，被读成「两条彼此印证的证据」。`notes` 规格早有同型纪律
> 「同一份内容 SHALL NOT 经两条通道重复注入同一次请求」，本 change 把该纪律**推广到压缩产物面**。
> **轴订正**：计划稿给的实参是 **id** 前缀 `("compaction.summary.", "compaction.mid.")`，
> 而排除面的比较对象是 `entry.source` ⇒ 传 id 前缀**一条都匹配不上**（**静默空操作**）。
> 树中 `source == "compaction"` 的条目**恰好两条**（mid / summary），压实产出的**事实 / 未决**是
> `source == "context"`（`compactor.py:101/115`）⇒ `("compaction",)` 是**可证正确且最小**的轴。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-FACT-EXCLUDE-01 | context/spec.md「动态上下文构建」Scenario「压缩产物不进事实面」 | 假 MemoryStore 返 2 条 `compaction`（长期 / 中期摘要）+ 2 条 `context`（事实 / 未决）；`exclude_fact_sources=("compaction",)` ⇒ `build()` | `facts` 的 source 序列 == `["context", "context"]` —— 摘要**退出**事实面、`context` 派生物**留下**（锚点：`tests/test_context.py::test_fact_source_exclusion_drops_compaction_entries`） |
| TC-FACT-EXCLUDE-02 | 同 Requirement（缺省逐字一致）—— **回归锚** | 同假 store；**不传** `exclude_fact_sources` ⇒ `build()` | source 序列 == `["compaction", "compaction", "context", "context"]` —— 四条**全在**，与变更前**逐字一致**（锚点：`...::test_fact_source_exclusion_default_is_verbatim`） |
| TC-FACT-EXCLUDE-03 | 同 Requirement（**前缀**语义，非子串 / 非 id） | `exclude_fact_sources=("compaction.",)`（**带点**）⇒ `build()` | 四条**全在** —— 裸 `compaction` **不**以 `compaction.` 开头 ⇒ 前缀按**字面**生效（id 前缀式的实参会**静默空操作**，本用例即其守卫）（锚点：`...::test_fact_source_exclusion_is_prefix_based`） |
| TC-FACT-EXCLUDE-04 | 同 Requirement（派生装配器继承） | `sealed.with_allow_source_prefixes("beast.qinglong")` ⇒ 派生装配器 `build()` | `derived._exclude_fact_sources == ("compaction",)` **且** `facts` source == `["context", "context"]` —— 放行面替换**不**冲掉事实面排除面（锚点：`...::test_fact_source_exclusion_survives_namespace_derivation`） |
| TC-FACT-EXCLUDE-05 | 同 Requirement（排除**只**落注入步骤）—— **回归锚** | 真 `MemoryStore` 写一条 `source="compaction"` 的 `compaction.mid.default` ⇒ `store.read("中期摘要正文")` | 仍**取回**该条 —— `read` 的检索语义 / 排序 / 预算 / 复用强化**逐字不变**（`compaction.*` 对抽取素材 / 检索素材 / CLI 查询仍可见）（锚点：`...::test_summary_stays_readable_through_memory_read`） |
| TC-FACT-EXCLUDE-06 | 组合根接线（真装配器带排除面） | `build_runtime(ConfigManager(yaml_path=…))` | 主 loop 装配器 `_exclude_fact_sources == ("compaction",)` **且** `_exclude_source_prefixes == ("beast.", "pet")` —— 排除面**真的接上**、封存红线**逐字不动**（锚点：`tests/test_context.py::test_build_runtime_excludes_compaction_from_fact_face`） |

> **红态证据**：`test_fact_source_exclusion_*` **红**（`DynamicAssembler.__init__() got an unexpected
> keyword argument 'exclude_fact_sources'` 与 `AttributeError: _exclude_fact_sources`）；
> `test_build_runtime_excludes_compaction_from_fact_face` **红**（同上构造 `TypeError`）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2191 passed**（基线 **2185**，**+6** = 排除面 4 + 检索语义回归 1
> + 组合根接线 1）。
> **逐字兼容不变量**：`exclude_fact_sources` 缺省空 ⇒ `_gather_facts` 走**原返回**语句（无新分支进入）、
> 装配结果与变更前**逐字相同**；过滤落在**读后** ⇒ `MemoryStore.read` 语义 / 排序 / 预算 / 复用强化
> **逐字不变**；`exclude_source_prefixes=("beast.","pet")` 主方向封存红线（`runtime.py`）**逐字不动**；
> 派生装配器 `with_allow_source_prefixes` 的封存继承语义**逐字不变**（新增仅事实面排除面的继承）；
> 无新配置键（排除面由组合根**硬接线**）、无新第三方依赖、无 import 方向变化。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0176 行（**预算近似** —— 被挡条目在 `read()` 内
> 已消耗配额、本 change 不回收 / `session_id` 为空时「专块取不到 + 事实面已排除」的**窄缝** /
> 前缀语义无边界 ⇒ 未来新 `compaction*` source 会被顺带挡掉 / 本 change **不**处理
> `loop.steps.<trace>` 的同型问题 —— 另立 `0186`）。

---

## 99. 原始步序素材退出事实注入面（TC-STEP-EXCLUDE，change `0186`／ADR-0177，台账 E123）

> **背景取证**：`loop.steps.<trace_id>`（`loop/default.py:819-831`）是每轮「工具动作（参数）→ 结果节选」
> 的**原始行动序列**，**声明角色**是**抽取器素材**（`_write_trajectory` docstring 明文：另立该条是为让
> 抽取器仍能看到原始序列）；但它的 `source` 与轨迹（`loop.<trace_id>`）、失败摘要（`loop.failure.<trace_id>`）
> **同为** `"loop"` ⇒ 检索命中即被当「相关事实」**注入 prompt**，而信息**已由**同轮轨迹 +（失败时）失败摘要
> 承载 ⇒ 同一份材料在两个面各出现一次、其中一次是**噪声**。
> **轴选**：三者 `source` **逐字相同** ⇒ 来源面（`exclude_fact_sources`，change `0185`）**天然不可分**
> （传 `("loop",)` 会连轨迹与失败摘要一起**过挡**）⇒ 区分判据只 `id` 前缀或 `tags`；取 **tags**
> （显式分类声明，且与 `memory._PRESERVE_TAGS` 同为标签面惯用法）。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-STEP-EXCLUDE-01 | context/spec.md「动态上下文构建」Scenario「原始步序素材不进事实面」 | 假 store 返 原始步序（`tags=["loop","steps"]`）/ 轨迹（`["loop","trajectory"]`）/ 失败摘要（`["loop","failure"]`）；`exclude_fact_tags=frozenset({"steps"})` ⇒ `build()` | `facts` 含 **轨迹 + 失败摘要**、**无**原始步序（锚点：`tests/test_context.py::test_fact_tag_exclusion_drops_step_entries`） |
| TC-STEP-EXCLUDE-02 | 同 Requirement（缺省逐字一致）—— **回归锚** | 同假 store；**不传** `exclude_fact_tags` ⇒ `build()` | 三条**全在**（顺序 `原始步序 / 轨迹 / 失败摘要`），与变更前**逐字一致**（锚点：`...::test_fact_tag_exclusion_default_is_verbatim`） |
| TC-STEP-EXCLUDE-03 | 同 Requirement（**交集**语义 / **非**前缀） | 三条目：`["loop","steps","extra"]` / `[]` / `["steps2"]`；`exclude_fact_tags=frozenset({"steps"})` | 只剩 `[]` 与 `["steps2"]` —— 多标签**任一**命中即挡、空标签不挡、`steps2` **不**被前缀误挡（锚点：`...::test_fact_tag_exclusion_is_intersection_based`） |
| TC-STEP-EXCLUDE-04 | 同 Requirement（排除**只**落注入步骤）—— **回归锚** | 真 `MemoryStore` 写 `tags=["loop","steps"]` 的 `loop.steps.t1` ⇒ `store.read("原始步序正文")` | 仍**取回**该条 —— **抽取器素材角色**不受影响（`read` 语义 / 排序 / 预算 / 复用强化逐字不变）（锚点：`...::test_step_sequence_stays_readable_through_memory_read`） |
| TC-STEP-EXCLUDE-05 | 组合根接线（三面并存、逐字不动） | `build_runtime(ConfigManager(yaml_path=…))` | 主 loop 装配器 `_exclude_fact_tags == frozenset({"steps"})` **且** `_exclude_fact_sources == ("compaction",)` **且** `_exclude_source_prefixes == ("beast.", "pet")` 逐字不动（锚点：`...::test_build_runtime_excludes_steps_from_fact_face`） |

> **红态证据**：`test_fact_tag_exclusion_drops_step_entries` / `test_fact_tag_exclusion_is_intersection_based` /
> `test_build_runtime_excludes_steps_from_fact_face` **红**（`DynamicAssembler.__init__() got an unexpected
> keyword argument 'exclude_fact_tags'` 与 `AttributeError: _exclude_fact_tags`）。绿后全量
> `.venv/bin/pytest -q` ⇒ **2196 passed**（基线 **2191**，**+5** = 排除面 1 + 缺省回归 1 + 交集语义 1
> + 检索语义回归 1 + 组合根接线 1）。
> **附带修复**：`0185` 的 `_fact_spy` 假条目补 `tags` 字段 —— 原 double 缺 `MemoryEntry` 的**必填**字段，
> 新过滤面使该缺漏**暴露**为 `AttributeError`；补全后双重**忠实**（非放宽生产代码）。
> **逐字兼容不变量**：`exclude_fact_tags` 缺省 `frozenset()` ⇒ 过滤子句恒假、装配结果与变更前**逐字相同**；
> 过滤落**读后** ⇒ `MemoryStore.read` 语义 / 排序 / 预算 / 复用强化**逐字不变**；`exclude_fact_sources`
> （`0185`）与封存元组 `("beast.","pet")`（`runtime.py`）**逐字不动**；`exclude_source_prefixes` /
> `allow_source_prefixes` 的检索侧语义**逐字不变**；无新配置键（排除面由组合根**硬接线**）、
> 无新第三方依赖、无 import 方向变化。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0177 行（**预算近似** —— 被挡条目已消耗配额、
> 不回收 / **标签是自律声明**、无强制门禁（别的条目打 `steps` 标签会被顺带挡掉）/ **不处理 notes 侧**
> 同源对账 / `key_fact` vs 笔记结论记为**设计上非重复**、不引入跨模块匹配）。

## 100. 复用强化落盘（TC-REUSE-PERSIST，change `0187`／ADR-0178，台账 E124）

> **背景取证**：`read()` 命中条目时 `entry.reuse_count += 1`，原注释自陈「复用即强化（**进程内强化，
> 不落盘避免写放大**）」；但 `FileBackend.search`（`backend.py:45-62`）返回的是 `self._entries.values()`
> 的**同一批对象引用**（非副本）⇒ 那行自增**就地改了后端内存对象**、只是**没有** `_persist()`。后果：
> 同进程内 `audit()`（走 `_backend.search("")`）**能**看到新值（故既有
> `test_read_reinforces_reuse_count` 一直绿），**磁盘 JSONL 却始终是旧值** ⇒ 进程结束即丢。而该计数
> **不止**用于当场排序：`_decay_score`（`store.py:105-115`）以
> `freshness ** (1 / (1 + log1p(reuse_count)))` 调制遗忘曲线 ⇒ 跨会话强化全丢、**最该留的先被归档**。
> **判据错位**：旧判据选在**进程内可见性**上，契约要的是**跨会话持久性** —— 「测试绿、语义错」的典型。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-REUSE-PERSIST-01 | memory/spec.md「温度分层检索」Scenario「复用强化跨会话持久」 | `FileBackend(tmp_path/"mem.jsonl")` 写 `e1` ⇒ `read("hello")` ⇒ 以 **同一 path 的新 `FileBackend`** 新建 `MemoryStore`（模拟进程重启） | 新 store `audit()[0].reuse_count == 1` —— 强化**落盘**、**非**退回 0（锚点：`tests/test_memory.py::test_reuse_reinforcement_survives_reload`） |
| TC-REUSE-PERSIST-02 | 同 Requirement（**未命中不写**）—— **回归锚** | 计数 `put` 的 `_PutCountingBackend`（纯内存）+ 空 store ⇒ `read("什么都没有", budget=100)` | 返回 `[]`、`backend.puts == []`、全局 `rollback().reverted == []` —— 强化**只**发生在命中路径上（锚点：`...::test_read_without_hit_records_no_write`） |
| TC-REUSE-PERSIST-03 | 同 Requirement（写回**可撤销**、undo **还原原值**） | `read("hello")` ×2（`reuse_count` = 2）⇒ `tracker.rollback("reuse.e1")` | `undo_failed == []`；后端 `reuse_count` 回到 **0**，且**重新装载的磁盘文件**亦为 0 —— 还原**同样落盘**（锚点：`...::test_reuse_writeback_is_reversible`） |
| TC-REUSE-PERSIST-04 | 同 Requirement（写放大**有界**：只写**选中**） | 两条各 `"alpha " * 50`（75 token）的候选 + `budget=60` ⇒ `read("alpha beta")` | 恰 1 条被选中；**选中**者 `reuse_count == 1` 且 `audit("reuse.<chosen>")` 长 1；**落选**者 `reuse_count == 0`、`audit("reuse.<other>") == []`（锚点：`...::test_only_selected_entries_are_reinforced`） |

> **红态证据**：`test_reuse_reinforcement_survives_reload`（新 store 读到 `reuse_count == 0`）、
> `test_reuse_writeback_is_reversible`（`rollback("reuse.e1")` 无效应可撤 ⇒ 后端仍为 2）、
> `test_only_selected_entries_are_reinforced`（落选者同样被强化）**红**；
> `test_read_without_hit_records_no_write` 自然绿（空 store 本就不进强化路径 —— 作为**回归锚**保留）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2200 passed**（基线 **2196**，**+4** = 跨会话保持 1 + 未命中不写 1 +
> 可回滚 1 + 有界 1）。既有 `test_read_reinforces_reuse_count` **继续绿**（回归锚：强化语义本身未变）。
> **逐字兼容不变量**：排序 / 预算 / 会话过滤 / 来源排除面语义**逐字不变**（只在末尾多一次落盘）；
> 非选中候选**不**写、**不**强化（原语义）；`summary_for` / `mid_summary_for`（**不同**只读取数面、
> 不经 `read()`）的「零写入 / 零效应」契约**逐字不动**（既有测试继续守护）；**不**把读条目插入 `_hot`
> （不引入隐式缓存）；无新配置键、无新第三方依赖、无 import 方向变化。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0178 行（**写放大仍在** —— 每次命中都对每个选中
> 条目**整文件重写**、有意不加节流 / **还原面是值不是事件** —— 并发交错下可能落在中间值、不引入锁 /
> **不改 `_hot` 的既有填充面**）。

## 101. 记忆面 → 诊断面桥（TC-FAIL-LOOKUP，change `0188`／ADR-0179，台账 E125）

> **背景取证**：轮级失败已由 `loop` 另立为 L2 条目 `loop.failure.<trace_id>`
> （`default.py:833-846`，`tags=["loop","failure"]`，正文 `failure_digest(...)`），但
> `Diagnoser.diagnose(traces, prior)`（`diagnoser.py`）只看 `Trace.success` / `plugin_id`，且
> `src/core/evolution/` 对 memory **只写不读** ⇒ 已沉淀的失败叙述**不驱动进化**（ADR-0170 局限②）。
> **接法**：依赖倒置注入查询接缝（`Callable`，**非** import）；组合根闭包走
> `MemoryBackend.search("")`（**不**经 `MemoryStore.read`）⇒ **零写入零效应**、按 id 精确、层无关。

| 用例 | 规格锚点 | 输入 / 操作 | 期望（锚点） |
|---|---|---|---|
| TC-FAIL-LOOKUP-01 | evolution/spec.md「对比诊断」（新增字段缺省）—— **回归锚** | `DiagnosisReport(target_plugin=None, issue="x")` vs 显式带 `failure_notes=[]` | 两者**相等** —— 新字段缺省不破既有构造 / 相等语义（锚点：`tests/test_evolution_attribution.py::test_diagnosis_report_new_field_defaults_to_empty`） |
| TC-FAIL-LOOKUP-02 | 同 Requirement（**未接线逐字一致**）—— **回归锚** | `Diagnoser().diagnose([失败 trace(plugin=loop.default)])` | `failure_notes == []` 且 `target_plugin` / `confidence` / `issue` / `evidence` 逐字不变（锚点：`...::test_diagnoser_without_lookup_leaves_failure_notes_empty`） |
| TC-FAIL-LOOKUP-03 | Scenario「已沉淀失败摘要并入诊断报告」 | 接线 lookup（spy 记录入参），输入 1 失败 + 1 成功 trace | `failure_notes == [摘要]`；spy **只见失败** trace 的 id（成功 trace 不查）；`target_plugin` 不变（锚点：`...::test_diagnoser_attaches_sedimented_failure_notes`） |
| TC-FAIL-LOOKUP-04 | 同 Requirement（**fail-open**） | lookup 抛 `RuntimeError` | `failure_notes == []`，而 `target_plugin` / `confidence` 与未接线**一致** —— 查询失败不牵连判定（锚点：`...::test_diagnoser_lookup_error_degrades_silently`） |
| TC-FAIL-LOOKUP-05 | 同 Requirement（**有界**） | lookup 恒返 500 字摘要；输入 5 条失败 trace | `len(failure_notes) == 3`（总数封顶）且每条 `len == 400`（单条截断）（锚点：`...::test_diagnoser_failure_notes_are_bounded`） |
| TC-FAIL-LOOKUP-06 | 组合根接线（端到端，离线） | `build_runtime(ConfigManager(yaml_path=…))` + `runtime.memory.write("L2", MemoryEntry(id="loop.failure.T1", …))` ⇒ 取 `runtime.evolution.engine._diagnoser` | 接缝**非 None**；`lookup("T1")` 返回该正文、`lookup("未沉淀")` 返回 `None`；`diagnose([失败 trace T1])` 报告 `failure_notes == [正文]` **且** `target_plugin == "loop.default"`（锚点：`tests/test_evolution_wiring.py::test_composition_root_wires_failure_lookup`） |

> **红态证据**：5 条单元用例 **红**（`Diagnoser.__init__() got an unexpected keyword argument
> 'failure_lookup'` 与 `DiagnosisReport` 无 `failure_notes` 字段）。绿后全量 `.venv/bin/pytest -q` ⇒
> **2206 passed**（基线 **2200**，**+6** = 回归锚 2 + 并入 1 + fail-open 1 + 有界 1 + 组合根接线 1）。
> **逐字兼容不变量**：未接线 ⇒ `failure_notes` 恒空、报告与既往**逐字一致**；`target_plugin` /
> `confidence` / `evidence` / `issue` 的判定**逐字不变**（桥只增补字段）；查询抛错 ⇒ 降级不中断；
> 只查**失败** trace；组合根 lookup 走 `search("")` ⇒ **零写入零效应**（不强化 `reuse_count`、
> 不落盘 —— 与 change `0187` 的有副作用读取面**划清**）；`evolution` 不新增 import 方向，
> `memory` / `context` / `loop` 零改动；无新依赖、无新配置键。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0179 行（**摘要未进候选载荷** / **归因算法未用摘要** /
> **只覆盖 `Diagnoser` 通道**（显式目标路径不构造它）/ **按 id 约定耦合**、无单一真源常量守护）。

## 102. 三面边界**另一侧**门禁（TC-BOUNDARY，change `0189`／ADR-0148 附，台账 E126）

**行为规格锚点**：**无**（规格中性，`.openspec.yaml` `skip_specs: true`）—— 本 change 只加**结构门禁**，
**零 `src/` 改动**。守护对象是 ADR-0148「已知局限」②（`memory` / `notes` 越界「兼做知识文档检索」无门禁）
与③（门槛靠人守）。

| 用例 | 锚点 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-BOUNDARY-01 | ADR-0148 决策② 守护**链成员** | 读 `_CORPUS_FREE_FACES` 与 `_REFERENCE_CHAIN` 两个模块常量 | `{"memory","notes"} ⊆ {"loop","context","memory","notes"}` —— 摘掉一个面即红（锚点：`tests/test_architecture.py::test_rag_guard_chain_covers_corpus_free_faces`） |
| TC-BOUNDARY-02 | ADR-0148 局限②（**当前即绿**） | `ast` 走查 `src/core/memory` ＋ `src/core/notes` 全部 `*.py` 的**公开面**（公开函数 / 方法 / 类名 ＋ 形参名），词元化后与语料词表求交 | 走查**非空**（防空过）**且**零命中（锚点：`...::test_memory_notes_api_excludes_document_corpus_dimension`） |
| TC-BOUNDARY-03 | 同前（**红态证据**，人工植入、不保留） | 向 `src/core/notes/store.py` 临时追加公开函数 `ingest_document(path: str, chunks: list[str])` | 门禁**变红**且**指名** `notes/store.py:<行> ingest_document -> ['document','ingest']` 与 `chunks -> ['chunks']`；`git checkout` 撤销后回绿 |
| TC-RAG-14（**回归锚**） | ADR-0148 决策② | `chain` 由局部字面量改为常量 `_REFERENCE_CHAIN` 后重跑既有守护 | 断言**逐字不变**、仍绿 —— 本 change 未放宽 rag 侧（锚点：`...::test_rag_not_imported_by_reference_chain`） |

> **红态证据**：TC-BOUNDARY-01/02 现状**绿**（规格中性 ⇒ 沿 change `0156` 先例，红态由**人工植入**
> `loop`/`notes` 侧的越界签名确认，见 TC-BOUNDARY-03；植入已撤销，`src/` 最终**零改动**）。绿后全量
> `.venv/bin/pytest -q` ⇒ **2208 passed**（基线 **2206**，**+2** = 链成员 1 ＋ 语料维度 1）。
> **不动面**：`test_rag_not_imported_by_reference_chain`（断言逐字不变）、
> `test_session_isolation.py::test_notes_api_has_no_session_dimension`（**已存在**的会话维度锚 ⇒
> **不重复**）、`memory` / `notes` / `context` / `loop` 的 `src/` 代码；无新依赖（stdlib `ast` / `re`）、
> 无新配置键。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0148 行（收窄后的 ②③：间接路径 / 非公开面不察；
> 门槛仍**靠人守 ＋ 最小绊线**），以及 ④「三面边界表是当前分工」逐字不变。

## 103. 检查点会话归因 + task 路径会话接线（TC-CKPT-SESSION，change `0190`／ADR-0180，台账 E127）

**行为规格锚点**：`orchestration/spec.md`「断点续跑」（检查点携带发起会话标识、SHALL NOT 写占位值）、
「任务入口与进度事件」bullet「任务入口会话归因」；`cli-ops/spec.md`「会话命令族与交互入口续聊」
（一次性任务入口铸会话入同一注册表）。

| 用例 | 锚点 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-CKPT-SESSION-01 | 断点续跑 Scenario「检查点携带发起会话标识」（fresh 非空） | 单子任务调度器以 `session_id="sess-A"` 跑 `astream`，记录 checkpoint / on_done 回调实参 | 两回调第 4 参均为 `"sess-A"`（锚点：`tests/test_orchestration.py::test_scheduler_checkpoint_callbacks_receive_session_id`） |
| TC-CKPT-SESSION-02 | 同前（缺省空串） | 同上但不传 `session_id` | 回调收到 `""`（未归属照实记录；锚点：`...::test_scheduler_checkpoint_callbacks_default_session_empty`） |
| TC-CKPT-SESSION-03 | 组合根写真值 | `build_runtime` 后 `orchestrator._checkpoint("task-s", [], plan, "sess-real")` | 检查点 `session_id == "sess-real"`（非占位 `"default"`；锚点：`tests/test_phase15.py::test_runtime_checkpoint_carries_initiating_session`） |
| TC-CKPT-SESSION-04 | cli-ops Scenario「一次性任务入口铸会话入同一注册表」 | 桩注册表 + 桩编排器跑 `task <目标>`（无 `--resume`） | 注册表 `create` 收 mode `cli`、`astream` 收到该会话标识（锚点：`tests/test_entry.py::test_task_fresh_mints_session`） |
| TC-CKPT-SESSION-05 | orchestration Scenario「CLI 续跑复用检查点会话」 | 检查点 `session_id="orig-sess"` 跑 `task --resume t1` | `astream` 收 `"orig-sess"` 且**不**再铸会话（锚点：`...::test_task_resume_reuses_checkpoint_session`） |
| TC-CKPT-SESSION-06 | 同前（旧占位值归一） | 检查点 `session_id="default"` 跑 `task --resume` | `astream` 收 `""`（未归属，行为与既往逐字一致）+ stderr 提示「未携带会话标识」（锚点：`...::test_task_resume_legacy_default_session_unattributed`） |

> **红态证据**：TC-CKPT-SESSION-01/02/03/04/05 在签名扩参前**红**（回调只收 3 参 / 检查点写死
> `"default"` / CLI 不传会话）；TC-CKPT-SESSION-06 在实现前红（无提示行）。既有替身
> （`test_orchestration.py` lambda / `test_phase14.py` checkpoint / `test_phase15.py` on_done）补第 4 参、
> 既有 resume 用例补 `session_id` 元数据后断言不变量不变。绿后全量 `.venv/bin/pytest -q` ⇒
> **2214 passed**（基线 **2208**，**+6** = 回调 2 ＋ 组合根 1 ＋ CLI 入口 3）。
> **不动面**：REPL `/task` 与 Web 任务入口（本就传会话，自动获益零改动）；`durability` 存储层
> （`Checkpoint.session_id` 既有字段）；`--resume` 「最新检查点」取法（文件序，ts 序对齐归 change `0191`）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0180 行（无 `--session` flag / `"default"` 归一
> 启发式 / 会话元数据无检索面 / 跨进程 undo 承 ADR-0136）。

## 104. 恢复呈现接线（TC-RECOVERY-SURFACE，change `0191`／ADR-0181，台账 E128）

**行为规格锚点**：`durability/spec.md`「崩溃恢复」（纯扫描语义、降级跳过、句柄标识任务）；`cli-ops/spec.md`
「会话命令族与交互入口续聊」（入口启动呈现、`--resume` 取 ts 最新）。

| 用例 | 锚点 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-RECOVERY-SURFACE-01 | durability Scenario「启动扫描呈现未完成任务」（句柄标识任务） | `build_runtime` 后建 `todo-task` 检查点（`done=False`）跑 `runtime.recover()` | 句柄的 `task_id == "todo-task"`；`done=False` 未完成任务返回、`done=True` 不返回（锚点：`tests/test_phase15.py::test_runtime_recover_restores_incomplete_skips_done`） |
| TC-RECOVERY-SURFACE-02 | durability Scenario「不可恢复任务不阻塞整体扫描」 | 一任务检查点全部 corrupt + 一任务有效，跑 `_recover_incomplete` | 坏任务跳过 + `UserWarning`，有效任务句柄照常返回（`[h.task_id] == ["good-task"]`；锚点：`tests/test_phase15.py::test_runtime_recover_skips_unrestorable_task`） |
| TC-RECOVERY-SURFACE-03 | 句柄标识所属任务（跨进程） | 真进程 `SIGKILL` 后另一进程 `restore("task1")` | 句柄 `task_id == "task1"`（锚点：`tests/test_durability_crash.py::test_real_sigkill_then_restore_and_resume`） |
| TC-RECOVERY-SURFACE-04 | cli-ops Scenario「入口启动呈现未完成任务」 | 桩 runtime（`recover` 返回 2 个句柄）跑 `task <新目标>` | stderr 打印「2 个未完成任务」+ `task --resume <id>`；`astream` **只**跑本次任务（不自动重执行）（锚点：`tests/test_entry.py::test_task_surfaces_incomplete_tasks`） |
| TC-RECOVERY-SURFACE-05 | 同前（空库静默） | 桩 runtime（`recover` 返回空）跑 `task` | stderr **无**「未完成任务」（锚点：`...::test_task_no_incomplete_is_silent`） |
| TC-RECOVERY-SURFACE-06 | cli-ops Scenario「续跑取时间戳最新检查点」 | `task --resume t1`：两检查点落盘序 ≠ 时间序（`cps[-1]` 为旧、`ts` 为早） | 取 `ts` 最新检查点重建目标（`astream` 收新 plan 的目标）（锚点：`...::test_task_resume_latest_by_ts`） |
| TC-RECOVERY-SURFACE-07 | cli-ops Scenario「入口启动呈现未完成任务」（serve） | 真 runtime + 落盘 `stale-task` 检查点跑 `serve`（桩 WebBridge） | stderr 打印「未完成任务」+ `task --resume stale-task`（锚点：`...::test_serve_surfaces_incomplete_tasks`） |

> **红态证据**：TC-RECOVERY-SURFACE-01/02/03 在 `RestoreHandle` 加字段 / try-except 前**红**
> （无 `task_id` / 坏任务抛 `DurabilityError` 中断整轮扫描）；04/06/07 在入口接线与 ts 序前**红**
> （无呈现行 / 取到旧检查点）。绿后全量 `.venv/bin/pytest -q` ⇒ **2219 passed**（基线 **2214**，
> **+5 新增** = 坏任务跳过 1 ＋ 入口呈现 4；另 3 处既有用例补 `task_id` 断言）。
> **不动面**：`resume()` 语义（无 replay = 纯扫描，现状诚实保留）；`scheduler`；`repl`/`app`/`run`
> 入口（不传 `surface_recovery` ⇒ 输出面逐字不变）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0181 行（呈现为提示非托管 / 无独立只读命令 /
> 扫描全量无索引 / `RestoreHandle` 破坏性变更 / 跨进程 undo 承 ADR-0136）。

## 105. 轮内压实会话化 + trace 会话键（TC-COMPACT-SCOPE，change `0192`／ADR-0182，台账 E129）

**行为规格锚点**：`loop/spec.md`「执行循环」（轮内压实的记忆固化步骤按本轮会话收窄）；`memory/spec.md`
「记忆压实」（空串全量语义保留给显式调用、循环内路径一律会话化）；`context/spec.md`「上下文自动压实」
（产物 `trace_id` 携带会话键）。

| 用例 | 锚点 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-COMPACT-SCOPE-01 | loop Scenario「轮内压实按会话收窄聚合」 | 会话 `s1`/`s2` 各一条 L2 episodic 条目，`loop.run("hi", session_id="s1")` 触发压实 | `s1` 条目迁 L4（被聚合归档）、`s2` 条目仍 L2（SHALL NOT 顺手聚合；变更前为跨会话串扰）（锚点：`tests/test_loop.py::test_loop_compaction_scopes_memory_to_round_session`） |
| TC-COMPACT-SCOPE-02 | context Scenario「压实产物 trace 携带会话键」 | `loop.run("hi", session_id="s1")` 触发压实 | 产物条目 `trace_id == "compaction.s1"`（非常量 `"compaction"`）（锚点：`...::test_loop_compaction_persist_trace_is_session_keyed`） |
| TC-COMPACT-SCOPE-03 | context Scenario「压实产物 trace 携带会话键」（单元） | `Compactor.persist(c, session_id="")` 与 `session_id="s7"` | `compaction.fact.default.0.trace_id == "compaction.default"`、`compaction.fact.s7.0.trace_id == "compaction.s7"`（锚点：`tests/test_context_compaction.py::test_persist_trace_is_session_keyed`） |
| TC-COMPACT-SCOPE-04 | 诚实化文案 | 读 `Compactor.compact.__doc__` / `DefaultLoop._compact.__doc__` | 不含「从多轮历史」、含「本轮」（`...::test_compaction_docstrings_state_round_scope`） |

> **红态证据**：01/02 在 `_compact` 传 `session_id` / persist trace 会话键化前**红**（他会话条目被顺手归档；
> trace 为常量 `"compaction"`）；03 在 trace 键化前**红**（均为 `"compaction"`）；04 在 docstring 诚实化前**红**
> （含「从多轮历史」）。绿后全量 `.venv/bin/pytest -q` ⇒ **2223 passed**（基线 **2219**，**+4 新增**）。
> **不动面**：`MemoryStore.compact` 的空串全量**实现**（逐字保留）；`_maintain`（本已会话化）；
> `summarize_slice` / `_summarize_sessions` / 关键事实抽取（trace 早已会话键化）；空会话轮行为逐字不变
> （`compact(session_id="")` ≡ 裸调）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0182 行（provenance 死面只注记不活化 / 空会话轮仍全量 /
> `_maintain` 多会话公平性承 ADR-0169⑦）。

## 106. 滚动摘要首尾保留 + 价值闸留痕（TC-SUMMARY-TAIL，change `0193`／ADR-0183，台账 E130）

**行为规格锚点**：`memory/spec.md`「记忆压实」（既有摘要投喂节选**首尾保留**、越界判据读全体长度；
价值门控跳过**留痕**且只报会话键）。

| 用例 | 锚点 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-SUMMARY-TAIL-01 | memory Scenario「摘要越界首尾保留（尾部不销毁）」 | 既有摘要 `首部结论：` + `早`×2200（> `MAX_SUMMARY_CHARS`）⇒ `build_prompt` | 「现有摘要」槽含**尾部**「早」串末段 ＋ 中略标记「⋯（中略 N 字）」；节选总长 ≤ `MAX_SUMMARY_CHARS`（锚点：`tests/test_memory.py::test_build_prompt_preserves_summary_tail_when_over_bound`） |
| TC-SUMMARY-TAIL-02 | memory Scenario「摘要越界首尾保留」 | 既有摘要 ≤ 上界 | 槽内**逐字**全文（与变更前一致，兼容性红线；`...::test_build_prompt_keeps_summary_verbatim_below_bound`） |
| TC-SUMMARY-TAIL-03 | 上界不破（token 有界） | 既有摘要 = `长`×(上界×10) ⇒ `build_prompt` | 槽长仍 ≤ `MAX_SUMMARY_CHARS`（`_elide_summary` 三段相加恰为上界；`...::test_build_prompt_slot_stays_bounded_for_huge_summary`） |
| TC-SUMMARY-TAIL-04 | memory Scenario「价值门控跳过留痕（只报会话键）」 | 低价值会话 `s-lo`（正文含「绝密正文」）越过价值闸 ⇒ 压实 | `warnings.warn(RuntimeWarning)` 触发；告警文本含会话键 `s-lo`、**不含**「绝密正文」（密钥红线）（`...::test_compaction_warns_when_skipping_low_value_session`） |

> **红态证据**：01/03 在 `_elide_summary` 落地前**红**（纯头截断 ⇒ 槽内无尾段）；04 在补 `warnings.warn`
> 前**红**（静默跳过、无告警）。02 为**兼容性回归锚**（变更前后同绿，证明未越界路径逐字未动）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2227 passed**（基线 **2223**，**+4 新增**）。
> **触发语义不动面**：`_deliver_promotion` 的越界判据读 `len(prior.content)`（**全体长度**）不读节选 ⇒
> 首尾保留**不触碰**提升触发，由既有 `test_memory_summary_promotion.py::test_summary_crossing_bound_delivers_promotion_once`
> 回归作证（触发路径零改动，故不另写重复用例）。
> **不动面**：`MAX_SUMMARY_CHARS` 值 / `_commit_summary`（canonical 仍落全文、不截断）/ `summarize_slice`
> （mid 层 `max_chars` 预截断）/ 价值闸**判据与结果**（仅补留痕）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0183 行（中略区仍不可逆丢失 / `omitted` 为人类可读提示
> 非契约 / mid 无提升通道显式不做 / 留痕每轮每会话一条属噪音）。

## 107. 摘要注入与历史回放解耦（TC-SUMMARY-DECOUPLE，change `0194`／ADR-0184，台账 E131）

**行为规格锚点**：`loop/spec.md`「执行循环」（两层摘要注入与历史回放开关**解耦**；关原文回放仍注入摘要）。

| 用例 | 锚点 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-SUMMARY-DECOUPLE-01 | loop Scenario「关闭历史回放仍注入摘要」 | 会话 `s1` 有长期 + 中期摘要，`history_turns=0`（关原文回放）⇒ `perceive` | `ctx.summary_long == "长期要点"`、`ctx.summary_mid == "中期要点"`（摘要**照常注入**）且 `ctx.history == []`（历史带为空）（锚点：`tests/test_history_replay.py::test_summaries_injected_when_history_replay_disabled`） |
| TC-SUMMARY-DECOUPLE-02 | 兼容性红线（缺省逐字不变） | 会话 `s1` 有摘要、`history_turns` 缺省（`20`）⇒ `astream` | system prompt 含两摘要块**且**历史原文「第一问 / 第一答」照常回灌（`...::test_history_replay_default_still_unchanged_after_decoupling`） |
| TC-SUMMARY-DECOUPLE-03 | 本职门控仍守 | 空标识（`sid=""`）/ 未注入转录（`with_transcript=False`）⇒ `astream` | 摘要与历史均不读不注入（`("", "", [])`）（`...::test_summaries_gated_on_session_and_transcript`，参数 2 组） |
| TC-SUMMARY-DECOUPLE-04 | 诚实化文案 | 读 `DefaultLoop._load_summaries.__doc__` | **不含**「完全同形」（假注释）、**含**「解耦」（`...::test_load_summaries_docstring_states_decoupling`） |

> **红态证据**：01 在门控删 `history_turns <= 0` 前**红**（`_load_summaries` 返回 `("", "")` ⇒ 摘要被静默丢弃）；
> 04 在 docstring 诚实化前**红**（含「完全同形」）。02 为**兼容性回归锚**（变更前后同绿）。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2229 passed**（基线 **2227**，**净 +2** = 3 新增 − 1 参数拆分）。
> **错锚订正**：既有 `test_summaries_gated_like_history` 的 `(0, "s1", True)` 参数组**把缺陷固化为断言**
> （「关回放 ⇒ 摘要亦不注入」）—— 与规格 Scenario「分层摘要作为独立系统块注入」（**不带** `history_turns`
> 条件）相悖 ⇒ 拆为 `test_summaries_gated_on_session_and_transcript`（留 2 组本职门控）+
> `test_summaries_injected_when_history_replay_disabled`（新行为锚）。
> **不动面**：`_load_history`（仍用 `plan.short_turns <= 0`）/ `_window_plan` / `plan_window`（短 0.5 /
> 中 0.3 / 长 0.2 配额）/ 预算记账 / `tiered` 判据 **零改动**；缺省（`history_turns=20 > 0`）行为逐字不变。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0184 行（摘要读取仍要求转录已注入 / 纯摘要配置下
> 摘要 token 仍计预算 / 未动滑窗配额）。

## 108. 长任务端到端门禁（TC-LONGTASK-E2E，change `0195`／ADR-0185，台账 E132，**规格中性**）

**行为规格锚点**：无 spec delta（`.openspec.yaml` `skip_specs: true`）—— 本 change **零 `src/` 改动**、
**零行为改动**，只把此前**两端分离**的链路接成端到端锚。锚点的**行为语义**分别归属：
`loop/spec.md`（压实 → 注入链、解耦）、`memory/spec.md`（越界首尾保留）。

| 用例 | 锚点归属 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-LONGTASK-E2E-01 | `loop` 压实 + 三层滑窗 | 真 `DefaultLoop` + `MemoryStore`（假摘要器）+ `TranscriptStore`；turn1（`token_budget=1` 触发轮内压实）产 `compaction.summary.s1` ⇒ turn2 复用同一 loop | turn2 装配后 system prompt 含 `历史摘要（长期）：` **且**含 turn1 压实产物字串「上一轮：季度结论 已完成」（防空过；锚点：`tests/test_longtask_e2e.py::test_compaction_product_reaches_next_turn_system_prompt`） |
| TC-LONGTASK-E2E-02 | `memory` 越界首尾保留（`0193`） | 既有摘要 > `MAX_SUMMARY_CHARS`（尾部含锚点字串），假摘要器内捕获 `build_prompt(entries)` | 投喂**摘要器**的既有摘要槽含尾部锚点 `最新结论：尾部保真锚点XYZ` **且**含中略标记 `⋯（中略`（`...::test_over_bound_summary_tail_reaches_compaction_prompt`） |
| TC-LONGTASK-E2E-03 | `loop` 解耦（`0194`） | 会话有既有摘要 + `history_turns=0`（关原文回放）⇒ `astream` | 装配后 system prompt 含 `历史摘要（长期）：` + 摘要正文；且 `messages[1:] == ["新一轮"]`（历史原文**不回灌**）（`...::test_summary_injected_into_prompt_when_history_replay_disabled`） |

> **锚点订正证据（本 change 的独有价值）**：初版 TC-LONGTASK-E2E-02 把锚点放在**循环注入的 system prompt**，
> 实测**失败** —— `_elide_summary` 约束的是**摘要器 prompt**（压实**输入**），循环注入的既有摘要是**逐字**的。
> ⇒ 锚点移正。**若不做 e2e，此误解不会被发现**。
> **反证（门禁非空过）**：①`_compact` 的 `memory.compact` → `pass` ⇒ 01 红；②`_elide_summary` 改回纯头
> 截断 ⇒ 02 红；③`_load_summaries` 恢复 `history_turns <= 0` 闸 ⇒ 03 红；复原后全绿 ⇒ 三条锚**均能咬住**。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2232 passed**（基线 **2229**，**+3**）。`git diff --stat src/` **为空**。
> **不重复**：CLI `--resume` 会话端到端已由 `test_entry.py::test_task_resume_reuses_checkpoint_session`
> （change `0190`）承载 ⇒ 本文件不重写。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0185 行（不覆盖 CLI resume / 桩 provider 不模拟推理 /
> 轮内压实走预算维度 / 仅进程内）。

## 109. 任务完成回调卸载（TC-DONE-OFFLOAD，change `0196`／ADR-0186，台账 E133）

**行为规格锚点**：`orchestration/spec.md`「异步执行单元契约」**MODIFIED**（+「收尾回路不阻塞」bullet
+ Scenario「完成回调不阻塞事件循环」）；canonical `orchestration` scen **49 → 50**、req **11 不变**。

| 用例 | 锚点归属 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-DONE-OFFLOAD-01 | `orchestration` 异步执行单元契约 | 桩 `on_done` 记录 `threading.get_ident()`；`TaskScheduler` 跑一个成功任务（`asyncio.run`） | 回调**按 `DONE` 后一次**调用（`len(seen) == 1`），且执行线程 ident **≠** 主线程 ident（在工作线程执行；`tests/test_orchestration.py::test_scheduler_done_callback_runs_off_event_loop`） |
| TC-DONE-OFFLOAD-02 | 同上（非阻塞） | 回调在**工作线程**等一个事件，事件由**事件循环上的**协程轮询释放 | 回调未超时（`timed_out == [False]`）—— 若回调同步跑在事件循环上，循环被冻结、释放协程永不推进 ⇒ 超时转红（`...::test_scheduler_done_callback_does_not_block_event_loop`） |

> **反证（门禁非空过）**：变更前（`self._on_done(...)` 同步调用）两锚**均红** —— 01 的 ident 等于主线程、
> 02 的释放协程被冻结 ⇒ 超时。落地 `await asyncio.to_thread(...)` 后转绿 ⇒ 两锚**均能咬住**。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2234 passed**（基线 **2232**，**+2**）。
> **调用时机/次数/顺序/终态逐字不变**：仍在 `DONE` 达成后**一次**、`task_finished` 事件之前、检查点写入之后。
> **不做**：`_checkpoint`（`scheduler.py:261-262`）**不**卸载（判据是「是否承载模型调用」而非「是否同步」）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0186 行。

## 110. 任务级 SOP 过程输入（TC-TASK-SOP，change `0197`／ADR-0187，台账 E134）

**行为规格锚点**：`skills/spec.md`「SOP 提炼（skill extraction）」**MODIFIED**（+「任务级过程输入」
bullet（含**样本隔离**硬约束）+ Scenario「任务达阈值提炼为任务级 SOP」/「任务级与单轮样本不混组」）；
canonical `skills` scen **45 → 47**、req **10 不变**。`orchestration` 规格**零改动**。

| 用例 | 锚点归属 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-TASK-SOP-01 | `skills` SOP 提炼（任务级过程输入） | `SopExtractor(..., namespace="task")` 提交任务级样本至阈值 | 入库 `task_types` **前缀化**为 `task::…` 的组键（`tests/test_skills.py::test_sop_extract_namespace_prefixes_group_key`） |
| TC-TASK-SOP-02 | 同上（缺省逐字不变） | `namespace=""`（单轮路径）提交样本 | 组键**无**前缀、与变更前**逐字一致**（`...::test_sop_extract_namespace_default_keeps_group_key_verbatim`） |
| TC-TASK-SOP-03 | `skills` SOP 提炼（样本隔离） | 同库已有词法相近的单轮技能 + 任务级实例提交样本 | 任务级样本**不**复用单轮 `task_types`、二者**不混组**，产物 `skill_id` 与单轮产物**不同**（`...::test_sop_extract_task_namespace_isolates_from_per_turn_group`） |
| TC-TASK-SOP-04 | `runtime` 组合根（步序回读） | `_steps_lookup(backend)` 对已沉淀的 `loop.steps.<tid>` 条目按 id 取回 | 逐行返回步序；**无**该条目 ⇒ **空列表**（不伪造）（`tests/test_task_sop.py::test_steps_lookup_reads_loop_steps_by_id`） |
| TC-TASK-SOP-05 | 同上（**零效应**） | 同上查找前后读条目 `reuse_count` | 前后**皆 0** —— 走 `search` **不经** `read` ⇒ 不强化、不落盘（**守 P2**；`...::test_steps_lookup_is_zero_effect`） |
| TC-TASK-SOP-06 | `runtime` 组合根（聚合） | `compose_task_steps(plan, outcomes, lookup)`：乱序 outcomes + 一个无 `trace_id` 的子任务 | 输出依 `plan.order` 排列；无 trace 者**跳过不炸**（`...::test_compose_task_steps_follows_plan_order`） |
| TC-TASK-SOP-07 | 同上（token 有界） | 20 个子任务 × 单行 5000 字步序 | 单行截断至 `_MAX_TASK_STEP_CHARS`(400)；总长 ≤ `_MAX_TASK_STEPS_CHARS`(2000) 且**提前收敛**（不聚满全部子任务）（`...::test_compose_task_steps_bounded`） |

> **反证（门禁非空过）**：变更前（`SopExtractor` 无 `namespace` / 组键**不**前缀化）01 红（组键无 `task::`）；
> 变更前（`_group_key` 只前缀化最终键、无 `_same_namespace()`）03 红（单轮面词法命中任务级键 ⇒ **反向**
> 采纳带前缀键、样本混组）⇒ **只前缀化不够**这一误解由该锚暴露。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2241 passed**（基线 **2234**，**+7**）。
> **单轮路径零改动**：`namespace` 缺省 `""` ⇒ `_group_key` 缺省行为、`observe` 签名、per-turn 采集路径**逐字不变**。
> **不新增密钥暴露面**：新路径消费的 `loop.steps.<trace_id>` 条目在**写入时已** `redact_secrets`（`loop/default.py:830`）。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0187 行（续跑二次触发 / 只编排路径生效 / 门属 0198 等）。

## 111. SOP 自动质量门（TC-SOP-GATE，change `0198`／ADR-0188，台账 E135）

**行为规格锚点**：`skills/spec.md`「SOP 提炼（skill extraction）」**MODIFIED**（+「自动质量门」
bullet（缺省不启用 / 未过 ⇒ 不入库 + 清组 + 只报组键 / 判定故障 ⇒ fail-open / **不得引入人工确认**）
+ Scenario「质量门未过不入库」/「未注入质量门时发布行为不变」）；canonical `skills` scen
**47 → 49**、req **10 不变**。**judgment 规格零改动**（纯消费已规格化 `noul` 原语）。

| 用例 | 锚点归属 | 输入 / 操作 | 期望 |
|---|---|---|---|
| TC-SOP-GATE-01 | `skills` SOP 提炼（自动质量门） | `gate=lambda *_: False`，同组样本达阈值 ⇒ 提炼产出非空文本 | 技能库**不新增**技能；该组**清空**（下一条不立即提炼）；`warnings` 恰一条且**只含组键**、**不含**提炼正文（`tests/test_skills.py::test_sop_extract_quality_gate_rejects_group_cleared_and_key_only`） |
| TC-SOP-GATE-02 | 同上（放行） | `gate` 记录入参并返回 `True` | 照常以 `active` 入库；门拿到的正是（任务文本, 提炼正文）（`...::test_sop_extract_quality_gate_passing_publishes`） |
| TC-SOP-GATE-03 | 同上（缺省不变） | 未注入门（`gate=None`） | 发布路径**逐字一致**（`...::test_sop_extract_without_quality_gate_publishes_unchanged`） |
| TC-SOP-GATE-04 | 同上（**fail-open**） | `gate` 抛 `RuntimeError` | **放行** —— 判定故障不阻断发布、也不中断主流程（`...::test_sop_extract_quality_gate_failure_fails_open`） |
| TC-SOP-GATE-05 | `judgment` SOP 质量门（noul 消费） | 真 `DecisionRouter` + 桩 provider，noul 答案真 / 假 | 真 ⇒ 放行、假 ⇒ 拒；且载荷 `state={"task": …}`、`action={"kind":"publish_sop","sop": …}`（`tests/test_judgment.py::test_sop_gate_maps_noul_answer` / `...::test_sop_gate_rejects_when_noul_false`） |
| TC-SOP-GATE-06 | 同上（fail-open 边界） | 桩**路由层**：`decide` 抛异常 / 返回缺 `noul` 的答案 | 两者均 ⇒ **放行**（`...::test_sop_gate_fails_open_on_judgment_fault` / `...::test_sop_gate_fails_open_on_missing_answer`） |

> **反证（门禁非空过）**：变更前（`SopExtractor` 无 `gate` 参数）TC-SOP-GATE-01/04 红（拒绝无从表达）；
> 变更前（`SopGate` 无守卫）05/06 的 fail-open 两条红（异常冒泡 / `KeyError` 冒泡）。
> **实测订正**：初版 05/06 走「provider 抛错」路径 ⇒ **转红** —— `DecisionRouter` **不冒泡**异常而是
> **回退主 LLM**（桩回退返回空串 ⇒ `_parse_yes("")` = `False` ⇒ 门**拒**）⇒ 用例改桩**路由层**，
> 并把该边界写入 ADR-0188 决策③（**门只看路由层之外的故障**）。**若不做该用例，此误解不会被发现**。
> 绿后全量 `.venv/bin/pytest -q` ⇒ **2249 passed**（基线 **2241**，**+8**）。
> **红线守持**：判定为**自动**（judgment noul），**无人工确认**；留痕**只报组键、绝不回显正文**。
> **已知局限**：见 `coding-plan/known-risk.md` §3 ADR-0188 行（拒即丢批 / 只挂任务级 / 路由降级算有结论等）。
