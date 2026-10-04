# Design: SOP 提炼（skill extraction）

## 决策 1：提炼是「生成」，走 DI 接缝而非 judgment 原语

`SopWriter = Callable[[str], str]`（prompt → SOP 文本）定义在 **skills 域**
（`skills/sop.py`：`build_sop_prompt` + `sop_writer_with(llm)`），模型调用由 L5 组合根注入——
与 0041 的 `memory/summarize.py` 同一依赖方向，skills **不 import LLM 抽象**。

**偏离 phase-18 原文**：计划写「LLM 提炼走 judgment（JEV 提炼不足则 fallback LLM）」。但 judgment
只有 choice / score / noul **决策**原语，**没有生成原语**——把「写一段 SOP」塞进 score 原语是
职责错位。故生成统一走 DI 接缝；judgment 在技能链路上的角色留在 **#7 语义路由打分**。偏离已记
ADR-0048。

## 决策 2：loop 侧只持有回调，不 import skills（架构红线）

`test_architecture` 明令 `loop` 不得 import `skills`/`skillhub`。故收尾钩子是普通可调用：
`SopObserver = Callable[[str, list[str]], object]`（任务文本 + 行动/结果序列），
`build_runtime` 注入 `sop_extractor.observe`——与既有 `skill_router=lambda task: [...]` 同法。

- **只有成功任务触发**（`ok=False` 的失败轨迹不是 SOP），因此接缝不需要 ok 参数；失败轨迹的
  教训沉淀已有 memory/evolution 通道。
- 钩子缺失（未注入）时 loop 行为**完全不变**；钩子抛错经 tracer 记 `sop_extract_failed` 降级，
  不影响本轮结果与终止语义。

## 决策 3：归组先复用已有 `task_types`，否则用任务词元签名

```python
terms = set(_terms(task))                      # 与 SkillRouter 同口径（小写空白切分）
for skill in library.all_skills():             # 命中任一 task_type 的词元 → 复用该 task_type 作组键
    for tt in skill.task_types:
        if terms & set(_terms(tt)): return tt
return " ".join(sorted(terms))                 # 未命中 → 任务自身的词元签名作新组键
```

- 复用已有 `task_types` 作组键，使**后续提炼落到同一技能**（`skill_id` 由组键派生、`register`
  覆盖同 id）——这正是 #8 迭代闭环的增量来源。
- 词法归组是**有意的下限**：同义不同词的任务各自成组（宁可分叉、不误并），语义归并归 #7。

## 决策 4：阈值 3 条成功轨迹；产物 `status="active"`（维度1 低风险自动发布）

- `_SOP_MIN_SAMPLES = 3`：同类任务累计 3 条成功轨迹才提炼一次，之后清空该组（下批再提炼）。
- 产物 `Skill(skill_id="skills.sop.<组键哈希>", description="SOP：<组键>", task_types=[组键],
  instructions=<提炼文本>, status="active")` → `SkillLibrary.register()`。
  - `skill_id` 由组键的 blake2b 摘要派生：确定性 + 幂等（重复提炼覆盖同一条，不增长）。
  - `status="active"` 是意图声明：维度1（技能库层、不动架构代码）本就是**全自动无人值守**，
    而 `draft` 对 `SkillRouter.match`（只认 active/gray）**不可见** → 置 draft 等于造一条死路径。
- 入库登记 `Effect(op="skills.register", undo=移除技能)`（开发约定 #3「一切副作用可逆」）；
  未注入 tracker 时不记（缺省降级）。
- **提炼文本为空则不入库**（不写半成品），该组样本保留待下轮。

## 决策 5：`SkillLibrary` 仍无版本维度——本次不引入

`register` 按 `skill_id` 覆盖（单版本注册表）。提炼只产出「当前版」，**不新增多版本存储**；
version 升级与 A/B 定夺是 #8 的交付物（`VersionManager` 已存在但未接 runtime）。本次不预先
造多版本结构（CLAUDE.md §2：不做投机抽象）。

## 已知缺口（如实记录，不扩大范围）

- **技能库无持久化**：`SkillLibrary` 是进程内注册表，重启即失（先于本变更存在）。
- **无 judgment 质量门**：低质量 SOP 直接 `active`；兜底是「只吸收成功轨迹 + 阈值 + 可逆回滚 +
  #8 迭代」。质量打分（judgment `score`）留待 #8 一并设计，避免现在加一个无消费者的门槛。
- **无跨进程去重**：进程内 `_samples` 易失，重启后重新累积（不落盘，避免无界写放大）。
