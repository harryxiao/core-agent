# 任务 —— change 0218 情景归纳

- [x] 1. 规格 delta：`memory` ADDED「情景归纳」＋ 6 Scenario（`specs/memory/spec.md`）
- [x] 2. `proposal.md` / `design.md` / `tasks.md`
- [x] 3. 红：新 `tests/test_memory_episodic.py` 覆盖六面（prompt 形状 / 缺省零变化 / 条目形状 /
      脱敏有界 / 幂等覆盖 / 不回喂摘要器（承重）/ 异常降级 / 配置三面 / `compact` 守卫）
- [x] 4. 绿：`src/core/memory/episodic.py`（新）＋ `store.py` 接缝与 `_consolidate_episodic`
      ＋ `__init__.py` 导出
- [x] 5. 绿：`configuration/manager.py` 加键 `memory.episodic_extract`（缺省 False）＋ 访问器；
      `runtime.py` 接线
- [x] 6. 四门禁：`ruff check` / `ruff format --check` / `pyright`（0-0-0）/ `pytest -q`
- [x] 7. 反证三组（摘调用 / `kind` 改 `"episodic"` / 摘 `redact_secrets`）＋ 复原 md5 校验
- [x] 8. ADR-0208 ＋ 台账 E155 ＋ `test-cases.md` §131
- [x] 9. `openspec validate --all` → 手工归档 → 单次提交
