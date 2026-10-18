# Tasks 0262 — 记忆检视与纠错 CLI

## 1. 规格

- [x] 1.1 `cli-ops` delta：MODIFIED「运维命令集」（`memory list/get/delete` + 3 scenarios）。

## 2. 红测试（先写）

- [x] 2.1 `memory list`：打印条目字段；`--limit` 截断展示并提示总数；`--limit 0` 全量。
- [x] 2.2 `memory get <id>`：打印全文；未知 id ⇒ 退出码 1。
- [x] 2.3 `memory delete <id>`：删除前追加备份（0600）、条目消失、打印备份路径。
- [x] 2.4 删除未知 id ⇒ 退出码 1 且**不落备份**。
- [x] 2.5 备份写入失败 ⇒ fail-closed（不删除、退出码 1）。
- [x] 2.6 密钥形态不回显（list 摘要 / get 全文均经 `redact_secrets`）。

## 3. 实现

- [x] 3.1 `entry.py` 注册 `list` / `get` / `delete` 子命令与分派。
- [x] 3.2 删除备份：`memory-deleted.jsonl` 追加 + 0600 + fail-closed。

## 4. 验证

- [x] 4.1 反证：摘备份 / 摘 discard / 摘脱敏 / 未知 id 写备份 ⇒ 对应用例红；复原后全绿。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0252；`coding-plan/known-risk.md` E198 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §174；`doc/03-interfaces/cli-ops-interface.md` 补命令面。
- [x] 5.3 单次提交 `feat(cli-ops): ... change 0262 / ADR-0252 / 台账 E198`；更新记忆。
