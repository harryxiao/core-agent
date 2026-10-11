# Design 0221 — 提词收紧轮登记

## D1 三处行为变更**并为一个 change**（而非拆开）

**背景**：本轮含三处行为变更（`parse_review` 等值、`build_sop_prompt` 签名、10 条提词措辞）。
`Pending-Arbitration.md` PA-07 未决点②问「是否拆开」。

**裁决**：**并为一个 change**。三者**同一提交**（`1f93b88`）、同一动机（提词收紧）、同一验证轮
（四门禁一次跑）。拆开会让「同一提交挂三个 change 号」—— 追溯反而更乱（change 号本应对应
一个可评审的独立意图片段）。**唯一需单列的是 `parse_review`**（它改判定语义）⇒ 以 **ADR-0211
的独立小节 D2** 承接，而非另立 change。

## D2 `parse_review` 等值化 = **规格符合性缺陷修复**（非规格变更）

**取证**：`doc/openspec/specs/evolution/spec.md:144-145` 已 SHALL：「判定 SHALL **fail-closed**：
输出不可解析（空输出 / **非判定词表** / 调用失败）SHALL 判**未通过**」；同域 Scenario `:190-192`
逐字承接（GIVEN 不属于判定词表 ⇒ THEN 未通过）。`validator.parse_review` 旧实现 `startswith` 会
把「通过不了」「PASS 但存在问题」「PASSING」读成**通过** ⇒ **实现偏离既有 Requirement**。

**裁决**：收紧为首行**等值**（`lines[0].strip().upper() in _PASS_WORDS`）—— 这是**向规格回归**，
**不**产生 spec delta（`skip_specs` 成立）。**不选**「NEW Scenario 承接」：既有无 Requirement 缺口，
补 Scenario 是**无源之水**（规格已有该判据）。

## D3 `build_sop_prompt` 轨迹分组签名 = 仓内私有适配器

`build_sop_prompt` 是 `skills.sop` 的**模块私有** prompt builder（L5 组合根经 `sop_writer_with`
注入），`skills/spec.md` 无「按轨迹分组」条 ⇒ 无 Requirement 承载其**形状**。签名从
`Sequence[str]` 改 `Sequence[Sequence[str]]` 是**内部契约**调整，规格中性；其**结构不变量**
（组内 `- ` 行、组间空行）由 `tests/test_prompt_pinning.py` 的 builder 结构锚 ＋ 新反证
`test_sop_prompt_groups_trajectories` 覆盖。

## D4 登记**不改写历史**

**裁决**：不 rebase / 不 amend `1f93b88`，本 change 以**新提交**追溯挂账（`prompts.md` 头部
「待补」→ change 号）。理由：`1f93b88` 已入主线，改写历史破坏他人 checkout；挂账同样达成
「可追溯」目的（P3 可归因：由 change 号 → 提交 → 文件三段闭合）。

- **规格（规格中性）**：无 spec delta；`skip_specs: true`。`openspec validate --all` 31 passed
  （canonical，本 change 无 delta）→ 归档后 31 passed **不变**。
- **反证**：本 change **零 `src/`/`tests/` 改动** ⇒ 无行为可反证；`git diff --stat src tests`
  **为空**即为「未改行为」的直接证据（沿 `0219` 的「零 src 改动」口径）。
- **局限**：① 挂账**不改善** `1f93b88` 提交信息本身（其 message 未含 change 号，仅本簿与本
  change 目录建立映射）；② `prompts.md` 头部「本轮收紧」清单**不逐条**列全 10 条措辞 diff
  （正文镜像已逐字承载，头部只标来源）。
