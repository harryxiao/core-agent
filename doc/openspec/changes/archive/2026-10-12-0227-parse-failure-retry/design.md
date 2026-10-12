# Design — 0227

## D1. 重试放规划器层（非 FaultChain）

`FaultChain`（0209/ADR-0199）是**行动阶段**（act）的白名单容错（`{TIMEOUT, EXECUTION_FAILED}`、
仅可逆工具），重试的是**工具执行**；解析失败发生在**推理阶段**（reason），重试的单位是「一次推理
请求」。放 planner 内 ⇒ ①不需要 loop 侧新接缝（`DefaultLoop` 零改动）；②上下文一致 —— 重试
沿用同一 `ctx` 装配（宪法/事实/技能照常在场）；③与既有流式边界判定（首个 `{` 缓冲不外发）
天然同层，能拿到「本轮是否已外发内容增量」的准确信号。

## D2. 触发判据（三个门同时开）

1. **配置门**：`parse_retry=True`（构造参，缺省 `False`）。
2. **失败门**：`_retryable(action)` —— 空工具 id + reply 以 `LLM_PLAN_PARSE_FAILED` 前缀
   （覆盖 `_parse` 全部失败分支 ＋ `_from_tool_calls` 的缺 name/参数不可解析 ＋ `_complete` 不涉及
   —— LLMError 分支 reply 前缀是 `LLM 调用失败`，天然不命中，不误触）。**空响应/缺字段类轻失败
   会被一并重试** —— 有益无害：成本一次、机会一次。
3. **外发门**：`not reply_stream` —— 已向终端外发过内容增量（自然语言流）时重试会产生
   「回答回滚」的观感；缓冲路径（首个 `{` 判定后全缓冲 ＋ 原生工具片段路径）未外发任何
   内容增量，重试对外零痕迹。**PA-01 现象②（流式泄漏）单独立项，不在本 change。**

原生 tool_calls 终态动作同样检查 `_retryable`（缺 function.name/参数不可解析时可受益），
同样只在未外发增量时（native_tool 路径本来就不外发内容增量 ⇒ 恒可重试）。

## D3. 回喂消息的形状（nudge）

- **用户角色 Message**：模型对「同轮纠错」的遵从度远高于 system 追加（OpenAI 兼容端点的惯例）。
- **内容 = 成因 + 协议重申 + 用法提示**（`_RETRY_NUDGE` 常量，`.format(cause=…)`）：
  - 成因：取自失败 reply 前缀之后的部分（已有的区分措辞直接复用 —— D4 的成因细化让这条
    消息在事故形态下能说「疑似工具调用 JSON 未闭合」）；
  - 协议重申：二选一 ＋ 「JSON 必须是第一个字符、其后不得再有任何字符」（`_SYSTEM_PROMPT`
    的既有措辞，不新造语义）；
  - 用法提示：事故形态是**长内容一把梭**导致退化 ⇒ 明示「分多次、每次写一小段」。
- **绝不携带原始退化产出**（0170 纪律：raw_output 只进 trace/呈现，不回模型 —— 回喂退化文本
  会把重复模式重新注入，是自激而不是纠错）。
- 追加到**本次** request.messages（`_build_request` 每次新造 list ⇒ 不污染 ctx）。

## D4. `{` 开头失败成因细化（复用既有判据，零新启发式）

`_first_brace_reply(text, finish_reason)` 三段：
1. `_unclosed_action_payload(text)` ⇒ 未闭合载荷（事故形态）——按 `finish_reason` 区分
   `_UNPARSED_TRUNCATED`（length）/ `_UNPARSED_UNCLOSED`（其余），与形态 4 的既有措辞**同文**；
2. `_embedded_action_payload(text)` ⇒ `_UNPARSED_EMBEDDED` —— 事故的第二种成因
   （重复对象 = 第一个对象已闭合、其后仍有正文）命中 `_embedded_action_payload` 的定义；
3. 皆不命中 ⇒ 维持通用文案（逐字）。

只改 `args["reply"]` 的信息量；`failed` / `raw_output` / 终止语义不变 ⇒
**既有断言（`test_truncated_json_marks_action_failed` 只断前缀）天然兼容**。该细化**无条件**
生效（非门控行为）—— 它是提示信息量的缺陷修复（形态 4/5 的措辞承诺本就该覆盖同根因的
`{` 开头类），0170/0222 的规格措辞承诺按成因区分，只是判据不可达；修的是可达性。

## D5. 恰一次重试的实现形状

- `_complete(ctx)` → 薄壳：`action, thinking = await self._complete_once(ctx)`；失败门命中 ⇒
  `action, thinking = await self._complete_once(ctx, nudge=…)` 再来一次（**不递归**，两次调用
  平铺 ⇒ 恰两次模型调用，无失控风险）。
- `astream(ctx)` 同型：`_astream_once(ctx, *, nudge, allow_retry)`；重试分支把第二次的产出
  **继续 yield**（事件序：先发完第一次的缓冲终态？**否** —— 重试时第一次的失败动作**不 yield**，
  直接转入第二次流；只有第二次的终态动作外发。终端看到的是一次干净的推理（对上
  D2 的「对外零痕迹」承诺）。
- usage 观测两段各自照常（`_last_prompt_tokens` 取 max 语义不受影响）。

## D6. 配置与接线

- `ConfigSpec("loop.parse_retry", "--loop-parse-retry", "CORE_LOOP_PARSE_RETRY", default=False,
  map_to="loop.parse_retry", exposure=ADVANCED)`；`loop` 是结构化段 ⇒ `_loop_errors` 加 bool 校验
  （镜像 `turn_checkpoint`）。
- 访问器 `parse_retry()` 镜像 `failure_lessons()`（`_FEATURE_TRUE` 字符串归一化）。
- runtime：`parse_retry = config.parse_retry()` 算一次，注入四个 planner（与 `max_tokens`/
  `block_plan` 同型同位）。宠物 loop 也接 —— 这是**协议层**自愈，不是记忆/转录面
  （对照红线清单：宠物不接的是 fault chain/turn checkpoint/transcript/failure_lessons）。

## D7. 观测与留痕

- 重试**第二次**的终态动作即对外动作 —— 无新遥测事件（trace 已按模型调用记录，两次调用
  各自可见于 provider 层日志）；失败门未开启时零新增路径。
- trace 侧的 `raw_output`（有界）随终态动作照旧 —— 若第二次仍失败，raw_output 是第二次的
  退化产出（第一次的已丢弃，与 D5 的「对外一次干净推理」一致）。

## 局限（登记，不修）

1. 重试**不能治疗退化本身**（glm 长上下文下的重复退化是模型/负载问题）；它把「一次退化 ⇒
   整轮报废」变成「一次退化 ⇒ 多一次干净产出机会」。`~` 展开（change 乙）与 maintenance
   HTTP 400 才是上游减压。
2. 非流式 `_complete` 的重试**不感知**「已向终端外发」概念（它本就不外发）⇒ 恒可重试。
3. nudge 追加使第二次请求的 prompt token 高于第一次 —— 记账取 max 语义已覆盖。
4. ② 原生 tool_calls 的流式片段在中途判失败（如 arguments JSON 断裂）时，
   `_from_tool_calls` 在**终态**才判 —— 不存在中途外发，安全。
5. Thinking 增量若已外发（`show_thinking=True` 且第一次响应带思考）⇒ 第二次会再次外发思考，
   呈现层出现两段思考 —— 可接受（呈现层折叠），登记。
