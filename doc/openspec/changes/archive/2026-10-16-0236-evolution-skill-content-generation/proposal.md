# Proposal 0236: 技能候选内容生成（进化内容面补全）

> 原草稿号 `1306`（时刻戳）已改号为 **0236**，与 0234/0235 序号对齐。

## Why

评审问题①：技能级候选的**内容面为空**。

- `proposer.py::Proposer.propose` 产出的 delta 只有 `{"issue": ...}`，不携带任何可执行内容；
- `engine.py::_crystallize_skill` 用 `delta.get("schema", {})` 结晶，得到的是**空 schema 占位壳**
  （`instructions=""`、`task_types=[]`、`preconditions=[]`）——四阶段闭环跑完只结晶出
  **不可路由、不可执行**的壳技能；
- 对照：架构级（plugin）候选有 `executor` 补丁生产者兜住内容，技能级没有任何内容生成器；
- 论文 skill distillation 主张「失败模式 → 可执行技能内容」的蒸馏，当前实现只蒸馏出空壳。

本 change 补「技能候选内容生成器 + 内容级验证」，对齐 skill distillation。

## What Changes

1. 新模块 `src/core/evolution/content.py`：
   - `SkillContent` dataclass：`task_types` / `instructions` / `param_schema` 必填，
     `preconditions` / `description` 可选；
   - `validate_skill_content(content)`：接受 `SkillContent` **或** `Mapping`（delta 内
     `asdict` 形态）；有效 / 空 task_types / 空 instructions / 非 dict schema 四态；
   - `build_skill_content_prompt(issue, failure_notes)`：含 issue 与有界 failure_notes
     （条数 ≤3、单条 ≤400 字符，与 diagnoser 同口径）；
   - `skill_content_writer_with(llm) -> writer`：照 `sop_writer_with` 工厂先例——入参为
     `Callable[[str], str]`，返回 `Callable[[str], SkillContent | None]`；writer 对合法 JSON
     构造 `SkillContent`，非法 JSON / 结构不符 / 调用异常 ⇒ `None`（fail-closed，不抛）。
2. `proposer.py`：可选 `writer` 注入；`kind=skill` 且注入且 writer 返回非空 ⇒
   `delta["content"]=asdict(content)`；writer 返回 `None` 或未注入 ⇒ delta **仍只**
   `{"issue": ...}`（**不**写入 `content` 键）；plugin 候选不生成 content。
3. `validator.py`：`require_skill_content`（缺省 `False`）；为 `True` 且 skill 无有效 content
   ⇒ `passed=False`、review 含「空壳」、`test_results={}`、fail-fast；plugin 不受影响。
4. `engine.py::_crystallize_skill`：有效 content ⇒ 真技能落库（instructions 写前
   `redact_secrets`；`description` 优先 content 值、缺省回退 issue）；缺省 / 无效 ⇒
   既有空壳回退。
5. `models.py`：`GATE_CALIBER` 2 → 3；版本轨迹注释追加 `3 = 技能内容判据（change 0236）`。
6. spec delta：ADDED「技能候选内容生成」；MODIFIED「验证门」（内容判据 + 场景）。
7. `runtime.py`：`Proposer(writer=skill_content_writer_with(_llm_text))` 与
   `Validator(require_skill_content=True)` **同开同关**。

## Impact

- **规格**：`evolution/spec.md` delta；`GATE_CALIBER` → 3。
- **代码**：`content.py`（新）、`proposer` / `validator` / `engine` / `models` / `runtime`。
- **兼容**：未装配时逐字不变；装配后空壳不过门。
- **旧候选**：caliber 2 在 caliber 3 下 crystallize ⇒ `GATE_CALIBER_STALE`，须按现口径重提案。

## Non-goals

- 不碰 0234（rejected 教训写回）。
- 不做诊断信号面增强 / 触发节拍 / 评测粒度。
- 不内置 LLM 实现：只提供 DI 工厂，evolution 不 import LLM 抽象。

## Risks

- 非法内容：writer → `None` ⇒ 无 content 键 ⇒ 门禁拒空壳。
- 敏感信息：结晶写库前 `redact_secrets`。
- 装配不一致：组合根同开同关 + 测试锚定。
- caliber 递增拒旧候选：预期语义。
