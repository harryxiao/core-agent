# 0287 — 文档卫生：coding-plan 索引漂移与 G1/G2 同名消歧（PA-11 / PA-12）

## Why

`coding-plan/Pending-Arbitration.md` 在 change `0226` 登记了两条文档卫生缺口，经 `0285` / `0286`
收口后仍开放：

- **PA-11（索引漂移，实证造成返工）**：`coding-plan/README.md` 自述「36 份 Phase 文档
  （`phase-0`~`phase-34`）」，实际仓库内已有 `phase-35.md`~`phase-41.md`。走查按 README 找账时
  **差点漏掉** `phase-36` / `phase-38` 两册最相关记录，把已裁决事项重报为缺口。
- **PA-12（编号歧义）**：`phase-38.md` §0 的批内缺口用 `G1` / `G2`，与「记忆三面路线图
  G1~G5」同名不同义；按 `G1` 检索会同时命中两套语义。

两条都只动文档与一条守卫测试，不改运行时代码、不改历史裁决内容。

## What Changes

- **PA-11 取方案 C（补索引 + 守卫）**：
  - `coding-plan/README.md` 的计数改为可机读事实：仓库内 `phase-*.md` 共 **46** 份
    （主文档 43 ＋ 配套记录 3），最大 `phase-41.md`；§1 表补齐 `phase-35.md`~`phase-41.md`
    共 7 行；§2 总览补 `phase-35`~`phase-41` 共 7 行。本地未跟踪的 `phase-32.md` /
    `phase-3-prompt.md` 按约定不提交、不计入。
  - 新增 `tests/test_coding_plan_index.py`：断言 README 声明的份数/最大编号与实际
    `phase-*.md` 一致，且 §1 表覆盖全部主文档。今后新增 Phase 未补索引会**转红**。
- **PA-12 取方案 B（局部改前缀 + 注记）**：
  - `phase-38.md` §0 批内缺口 `G1`/`G2` 改为 `B38-1`/`B38-2`/`B38-3`，并加一行
    「与记忆三面路线图 G1~G5 **非同组**」注记；§118 的路线图 G1~G5 收官声明逐字保留。
  - 守卫测试钉住 `B38-*` 前缀与注记存在，且 §0 不再出现裸 `**G1` / `**G2`。
- **登记簿收口**：`Pending-Arbitration.md` §1.2 两行标「已闭」并带 change 号；§2 两条逐条
  小节追加收口段（现象/证据/可选项/建议/落地面五要素保留）。
- **销已知项**：`known-risk.md` 中「README §2 标 ✅ 与事实不符，属已知」的措辞订正为
  「✅ 表示 Phase 计划完成，不代表整包已生产接线」，不再把它记成索引漂移的免检项。
- **台账**：ADR-0277、known-risk 行 E223 与 §3 局限、test-cases §199。

## Non-goals

- 不全局重编号历史 ADR / 台账 / change（PA-12 选项 C，历史成本极高）。
- 不改写 `phase-38.md` 的任何历史裁决内容或 §118 路线图收官声明。
- 不把 `composition` / `distributed` 的 ✅ 状态改成未完成（✅ 口径是 Phase 计划完成）。
- 不为其他文档（`doc/` 各册、`contracts_summary.md`）做同类索引守卫 —— 本次只收 PA-11/PA-12。
- 不改任何 `src/` 行为；无配置面、无规格 delta（`skip_specs: true`）。

## Impact

- 代码：无。
- 文档：`coding-plan/README.md`、`coding-plan/phase-38.md`、`coding-plan/Pending-Arbitration.md`、
  `coding-plan/known-risk.md`、`doc/01-architecture/adr.md`、`doc/04-testing/test-cases.md`。
- 测试：新增 `tests/test_coding_plan_index.py`（3 例）；`tests/test_arbitration_ledger.py`
  仅订正一处注释措辞（开放项 → 第二轮项，含已闭项仍须五要素）。

## Risks

- 守卫对 README 的固定句式有依赖：改文案可能误红。缓解 —— 只锚一条显式「索引计数（守卫）」
  行，改格式时测试失败信息直接指出缺失句式。
- §1 表覆盖判据只认主文档（`phase-N[.N].md`），4 份配套记录不计入主文档集合；若配套记录
  改名为主文档需同步计数与测试口径。
- `B38-*` 与历史文本里的 `G1`/`G2` 并存（§118 路线图），检索仍可能命中两义；注记与
  测试把范围限定在 §0 批内表，全局重编号明确不做。
