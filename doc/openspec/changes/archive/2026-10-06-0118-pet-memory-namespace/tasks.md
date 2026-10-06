# tasks — 宠物记忆独立命名空间（change 0118 / phase-30 §8-A 遗留项）

## 1. 规格（先行）
- [x] 1.1 `specs/pet-mode/spec.md`：MODIFIED「Pet Session Runtime Wiring」——宠物轨迹落**独立记忆命名空间**
  （`source=pet`）+ 主 Agent（及神兽）检索面**封存** `pet` + 宠物自身**放行**自身命名空间 +
  `session_id`/`source` 双维度分工 + 主人偏好 `source=user` 不受影响（4 条新 Scenario）
- [x] 1.2 `openspec validate 0118-pet-memory-namespace` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_pet_memory_namespace.py`（新）：**宠物轨迹写 `source=pet`** —— 真 `DefaultLoop(source="pet")`
      + 真 `MemoryStore`，跑一轮后条目 `source == "pet"`
- [x] 2.2 同文件：**主 Agent 检索面封存** —— 主装配器（`exclude=("beast.", "pet")`）在
      `session_id=""`（不过滤会话）下检索，**不含** `source=pet` 条目、**含**主线条目（反例守门）
- [x] 2.3 同文件：**宠物自身可召回** —— 宠物装配器（派生，`allow=("pet",)`）检索**含**自身 `pet` 条目、
      **不含** `beast.*` 条目
- [x] 2.4 同文件：**主人偏好不受影响** —— `source=user` 条目在主 Agent 检索面**仍出现**
- [x] 2.5 `tests/test_pet_wiring.py`（或既有宠物装配用例文件）：**生产装配级** —— 组合根装配的宠物 loop
      其 `source` 为 `"pet"`，且其 planner 装配器排除面含 `pet`、放行面含 `pet`
- [x] 2.6 回归守门：主装配器 `exclude_source_prefixes` 仍含 `"beast."`（phase-26 红线逐字不动）

## 3. 实现
- [x] 3.1 `src/core/runtime.py:566`：主装配器排除面 `("beast.",)` → `("beast.", "pet")`（注释同步）
- [x] 3.2 `src/core/runtime.py:902-919`（`_pet_loop`）：`LLMPlanner(assembler=assembler.with_allow_source_prefixes("pet"))`
      + `DefaultLoop(..., source="pet", ...)`；docstring 补第 ③ 条差异

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1477 passed ⇒ 新增用例后应全绿）
- [x] 4.5 `openspec validate --all`（归档前后各一次，须 30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/pet-mode/spec.md`（逐文件对齐既有排版：
      `#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0118-pet-memory-namespace/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0111**（决策 + 已知局限）+ 变更追踪表行
- [x] 6.2 `doc/03-interfaces/pet-mode-interface.md`（如涉记忆命名空间段）+ `doc/02-modules/pet.md`
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行
- [x] 6.4 `coding-plan/phase-30.md` §8-A：待裁决 → **已裁决并关闭**（change `0118` / ADR-0111）；
      `coding-plan/phase-28.md` §9-A 指针同步；`coding-plan/README.md` 状态列
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [x] 7.1 单次提交：`feat(pet,runtime): 宠物记忆独立命名空间（change 0118）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`src-tauri/Cargo.lock`、
      `node_modules/`、`frontend/dist/`
