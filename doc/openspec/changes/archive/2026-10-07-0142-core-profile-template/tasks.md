# Tasks · 0142 core-profile 题词模板产出物

## 1. 规格（先行）

- [x] 1.1 `core-profile/spec.md` **MODIFIED「题词模板」**：产出物具名（`templates/Core.global.md` /
      `templates/Core.project.md`）+ 分区标题逐字对齐解析器 + 分区非空；两条既有 Scenario **逐字保留**
- [x] 1.2 新增 Scenario「骨架复制即被解析器接受」（原文喂 `SectionParser` + `Validator` ⇒ 零 `SECTION_INVALID`）
- [x] 1.3 `openspec validate 0142-core-profile-template` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_core_profile_templates.py`：两骨架存在
- [x] 2.2 全局骨架含两分区标题、**不含** `## 项目信息`
- [x] 2.3 全局骨架**原文往返**：`["constitution","personality"]` 且 `warnings == []`
- [x] 2.4 项目骨架**原文往返**：`["project_info"]` 且 `warnings == []`
- [x] 2.5 注入说明注释含运行时通道关键字（`constitution:v1` / `L0` / `ContextEngine`）
- [x] 2.6 篇幅受控：各 ≤ 50 行
- [x] 2.7 **验红**：模板文件不存在时 6 failed（实测 `6 failed in 0.18s`）；建骨架后 **6 passed**

## 3. 实现（静态产出物，无运行时代码变更）

- [x] 3.1 新增 `templates/Core.global.md`（`## 宪法与全局规则` + `## 人格`；HTML 注释注明注入通道）
- [x] 3.2 新增 `templates/Core.project.md`（`## 项目信息`；同上）

## 4. 文档

- [x] 4.1 `doc/03-interfaces/core-profile-interface.md`：新增 §8「题词模板（骨架产出物）」
      （骨架 ↔ 落向 ↔ 标题约定表 + 标题即契约 + 注释形式之因 + 门禁），原「关联」顺延为 §9
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0134 + `## 变更追踪` 行
- [x] 4.3 `doc/04-testing/test-cases.md`：§58（TC-PROFILE-01…06）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1680 passed**（基线 1674 + 6）
- [x] 5.5 `openspec validate --all` —— 31 passed / 0 failed（归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0142-core-profile-template/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（§2 E85 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`feat(core-profile): 题词模板骨架产出物（change 0142）`）
