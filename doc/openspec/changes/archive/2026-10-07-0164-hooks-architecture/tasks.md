# 0164 · 任务清单

> **本 change 零 `src/` 改动**（架构契约先行，实现另立 change —— 见 design.md §9「实现待办」）。

## 1. 规格与决策（先行）

- [x] 1.1 新建 capability 规格 `specs/hooks/spec.md`：**ADDED** 4 Requirement / 10 Scenario
      （事件面与载荷 / 形态与接缝 / 失败处置与安全边界 / 声明面）
- [x] 1.2 `design.md`：事件表 · 接缝映射表（既有 / 待新增逐条标注）· 命令协议 · 失败矩阵 ·
      安全边界 · 与既有裁决的关系 · 实现待办
- [x] 1.3 `proposal.md`：Why / What Changes / Non-goals / 5 风险
- [x] 1.4 **ADR-0155**（不建事件总线 / 复用既有接缝 / 两形态同一失败语义 / fail-closed 默认 /
      不可逆显式例外 / 声明面标量三面而清单只落 yaml）+ 变更追踪行
- [x] 1.5 `openspec validate 2026-10-07-0164-hooks-architecture` ⇒ valid

## 2. 文档

- [x] 2.1 新建 `doc/02-modules/hooks.md`（模块设计：定位 / 事件面 / 接缝 / 协议 / 失败矩阵 / 安全边界）
- [x] 2.2 `coding-plan/known-risk.md` §1 新行 **E101**「hooks 架构缺失」⇒ **设计已闭（0164 / ADR-0155）、
      实现未闭**；§3 增 ADR-0155 局限行
- [x] 2.3 规格 Purpose 与 ADR 局限**明写**「**未实现**（架构契约先行）」⇒ 防「规格有了 ≠ 能用」误读

## 3. 收口

- [x] 3.1 门禁：本 change **无代码、无测试** ⇒ 只跑 `ruff check` / `ruff format --check` /
      `pyright` / `pytest -q` 确认**无回归**（**1923 passed**，与 0163 收口同数 —— 本 change 零代码）
- [x] 3.2 手工归档（本仓 `openspec archive` 必失败）：把 delta 落成**新** canonical
      `doc/openspec/specs/hooks/spec.md`（`# Hooks Specification` + `## Purpose` + `## Requirements`
      头 + 四条 Requirement 正文）⇒ `mv` 至 `changes/archive/2026-10-07-0164-hooks-architecture/`
      ⇒ `openspec validate --all` ⇒ **31 passed, 0 failed**（新 capability 计数 +1）
- [x] 3.3 台账 + 记忆（`MEMORY.md` / `coding-plan-leftover-walkthrough.md`）
- [x] 3.4 单次提交 `docs(hooks): hooks 架构设计（事件面/接缝复用/失败处置，规格 + ADR-0155，零 src 改动）`

## 验收口径（本 change 的「可验证」边界）

无实现 ⇒ **无可运行判据**；验收＝① `openspec validate` 单条与 `--all` 全绿；② 文档自洽（事件表 /
接缝表 / 失败矩阵互不矛盾，且与既有 `loop` 规格「横切中间件插入」逐字不冲突）；③ 零 `src/` 改动
（`git diff --stat` 只含 `doc/` 与 `coding-plan/`）。
