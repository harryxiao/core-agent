# Tasks 0288 — 台账销账与 E100 盘点

> 验证目标：E55 标已闭且证据可点；E100 的 11 个动词按「已有真实承载 / 无真实后端」分类，
> 文档与 `dispatcher` 集合之差由守卫测试锁定；四门禁与 `openspec validate --all` 全绿。

## 1. 测试先行

- [x] 1.1 新增 `tests/test_cli_verb_inventory.py`：差集比对 + 声明计数（先红）。
- [x] 1.2 跑目标用例确认失败信息可读（缺「未注册动词（守卫）」行）。

## 2. 文档盘点

- [x] 2.1 `doc/03-interfaces/cli-ops-interface.md` §5：替换未注册动词条目为盘点口径
      （6 个已有承载 + 5 个无后端）＋机读守卫行。
- [x] 2.2 跑 `tests/test_cli_verb_inventory.py` 转绿。

## 3. 台账与索引

- [x] 3.1 `coding-plan/known-risk.md`：E55 行改**已闭**（0257 / ADR-0248 / §170）；
      E100 行改为「盘点已闭、实现面按后端解挂」并保留来源。
- [x] 3.2 `doc/01-architecture/adr.md`：ADR-0278 + 变更追踪映射行。
- [x] 3.3 `coding-plan/known-risk.md` §3：ADR-0278 局限行。
- [x] 3.4 `doc/04-testing/test-cases.md` §200（TC-CLI-VERB-INV，2 行）。

## 4. 验证与收尾

- [x] 4.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 4.2 反证 3/3（删文档动词 / 改声明计数 / 临时注册 `kill` ⇒ 各红；cp 复原 + md5sum）。
- [x] 4.3 `openspec validate --all` 32/0（活动期），归档后 31/0。
- [x] 4.4 单次提交 `docs(coding-plan): ...` + Co-Authored-By。
