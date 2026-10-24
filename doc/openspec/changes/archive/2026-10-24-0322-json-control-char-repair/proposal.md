# Proposal — 退化 JSON 的控制字符修复（change 0322）

## Why

2026-10-24 15:28，后台子 Agent（任务 `bg-77cd2045c223`，实施 change 0305）在第 20 轮失败
（trace `fe9f78fd…`）。模型交出的动作对象**结构完整**，但 `script` 字符串值里**原样**写入了
换行（多行 heredoc）：

```json
{"tool_id": "tools.code_run", "args": {"cwd": "…", "script": "grep …; python - <<'EOF'
from core.memory.store import MemoryStore
…
EOF","type": "bash"}}
```

JSON 字符串不允许裸控制字符（U+0000–U+001F，此处 4 个 `\n`），`json.loads` 报
`Invalid control character`。change 0321 的字面量修复只处理**非法反斜杠转义**与**未转义内引号**，
不改变裸控制字符 ⇒ 修复不采纳，整轮仍落到 `LLM_PLAN_PARSE_FAILED`。`loop.parse_retry` 缺省关，
第 20 轮的 19 轮工具结果全部白费。

该形态与 0321 同类：意图完全确定（模型想执行的就是它写出的多行脚本），确定性修复比再发一次
模型调用更便宜，也无语义歧义。

## What Changes

- **A. 控制字符转义**：确定性字面量修复的单遍扫描在字符串内额外处理**裸控制字符**
  （`ord(char) < 0x20`）：`\n` `\r` `\t` `\b` `\f` 改写为对应 JSON 转义，其余 `< 0x20`
  改写为 `\u00XX`；解码后的字符串值逐字保留原字符。
- **B. 既有边界不变**：采纳门槛（可解码为 dict 且含非空 `tool_id` 或 `reply`）、结构不补全、
  不删改非控制字符、先于 `loop.parse_retry`，全部沿用 change 0321 / ADR-0311。

## Impact

- 代码：`src/core/loop/planner.py`（`_repair_string_fragment` 增加一支 + 一个常量）。
- 规格：`loop`「推理动作解析与失败可见」MODIFIED（修复规则补控制字符 + 2 条 Scenario）。
- 测试：`tests/test_degenerate_json_repair.py` 增加事故复刻与合法转义零影响用例。
- 配置：**零新键**。

## Out of Scope

- 不处理未闭合 / 截断（维持既有失败语义）；
- 不做通用 JSON5 / 容错解析器；不改 `loop.parse_retry` 缺省值；
- 不处理 U+007F DEL 等非 JSON 字符串合法但罕见的字符（JSON 允许，`json.loads` 亦可解码）。
