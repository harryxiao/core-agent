# 0166 · 设计

## 1. 事故链（trace 可复核）

```
模型 content = 「解释文字：\n\n{"tool_id": "tools.code_run", "args": {…}}」   ← 无原生 tool_calls
        │
        ├─ planner._parse(text)：text.startswith("{") ? 否 ──► :280 Action(args={"reply": text})
        │                                                      （整段原文成「最终答复」）
        ▼
loop.act(action)：action.is_terminal ──► ActionResult(failed=False, data={"reply": …})
        ▼
loop.observe：`"reply" in data` ──► ctx.reply = 原文；ctx.finish()        ← 本轮结束
        ▼
step_completed{"round":1,"failed":false}；_notify_turn(ok=True)
        ▼
tool_call 遥测**不落**（`:281` 只对非终止动作落）⇒ trace 里没有工具调用痕迹
        ▼
下一轮：模型看到「上一条 assistant 说执行了、且无 tool 结果」⇒ 编造 c3ba760 / 32 passed
```

两个独立缺陷，缺一不可地造成「静默伪成功」：**① 识别面太窄**（首字符判定）、**② 失败面被抹平**
（终止动作恒 `failed=False`）。本 change 各修一处。

## 2. 识别面：尾部动作 JSON（`planner._parse`）

```python
def _parse(self, content: str) -> Action:
    text = content.strip()
    if not text:
        return Action(args={"reply": f"{_PARSE_FAILED}: 空响应"}, failed=True)
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return Action(args={"reply": f"{_PARSE_FAILED}: 无法解析模型输出为动作"}, failed=True)
        return self._from_dict(data)
    embedded = _trailing_json_object(text)          # 新增：尾部 JSON 对象（允许围栏收尾）
    if embedded is not None and embedded.get("tool_id"):
        return self._from_dict(embedded)            # 复用：与纯 JSON 路径同一套语义
    return Action(args={"reply": text})
```

`_trailing_json_object`：以 `json.JSONDecoder().raw_decode` 从每个 `{` 起试解析（对象嵌套时内层会被
「必须收在文末」的条件排除，只有最外层命中），**要求其后再无实质内容**（只允许空白与 Markdown
围栏符）。返回 `dict` 或 `None`。

**为什么复用 `_from_dict` 而不另写一支**：动作协议只有一份（`{"tool_id","args"}`），参数校验的
单一真源在工具调用链（`ToolProvider` → `constraints.Validator`）。解析层再写一遍 required/enum
校验就是第二份副本（本仓明令避免，参见 `gate_run` 在处理器内补偿 `enum` 的两处注释）。因此判据
**只到「含非空 `tool_id`」**：命中即交执行链，未注册工具由链上回 `INVALID_ARGS`（**可见**失败）。

**为什么只认尾部**：宁可漏检（尾部之外的形态仍按答复，已知局限）也不误判 —— 模型解释协议时会
**引用**动作 JSON 作示例（trace 中已有此类答复），全篇扫描会把「解释」变成「执行」。尾部形态覆盖
真实事故（解释在前、动作在后，是模型自然而然的行文次序）。

## 3. 失败面：`Action.failed` → 本轮失败

新增字段（`loop/protocol.py`）：

```python
@dataclass
class Action:
    tool_id: str = ""
    args: dict[str, Any] = field(default_factory=dict[str, Any])
    is_irreversible: bool = False
    failed: bool = False   # 终止动作的**失败态**（推理产出不可用）；非终止动作无意义
```

置位点（planner 侧，全部为「推理产出不可用」）：

| 站点 | 文案 |
|---|---|
| `_parse` 空响应 | `LLM_PLAN_PARSE_FAILED: 空响应` |
| `_parse` 首字符 `{` 但 JSON 坏 | `LLM_PLAN_PARSE_FAILED: 无法解析模型输出为动作` |
| `_complete` / `astream` LLM 异常 | `LLM 调用失败: {exc}` |
| `_from_tool_calls` 三处 / `_from_dict` 两处 | `LLM_PLAN_PARSE_FAILED: …` |

消费点（loop 侧，三处，**不新造状态**）：

1. `act()` 终止分支：`ActionResult(failed=action.failed, data=action.args)`
   ⇒ `observe()` 写 `trajectory{"ok": not failed}` 与 `step_completed{"failed": …}`；
2. `arun` 轮内记一个局部标记（`action.is_terminal and result.failed`），收尾用于两处：
   - `_notify_turn(ctx, trace_id, ok=not limit_reason and not <标记>)`
   - `loop_finished` 载荷 `failed = bool(limit_reason) or <标记>` ⇒ `LoopResult.failed`
3. `loop_failed` 事件仍**只**由 `limit_reason` 触发（不改终止语义：解析失败照旧以回复收尾，
   只是**成败标记**变了）—— 与规格「合成终止不写入转录」「循环自身失败带模块归因」两条**互不干扰**。

**不置位**的终止动作（同族但本次不动，ADR 记遗留）：`decline()`（审批拒绝/校验未过）、
`pet/safety` 阻断 —— 属**审批**语义，与「推理产出不可用」不同源。

## 4. 系统提示

`_SYSTEM_PROMPT` 补一句：工具调用 JSON SHALL **单独成块**、SHALL NOT 与正文混写成一段、
SHALL NOT 用代码块包裹。这是**降低触发频率**的辅助手段（`_parse` 的容错才是兜底），
不改任何解析语义；对既有「输出格式二选一」表述是**加严**而非替换。

## 5. 零回归边界

| 路径 | 约束 |
|---|---|
| 纯 JSON | 逐字不变（含 `_from_dict` 各 `_PARSE_FAILED` 文案） |
| 原生 `tool_calls` | 逐字不变（`_from_tool_calls` 优先序不动） |
| 普通文本答复 | `_parse` 末行**仍是** `Action(args={"reply": text})`，仅 `failed` 缺省 False |
| 流式（`astream`） | `reply_stream` 首字符判定**不动**（正文照旧实时外发）；末态 `_parse` 走同一分支 |
| limit_reason 语义 | 不动（`loop_failed` 只认 `limit_reason`） |
| 转录追加 | 不动 |

## 6. 局限（写进 ADR 与 known-risk）

1. **非尾部**动作 JSON 仍按答复处理（漏检），不误判为优先。
2. 尾部 JSON 若确为「示例引用」则会被执行 —— 缓解：仍需过授权/审批链、事件面可见、工具可逆。
3. 解析失败的**合成文案仍进转录**（既有口径），下一轮模型可见 —— 本次不动。
