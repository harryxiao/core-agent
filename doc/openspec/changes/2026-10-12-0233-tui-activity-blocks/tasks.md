## 1. Specification
- [x] 1.1 写入 `specs/ui/spec.md` delta：MODIFIED「思考过程回显」TUI 缺省收起；MODIFIED「TUI 步骤块」缺省收起 + 友好标题语法（Read/Write/Edit/Delete、Bash()/SubAgent()/Planner()、无 ⏺）+ 动态标题 + 灰显折行；必要时 ADDED/MODIFIED 场景覆盖 `loop.reasoning.round`。
- [x] 1.2 `openspec validate`（本 change）与 `openspec validate --all` 相关项全绿。

## 2. Tests（先红）
- [x] 2.1 标题格式：`format_action_event` / `_action_title`（或后继）对 file_read/write/patch/code_run/delegate **不含** `⏺`；Bash/SubAgent 带括号摘要；无摘要时 `Bash()` / `SubAgent()`。
- [x] 2.2 Thinking：开启回显时新建块 **`collapsed=True`**；同 `round` 增量归并同一块；新 `round` 新块。
- [x] 2.3 工具块：`action_started` 创建即收起；`action_completed` 更新标题耗时/失败且正文可展开；正文 class 为 muted/灰显口径可测。
- [x] 2.4（若补 round）`loop.reasoning` 载荷含 `round`；缺 round 时降级不丢文本。

## 3. Implementation
- [x] 3.1 `repl.py`：友好名表 + 标题生成；去掉 ⏺/▸ 主标识；Thinking/Tool 默认 `collapsed=True`。
- [x] 3.2 `repl.py`：ActivityBlock / 按 round 归并 Thinking；Thinking 标题不刷原文（`Thinking`/`Thinking…`）；正文折行 CSS。
- [x] 3.3 必要时 `loop/default.py` 或 `ui/api.py`：reasoning 事件补 `round`。
- [x] 3.4 编排 `plan_ready`（及同类）呈现为 `Planner(...)`；`tools.delegate` → `SubAgent(...)`。

## 5. Task 壳（回合活动组）— **已撤回**
- [x] 5.1–5.4 曾落地方案 A；产品反馈不友好后撤回。
- [x] 5.5 去掉 `Task` 壳：活动块改回直接 `_add`；规格 REMOVED；相关测试删除/回退。

## 4. Gates & Archive
- [x] 4.1 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`（相关 + 全量策略按仓规）。
  - ruff/pyright 全绿；pytest 本机 Windows 8 红（`ci_cd` 路径分隔符 / `geteuid` / `SIGKILL` / sidecar / durability 时间窗），与 0233 无关。
- [ ] 4.2 `openspec validate --all`；归档本 change；台账/ADR 按仓规回填；提交
      `feat(ui): TUI 活动块 — Thinking 默认收起、友好标题与 Task 壳（change 0233）`。
