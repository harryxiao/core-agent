# 任务：rag 定位文档化（记忆三面路线图 G5）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> 本 change **规格中性**（`.openspec.yaml` `skip_specs: true`）⇒「测试先行」体现为**结构守护**
> （既有现状已满足 ⇒ 守护应**绿**；红态由「人工植入 `loop`→`core.rag` import」验证守护有效）。
> 状态：**已归档**（2026-10-07；四门禁全绿，`openspec validate --all` 归档前 31/0 ⇒ 归档后 30/0）。

## 1. 定位与规格判断（先行）

- [x] 1.1 一手核实：rag 现状 = 辅助本地知识库（CLI `rag ingest|search|ask` 一次性）；
      `core.rag` 仅被 `runtime`（组合根）与 `entry`（CLI）import，主链路零引用
- [x] 1.2 判定**规格中性**（无 SHALL 变更）⇒ `skip_specs: true`
- [x] 1.3 门径钉死：参与 loop 上下文须**先改 ADR-0097 ⑥**（ADR-0148 复述）

## 2. 测试先行（守护）

- [x] 2.1 `tests/test_architecture.py`：新增「主链路 / 三面兄弟（loop / context / memory / notes）
      不 import `core.rag`」守护（实现前后**应绿** —— 现状即满足）
- [x] 2.2 红态确认：临时植入 `loop` → `core.rag` import 使守护变红，撤销后回绿

## 3. 文档与 ADR

- [x] 3.1 `doc/11-rag/rag-architecture.md` §1：三面边界 + 不注入主链路
- [x] 3.2 `doc/02-modules/rag.md` §1：同步定位
- [x] 3.3 `doc/03-interfaces/rag-interface.md`：新增「定位：辅助按需，不注入主链路」节
- [x] 3.4 `doc/01-architecture/adr.md`：ADR-0148 + 变更追踪行

## 4. 台账

- [x] 4.1 `coding-plan/known-risk.md` §3：ADR-0148 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（+1 守护）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：`shutil.move` 至 `archive/2026-10-07-0156-rag-positioning/`

## 6. 记忆与提交

- [x] 6.1 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`；路线图 G1~G5 全闭）
- [x] 6.2 单次提交：`docs(rag): 定位文档化，辅助本地知识库不注入主链路（change 0156）`
