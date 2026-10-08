# Tasks: extraction-quality

> 规格先行 → 红态 → 实现 → 四门禁（直连二进制，**禁** `uv run`）→ 手工归档 → 台账 → 记忆 → **单次提交**

## 0. 规格与设计（先行）

- [x] 0.1 重划范围：核实原稿 6 条，收窄为 D1/D2/D3；切出 0173/0174；剔除上界调整
- [x] 0.2 `specs/memory/spec.md` MODIFIED delta：既有 Requirement 逐字复现 + 8 条既有 Scenario **逐字不改**
- [x] 0.3 `design.md`：现状核实表 / 三条决策 / 接缝不变量 / 实现待办 / 已知局限

## 1. 测试先行（红）

- [x] 1.1 `tests/test_memory_key_facts.py` 新增：同批同 slug 归并 ⇒ **单条**（取值=首条）+ 留痕 + 不重复占额
- [x] 1.2 新增：同批同 slug 归并**不动**跨批幂等覆盖（既有 `test_same_entity_is_idempotent_overwrite:137` 仍绿）
- [x] 1.3 新增：解析失败（非空文本、无 JSON 数组）⇒ `warnings.warn` 且留痕**不含**模型输出正文
- [x] 1.4 新增：合法空数组 `[]` ⇒ **不**告警（防误报）
- [x] 1.5 新增：`value` 超长 ⇒ 落库长度 ≤ `_MAX_FACT_CHARS` **且**首尾皆在（含 `…`）
- [x] 1.6 新增：`entity` / `ref` 仍为头部截断（形态未被误改）
- [x] 1.7 **红态取证**：对 `git stash` 后的旧实现跑新增用例 ⇒ 全红（禁 `ImportError` 式"假红"：只 import 公开面）

## 2. 实现（绿）

- [x] 2.1 `extract.py`：`import warnings` + `_truncate_value` + `scrub_key_fact` 返回式改用之（`entity`/`ref` 不动）
- [x] 2.2 `extract.py`：`extract_with._extract` 判别「有输出但无 JSON 数组」⇒ warn（不含正文）
- [x] 2.3 `store.py`：`_plan_key_facts` 返回三元组 + `seen` 归并只留首条
- [x] 2.4 `store.py`：`_extract_key_facts` 解包三元组 + `deduped` 独立 warn（文案区别于 dropped）
- [x] 2.5 接口零变更核验：`parse_key_facts` / `scrub_key_fact` / `slug_entity` / `KeyFact` /
      `KeyFactExtractor` / `MemoryStore` 公有面 / `core.memory.__init__` 导出 **逐字不动**

## 3. 门禁（直连二进制）

- [x] 3.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 3.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 3.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 / 0 / 0**
- [x] 3.4 `.venv/bin/pytest -q` ⇒ 全绿（基线 **1973**，记增量）
- [x] 3.5 `openspec validate 2026-10-08-0172-extraction-quality` ⇒ valid

## 4. 归档（手工：`openspec archive` 在本仓必失败）

- [x] 4.1 delta 并入 canonical `doc/openspec/specs/memory/spec.md`（MODIFIED ⇒ Requirement 数不变、
      Scenario 8 → 11；红线段落逐字不动）
- [x] 4.2 `mv doc/openspec/changes/2026-10-08-0172-extraction-quality doc/openspec/changes/archive/2026-10-08-0172-extraction-quality`
- [x] 4.3 `openspec validate --all` ⇒ **31 passed / 0 failed**（MODIFIED ⇒ capability 数不变）

## 5. 文档与台账

- [x] 5.1 `doc/01-architecture/adr.md` **ADR-0163** + 变更追踪行
- [x] 5.2 `doc/03-interfaces/memory-interface.md` §3：归并 / 截断形态 / 解析失败留痕
- [x] 5.3 `doc/02-modules/memory.md`：同上（同步既有 8/200 数字旁注）
- [x] 5.4 `doc/04-testing/test-cases.md` 新节（TC-EXTRACT-QUALITY）
- [x] 5.5 `coding-plan/known-risk.md` §1 **E109** + §3 ADR-0163 局限行

## 6. 记忆与提交

- [x] 6.1 `MEMORY.md` + `coding-plan-leftover-walkthrough.md` 追加 0172 条目
- [ ] 6.2 **单次提交** `fix(memory): 关键事实抽取端质量（change 0172 / ADR-0163 / 台账 E109）`

## 端到端目视（用户）

- [ ] 跑一段**会触发压实**的会话（≥ 10 轮），检查 `$CORE_STATE_DIR` 下记忆后端：同批同 slug 不再
      产出重复 `keyfact.*` 条目、长取值**首尾皆在**
