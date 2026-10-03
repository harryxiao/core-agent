# Tasks

## 1. 规格契约（P0）

- [x] 1.1 MODIFIED loop/spec.md「异步流式执行」：五类→七类 + 场景「工具动作事件」
- [x] 1.2 design.md 载荷定稿（round/tool_id/args/ok/duration_ms/output 节选 400）

## 2. loop 实现（P0）

- [x] 2.1 default.py：非终止动作执行前后发 action_started/action_completed
- [x] 2.2 duration_ms 计时 + args/output 节选常量 `_MAX_ACTION_EXCERPT = 400`
- [x] 2.3 tests/test_loop.py：事件顺序/载荷/终止动作不产出/审批拒绝落 ok=false

## 3. UI 链路（P1）

- [x] 3.1 api.py `_EVENT_MAP`：action_started/completed → loop. 前缀
- [x] 3.2 repl.py `format_action_event`（CLI/TUI 共用单行文本）
- [x] 3.3 repl.py TUI 动作行：⏺ Collapsible 单行 + 完成态 ✓/✗(耗时) + 展开区 args/output
- [x] 3.4 entry.py `_stream`：CLI 动作行单行打印
- [x] 3.5 tests：ui 映射断言 + repl 动作行生命周期
- [x] 3.6 接口文档：loop-interface 事件面七类、ui-interface §1.1 两行替换

## 4. 门禁与归档

- [x] 4.1 四门全绿（ruff check/format、pyright、pytest）
- [ ] 4.2 openspec validate → E2E 冒烟（工具动作行 + 展开）→ archive
