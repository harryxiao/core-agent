# 0223 设计 — 技能迭代注入「失败实况」

## D1 为什么注入失败实况（材料，而非更多计数）

`_PROMPT_HEAD` 要求「新增的防护步骤要写明它防的是**哪一类**失败」，而输入只有计数 ⇒ 模型必须
**编造**失败类别。注入本轮实际步骤把「哪一类失败」从猜测变为可读事实：模型能看出「是超时」还是
「路径错」还是「参数形状不符」，从而写出**有指向**的防护步骤。

**不做**：不改 `_PROMPT_HEAD` 措辞（它是 pin + 镜像的逐字锚，改一词即三处同改，与本 change 的
目标无关，且当前措辞在拿到材料后**恰好成立**）。

## D2 为什么落在 skills 侧（而非 loop 侧拼 prompt）

依赖方向：`loop` 不 import `skills`，`skills` 也不该被 `loop` 反向注入 prompt 文本。既有先例是
`runtime.py::_loop_hooks().on_turn` 在**组合根**把 `steps` 转交 `sop_extractor.observe(task, steps, ok=ok)`
（`sop.py` 自建 prompt）。本 change 完全同型：组合根只多传一个实参，prompt 由 `skills` 侧自建。

## D3 有界 + 行内脱敏（顺序即安全）

`steps` 由 `loop` 的 `_action_steps` 产出（人类可读摘要，**未脱敏**）。本 change 让这批文本**首次**
进入改写 prompt ⇒ 在迭代器内做两道处理：

1. **`redact_secrets` 先行**（`core.memory` 的 pure helper，`skills/router.py` 已 import `core.memory`
   ⇒ 无新依赖方向、无环）。与 `loop` 的 `failure_digest` 同口径：**只抹密钥子串、保留工具名/路径**
   —— 「做了什么」正是技能迭代要用的信息。
2. **再截断**：末尾至多 `_MAX_FAILURE_STEPS = 5` 步 × 单步至多 `_MAX_FAILURE_STEP_CHARS = 200` 字。
   先脱敏后截断 ⇒ 密钥不会跨截断边界泄漏。上限的意义是 **token 有界**，而非信息完整。

**取末尾**（`[-5:]`）而非开头：失败通常落在序列尾部，末尾材料更贴近失败原因。

## D4 缺省空 = 逐字不变

`failure_steps=()` 是**可选**入参：所有既有调用点（含测试替身）不传 ⇒ 不产块 ⇒ 与今日产物逐字节
相同。这是全批纪律「缺省关 ⇒ 逐字不变」在本 change 的落点。

## D5 未做 / 局限

- **SOP 路径同源暴露未修（登记）**：`sop.py::observe` 把**同一批未脱敏** `steps` 喂给
  `build_sop_prompt`，这是**既有**行为、非本 change 引入。本 change 只覆盖技能迭代这一条新路径；
  SOP 路径的统一脱敏**不在本 change 范围**（PA-02 的裁决范围 = 技能迭代注入），登记为后续候选。
- **不保证「最新一次」**：`steps` 是本**失败轮**的步骤，但若迭代经过多轮才达阈值，注入的是**触发
  迭代那一轮**的材料，而非历史全部失败 —— 这是有意的（token 有界 + 与计数口径一致）。
- **不改 `consider` 的触发判据**：本 change 只增输入，不加新触发/新门。
