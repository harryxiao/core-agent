# Tasks: 语义路由（semantic skill routing）

## 1. 规格先行

- [x] 1.1 `specs/skills/spec.md` delta：ADDED「语义路由（semantic routing）」（触发 / 打分口径 /
      阈值 / 降级，5 个 Scenario）
- [x] 1.2 `openspec validate 0044-semantic-skill-routing` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/skills-interface.md §4`：SkillRouter 增 `scorer` / `threshold`，
      语义兜底触发点与 miss 口径
- [x] 2.2 `03-interfaces/judgment-interface.md`：新增 SkillMatcher 一节（逐候选打分 + 容错）
- [x] 2.3 `03-interfaces/context-interface.md`：删 `ContextPack.skills` 字段行与保留策略中 skills 一句
- [x] 2.4 `01-architecture/adr.md`：ADR-0049（词法 fast path + score 逐候选 + 阈值 + miss 口径 +
      B4 删除该字段的取舍）
- [x] 2.5 `02-modules/skills.md`（若提及路由口径）同步一句

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_skills.py`：词法无命中 → 语义兜底命中（返回语义分、不记 miss）
- [x] 3.2 词法命中 → 打分器不被调用
- [x] 3.3 未注入打分器 → 词法 miss 仍记 miss（行为不变）
- [x] 3.4 语义分低于阈值 → 不采纳 + 记 miss；打分器抛错 → 不抛、记 miss
- [x] 3.5 候选只含 active/gray（draft/deprecated 不打分）
- [x] 3.6 `tests/test_judgment.py`：`SkillMatcher.score` 逐候选一次调用 → {skill_id: 分}；
      坏答案跳过；provider 不可达（回退 0.0）
- [x] 3.7 `tests/test_phase13.py`：`build_runtime` 注入 scorer（有 JEV）/ 不注入（无 JEV）
- [x] 3.8 `tests/test_context.py`：删 skills 用例；确认 `ContextPack` 无该字段

## 4. 实现

- [x] 4.1 `src/core/judgment/skills.py`：`SkillMatcher`（逐候选 decide + 容错）+ `__init__.py` 导出
- [x] 4.2 `src/core/skills/router.py`：`SkillScorer` seam + 语义兜底 + 阈值 + miss 口径；
      `__init__.py` 导出 `SkillScorer`
- [x] 4.3 `src/core/runtime.py`：构造 `SkillMatcher(router)`（仅 JEV 配置时）注入 `SkillRouter`
- [x] 4.4 B4 删除：`context/models.py` 删字段；`context/budget.py` 删 skills 裁剪/计量

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
