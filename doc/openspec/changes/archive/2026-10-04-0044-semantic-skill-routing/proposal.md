# Proposal: 语义路由（semantic skill routing）

## Why

Phase 18 #7（维度1 技能库全自动进化的第二环）。走查确认：

1. **路由是纯词法的，且 miss 是死路**：`SkillRouter._score` 只做「任务词元 ∩
   `skill_id`/`description`/`task_types` 的字符包含」，同义不同词（"整理会议纪要" vs 技能声明
   "summarize report"）**永远匹配不上**；未命中即 `_record_miss` 记一条 L2（M3 遗留：miss
   **只沉淀、不复用**）。
2. 有了 #6（SOP 提炼）之后，技能库开始有真实内容，但**只有命中者才用得上**——提炼出的 SOP
   如果措辞与后续任务用词不同，就永远不会被取用，「省 token」的收益被词法口径吃掉。
3. skills spec 的「技能路由」只要求「按任务类型匹配 + 无匹配回退」，**没有语义匹配的
   Requirement**。
4. **B4 收口**（用户 2026-10-04 定夺：删除）：`ContextPack.skills` **无生产者、无消费者**
   ——技能实际经 `planner.skill_router` 回调进 prompt；若改由装配器填充，技能会与事实争
   同一预算（`BudgetManager` 先裁事实、技能只吃剩余），记忆丰富时技能可能被挤出 prompt
   （今天技能恒注入、不受预算约束）。**判定冗余，删除该字段**。

## What Changes

- **ADDED Requirement: 语义路由（semantic routing）**——词法**全无**命中时，以 judge-memory
  打分逐候选求语义匹配度，达阈值者按分排序返回并**不再记 miss**；未注入打分器 / 打分失败 /
  低于阈值时行为与今天完全一致（回退词法结果）。
- 新增 `src/core/judgment/skills.py`：`SkillMatcher.score(task, skills) -> dict[str, float]`
  ——**逐候选一次 `score` 原语调用**（`score` 原语只给「条目集单一分数」，无 per-item 分数），
  照 `judgment/compactor.py` 先例做 domain adapter（**不 import skills**，只吃 dict）。
- `SkillRouter` 增 `scorer` 注入点（`SkillScorer = Callable[[str, list[dict]], dict[str, float]]`，候选以 dict 快照传入）
  与 `threshold`；词法仍是 **fast path**（命中即不调模型）。
- `build_runtime`：`scorer=SkillMatcher(router) if jev is not None else None`（与 memory 的
  `compactor=Compactor(router) if jev is not None` 同口径；未配置 JEV → 纯词法，零行为变化）。
- **B4 删除**：`ContextPack.skills` 字段 + `BudgetManager` 的 skills 裁剪/计量 +
  `context-interface.md` 字段与保留策略里 skills 一句 + `test_context` 对应用例。

## Non-goals

- **SOP 提炼的归组仍走词法**（#6 已交付的下限：宁可分叉、不误并）；本次只改**路由取用侧**。
- **embedding 语义相似度**：不引入向量/本地模型（rag 的 `LLMEmbedder` 是记忆检索底座，
  与技能路由不是同一层）；打分来源是 judgment `score`。
- **技能版本 / A-B 定夺**（#8）、**技能质量门**（#8）。
- **`ContextPack.pending`** 不在本次范围（它参与必保预算判定，非恒空字段）。

## Impact

- 规格：`skills/spec.md`（+1 Requirement）。
- 代码：新增 `src/core/judgment/skills.py`；`src/core/skills/router.py`（语义兜底）；
  `src/core/skills/__init__.py`（导出 seam 类型）；`src/core/runtime.py`（构造 + 注入）；
  `src/core/context/models.py` + `budget.py`（B4 删除）。
- 契约：`doc/03-interfaces/skills-interface.md §4`、`doc/03-interfaces/judgment-interface.md`
  （新增 SkillMatcher 一节）、`doc/03-interfaces/context-interface.md`（删字段）、ADR-0049。
- 兼容性：未注入 `scorer` 时 `SkillRouter` 行为与今天**逐字节一致**；`SkillRouter.match`
  签名不变（新增两个关键字参数，均有缺省）；`ContextPack` 少一个恒空字段（构造方均未传）。

## Risks

- **误匹配（语义把一个不相关技能挂上）**：以阈值 `0.5` 拦截 + 只在词法**全无**命中时才启用
  （词法命中时零模型调用、零语义干扰）；打分器逐候选失败即跳过，坏答案不会污染候选集。
- **成本**：仅「词法 miss」时产生 K 次 judgment `score` 调用（K = 当前 active/gray 技能数）；
  命中路径零额外调用。JEV 不可达时全部回退为 `score=0.0` → 等价词法。
- **延迟**：miss 轮的推理前多一次 K 次调用（受技能库规模约束，属可接受的一次性成本）。
