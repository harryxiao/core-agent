# Phase 17.5 — 接线补丁（memory 召回注入 + pet/beast 运行时注入）

> 里程碑：**无独立里程碑**（Phase 17 的接线补丁；建议 Phase 18 开工前完成——否则 Phase 18「记忆固化自动化」建在半接通的召回链路上）
> 位置：补 Phase 17（编排打通 + 记忆语义化）+ Phase 8/10（pet/beast 子系统）
> 上游：Phase 17（subagent 池 / delegate / FileBackend 落盘 / 语义读写 / session 维度）已交付
> 配套：`phase-17.md`（原交付说明）、`doc/openspec/specs/{loop,memory,pet-mode,beast-mode}/spec.md`

---

## 1. 范围与定位

Phase 17 把**写入侧**做完了（落盘 / 分层 / 预算 / 降级 / 并发 / 中文二元检索 / `remember` 语义正文），但**召回注入侧只接了半条**；pet/beast 子系统「已定义、可单测、**未接线**」。本 Phase 是**接线补丁**：不加新 capability，只把已有零件接到运行时。

1. **memory 召回链路接合**（Gap A/B）：让按**当前任务**检索到的记忆真正进 system prompt，且检索 query 用任务而非阶段名。
2. **pet 运行时注入**：注入 loop/memory/explorer/safety/notifier + 跨进程存活 + wake 触发。
3. **beast 运行时注入**：注入 router(handoff) + 20 神通进 SkillLibrary + 会话 loop/memory。

> **不在范围**：subagent（Phase 17 已打通，无已知缺口，见 §3.4）。

---

## 2. 缺口清单（实证，行号以当前 HEAD 为准）

### 2.1 memory — 召回注入链路两处各半条

**Gap A：`ctx.memory` 读了但没进 prompt。**
`DefaultLoop.perceive` 用 **user_input** 检索记忆并放入 `ctx.memory`（`src/core/loop/default.py:212-213`，query 正确），但 `LLMPlanner._build_request / _system_prompt` 全程不引用 `ctx.memory`（`src/core/loop/planner.py:109/121`，全文件 "memory" 零命中）→ 这半条结果被丢弃。

**Gap B：进 prompt 的「相关事实」用 stage 当 query。**
`planner.py:124` 调 `assembler.build(self._task(ctx), stage="reason", budget=2048)` → `DynamicAssembler.build`（`assembler.py:34`）→ `_gather_facts(stage, budget)`（`assembler.py:56`）→ `self._memory.read(**stage**, budget)`（`assembler.py:60`）。检索 query 恒为字面量 `"reason"`，与用户任务无关 → 排序退化由 freshness/reuse/layer 主导，**中文召回 / 词法相似在这条线上用不上**（恰是 Phase 17 刚补的二元分词）。

**净效果**：记忆「写入 / 落盘 / 分层 / 预算 / 降级 / 并发 / 分词」完成且可测；「**按当前任务语义召回并注入 prompt**」**未接通**。

### 2.2 pet — 子系统已实现，运行时注入缺失

- 已实现：`PetSession` 四态生命周期 + 让行、`PetManager` 多宠隔离、`PetActivator` 三入口契约、persona 加载（`load_persona(s)`）。
- 缺口（`src/core/pet/core/activator.py:62`）：`PetSession(persona=persona)` —— **loop / memory / explorer / safety / notifier 全未注入**：
  - `session.py:43` 默认 `DefaultLoop()`（无 planner / 工具 / LLM，纯 echo）；`session.py:44` `memory=None` → `observe()/prefer()` 抛 `PET_PREFERENCE_WRITE_FAILED`（`session.py:116/126`）。
  - `entry.py:768` 每次调用新建 `PetManager()` → 进程退出即丢 → `pet list` 永远空；无 wake 触发（无后台自治）。
  - `runtime.py` 零 pet 引用；UI/API 层零 pet 引用（WebUI 自然语言入口未接）。
- 实测：`CORE_PET_ENABLED=1 core-agent pet gather "收集行业新闻"` → 仅打印「已激活宠物会话 …（状态 active）」；随后 `core-agent pet list` → 「当前无激活宠物」。

### 2.3 beast — 子系统已实现，运行时注入缺失

- 已实现：`BeastRegistry`（20 山海经神兽）、`BeastSession` 四态、`BeastManager`（兽间并行 / 兽内串行）、`BeastActivator` 三入口、`build/register_innate_skills`（20 神通 Skill 定义）。
- 缺口：
  - `entry.py:834` → `BeastActivator()` → `BeastManager(router=None)`；`manager.py:52` `if self._router is not None:` 整段跳过 → **不 handoff、不执行任务、不 recall**（故 `summon` 后停在 active）。
  - `register_innate_skills`（`skills.py:35`）**零生产调用者** → 20 神通从未进 `SkillLibrary`；`skills.py` 注释自陈「runtime 调用 deferred（loop 只消费 ToolProvider，不接 SkillLibrary）」。
  - `runtime.py` 零 beast 引用；`BeastSession` 默认 `DefaultLoop()` + `memory=None`（`remember()` 抛 `BEAST_MEMORY_WRITE_FAILED`）。
- 实测：`core-agent summon 白泽 "整理一份季度总结"` → 「已召唤神兽 beast.baize（状态 active）」，任务未执行。

---

## 3. 修复清单

### 3.1 memory 召回接合（决定点 D1）

先拍板「检索真源」，再改代码：

- **方案 A（推荐）**：以 perceive 的 `ctx.memory` 为**唯一**检索真源 —— planner 把 `ctx.memory` 渲染成「记忆」块进 system prompt（`user_input` 检索，query 正确）；同时移除 / 停用 `assembler._gather_facts` 的 stage-keyed 检索，避免双检与预算翻倍。
- **方案 B（最小改）**：保留 assembler 路径，把 `_gather_facts(stage, budget)` 的 query 由 `stage` 改为 `task`（`assembler.py:56/60`；`build` 已收到 `task`）；`ctx.memory` 仍冗余（可不动）。

**建议 A**：接口文档已把 perceive 定义为「检索记忆 + 拼上下文」，`LoopContext.memory` 就是为渲染而生；B 会留下两条检索路径。

> **规格先行（SDD）**：任一方案都改变 loop 的「记忆注入 prompt」行为 → 先改 `doc/openspec/specs/loop/spec.md`（观察→推理→行动→记忆 的上下文装配 Requirement）+ `doc/03-interfaces/loop-interface.md` §2/§3，再落代码。
> **预算约束**：注入块须走既有 2048 预算，不得把整个记忆塞进上下文（loop spec §约束）。

**验收**
- [ ] 新测试：给定 L2 记忆「用户偏好 uv 管理依赖」，装配后 system prompt 含该条（按任务召回）；换无关任务不注入或显著降权
- [ ] 既有 `test_llm_planner_*` 不回归

### 3.2 pet 运行时注入

- **注入**：`PetActivator._activate` 支持注入 `loop`（真实 `LLMPlanner` + ToolProvider）/ `memory` / `explorer` / `safety` / `notifier`；由 runtime 组合根构造并传入（`runtime.py` 新增 pet 装配）。
- **存活**：`PetManager` 落盘（`$CORE_STATE_DIR/pet.jsonl` 或复用 `CheckpointStore`）→ `pet list`/`stop` 跨进程可用。
- **唤醒**：接一个 wake 触发（tick / 让行 `busy` 回调），让「后台自治」真正跑起来。
- **三入口**：UIAPILayer / WebUI 自然语言入口接 `activate_from_nl`。

**验收**
- [ ] `pet gather` 后 `pet list`（新进程）可见该会话；`pet stop` 可终止
- [ ] `observe()` 偏好落 L2 成功（memory 已注入），`prefer()` 能读回
- [ ] 一次 wake 走真实 loop（非 echo）

### 3.3 beast 运行时注入

- **router**：runtime 组合根构造 `BeastManager(router=agent_router)`，并把 `BeastActivator` 传同一 manager（`entry.py:834` 改用 runtime 的 activator）；确保 `summon` 真正 handoff 并自动 recall。
- **神通**：runtime 启动时 `register_innate_skills(skill_library, registry)` → 20 神通进 SkillLibrary（注意 loop 只消费 ToolProvider，故需决定神通如何「被走到」——经 `skill_router` 进 planner 的「可用技能」块，或提供 Skill→Tool 适配）。
- **会话**：`BeastSession` 注入真实 loop + memory（`source=beast.<agent_id>` 命名空间隔离）。

**验收**
- [ ] `summon 白泽 "<任务>"` 经 handoff 执行并返回 `last_result`，终态 recall；`failed` 可见
- [ ] 20 神通注册进 SkillLibrary 且被 `skill_router` 命中（「可用技能」块出现）
- [ ] 兽间并行、兽内串行、重复召唤拒绝不回归

### 3.4 subagent（仅口径记录，无改动）

Phase 17 已打通：注册**无个数上限**（`router.register`）、默认 3 画像（coding / research / general-fallback）、委托**深度上限 1**（`_DELEGATE_DEPTH` + 子工具面无 delegate）、子任务并发 `TaskScheduler(max_concurrency=4)`、delegate 超时 600s。

---

## 4. 依赖与前置

- **上游**：Phase 17（memory / subagent / delegate）已交付；Phase 13（runtime 组合根）、Phase 8/10（pet/beast 子系统）。
- **前置决策**：D1（memory 检索真源：A/B）。
- **规格前置**：loop spec + loop-interface 同步（§3.1 任一方案）。

---

## 5. 实现顺序

1. 拍板 **D1** → 改 loop spec + interface（SDD 先行）
2. memory 召回接合（§3.1）+ 测试（先红后绿）
3. pet 注入 + 存活 + 唤醒（§3.2）
4. beast 注入 router + 神通注册（§3.3）
5. 四门禁全绿 → 提交 → 回填 README Phase 17.5 行

---

## 6. 门禁验收

- 四门：`ruff check` / `ruff format --check` / `pyright` / `pytest -q` 全绿。
- 本 Phase 专属：
  - [ ] **memory**：按任务召回进 prompt（新测试）；无双检 / 预算不翻倍
  - [ ] **pet**：跨进程 list/stop；偏好落 L2；一次真实 wake
  - [ ] **beast**：summon 真 handoff + 自动 recall；20 神通进 SkillLibrary 且可被 `skill_router` 命中
  - [ ] loop spec / interface 与实现一致；`openspec validate` 全绿（若涉 delta）

---

## 7. 提交规范

- 可分 3 提交（memory / pet / beast）或 1 提交；message 形如：`fix(wiring): memory 召回注入 + pet/beast 运行时接线（Phase 17.5）`
- 提交后回填 `README.md`：§1 文档清单加 `phase-17.5.md` 行；§2 总览表加 Phase 17.5 行（状态 📋 待开工）。
- **不入库**：`config.yaml`、`coding-plan/phase-3-prompt.md`、`.claude/settings*.json`。

---

## 8. 不做

- 不新增 capability / spec；不改 subagent。
- pet/beast 的 UI 呈现细节（TUI 组件）不在此 Phase，仅接功能入口。
