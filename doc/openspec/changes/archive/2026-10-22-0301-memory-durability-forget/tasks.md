# Tasks — 0301 记忆落盘跨进程合并与遗忘检索隔离

## 1. 规格与测试先行

- [x] 1.1 `specs/memory/spec.md` MODIFIED ×3（后端落盘耐久 / 记忆遗忘 / 情景链(h)）
- [x] 1.2 `tests/test_memory_backend_durability.py` +4（跨实例合并 / 读取强化不覆盖 /
      删除不复活 / 锁不可用仍可写）
- [x] 1.3 新增 `tests/test_memory_forget_recall.py`（7：缺省不可召回 / 预算前排除 /
      `include_forgotten` / 审计可见 / 失败教训排除 / 回滚恢复 / 非遗忘归档仍可召回）
- [x] 1.4 红/绿分布（实现前 `pytest` 两文件：**8 failed / 8 passed**）：红 =
      跨实例合并 / 读取强化不覆盖 / 删除不复活（后端快照覆盖）+ 缺省不可召回 / 预算前排除 /
      `include_forgotten`（TypeError）/ 审计可见 / 失败教训排除；绿 = 既有 5 条耐久用例 +
      锁不可用（尚无锁，平凡绿）+ 回滚恢复 + 非遗忘归档仍可召回（回归锚）

## 2. 实现

- [x] 2.1 新增 `src/core/filelock.py`（自 `orchestration/state_files.py` 迁出）
- [x] 2.2 `src/core/orchestration/state_files.py` 改为 re-export（调用方零改动）
- [x] 2.3 `FileBackend._persist(changed, deleted)`：锁内读盘 → 合并变更集 → 原子写 →
      采纳盘上集合；`put` / `put_many` / `delete` 改传变更集
- [x] 2.4 `MemoryStore.forget()`：追加 `forgotten` 标签 + 同 trace 的可撤销移除效应
- [x] 2.5 `MemoryStore.read(..., include_forgotten=False)`：排名/预算前排除标签
- [x] 2.6 `MemoryStore.failure_lessons()`：排除 `forgotten` 条目
- [x] 2.7 `protocol.py` 的 `MemoryStore` 协议同步 `read` 新关键字参数

## 3. 门禁与文档

- [x] 3.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`（全绿）
- [x] 3.2 `uv run pytest -q`（全量全绿，**3404 passed**，基线 3393 + 11）
- [x] 3.3 反证（`cp` + `md5sum`）：旧 `_persist` ⇒ 合并 3 例红；去 `read()` 排除 ⇒ 遗忘 2 例红；
      去 `failure_lessons` 排除 ⇒ 教训 1 例红；复原后 `md5sum` 一致
- [x] 3.4 `cd doc/openspec && openspec validate --all`（归档前全绿：**32 passed / 0 failed**）
- [x] 3.5 `doc/02-modules/memory.md` §§3.10/3.11/3.16；`doc/03-interfaces/memory-interface.md`
      §1/§5；ADR-0291 / known-risk E237 / test-cases §214
- [x] 3.6 归档 / 提交（用户已确认）
