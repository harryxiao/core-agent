# Tasks 0287 — 文档卫生（PA-11 / PA-12）

> 验证目标：README 计数/最大编号/§1 覆盖与实际 `phase-*.md` 一致且由测试守卫；
> `phase-38.md` §0 批内缺口改用 `B38-*` 并注明与路线图 G1~G5 非同组；
> 登记簿两条标已闭且结构守卫仍绿；四门禁与 `openspec validate --all` 全绿。

## 1. 测试先行

- [x] 1.1 新增 `tests/test_coding_plan_index.py`：计数/最大编号、§1 覆盖、`B38-*` 注记（先红）。
- [x] 1.2 跑目标用例确认失败信息可读。

## 2. PA-11 索引

- [x] 2.1 README 头部计数改为「`phase-*.md` 共 46 份（主文档 43 ＋ 配套记录 3），最大 `phase-41.md`」；本地未跟踪 `phase-32.md` / `phase-3-prompt.md` 不计入。
- [x] 2.2 加唯一一行「索引计数（守卫）」，供测试机读。
- [x] 2.3 §1 表补 `phase-35.md`~`phase-41.md`（7 行）；`phase-32.md` 本地未跟踪，不入索引。
- [x] 2.4 §2 总览补 `phase-35`~`phase-41`（7 行）。

## 3. PA-12 消歧

- [x] 3.1 `phase-38.md` §0 三行批内缺口改 `B38-1/2/3`。
- [x] 3.2 表下加「与记忆三面路线图 G1~G5 非同组」注记；§118 逐字不动。

## 4. 登记与台账

- [x] 4.1 `Pending-Arbitration.md` §1.2 两行标已闭（带 `0287`）；§2 两条追加收口段。
- [x] 4.2 `known-risk.md` 销「README 已知」措辞；新增 E223 ＋ §3 ADR-0277 局限行。
- [x] 4.3 ADR-0277 ＋ 变更追踪映射行。
- [x] 4.4 test-cases §199（TC-CODEPLAN-IDX）。

## 5. 验证与收尾

- [x] 5.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 5.2 反证 3/3（改计数 / 删 §1 行 / 恢复裸 G1G2 ⇒ 各红；cp 复原 + md5sum）。
- [x] 5.3 `openspec validate --all` 32/0（活动期），归档后 31/0。
- [x] 5.4 单次提交 `docs(coding-plan): ...` + Co-Authored-By。
