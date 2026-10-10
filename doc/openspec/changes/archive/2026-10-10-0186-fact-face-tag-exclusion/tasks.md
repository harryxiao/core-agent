# 任务 — 原始步序素材退出事实注入面（change 0186 / ADR-0177 / 台账 E123）

## 1. 规格（spec-first）

- [x] `specs/context/spec.md` — MODIFIED「动态上下文构建」（+ 事实面**标签**排除面条款）+ 1 新 Scenario；
      既有 5 Scenario 逐字保留
- [x] `proposal.md` / `design.md`（含轴选 `tags` 的备选表 + `key_fact` vs 笔记结论「设计上非重复」）/ `tasks.md`

## 2. 红测试（先失败）

- [x] `tests/test_context.py` 新增节「原始步序退出事实面」：
      `tags` 含 `steps` 不进 `facts` / 轨迹与失败摘要仍在（回归锚）/ 缺省不传 ⇒ 逐字不变（回归锚）/
      **交集**语义（多标签任一命中即挡）/ `read()` 仍召回（回归锚）
- [x] 组合根接线：主装配器 `_exclude_fact_tags == frozenset({"steps"})`
- [x] 确认红

## 3. 实现

- [x] `src/core/context/assembler.py`：`exclude_fact_tags` 参数 + `_gather_facts` 读后交集过滤 +
      `with_allow_source_prefixes` 派生继承
- [x] `src/core/runtime.py`：主装配器传 `frozenset({"steps"})`

## 4. 四门禁（直连二进制）

- [x] `.venv/bin/ruff check src tests` → All passed
- [x] `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` → 0/0/0
- [x] `.venv/bin/pytest -q` → 基线 2191 → **2196**（+5）

## 5. 归档（手工）

- [x] `openspec validate 2026-10-10-0186-fact-face-tag-exclusion` → valid
- [x] 脚本化合并（MODIFIED 替换同名 Requirement 块；断言 0 标题丢失 / 未触碰块逐字不变）⇒ `mv` 至 archive
- [x] `openspec validate --all` 全绿

## 6. 文档 / 台账

- [x] `doc/01-architecture/adr.md`：ADR-0177 + 变更追踪行
- [x] `doc/02-modules/context.md`；`doc/03-interfaces/context-interface.md`
- [x] `doc/04-testing/test-cases.md` 新 TC 节（§99）+ 基线 bump
- [x] `coding-plan/known-risk.md` §1 E123 行 + §3 ADR-0177 局限行

## 7. 记忆 / 提交

- [x] `MEMORY.md` + `coding-plan-leftover-walkthrough.md`（`0186` 节 + 批次进度）
- [x] 单次提交 `feat(context): …（change 0186 / ADR-0177 / 台账 E123）`
