# Design 0207 — 恢复扫描入口全覆盖

## 决策

1. **复用 `_build_ui` 的 `surface_recovery` 旗，不新造路径**：repl/run/app 三入口本就调
   `_build_ui`，加旗即可（`0191` 已为 serve 建好机制，本 change 是接线补全，非新能力）。
2. **`mcp serve` 显式补调，不走 `_build_ui`**：它自建 runtime（无 UIAPILayer 需求），故单独
   `_surface_incomplete(runtime)`。顺序放在 `build_runtime` 之后、`MCPServer` 构造之前——
   呈现先于协议就绪，用户先看到告警。
3. **stderr 单一呈现面**：`_surface_incomplete` 既有实现已是 `warnings.warn` + `print(file=sys.stderr)`
   ⇒ 对 `mcp serve` 零额外改动即满足「stdout 是协议」约束。
4. **测试锚点用桩 runtime**：`tests/test_entry.py` 既有 `_patch_fake_runtime` 模式（桩
   `runtime.recover()` 返回带 task_id 的句柄）⇒ 断言四入口 stderr 含告警 + 续跑提示。反证 =
   摘掉旗（`surface_recovery=True` → 默认）⇒ 用例红。
