# Phase 13 — 系统级接线（Runtime 组合根 + 全链路装配）

> 里程碑：**M9 系统级闭环（单 Agent 真闭环）**
> 位置：跨层装配（组合根 `runtime.py`）+ 热路径（loop × LLM × context × skills × tools × permission × constraints × observability × judgment）
> 上游：Phase 0–11 已落地 28 capability（含 judgment；mcp 传输层/安全 production 实现 deferred 于 Phase 12），模块层完成、缺系统级装配
> 后续：Phase 14–15 进化闭环（冷路径 + 长任务 + 验证门/评测/结晶），**与 M9 连排不可拆分**
> 对应 change：无新增 openspec change（既有 29 spec 的运行时装配；组合根若暴露 spec 缺口再补 delta）

---

## 1. 范围与定位

Phase 0–11 把 28 个 capability 逐个做成真实实现（非 stub；mcp 传输层/安全 production 实现 deferred 于 Phase 12）且均为 DI 友好构造，但**没有任何生产代码把它们装配成运行系统**：`DefaultLoop`/`LiteLLMProvider`/`MemoryStore`/`ToolProvider`/`ConfigManager`/`Tracer` 在生产代码（非测试）中零构造点，唯一构造点是 `ui/api.py` 的空默认实例；`DefaultLoop.reason()` 在 `planner=None` 时走 `_echo` 回显（**「无智能」是最大缺口**）；judgment/constraints/observability/permission/durability 均未注入。

本 Phase 补上架构总览 §5「运行时视图」那张装配图，并把 §4.1「单轮循环热路径」真正跑通，交付**第一个「有脑可跑」的单 Agent 闭环**。

**核心动作（三条铁律）**：

1. **组合根独立成 `runtime.py`**：新建 `src/core/runtime.py`，是唯一被允许 import 所有模块的地方（组合根反模式的标准例外），专职装配；`entry.py` 保持「解析 + 路由」薄壳，不内联装配逻辑。
2. **`loop.reason()` 接 LLM**：新建 `LLMPlanner`（context 装配 + skills + tool schemas → `LLMRequest` → `LLMProvider.completion` → 解析 `Action`），替换 `_echo`，是唯一需要新写的核心代码。
3. **judgment 接线本 Phase 一并收口**：把 `DecisionRouter`/`Compactor`/`Guardrail` 注入 loop/memory/permission 三决策点 seam，拆掉 Phase 11 的 `deferred` 标记；真实 JEV 是否启用由 `judgment.provider` 配置决定（未配 fallback 主 LLM 兜底，已配走 JEV）。

---

## 2. 契约红线（实证现状 vs 契约）

### 2.1 已就绪契约（无需重造）

| 契约 | 实证落点 |
|---|---|
| 29 capability spec（含 judgment 4 需求） | `openspec/specs/*/spec.md` 全部在，`openspec validate --specs` 29/29 全绿 |
| 29 接口（含 loop/context/skills/memory/tools/permission/observability/judgment） | `doc/03-interfaces/*.md` 全部在 |
| 架构 §4.1 热路径数据流 + §5 运行时视图 | `doc/01-architecture/architecture-overview.md` |
| 各模块真实实现 | `LiteLLMProvider`/`MemoryStore(FileBackend)`/`ToolProvider`/`Tracer`/`ContextEngine`/`SkillRegistry`/`PermissionGuard`/`DecisionRouter`/`DefaultLoop` 均已在 `src/core/*` |

### 2.2 契约缺口（本 Phase 补齐）

| 缺口 | 现状 | 补法 |
|---|---|---|
| 无组合根 | `src/core/runtime.py` 不存在 | 新建 `runtime.py`（ConfigManager.load → resolve key → 装配全量依赖） |
| loop 无 LLM planner | `reason()` 走 `_echo` | 新建 `src/core/loop/planner.py`（`LLMPlanner`） |
| loop 无 observability 注入 | `DefaultLoop` 无 `tracer` 参数 | 给 `DefaultLoop` 加 `tracer` 注入，每步发 `TraceEvent` |
| judgment 三决策点未接 | loop/memory/permission 无 `DecisionRouter`/`Compactor`/`Guardrail` 注入 | 三决策点 seam 注入 + fake 断言测试（拆 `deferred`） |
| entry 空装配 | `run/serve/repl` 走空 `UIAPILayer()` | `entry.py` 改用 `runtime` 装配 |

---

## 3. 验收口径（M9 系统级闭环）

- **组合根**：`runtime.py` 一次性装配 `ConfigManager → LiteLLMProvider → MemoryStore → ToolProvider → Tracer → PermissionGuard → DecisionRouter → ContextEngine → SkillRegistry → LLMPlanner → DefaultLoop`，各依赖非空、coeffect 解析通过。
- **真闭环**：`core-agent run --prompt "读 xxx"` 走完「perceive → ContextEngine.assemble → LLM reason → PermissionGuard.check → act(file_read) → EffectTracker.record → remember → MemoryStore.write → TraceEvent」真实链路，`reply` 来自 LLM 而非回显。
- **judgment 接线**：loop（choice）/ memory（score）/ permission（noul）三决策点经注入 `DecisionRouter`/`Compactor`/`Guardrail` 断言被调用；未配 `judgment.provider` 时 fallback 主 LLM 兜底。
- **密钥安全**：`resolve_secret(api_key_ref)` 仅取明文供 `LiteLLMProvider` 构造，绝不进日志/记忆/轨迹。

---

## 4. 首步任务（开工前）

1. **读接口原文**：`loop-interface.md` / `context-interface.md` / `skills-interface.md` / `memory-interface.md` / `tool-use-interface.md` / `permission-interface.md` / `observability-interface.md` / `llm-provider-interface.md` 的构造签名与调用面为唯一真源，不复述重造。
2. **核对 LLMProvider 构造面**：`LiteLLMProvider` / `LLMProviderRegistry` 如何由 `AppConfig`（provider/model/endpoint/api_key）构造；密钥经 `ConfigManager.resolve_secret` 注入，明文不落日志。
3. **定 LLMPlanner 边界**：`LLMPlanner(ctx, llm, context, skills, tools)` → `Action`；ReAct 式：context.assemble（信息地图 + 压实）→ skills 注入 → tool schemas → LLM completion → 解析 Action；解析失败走结构化错误码，不向模型抛裸异常。
4. **定 judgment 决策点 seam**：loop 决策点（`DecisionRouter.choose` 路由候选分支，可选快路径）/ memory 压实（`Compactor.score` 保留丢弃）/ permission 守卫（`Guardrail.check` 放行拦截）；三处均经 DI 注入，不内联 JEV 调用（对齐 beast/pet「抽象不锁选型」）。
5. **定 observability 接线**：`DefaultLoop` 加 `tracer` 注入，每步（loop_started / step_completed / loop_finished）发 `TraceEvent`，供 Phase 14 EvolutionWorker 消费；不另造观测真源。

---

## 5. 依赖与顺序

```
configuration(ConfigSpec) ─┐
llm_provider(LiteLLM) ─────┼─► runtime.py 组合根 ─► LLMPlanner ─► DefaultLoop（全量注入）
memory / tools / context ──┤                                      ├─ PermissionGuard(替 SafetyGate)
skills / observability ────┤                                      ├─ constraints middlewares
permission / judgment ─────┘                                      ├─ DecisionRouter 决策点
                                                                  └─ Tracer(每步 TraceEvent)
                                                                      └─► entry.py run/serve/repl 贯通
```

- **硬依赖**：Phase 0–11 全部 capability 已落地；本 Phase 零新增三方依赖（沿用 litellm + stdlib）。
- **顺序**：runtime.py 组合根 → LLMPlanner（loop.reason 接 LLM）→ 横切注入（PermissionGuard / constraints / observability / judgment）→ entry 贯通。
- **并行**：LLMPlanner 与组合根骨架可并行；judgment 三决策点 seam 依赖 loop/memory/permission 注入面就绪后收口。

---

## 6. 里程碑验收清单

- [x] `src/core/runtime.py` 组合根落地：装配全量依赖，各依赖非空、coeffect 解析通过
- [x] `src/core/loop/planner.py`（`LLMPlanner`）落地：context+skills+toolschema → LLM → Action，`reply` 来自 LLM
- [x] `DefaultLoop` 加 `tracer` 注入：每步发 `TraceEvent`（loop_started / step_completed / loop_finished）
- [x] `PermissionGuard` 替代 `SafetyGate` 默认：不可逆动作过审批门，被拒短路
- [ ] constraints middlewares 注入 loop：schema 校验 / 熔断中间件链按序执行（deferred：constraints.Middleware 为 ExecRequest/ExecResponse 形状，与 loop 中间件 Callable[[LoopContext,Action],Action|None] 不同，需适配层，随 Phase 14）
- [x] judgment 三决策点 DI 接线：loop（choice）/ memory（score）/ permission（noul）注入断言被调用；未配 provider fallback 兜底
- [x] `entry.py run` 改用 runtime 装配（`reply` 来自 LLM，走真闭环）；serve/repl 运行时装配 + 每会话独立 loop+memory+tools deferred
- [x] 密钥安全：api_key 经 resolve_secret 注入，绝不进日志/记忆/轨迹
- [x] 门禁四件套全绿：ruff check ✓ · ruff format --check ✓ · pyright 0 errors · pytest 全通过（含本 Phase 新增用例）
- [x] `tests/test_architecture.py` 增 runtime 依赖约束：runtime 是唯一允许 import 全部模块的地方，其余模块禁止反向依赖 runtime

---

## 7. 测试要点

- [x] 组合根：`runtime.py` 装配后各依赖非空；coeffect 缺失时拒绝启动（结构化错误）
- [x] LLMPlanner：fake LLM 返回既定 Action，断言 context/skills/toolschema 进了 `LLMRequest`；解析失败走错误码
- [x] 热路径：fake LLM + fake MemoryStore + fake ToolProvider + fake Tracer，断言「perceive→reason→act→remember→trace」全链路顺序与落点
- [x] PermissionGuard：不可逆动作 → 审批门；审批拒绝 → 短路（不执行工具）
- [x] observability：loop 每步 `TraceEvent` 被 `Tracer.record` 捕获（含 trace_id / ts / payload）
- [x] judgment 三决策点：loop/memory/permission 注入 fake `DecisionRouter`/`Compactor`/`Guardrail` 断言调用；未配 provider fallback 主 LLM
- [x] entry 贯通：`core-agent run --prompt` 走完真闭环（reply 来自 LLM）

---

## 8. 提交规范

- **一个 Phase 一个 commit**：runtime.py + LLMPlanner + loop tracer 注入 + 横切注入 + judgment 三决策点接线 + entry 贯通 + 架构测试 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase13): 系统级接线 runtime 组合根 + 热路径真闭环（M9）`
- 提交后更新 `README.md` §2 总览表 Phase 13 行状态列为「完成」。

---

## 9. 后续连排（Phase 14–15，不可拆分）

> **决策 3：Phase 14→15 必须连着排** —— 进化「真能自动改技能」依赖验证门/评测基建，只做 Phase 14（采集+提案 dry-run）不做 Phase 15（评测+结晶）会把进化做成「只能看不能落」。故二者合并为同一里程碑 **M10 进化闭环**，一次排期、连续交付。

| Phase | 内容 | 验收 |
|---|---|---|
| 14 冷路径 + 长任务 | `EvolutionWorker` 消费 `Tracer` 轨迹 → `Diagnoser` → `Proposer`；`Orchestrator` decompose → 派发多 `DefaultLoop` → `TaskHandoff` → checkpoint | 一段轨迹产出诊断+提案；多子任务跑通 |
| 15 验证门 + 结晶 | eval 基建（design-completeness-eval P2）+ `Validator`(review+运行时测试) + `Evaluator`(留出集) → `Crystallize` → `SkillRegistry`/`MemoryStore`；沙箱颗粒度（P1）+ HITL 协议（P3）+ `CrashRecovery`/`TimeTravel` 接 loop | 一个真实缺陷走完「诊断→提案→验证→结晶」全链路 |
