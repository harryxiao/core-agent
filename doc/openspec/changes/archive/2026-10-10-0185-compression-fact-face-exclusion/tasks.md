# 任务 — 压缩产物退出事实注入面（change 0185 / ADR-0176 / 台账 E122）

## 1. 规格（spec-first）

- [x] `specs/context/spec.md` — MODIFIED「动态上下文构建」（+ 事实面排除面条款）+ 1 新 Scenario；
      既有 4 Scenario 逐字保留
- [x] `proposal.md` / `design.md`（含对计划实参 `("compaction.summary.","compaction.mid.")` 的**订正**：
      轴是 `source` 而非 `id`，故实参为 `("compaction",)`）/ `tasks.md`

## 2. 红测试（先失败）

- [x] `tests/test_context.py` 新增节「压缩产物退出事实面」：
      mid 不进 `facts` / 长期摘要不进 / `source="context"` 仍在（回归锚）/
      缺省不传 ⇒ 逐字不变（回归锚）/ 专块渲染不变
- [x] 组合根接线：主装配器 `_exclude_fact_sources == ("compaction",)`
- [x] 确认红

## 3. 实现

- [x] `src/core/context/assembler.py`：`exclude_fact_sources` 参数 + `_gather_facts` 前缀过滤 +
      `with_allow_source_prefixes` 派生继承
- [x] `src/core/runtime.py`：主装配器传 `("compaction",)`

## 4. 四门禁（直连二进制）

- [x] `.venv/bin/ruff check src tests` → All passed
- [x] `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` → 0/0/0
- [x] `.venv/bin/pytest -q` → 基线 2185 → **2191**（+6）

## 5. 归档（手工）

- [x] `openspec validate 2026-10-10-0185-compression-fact-face-exclusion` → valid
- [x] 脚本化合并（MODIFIED 替换同名 Requirement 块；断言 0 标题丢失 / 未触碰块逐字不变）⇒ `mv` 至 archive
- [x] `openspec validate --all` 全绿

## 6. 文档 / 台账

- [x] `doc/01-architecture/adr.md`：ADR-0176 + 变更追踪行
- [x] `doc/02-modules/context.md`；若涉装配参数面则 `doc/03-interfaces/context-interface.md`
- [x] `doc/04-testing/test-cases.md` 新 TC 节（§98）+ 基线 bump
- [x] `coding-plan/known-risk.md` §1 E122 行 + §3 ADR-0176 局限行

## 7. 记忆 / 提交

- [x] `MEMORY.md` + `coding-plan-leftover-walkthrough.md`（`0185` 节 + 批次进度）
- [x] 单次提交 `feat(context): …（change 0185 / ADR-0176 / 台账 E122）`
