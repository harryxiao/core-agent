# 0155 · 任务清单（结构化实体抽取 / 关键事实 / 记忆三面路线图 G4）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`memory` **ADDED**「结构化实体抽取（关键事实）」（注入面 / 落库形态 / 密钥红线 / 8 Scenario）。
> 状态：**已归档**（2026-10-07；四门禁全绿，`openspec validate --all` 归档前 31/0 ⇒ 归档后 30/0）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/memory/spec.md`（delta，ADDED）：注入面 / 落库形态 / 密钥红线 fail-closed / 有界 + 8 Scenario
- [x] 1.2 `openspec validate 0155-key-facts-extraction` ⇒ valid
- [x] 1.3 ADR-0147（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_memory_key_facts.py`：`scrub_key_fact` —— 已知前缀族 / 长随机串 ⇒ `<redacted>`
- [x] 2.2 同上：`ref` 在场 ⇒ `value` 一律 `<redacted>`（即便原值不含密钥形态）
- [x] 2.3 同上：fail-closed —— 裸密钥无 `ref` ⇒ 整条丢弃 + `warnings.warn`（留痕不含取值）
- [x] 2.4 同上：未注入抽取器 ⇒ 零 `key_fact` 条目、摘要/迁移逐字不变
- [x] 2.5 同上：落库形态（id / kind / source / tags / trace_id / content）+ 同实体幂等覆盖不增长
- [x] 2.6 同上：抽取器抛错 / 返回不可解析 ⇒ 降级不抽取 + 摘要照写 + 原条目照迁 L4 + 留痕
- [x] 2.7 同上：按 `compaction.<sid>` 回滚 ⇒ 关键事实条目一并移除
- [x] 2.8 同上：条数上界 + 长度上界（**先脱敏后截断**）
- [x] 2.9 同上：`parse_key_facts` 容错（代码围栏 / 非 JSON / 非数组 / 元素缺字段 ⇒ 丢弃该元素或空）
- [x] 2.10 红态确认：实现前若干红 / 其余绿；实现后全绿

## 3. 实现

- [x] 3.1 `src/core/memory/extract.py`（新增）：`KeyFact` / `REDACTED` / `scrub_key_fact` / `build_extract_prompt` / `parse_key_facts` / `extract_with` / 上界常量
- [x] 3.2 `src/core/memory/store.py`：`key_fact_extractor` 注入面 + `_extract_key_facts()`（store 侧无条件脱敏、fail-closed、有界、同 trace）
- [x] 3.3 `src/core/memory/__init__.py`：导出
- [x] 3.4 `src/core/runtime.py`：`extract_with(_llm_text)` 接线

## 4. 文档同步

- [x] 4.1 `doc/02-modules/memory.md`：新增 §「结构化实体抽取（关键事实）」
- [x] 4.2 `doc/03-interfaces/memory-interface.md` §3：注入面 + 落库形态表 + 红线
- [x] 4.3 `doc/04-testing/test-cases.md`：新增 `## 71.`（TC-KEYFACT）
- [x] 4.4 `coding-plan/known-risk.md`：E92 行 → 已修；§3 加 ADR-0147 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（含本 change 新增用例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（memory）⇒ `shutil.move` 至 `archive/2026-10-07-0155-key-facts-extraction/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E92 → 已修）；ADR-0147 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(memory): 结构化关键事实抽取，密钥引用式 + fail-closed 脱敏（change 0155）`
