# 设计 · 0170 未闭合动作载荷：识别面收紧 + 失败可见 + 原始产出可诊断

## 1. 判据为何是「深度从未归零」而不是「可解析即动作」

0166（ADR-0156）把「尾部可解析且含非空 `tool_id` 的对象」定义为唯一容错形态，并明文取向
**宁可漏检不误判**。事故轮暴露了该取向的空洞：**外层动作对象被截断时，尾部最末一个「可解析且
其后无剩余」的对象往往不是动作，而是它的内层 `args`**（本例 `{'path','content'}`）—— 于是
`embedded.get("tool_id")` 为假，落兜底 `Action(args={"reply": text})`，**整段 JSON 变正文且
`failed=False`**。

判据的难点是**区分两种「尾部不是动作」**：

| 情形 | 语义 | 期望 |
|---|---|---|
| 解释文字 + **闭合**的示例对象（含/不含 `tool_id`） | 模型在**说**，不是**做** | 自然语言回复（0166 口径） |
| 解释文字 + **未闭合**的 `"tool_id"` 结构 | 模型在**做**，只是产出坏了 | 失败态终止动作（本 change） |

**判据**：自**最后一次**出现的 `"tool_id"` **回退到其外层 `{`**，对其后文本做**字符串感知**的
括号深度扫描（`{}`/`[]` 计深度、引号内与转义符不计）。

- 深度**曾经**回到 0 ⇒ 结构闭合 ⇒ **不命中**（含闭合示例、含「闭合动作 + 其后正文」）；
- 深度**从未**回到 0（含结束时仍在字符串内）⇒ 未闭合 ⇒ **命中**。

**为何不用「`raw_decode` 报错且错误位置在文末」**：`Unterminated string` 类错误的 `pos` 指向**字符串
开头**而非文末，而「长 `content` 字符串被截断」正是最常见的坏法 ⇒ 该判据会漏掉主场景。
**为何不用「遍历每个 `{` 起 `raw_decode`」**：无法区分「截断」与「正文里恰好有不配对的 `{`」。
**为何取最后一次 `"tool_id"`**：截断必发生在文末，最后一次标记即当事结构；更早的结构由其自身闭合性
决定，不影响判据（若最后一次已闭合而更早未闭合，视为答复 —— 记入已知局限）。

**实测校验**（`~/.core/state/traces.jsonl` 轮 `9ae2ae1fe3b34329a8cfaf028e722200`）：命中外层
`{"tool_id": "tools.file_write"`（index 2337）⇒ 深度末态 1、从未归零 ⇒ 命中；其前那个**闭合**的
`tools.code_run` 动作不参与判定（只认最后一次标记）。

## 2. 三处「可解析性」一致性

| 输入 | 路径 | 结果 |
|---|---|---|
| `{"tool_id": "tools.echo",`（无前缀） | `text.startswith("{")` → `json.loads` 失败 | `LLM_PLAN_PARSE_FAILED`（**既有**，可见） |
| `解释文字 + {"tool_id": "tools.echo",` | 判据命中 | `LLM_PLAN_PARSE_FAILED`（**本 change**，可见） |
| `解释文字 + {"tool_id": "tools.echo"}` | `_trailing_json_object` | 工具动作（0166，不变） |
| `解释文字 + {"max_rounds": 3}` | 判据不命中 | 自然语言回复（0166，不变） |

第一、二行**同一个缺陷**此前一可见一静默 ⇒ 本 change 把两者对齐。

## 3. 原始产出的通道（有界、不进持久面）

`Action` 增尾字段 `raw_output: str = ""`（缺省空 ⇒ 全部既有构造点零改动）。**不复用 `args`**
（`args` 是工具参数面；终止动作的 `args` 会成 `ActionResult.data`，塞诊断字段会污染该面）。
传递链：

```
planner._parse  →  Action(raw_output=_bounded(text), failed=True)
                →  default.act: ActionResult(failed=True, data=action.args)   # 不读 raw
                →  default.astream: action 仍在作用域内 ⇒ 局部 raw_output 直取
                →  LoopResult(raw_output=...)      （呈现面）
                →  self._trace("loop_finished", {... | {"raw_output": raw}})   （诊断面）
```

**不变量**（写入规格）：
- `ctx.reply` 只取 `data["reply"]`（可读提示）⇒ 转录（`_append_transcript`）与记忆
  （`remember(..., {"reply": ctx.reply})`）**天然不含**原始产出 —— 无需门控代码；
- 终止动作**不回灌** `ctx.messages`（`_record_observation` 首行即 `if action.is_terminal: return`）
  ⇒ 原始产出**不进**下一轮提示词；
- 上界 `_RAW_OUTPUT_MAX = 4096`，超出截断（trace 是本地 jsonl；失败率实测 ≈9%）。

## 4. 成因可辨：消费 `finish_reason`

`LLMResponse.finish_reason` **早已存在**（`llm_provider/models.py:64`，`stdlib_provider:253` 已填），
planner **从不读它**；`LLMChunk` **没有**该字段，`_map_chunk` 也**丢弃**它 ⇒ 流式（TUI 主用）无信号。

- `LLMChunk` 增尾字段 `finish_reason: str = ""`；`_map_chunk` 取值 `choices[0].finish_reason`（缺省 `""`）。
- `planner._parse(content, *, finish_reason="")`：`"length"` ⇒ 提示明示**被截断**；否则 ⇒ **未闭合**。
- `_complete` 传 `response.finish_reason`；`astream` 累积末个非空 `chunk.finish_reason`（用
  `getattr(chunk, "finish_reason", "")` 取值，第三方 provider 的自有形块不致破）。

**为何不下发 `max_tokens`（Non-goal）**：截断的**上游**成因是「`_build_request` 至今不下发
`max_tokens` ⇒ 端点按其自身缺省限额」。以 `loop.output_reserve`（语义即「输出预留」）驱动该字段
看似顺理成章，但**部分端点会拒绝过大的 `max_tokens`（400）**，属独立兼容性决策 ⇒ 另立台账项，
本 change 只保证「截断**看得见、归得因**」。

## 5. 呈现面（承 0169）

`_StepBlock.__init__` 增 `collapsed: bool = False` 形参（既有调用点零改动）；TUI 在 `loop.result`
（`_EVENT_MAP["loop_finished"]` = `loop.result`，载荷为 `LoopResult` 透传）携带 `raw_output` 时挂
`_StepBlock("⚠ 未能解析的模型原始输出", collapsed=True)`。分支须置于 `_format_event` **之前**
（后者对 `LoopResult` 返回 `None`，不显示）；`continue` 后不落 `❯` 回显。

## 6. 备选与取舍

| 方案 | 弃因 |
|---|---|
| 尝试**修复/补全**截断 JSON 后执行 | 半成品动作 = 新增破坏面（违 P2 取向）；且 `args` 语义不完整时无法判定意图 |
| 回溯执行**非尾部**的合法动作（本例那个完整 `code_run`） | 与 0166「只认尾部」直接冲突；会把「解释时引用」当执行 |
| 新增 `LoopEvent` 类型承载原始产出 | 七类事件契约面扩张，三端 + 编排回流白名单全要跟改；`LoopResult` 加尾字段已达目的 |
| 复用 `Thinking`（呈现-only 通道）呈现原始产出 | 语义错误（那不是推理原文），且 TUI 会标成「思考」块 |
| 让 planner 直接写 trace | planner 无 tracer（架构红线：靠组合根装配）；trace 由 loop 单点写 |

## 7. 局限（写进 ADR + known-risk）

1. 判据只认**最后一次** `"tool_id"` 标记：若「更早一处未闭合、最后一处闭合」，按答复处理（漏检）。
2. 未闭合判定为**结构**判据，不解释成因：`finish_reason` 不可用（如第三方端点不回该字段）时，
   提示为「未闭合（疑似截断或写坏）」，不下断语。
3. 原始产出上界 4096 字符，超长截断（长 `content` 截断点之后的内容不留存）。
4. **不发 `max_tokens`** ⇒ 端点缺省限额导致的截断**仍会发生**，本 change 只使其可见。
5. Web / APP 不呈现该折叠块（新字段可忽略；SPA 零改动）。
