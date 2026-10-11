# Proposal 0221 — 提词收紧轮登记（change `1f93b88` 补挂 change / ADR / 台账，规格中性）

## Why（缺口）

2026-10-11 提词收紧轮已落地并**提交**（`1f93b88`）：10 条内置 prompt 措辞收紧 ＋ 2 处配套代码
（`evolution.validator.parse_review` 判定等值化、`skills.sop.build_sop_prompt` 按轨迹分组），
并同步 `tests/test_prompt_pinning.py` 副本与 `doc/03-interfaces/prompts.md`。但该轮**未登记**
change 号 / ADR / 台账 —— 与 `0215`（立 9 条 pin / ADR-0205 / E152）、`0219`（补 3 条 ＋ 建总表 /
ADR-0209 / E156）的惯例不一致，形成**追溯断点**（`coding-plan/Pending-Arbitration.md` PA-07）。

本 change 只做**登记**，不改任何行为 —— 代码已由 `1f93b88` 提交，本 change 是**追溯挂账**。

## What Changes

1. **新增 change 目录**（本目录）＋ **ADR-0211**：记载本轮三处行为变更的裁决与规格判定。
2. **`doc/03-interfaces/prompts.md` 头部**：「待补」→ change `0221` / ADR-0211 / 台账 E158。
3. **台账**：`coding-plan/known-risk.md` §1 E158 ＋ §3 ADR-0211；`doc/04-testing/test-cases.md` §134；
   `doc/01-architecture/adr.md` 变更追踪表 ＋ ADR-0211 正文。

**规格中性判定**：三处行为变更**均无 spec delta** ——
- 10 条 prompt 措辞：模块私有实现细节（`0215`/ADR-0205 已立「pin 实现细节、不升规格」口径）；
- `parse_review` 等值化：**规格符合性缺陷修复** —— `evolution/spec.md:144-145` 已 SHALL
  「输出不可解析（空输出 / **非判定词表** / 调用失败）SHALL 判未通过」，Scenario `:190-192` 逐字
  承接；`startswith` 把「通过不了」「PASS 但存在问题」读成通过是**实现偏离既有 Requirement**，
  收紧到等值是**向规格回归**，非改规格；
- `build_sop_prompt` 签名改 `Sequence[Sequence[str]]`：**仓内私有适配器**，`skills/spec.md` 无
  「轨迹分组」条 ⇒ 无 Requirement 承载，规格中性。

⇒ `.openspec.yaml` `skip_specs: true`（沿 `0156`/`0189`/`0195`/`0215`/`0219` 先例）。

## 显式不做

- **不改任何 `src/` / `tests/` 源码** —— 已由 `1f93b88` 提交，本 change 只挂账（`git diff --stat src tests` 为空）。
- **不重写 `1f93b88`** —— 追溯登记，不改写历史。
- 不做 `PA-01`/`PA-02`/`PA-03`（各自独立走 change）。
