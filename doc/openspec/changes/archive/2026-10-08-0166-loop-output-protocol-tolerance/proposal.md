# 0166 · 推理输出协议容错与失败可见（尾部动作 JSON + 解析失败不算成功）

## Why

用户 2026-10-08 实测报告（原话）：「执行 llm 回的 tool_id 执行信息，刚开始是好的，跑着跑着后面执行
都突然无法正常执行」—— 模型回了**完全正确**的动作 JSON（`tool_id` / `args` / `type:"bash"` / 脚本全对），
core-agent 却**什么都没执行**，且**整轮记为成功**。

trace 证据（`~/.core/state/traces.jsonl`，轮 `14683edf49554534a414f7695dfa3797`）：
`loop_started` → `step_completed{"round":1,"failed":false}` → `loop_finished`，
**全程无 `tool_call` 记录**；其 `reply` 是

```
执行提交（先 add 再 commit，然后归档 + 复跑 validate，一气呵成但分步验证）：

{"tool_id": "tools.code_run", "args": {"type": "bash", "script": "git add … && git commit … "}}
```

根因（两层，各一处）：

1. **判定只认首字符**：`src/core/loop/planner.py:270-280` 的 `_parse` 以
   `text.startswith("{")` 区分「动作」与「答复」—— 上面这段以「执」开头 ⇒ 落 `:280`
   `Action(args={"reply": text})`，**整段原文（含合法动作 JSON）当成了最终答复**。
   除「整体就是一个纯 JSON 对象」外，**任何**形态（正文 + JSON、```json 围栏、解释 + JSON）
   一律被静默当答复 —— 不是识别率低，是**没有识别**。
2. **失败态被抹平**：终止动作一律 `failed=False`（`loop/default.py:495-496`），
   连明确的 `LLM_PLAN_PARSE_FAILED` 也记为成功 ⇒ 本轮 `turn_after ok=True`、
   skill 迭代 / SOP 提炼 / notes 回写全部吸收了一条**伪成功**轨迹（违 P3 可归因、P4 验证门）。

下游后果：模型看到自己上一轮「这么写被接受了」且**没有配对的工具结果**，倾向模仿 ⇒
一次吞掉即固化，连续复发时体感就是「跑着跑着突然全都无法执行」；下一轮更直接**编造结果**
（`c3ba760` / "3 files changed" / "32 passed"，仓库实况：改动仍未 staged、无该 commit）。

## What Changes

- **尾部动作 JSON 容错**（`planner._parse`）：正文不以 `{` 开头时，取文本**尾部**可解析的 JSON
  对象（允许 ```json 围栏收尾）；该对象含非空 `tool_id` ⇒ **按动作处理**（复用既有 `_from_dict`，
  与纯 JSON 路径**同一套语义**，不另造校验）。尾部 JSON 非动作形态 ⇒ 与现状逐字一致（仍是答复）。
- **解析失败不再算成功**：`Action` 增 `failed: bool = False`（**仅对终止动作有意义**）；
  planner 的全部失败性终止动作（`LLM_PLAN_PARSE_FAILED` 各分支、`LLM 调用失败`）置位 ⇒
  loop 的终止动作 `ActionResult.failed=True` ⇒ 本轮 `trajectory.ok=False`、
  `loop_finished.failed=True`、`LoopResult.failed=True`、收尾钩子 `ok=False`。
- **系统提示明确禁止混写**（`_SYSTEM_PROMPT` 补一句）：降低漂移触发频率（不改变任何解析语义）。

## Non-goals

- **不改**「工具执行失败是否使本轮失败」的口径：本轮只收窄到「**推理产出不可用**」
  （解析失败 / 模型调用失败）。工具失败仍由 ReAct 多轮自愈，是否影响本轮成败**另议**。
- **不动** `decline()`（审批拒绝/校验未过）与 `pet/safety` 阻断这两处终止动作 —— 同族站点，
  但属审批语义，本次不扩口径（在 ADR 记为遗留）。
- **不做**启发式猜测：只认定「**尾部** JSON 对象含 `tool_id`」这一种严格形态；
  正文中间夹动作 JSON 仍按答复处理（已知局限，写进 ADR）。
- **不动**转录追加口径（解析失败的合成文案仍进转录，既有行为逐字不变）。

## 风险

1. **误判**：模型在答复里**引用**一段动作 JSON（如解释协议时）且该 JSON 恰在尾部 ⇒ 会被执行。
   ⇒ 判据收窄为「尾部 + 含非空 `tool_id`」，且动作仍走既有授权/审批链、事件面可见、工具可逆（P2）。
2. **`failed=True` 的外溢**：会使解析失败轮的 skill 迭代与 notes 观察以失败入账 —— 这正是本 change 的
   目的；但对既有断言（`loop_finished.failed` / `LoopResult.failed`）可能触发回归 ⇒ 四门禁全绿为验收线。
3. **零回归边界**：纯 JSON 路径、原生 `tool_calls` 路径、普通文本答复三条既有路径 SHALL 逐字不变。
