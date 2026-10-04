# Tasks: 技能迭代闭环（skill iteration）

## 1. 规格先行

- [x] 1.1 `specs/skills/spec.md` delta：ADDED「技能命中注入」/「技能执行反馈」/「技能迭代闭环」
      （载荷与节选口径 / 命中与结果口径 / 触发与灰度与 A/B 定夺，8 个 Scenario）
- [x] 1.2 `openspec validate 0045-skill-iteration` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/skills-interface.md`：§3 VersionManager 补「接 runtime（灰度/A/B 触发者）」
      与 §4 补命中快照 `skill_hint`（id/版本/instructions 节选）
- [x] 2.2 `03-interfaces/loop-interface.md`：收尾钩子改名 `turn_observer(task, steps, ok)`
      （成功/失败都提交）+ 技能块渲染为 `- <id>（<版本>）：<步骤节选>` + 事件更名
      `turn_observer_failed`
- [x] 2.3 `01-architecture/adr.md`：ADR-0050（命中注入走纯 dict 组合根组装 + 收尾钩子扩 ok +
      反馈按 (id,version) 进程内 + 复用 VersionManager 灰度/A/B + 退化只丢草稿）
- [x] 2.4 `02-modules/skills.md`：路由/迭代一段同步（命中注入 + 反馈 + 迭代闭环）

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_skills.py`：`SkillFeedback` 按 (id, version) 累计（命中/成功/失败/合计/
      无样本成功率 0.0）
- [x] 3.2 `skill_hint`：字段齐全 + instructions 超长按 `_MAX_HINT_CHARS` 截断 + 空 instructions
- [x] 3.3 `SkillIterator.consider`：达阈值触发（草稿入灰度、返回版本号）；样本不足不触发；
      失败率不足不触发；未注入 writer 不触发（且 writer 未被调用）；空改写文本不入草稿
- [x] 3.4 `SkillIterator.resolve`：灰度按比例分流（rng 可控）→ 草稿版本返回草稿文本；未灰度回退当前版
- [x] 3.5 `SkillIterator.decide`：新版本成功率更高 → 落地（version/instructions 更新 + 可逆效应）；
      更低 → 保持原版本且状态不 deprecated；样本未齐 → None
- [x] 3.6 `tests/test_loop.py`：收尾钩子带 `ok`（成功 True / 失败 False 都提交）；
      钩子抛错不改变本轮结果（`turn_observer_failed`）
- [x] 3.7 `tests/test_planner.py`（或既有 planner 用例）：技能块渲染 id + 版本 + 步骤节选
- [x] 3.8 `tests/test_phase13.py`：`build_runtime` 接线（feedback/iterator/VersionManager 指标 +
      命中注入 + 收尾反馈）；未配置时零行为变化

## 4. 实现

- [x] 4.1 `src/core/skills/feedback.py`：`SkillStats` + `SkillFeedback`
- [x] 4.2 `src/core/skills/router.py`：`skill_hint()`（快照 + 节选上界）
- [x] 4.3 `src/core/skills/iteration.py`：`SkillIterator` + `build_iterate_prompt`
      （复用 `SopWriter` 接缝类型）+ `__init__.py` 导出
- [x] 4.4 `src/core/loop/planner.py`：技能块渲染 dict 载荷（`SkillHint`）
- [x] 4.5 `src/core/loop/default.py`：`sop_observer` → `turn_observer(task, steps, ok)`，
      成功/失败都提交，事件更名 `turn_observer_failed`
- [x] 4.6 `src/core/runtime.py`：构造 feedback/iterator/VersionManager 并接线命中钩子 +
      收尾钩子（含子 Agent loop）；`Runtime` 暴露 `skill_feedback` / `skill_iterator` /
      `skill_extractor`

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
