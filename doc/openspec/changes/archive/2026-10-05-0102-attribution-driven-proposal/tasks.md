# 任务 — 归因驱动提案与结晶语义诚实化（change 0102）

## 1. 规格先行

- [x] 1.1 `specs/evolution/spec.md`：MODIFIED「模块级提案」——`kind` SHALL 由诊断归因驱动
      （内部核心模块 ⇒ `plugin`/`high`，否则 ⇒ `skill`/`low`），显式覆盖 SHALL 优先于归因
- [x] 1.2 `specs/evolution/spec.md`：MODIFIED「架构级候选强制人工审批（HITL confirm gate）」——
      结局诚实：架构级获批过门后 SHALL 登记 `accepted`（不谎报 `published`），技能级 SHALL 仍为
      `published`；两者观察期开窗一致
- [x] 1.3 打开新变更 `2026-10-05-0102-attribution-driven-proposal` 的 delta 结构齐备（proposal/design/tasks/specs）

## 2. 测试（先写，确认红）

- [x] 2.1 新 `tests/test_evolution_attribution.py`：`Proposer()` 对归因白名单 id ⇒ `kind=="plugin"`、
      `risk_level=="high"`、`status=="pending"`
- [x] 2.2 同文件：对非白名单 id（如 `tools.file_read` / `memory.retrieve`）⇒ `skill`/`low`
- [x] 2.3 同文件：显式 `Proposer(kind="skill")` 对白名单 id ⇒ 仍 `skill`/`low`（覆盖优先）
- [x] 2.4 同文件：`INTERNAL_PLUGIN_IDS` 与仓内全部 `plugin_id = "..."` 声明逐元素一致（防漂移）
- [x] 2.5 同文件：模块归因失败 trace → `run_cycle` 得 `pending` + `kind=="plugin"`；签审批单
      `confirm` → `crystallize` 得 **`accepted`**（**非** `published`）
- [x] 2.6 同文件：技能级候选走完同一链路 ⇒ 结局仍为 `published`（技能确实入库）
- [x] 2.7 同文件：未 `confirm` 的候选 `crystallize` 仍抛 `CANDIDATE_PENDING`（红线守护）
- [x] 2.8 运行确认**红**（新增用例失败、既有用例全绿）；另改既有 4 处架构级断言
      （`test_evolution.py:340`、`test_phase15.py:174`、`test_evolution_pending.py:168`/`:260`）

## 3. 实现（后写，转绿）

- [x] 3.1 新 `src/core/evolution/plugin_ids.py`：`INTERNAL_PLUGIN_IDS: frozenset[str]`（13 个 id，
      文档串写明「归因白名单，非 `PluginRegistry` 成员」）
- [x] 3.2 `src/core/evolution/__init__.py`：导出 `INTERNAL_PLUGIN_IDS`
- [x] 3.3 `src/core/evolution/proposer.py`：`kind: Literal["skill","plugin"] | None = None`；
      `propose()` 内 `self._kind or ("plugin" if target in INTERNAL_PLUGIN_IDS else "skill")`
- [x] 3.4 `src/core/evolution/engine.py`：`_crystallize_plugin` 返回 `status="accepted"`
      （L3 留痕与观察期开窗保留）
- [x] 3.5 `src/core/evolution/models.py`：`EvolutionOutcome.status` 注释词表 + `accepted`
- [x] 3.6 `src/core/entry.py`：`_evolve_confirm` 结局文案——架构级分支不再说「已确认并发布」
- [x] 3.7 四门全绿（直连二进制不用 `uv run`）：ruff check / ruff format --check / pyright 0
      errors 0 warnings / pytest 1176 passed

## 4. 文档

- [x] 4.1 `doc/03-interfaces/evolution-interface.md`：`Proposer` 签名（kind 缺省由归因驱动）+
      `EvolutionOutcome.status` 词表 `+ accepted` + §3 confirm 口径补「架构级结局 = accepted」
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0095（归因驱动 kind + 结局诚实化；为何枚举白名单、
      为何新词而非复用 published）+ 末尾映射表行
- [x] 4.3 `doc/04-testing/test-cases.md`：TC-EVO-08 追踪号

## 5. 收口

- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/evolution/spec.md` + tick tasks
      + `shutil.move` 进 `archive/2026-10-05-0102-attribution-driven-proposal/`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填（`coding-plan/phase-21.md` §2 ⑤⑥ 勾选 + §5.3–5.5 标 ✅ + `coding-plan/README.md` 行 21）
- [x] 5.4 记忆更新 + 提交（`feat(evolution): 归因驱动提案与结晶语义诚实化（change 0102）`）
