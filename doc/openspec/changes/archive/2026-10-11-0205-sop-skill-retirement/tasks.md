# Tasks 0205 — SOP 技能退役

## 1. 规格（spec-first）

- [ ] `specs/skills/spec.md`：**MODIFIED**「技能迭代闭环（skill iteration）」（全量替换，含 4 既有
      Scenario；`定夺` bullet 收窄为**单次**失败 + 前向引用新要求）
- [ ] `specs/skills/spec.md`：**MODIFIED** Scenario `A/B 退化丢弃新版本`（GIVEN 收窄为「**单次**退化」，
      标题与 THEN **逐字保留**）
- [ ] `specs/skills/spec.md`：**ADDED**「SOP 技能退役（skill retirement）」+ 6 Scenario
- [ ] ADR-0195（`doc/01-architecture/adr.md`，含 ADR-0011 / ADR-0052 边界调和）+「变更追踪」表行
- [ ] 其余 9 条 `skills` Requirement **逐字保留**

## 2. 测试先行（红）

- [ ] `tests/test_skill_retirement.py`：
      - `deprecate`：置 `deprecated` + 落盘（同路径新实例重载仍 `deprecated`）+ **幂等**
        （已 `deprecated` 不重复记效应）+ 未知 id 抛 `KeyError` + **可逆**
        （`rollback("skills.deprecate")` 恢复原 `status`）
      - `SkillIterator`：连续 3 次退化 ⇒ 自动退役；一次提升 ⇒ 计数归零、不退役
      - **缺省关**（`retire_after=None`）：连续多次退化 ⇒ 仍 `active`（零回归锚）
      - 退役技能 ⇒ **退出路由候选**（`SkillRouter.match` 不返回）
      - **粘性防复活**：同组键重抽 ⇒ 已退役技能**仍 `deprecated`**
      - 配置缺省关 + 三面（CLI/ENV/原生 bool）解析
- [ ] **反证**：摘掉 `decide()` 退化分支的 `deprecate` 调用 ⇒ 连续退化用例转红；摘掉 `sop.py`
      防复活守卫 ⇒ 防复活用例转红

## 3. 实现（绿）

- [ ] `src/core/skills/library.py`：`_DEPRECATE_TRACE` 常量 + `deprecate()`（镜像 `activate`）+
      `_track_deprecation()`（镜像 `_track_activation`，undo 复用既有 `_restore_status`）
- [ ] `src/core/skills/iteration.py`：公开常量 `RETIRE_AFTER_DEGRADATIONS = 3` + `SkillIterator.__init__`
      加 `retire_after: int | None = None` + `self._degradations` + 退化计数折叠进 `decide()`
- [ ] `src/core/skills/sop.py`：`observe()` 的 `register` 前加**粘性防复活守卫**（不改 `register` 通用语义）
- [ ] `src/core/configuration/manager.py`：`skills.retirement`（ConfigSpec 行 + 访问器 `skill_retirement()`）
- [ ] `src/core/runtime.py`：`SkillIterator(..., retire_after=RETIRE_AFTER_DEGRADATIONS if
      config.skill_retirement() else None)`

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：见 §2 末（两处）
- [ ] `openspec validate 2026-10-11-0205-sop-skill-retirement`
- [ ] 手工归档（MODIFIED 合并 + ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失；
      `skills` 10→11 / 49→55）
- [ ] `doc/04-testing/test-cases.md` §118 + 基线 bump；台账 E142（`known-risk.md` §1）+
      §3 ADR-0195 行；`doc/02-modules/skills.md` 增一节
- [ ] 单次提交 `feat(skills): SOP 技能连续退化自动退役 + 粘性防复活（缺省关）`
