# 0145 · Think 思考过程回显链路（TUI / Web / APP）

> 账本：`coding-plan/phase-32.md` **E56~E60**（一条链五处断，**新能力 feature**，非缺陷账本）
> 规格面：`llm-provider` MODIFIED ＋ `loop` MODIFIED ＋ `ui` ADDED ＋ `configuration` MODIFIED
> ADR：**0137** ｜ 用户裁决（§3 五裁决点）：按**建议值**实施（单一内部字段 `thinking`／
> config 开关 `show_thinking` **默认关**／`loop.reasoning` **不进**编排子任务回流白名单／
> 三端**折叠块默认收起**／非流式 `__call__` 一并支持终态思考）

## Why

模型**已经具备**推理能力、其思考原文由供应商返回，但**一条链五处断**，用户在三端看不到
任何思考过程（`phase-32.md` §0 一手核实，行号见该文）：

| 落点 | 断点 | 证据 |
|---|---|---|
| E56 | provider 解析层**丢弃** `reasoning_content` | `llm_provider/models.py:59/78`（响应/增量模型无 thinking 字段）＋ `stdlib_provider.py:232/248`（只取 `content`） |
| E57 | planner 流式协议**无** thinking 通道 | `loop/planner.py:74`（`AsyncIterator[str | Action]`）／`:87/92`（只外发 `content`）／`:64`（非流式同样只取 content） |
| E58 | loop **不 emit** `loop.reasoning` | `loop/default.py:215-227`（只 emit `reply_delta`）—— 而 `ui/models.py:16` 早已**预留**该类型 |
| E59 | UI 映射**不转发** | `ui/api.py:33-41`（七类映射无 reasoning） |
| E60 | 三端**不渲染** | `ui/repl.py:69/157` ＋ `frontend/src/views/Chat.svelte` |

反向佐证：**请求侧**推理档位 `reasoning_effort` 已透传（`stdlib_provider.py:203-204`）——
即「模型思考能力已接、响应侧思考原文被丢」。

## What

按**数据面 → 事件面 → 呈现面**三切片落一条链（**全部为增量**，开关关闭时既有行为逐字不变）：

1. **数据面（E56 + E57）**
   - `LLMResponse` / `LLMChunk` 各增 `thinking: str = ""`（provider 归一化后的推理原文）。
   - `stdlib_provider` 两处映射归一 `thinking`：`message`（非流式）与 `delta`（流式），
     接受**两家既有口径** `reasoning_content`（智谱 GLM 系）／`reasoning`（OpenAI 兼容）。
   - `loop/protocol.py` 增 `Thinking(delta)` dataclass item；`LLMPlanner.astream` 在**开启**时
     逐段外发 `Thinking`，`__call__`／无 `astream` 的降级分支**一并支持终态思考**（一次性全文）。
2. **事件面（E58 + E59）**
   - `loop/default.py::_reason_events` 把 `Thinking` 转 `LoopEvent("loop.reasoning", {"text": …})`。
   - `ui/api.py::_EVENT_MAP` 显式登记 `loop.reasoning`（**identity 映射**，把「透传」写成
     **有意**而非偶发）。
   - **红线**：`loop.reasoning` **不进** `orchestration/scheduler.py::_PROGRESS_FIELDS`（白名单
     封闭表外类型天然丢弃 ⇒ 思考原文**不上子任务回流通道**）；**不进**转录／记忆／日志／trace 遥测。
3. **呈现面（E60）**：三端**折叠块默认收起** —— TUI 新增 `▸ 思考` 折叠块（复用既有
   `Collapsible` 样式），Web `Chat.svelte` 渲染 `<details>` 块（增量追加同一条、终态收口），
   APP 复用同一 SPA 产物（零额外改动）。
4. **开关**：`llm.show_thinking`（yaml 子项，缺省 **`false`**；取值口径与 feature flag 同集
   —— 原生布尔与 `true/false`·`yes/no`·`on/off`·`1/0`，其余取值**校验期拒绝并阻断启动**）。
   关闭时 planner **不产** `Thinking` item ⇒ 事件面**零新增**、三端零回归。

## 影响

- **零回归（开关缺省关）**：`_EVENT_MAP` 新增一行是**identity 映射**（未登记时 `_map_event`
  本就按原类型透传）⇒ 关闭时事件面与既有**逐字一致**；`LLMChunk`/`LLMResponse` 新增字段带
  默认值 ⇒ 既有构造点、既有断言全部不动。
- **`streamed` 判据收窄**（`default.py`）：由「产出任何 `LoopEvent`」改为**只认
  `reply_delta`** —— 否则思考事件会把「已流式外发」置真、**吞掉**终态全文补发（既有
  `reply_delta` 语义不变，非流式路径仍补发）。
- **`core-agent run`（非交互快照入口）不渲染思考**：与 `loop.delta` 同处置（只打印终态
  结果），避免逐 delta 刷屏；思考回显是 TUI / Web / APP **三端**能力（见 ui 规格）。
- **无 JS 测试**：`Chat.svelte` 改动记 `doc/04-testing/test-cases.md` 手工验收项。

## 验证

- `.venv/bin/ruff check src tests` / `ruff format --check` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ 基线 1697 + 本 change 新增（provider 归一化 / planner 通道 /
  loop emit 与红线 / ui 映射 / repl 折叠 / 配置开关）。
- `openspec validate --all` ⇒ 30 passed / 0 failed（delta 并入既有 spec，cap 目录数不变）。

## 风险与已知局限

- **字段名未经线上实测**：`config.yaml` 指向 `zai/glm-5.3`，但**本机无可用的密钥解析面**
  （凭证不可物化）⇒ 无法对真端点发一次流式请求取证。故归一化按**两家既有口径并存**实现
  （`reasoning_content` 优先、`reasoning` 兜底），**不臆断单一字段名**；真端点取证列为
  `test-cases.md` **手工验收项**（ADR-0137 已知局限①）。
- **思考原文的持久面**：本 change **不新增**任何持久化路径，且断言 `loop.reasoning` 不进
  转录／记忆／日志／trace（守 change `0115` 边界）。
