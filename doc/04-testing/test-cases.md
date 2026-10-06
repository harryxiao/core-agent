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
| TC-NOTE-18 | 同上 CLI 面 | 跨进程：一进程经 `NoteStore` 写 canonical（含 `observe_turn`），另一进程 `core-agent notes list` / `search <中文任务句>` / `show <id>`；`show` 不存在的 id | 三子命令都在**新进程**里从 canonical Markdown 读到内容（落盘为真源）；中文长句命中；缺失 id ⇒ `NOTE_NOT_FOUND` + 退出码 1（锚点：`tests/test_entry.py` notes 子命令用例 + change 0106 端到端冒烟） |
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

## 关联

- 测试计划：`doc/04-testing/test-plan.md`
- 需求：`doc/00-product/requirements.md`
- 规格：`doc/openspec/specs/*`
