# 0168 · 任务清单

> 触发：用户 2026-10-08 复查 `0165` 后追问「其余视图仍在用 `\t` 可以修正吗」；范围经确认取**全部 5 处**。

## 1. 规格与决策（先行）

- [x] 1.1 `specs/cli-ops/spec.md` **MODIFIED** Requirement「诊断视图列对齐」：作用域由 `render_notes`
       扩为**全部列表型视图**，明写两形态；既有 3 Scenario 逐字保留 + 新增 2 个
- [x] 1.2 **ADR-0159**（抽模块做单一真源 / 两形态而非一个通用函数 / 明细行以 `str` 条目透出 /
       `render_notes` 回填共用助手 / 范围扩至全部诊断视图 / 局限）+ 变更追踪行
- [x] 1.3 `openspec validate 2026-10-08-0168-diagnostics-column-alignment` ⇒ valid

## 2. 测试先行（红）

- [x] 2.1 测试助手：`_display_width`（**独立实现**，不复用被测代码）、`_cell_columns`
      （按单元格内容定位起始**显示列**）、`_body`（去标题行 + 断言行数）、`_assert_aligned`
      （禁 `\t` + 指定列起点一致）
- [x] 2.2 `test_render_sessions_columns_aligned`（表格型，含中日韩标题）
- [x] 2.3 `test_render_mcp_columns_aligned`（表格型；`transport=""` ⇒ `自动`）
- [x] 2.4 `test_render_config_labels_aligned`（键值型）
- [x] 2.5 `test_render_skills_labels_aligned`（键值型 + 明细行原样透出：只对非 `·` 行断言）
- [x] 2.6 `test_collect_status_labels_aligned`（键值型）
- [x] 2.7 `test_render_notes_columns_aligned` 改用共用助手 `_assert_aligned`
- [x] 2.8 红态确认：`git stash push -u -- src/core/diagnostics` ⇒
      `.venv/bin/pytest -q tests/test_diagnostics.py` ⇒ **5 failed / 19 passed**（新增 5 条全红，
      旧的 `render_notes` 用例因 `0165` 已修而本 change 前即绿）；`git stash pop` 复原

## 3. 实现（绿）

- [x] 3.1 新建 `src/core/diagnostics/align.py`：`display_width` / `pad` / `align_rows` / `align_pairs`
      （`_SEP = "  "`；`align_rows` 行末不补；`align_pairs` 的 `str` 条目原样透出）
- [x] 3.2 `views.py`：删私有 `_display_width` / `_pad`（及 `unicodedata` import），改从 `.align` 导入
- [x] 3.3 `views.py`：`render_sessions` / `render_mcp` / `render_notes` 改 `align_rows`
      （笔记的常驻标记并入时间戳格，列数恒为 3）
- [x] 3.4 `views.py`：`render_config` / `render_skills` 改 `align_pairs`；
      `_catalog_lines` ⇒ `_catalog_entries`（返回条目）；明细行抽 `_detail_lines`
- [x] 3.5 `checks.py`：`collect_status` 由 f-string 拼接改条目列表 + `align_pairs`（读数逻辑一字不改）
- [x] 3.6 绿态确认：`.venv/bin/pytest -q tests/test_diagnostics.py` ⇒ **24 passed**

## 4. 文档

- [x] 4.1 `doc/03-interfaces/cli-ops-interface.md` §5 补一条（`align.py` = 对齐单一实现，两形态两入口）
- [x] 4.2 `doc/04-testing/test-cases.md` 新节 `## 81.`（TC-ALIGN-ALL）
- [x] 4.3 `coding-plan/known-risk.md`：§1 新行 **E105**（残留 `\t`，承 E104）+ §3 ADR-0159 局限行；
      E104 与 ADR-0158 局限③ 回填「已由 0168 闭合」

## 5. 门禁与收口

- [x] 5.1 `ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest -q` 四门禁直连全绿
- [x] 5.2 `openspec validate 2026-10-08-0168-…` ⇒ valid ⇒ 手工归档（**MODIFIED** ⇒ 替换 canonical
      中该 Requirement，**非**追加；`mkdir -p` 先建目标再 `mv`）⇒ `openspec validate --all` ⇒ 31/0
- [x] 5.3 台账回填 + 记忆更新 + **单次提交**

> **5.1 实测**：`ruff check` All checks passed / `ruff format --check` 370 files already formatted /
> `pyright` **0 errors, 0 warnings, 0 informations** / `pytest -q` **1947 passed**（`0165` 基线 1942 ⇒ **+5**）。
> 实现期两处门禁返工：① `ruff` I001 导入次序 + E501 + PLR2004 ×3（`6` / `2` / `8` ⇒ 提为
> `_CONFIG_LABELS` / `_SKILL_LABELS` / `_STATUS_LABELS`）；② `pyright` 报 `list` **不变型** ——
> `checks.py` 推不出 `list[tuple[str, str] | str]`（写出的是 `list[tuple[str, str]]`）⇒ `align_rows` /
> `align_pairs` 的入参改 `Sequence`（**协变**，且函数只读不写）。
> **5.2 实测**：`openspec validate --all` ⇒ **31 passed, 0 failed**（capability 数不变 —— 本 change 是
> **MODIFIED** 既有 Requirement，不新增 capability）。
