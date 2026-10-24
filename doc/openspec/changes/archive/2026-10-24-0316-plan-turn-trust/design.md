# Design — 计划轮可信度与可打断性（0316）

## 1. 证据链（实测，本机进程 3460710）

| 时刻 | 证据源 | 事实 |
|---|---|---|
| 11:29:39→11:29:50 | `traces.jsonl` | 勘察轮执行完毕，回复即「无法执行…建议安装 arxiv-mcp-server」 |
| 11:29:50 | `messages.jsonl` / `memory.audit.jsonl` | 轮末记忆写回正常（轮次确实收束） |
| 11:35:19 | `traces.jsonl` | 批准后自跑：3 次 `tools.web_fetch` 访问 arxiv.org，`loop_finished` |
| — | `checkpoints.jsonl` | 被批准计划唯一子任务的 `goal` == 「原始目标 + 【只读勘察结论（供拆解参考）】 + 勘察原文」 |
| — | `/tmp/llm_probe.py` | provider 健康：简单补全 2.2s；拆解补全 27.0s（2234 字符） |

结论：不存在死锁或供应商故障；三处缺陷均为**语义/呈现**缺陷。

## 2. 根因与决策

### A. `tools.list` 口径（`src/core/tools/install_tools.py`）

`list` 属**插件安装工具**族，语义就是「已安装插件清单」；但它与「可用工具」在模型眼里是
同一概念。规格要求列出已安装插件，**不要求**扩展成工具全集（那会泄露完整工具面且与
`tool-use` 既有边界冲突）。

- **决策**：描述改为「列出**已安装插件**清单（不含内置原子工具）」，载荷追加静态
  `note`：内置原子工具（`tools.web_fetch` / `tools.code_run` / 文件工具等）与插件安装
  状态无关，始终按系统提示「可用工具」可用；清单为空不代表无可用工具。
- **被拒**：① 把 `installed` 改名（破坏既有载荷契约）；② 返回全量工具面（超出本工具
  语义、扩大模型可见面）；③ 在勘察 prompt 里加硬编码纠偏（治标且把口径散到 prompt）。

### B. 草案归一拆解器回落（`src/core/orchestration/scheduler.py::draft_plan`）

`LLMSubtaskPlanner.__call__` 在 LLM 错误或 JSON 不可解析时回落 `_fallback(goal)` —— 单子任务
且 `goal` **等于送入的整段文本**。`draft_plan` 把「原始目标 + 勘察结论」送入拆解，回落值因此
把勘察结论带成了子任务指令。0313 规格已写「`goal` SHALL 精确等于原始目标」，但只覆盖顶层
`goal` 字段。

- **决策**：`draft_plan` 在 `len(subtasks) == 1` 且该子任务 `goal.strip() == text.strip()` 时，
  把子任务目标还原为原始 `goal`。判定是**精确相等**（回落定义），正常拆解出的子任务目标不会
  与整段送入文本逐字相同，故不误伤；顶层 `goal` 还原逻辑不变。
- **被拒**：① 草案遇到回落直接 `UI_PLAN_DRAFT_FAILED`（把可执行任务判死，违反
  「执行路径多轮工具调用仍可推进」的回落设计）；② 在 `LLMSubtaskPlanner` 里加 draft 专用参数
  （拆解器不认识草案语义，职责错位）。

### C. 拆解阶段可见（`src/core/ui/api.py` / `repl.py`）

`run_plan_turn` 在勘察 stream 结束后**直接** `await draft_plan(...)`，无阶段事件；TUI 状态行
停在「只读勘察中」，用户无法区分「还在勘察」与「正在拆解」。

- **决策**：拆解前产出 `Event(type="plan.drafting")`（无载荷，纯阶段信号）；TUI 收到后
  `_spin_start("拆解计划中")`。事件面**只增不改**：既有 `loop.*` 与 `plan.draft_ready` 顺序
  不变（drafting 只插在两者之间）。
- **被拒**：复用 `plan.draft_ready` 加 phase 字段（语义混淆、破坏既有载荷形状）。

### D. `Ctrl+B` 打断本轮（`src/core/ui/repl.py`）

现状 `action_barge_in` 只做 TTS barge-in 提示；`ui` 规格明文「Ctrl+B 打断（停本轮）与
Ctrl+Q 退出（结束进程）语义 SHALL 保持分离」，场景「仅打断本轮（进程继续运行）」。

- **决策**：登记 `self._turn_worker`（计划轮 / 快速轮 / 神兽轮三个 `run_worker` 调用点），
  `action_barge_in` 分支：
  1. 计划草案 y/n 待决 ⇒ `_plan_future.set_result(False)`（等价 `n`：丢弃草案、回 `quick`，
     随后提示「已放弃计划」）；
  2. 存在在途轮 worker（未结束）⇒ `worker.cancel()`（轮次收尾走既有 `finally`：忙态复位、
     尾段固化、轮次分隔），并提示「已打断本轮（Ctrl+Q 退出）」；
  3. 否则 ⇒ 既有 TTS barge-in 行为逐字不变。
- **为什么取消 worker 足够**：`_run_turn` / `_run_plan_turn` / `_run_beast_turn` 的 `finally`
  都会 `_end_turn()`（忙态复位不变式，change 0231）；Textual `Worker.cancel()` 在下一次
  `await` 点投递 `CancelledError`，worker 状态即时转 `CANCELLED`。
- **被拒**：① 只做「无可中断时提示」（用户真正需要的是停本轮）；② 引入新的 asyncio 取消脚手架
  （Textual worker 已提供）；③ Ctrl+B 直接丢弃整轮输出（规格要求收尾保字，`flush_live` 不变）。

## 3. 规格映射

| 变更 | 规格 |
|---|---|
| A | `tool-use` MODIFIED「插件安装工具」+ 场景「空插件清单不误导模型」 |
| B | `orchestration` MODIFIED「计划草案产出」+ 场景「回落计划不把勘察结论当指令」 |
| C | `ui` MODIFIED「会话级执行模式与计划审批」+ 场景「拆解阶段可见」 |
| D | `ui` MODIFIED「TUI 退出及时性」+ 场景「打断在途轮次后输入恢复 / 打断待决草案 / 空闲 barge-in 不变」 |

## 4. 测试与反证

- 红→绿：`tests/test_install_tools.py`（载荷附注）、`tests/test_self_run.py`（回落归一 +
  正常计划不误伤）、`tests/test_plan_mode.py`（drafting 先于草案产出）、`tests/test_repl.py`
  （Ctrl+B 取消在途轮 / 丢弃待决草案 / 空闲不变）。
- 反证（`cp` 到 `/tmp` + `md5sum` 复原）：去掉 `note` ⇒ 载荷用例红；去掉回落归一 ⇒ 归一用例
  红；去掉 `plan.drafting` ⇒ 顺序用例红；`action_barge_in` 恢复仅提示 ⇒ 打断用例红。
