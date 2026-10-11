# 0223 — 技能迭代注入「失败实况」（PA-02）

## Why

`SkillIterator.consider` 触发的改写 prompt 只给模型**计数**（`N 次，失败 M 次，失败率 x%`）与**现行
步骤**，不给任何**失败现场**（`build_iterate_prompt`，`src/core/skills/iteration.py`）。

`_PROMPT_HEAD` 自己要求「新增的防护步骤要写明它防的是哪一类失败」—— 但没有失败材料，这条要求
**无法兑现**：模型只能凭空猜「哪一类失败」，防护步骤退化为空话（与 `0198` 判过的 SOP 质量门同一
病根：材料不足以支撑要求）。

而失败实况**已经在手**：同一条 `on_turn` 收尾钩子里，本轮的 `steps`（工具动作 + 结果摘要）已经
被 `sop_extractor.observe` 与 `note_store.observe_turn` 消费 —— 唯独技能迭代这条路把它丢掉。

## What Changes

- `build_iterate_prompt(skill, stats, *, failure_steps=())`：非空时在「执行情况」与「现行步骤」之间
  多一节「最近一次失败的实际执行步骤：」，逐条 `- ` 回灌。
- `SkillIterator.consider(skill, *, failure_steps=())`：透传给改写器 prompt。
- 组合根 `runtime._loop_hooks().on_turn`：失败轮把本轮 `steps` 一并交给 `consider`。
- 注入前**有界 + 行内脱敏**（在迭代器内做，见 design D3）。

## Impact

- capability：`skills`（行为面）—— **规格中性**：`skills` spec「技能迭代闭环」只规定
  触发 / 灰度 / 定夺 / 可逆四件事，**未约束 prompt 的输入材料**（实现细节）。不新增、不改动
  Requirement / Scenario。
- 向后兼容：`failure_steps` 缺省空 ⇒ 老调用点产物**逐字不变**；`_PROMPT_HEAD` 逐字不动 ⇒
  提词 pin（`tests/test_prompt_pinning.py::test_iteration_head_verbatim`）与镜像（`prompts.md` ⑨）
  均不受影响。
- 安全：失败步序进模型 prompt 前经 `redact_secrets`（与 `loop` 的 `failure_digest` 同口径）。
