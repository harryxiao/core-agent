# 变更提案：Web 流式增量以专类型帧推送（change 0132 / phase-34 E65）

## 背景

`coding-plan/phase-34.md` §1 登记的 **E65**（中高，用户可见）。

后端 `UIAPILayer._map_event` 把 loop 事件映射为 SSE 帧类型：`reply_delta`（流式增量）与
`loop_finished`（终态）**共用** `loop.result` 一个类型，仅靠**载荷形状**区分（增量是 dict
`{text}`，终态是 `LoopResult` 对象）。

- TUI/CLI 侧认这个约定（`ui/repl.py::_event_delta` 判「类型 = `loop.result` **且** 载荷是 dict」；
  `entry.py::_stream` 同判据跳过增量帧）。
- **Web 侧没认**：`frontend/src/views/Chat.svelte` 对每个 `loop.result` 帧取
  `payload.reply ?? payload.message ?? JSON.stringify(payload)` 并**追加一行** ⇒ 增量帧没有
  `reply`/`message`，每帧渲染出一段 **JSON 字面量**（`{"text":"你"}`、`{"text":"好"}`…），
  且增量与终态各占一行，最终回复被埋在 JSON 垃圾里。

根因是**一个事件类型承载两种载荷形状**：靠「载荷是不是 dict」这种隐式约定分流，任何新消费者
只要不照着 TUI 抄一遍判据就会踩坑（Web 就是）。违规于「类型表示载荷形状」的既有契约。

## 变更内容

1. **拆分事件类型**（`src/core/ui/api.py::_EVENT_MAP`）：`reply_delta` ⇒ **`loop.delta`**
   （专类型，载荷**恒为** `{"text": <增量文本>}`）；`loop.finished` 仍是 `loop.result`（载荷
   `LoopResult` 对象）。二者不再共型，消费方**只要判类型**即可分流。
2. **消费方对齐**（同 change，一条链不可拆）：
   - `src/core/ui/repl.py`：`_event_delta` 改判 `loop.delta`；`_format_event` 的 `loop.delta`
     分支返回增量文本，`loop.result` 分支**只**处理终态（dict 分支随共型消失）。
   - `src/core/entry.py::_stream`：非交互 CLI 跳过增量帧的判据改判 `loop.delta`（行为不变）。
   - `frontend/src/views/Chat.svelte`：`loop.delta` 帧**追加到当前 agent 行尾部**（首帧新建行，
     其后原地追加），`loop.result` 帧落终态文本 —— 与 TUI `_show_delta` / `_flush_live` 同语义。
3. **规格**：`ui/spec.md`「Web 界面访问」**MODIFIED** —— 正文补「流式增量 SHALL 以**专类型**帧
   推送（载荷为增量文本），SHALL 与终态结果帧区分；前端消费增量帧 SHALL 以**文本追加**呈现
   （SHALL NOT 逐帧新建行、SHALL NOT 序列化载荷）」，+ **1** Scenario「增量帧以文本追加（非逐帧
   JSON）」。

## 不做（明确排除）

- **不改 `LoopEvent` 层**（`core/loop` 仍产 `reply_delta`）：本 change 只改 **UI 映射层**的对外
  帧类型；loop 内部事件面不动（0145 的 `thinking` 通道另议）。
- **不引入 SSE 帧重放/断线补帧**：`SSE 断线重连` 既有 Scenario 语义不变。
- **不动 `_PROGRESS_FIELDS` 白名单**：增量帧**不**进编排里程碑回流（该红线由既有测试守）。
- **不新增前端 JS 测试基建**：Svelte 改动记 `doc/04-testing/test-cases.md` 手工验收项。

## 影响面

| 面 | 变化 |
|---|---|
| 后端 SSE 帧类型 | `reply_delta` 的对外类型 `loop.result` ⇒ **`loop.delta`**（**唯一**对外可见变化） |
| TUI / 非交互 CLI | 判据随类型更新，**呈现逐字不变** |
| Web SPA | 增量改为尾部追加（修 E65 的渲染破碎） |
| 编排进度回流 | 不变（增量本就不在白名单） |

## 验证

- 四门禁：`ruff check` / `ruff format --check` / `pyright` **0/0/0** / `pytest -q`（1620 → 1622）。
- `openspec validate --all`：active 期 31/0，归档后 30/0。
- 前端无 JS 测试 ⇒ Svelte 追加逻辑记手工验收（`doc/04-testing/test-cases.md`）。
