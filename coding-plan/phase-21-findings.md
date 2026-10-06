# phase-21 关键发现（审计工作底稿，供 Claude Code 参考）

> 本文件是 phase-21.md 的编写依据，含 4 个断裂点的精确代码证据。
> 工程路径：/home/harry/work/core-agent

## 4 个断裂点（精确行号 + 原文证据）

### 断裂 1：trace plugin_id 绑「tool 名」，非架构模块 id
- 证据：`src/core/evolution/worker.py:112` `plugin_id=tool or None`（`_to_traces` 内，`tool = str(payload.get("tool", ""))`）。
- 结论：trace 的 plugin_id 是**工具名**（如某 tool 名），与 13 个架构模块 id（`composition.engine` 等）两套命名空间**不交叉**。
- `src/core/observability/events.py:19`：`kind: str  # "model_io" | "tool_call" | "effect" | "metric"`——仅四种，**无「架构模块失败」遥测通道**。

### 断裂 2：Diagnoser(plugin_signals) 无来源
- 证据：`src/core/evolution/diagnoser.py:22` `def __init__(self, plugin_signals: dict[str, float] | None = None)`。
- 装配：`src/core/runtime.py:448` `diagnoser=Diagnoser()` **无参装配** → plugin_signals 恒 None。
- `src/core/plugin_registry/registry.py` 无质量信号接口：方法清单仅 register/load/unload/check/activate/deactivate/suspend/resume/compose/get/state/list_ids；`_generations`（register 时写 plugin.generation）**无读取/晋升方法暴露**。

### 断裂 3：Proposer(kind="skill") 静态绑定
- 证据：`src/core/evolution/proposer.py:21` `def __init__(self, *, kind: Literal["skill", "plugin"] = "skill")`。
- 装配：`src/core/runtime.py:449` `proposer=Proposer()` **无参** → kind 恒 "skill"。
- `proposer.py:33` `risk_level="high" if self._kind == "plugin" else "low"` → 恒 low。

### 断裂 4：_crystallize_plugin 只写 L3 记忆，不晋升 registry 世代
- 证据：`src/core/evolution/engine.py:259` `_crystallize_plugin`（crystallize 分支：`kind == "skill"` → `_crystallize_skill`，否则 `_crystallize_plugin`）。
- 行为：只写 L3 记忆（`layer="L3"`），**不晋升 registry 世代**；registry 无独立世代晋升方法。

## 13 个内部核心插件 plugin_id（进化应覆盖的模块集合）
1. composition.engine
2. composition.packager
3. composition.resolver
4. evolution.collector
5. evolution.diagnoser
6. evolution.engine
7. evolution.evaluator
8. evolution.proposer
9. evolution.validator
10. evolution.worker
11. im.gateway
12. loop.default
13. memory.store

## 红线（phase-18 §0 结论，phase-21 不得违反）
- 维度1（技能库/SOP）：全自动。
- 维度2（架构级）：HITL 人工审核，candidate `status="pending"` 必审，confirm 后才落库。
- JEV 优先、LLM 兜底决策。
- phase-21 只打通「归因到内部核心插件 + 产出 kind=plugin 候选进 pending 人工队列」，**不自动改架构代码**。

## 关键模型字段（src/core/evolution/models.py）
- `GenerationCandidate.kind: Literal["skill", "plugin"]`
- `GenerationCandidate.status: str = "pending"  # pending | confirmed | rejected`
- `GenerationCandidate.risk_level: Literal["low", "high"] = "low"`（plugin 应为 high）
- `Trace.plugin_id: str | None`（归因线索，当前绑 tool 名）

## 模板要求
- README L133-140 八段结构：范围定位 / 里程碑验收 / 依赖前置 / 首步任务 / 实现顺序 / 契约对齐 / 门禁验收 / 提交规范。
- 总览表（README L24-50）需追加 phase-21 行；状态列（L83-84）需追加 phase-21 状态。
