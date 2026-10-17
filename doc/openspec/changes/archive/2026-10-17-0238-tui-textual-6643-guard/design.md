# Design 0238: TUI 点击与流式 Markdown 换段竞态崩溃兜底

## 背景与根因

见 proposal。要点：**上游无修复可用**（issue #6643 OPEN、最新 release 8.2.8 即本仓安装版），
只能在应用侧兜底。崩溃点为 `Screen._forward_event`（`screen.py:1914`）对
`container = content_widget.parent`（已摘除段落 ⇒ `None`）的 `.region` 解引用，
异常沿 `App.on_event` 冒到崩溃处理器 ⇒ 整个 TUI 退出。

## 决策

- **D1 守卫落 `ReplApp.on_event` 边界**（用户裁决：三选一中的「App 边界守卫」）。
  `App.on_event` 是崩溃 traceback 的确切帧（`app.py:4082`）且是我们拥有的唯一层 ——
  在此包 `contextlib.suppress(AttributeError)` 即拦住整类竞态，零框架补丁。
- **D2 只收 `AttributeError`**：这是该竞态的确切异常类型；宽捕会吞掉真缺陷。
  守护锚用例钉死「`RuntimeError` 照常冒泡」（与 0231 D 系列「不吞 turn body 异常」同口径）。
- **D3 丢弃语义 = 丢该单个事件**：竞态命中时本次 `MouseDown` 不形成选择（用户再点即可）；
  非竞态路径逐字透传（守护锚钉「恰转发一次」）。`_mouse_down_offset` 已在崩溃点之前赋值，
  但后续 `MouseUp` 分支只走 `clear_selection`（无 `.parent` 解引用）⇒ 无残留态风险。
- **D4 不 monkeypatch、不关选择**：`Screen.get_widget_and_offset_at` 过滤（上游建议修法①）
  需对三方库做类级补丁（上游改名即静默失效）；`ALLOW_SELECT = False` 牺牲应用内文本选择。
  两者都被用户裁决否决。
- **D5 缺陷修复 ⇒ 无条件生效**（判例 0206/0210/0228），不设配置门。

## 改动面

| 文件 | 改动 |
|---|---|
| `src/core/ui/repl.py` | `ReplApp` 新增 `on_event` 覆写：`contextlib.suppress(AttributeError)` 包 `await super().on_event(event)` |
| `tests/test_ui_event_guard.py` | 新增 3 用例（见下） |

## 测试与反证（实测）

- **承重**：`run_test()` 内 monkeypatch `screen.get_widget_and_offset_at` 返回**从未挂载**的
  `Static`（`parent=None`，即 #6643 的崩溃形态）+ 非空 offset ⇒ 走**真实 textual 代码路径**
  在 `screen.py:1914` 抛出与用户崩溃**逐字相同**的 `AttributeError`（红锚复现截图级一致）；
  有守卫 ⇒ 存活。
- **守护锚 ×2**：正常事件恰转发一次（守卫透明）；`RuntimeError` 照常冒泡（不吞真缺陷）。
- **反证**：摘除 `on_event` 覆写 ⇒ **1 红**（承重；两守护锚恒绿——它们不依赖守卫存在，
  语义为「无吞 / 无重派」）；`cp` 复原 ⇒ md5 逐字节同（`4db7529d…`）⇒ 3 passed。

## 局限

① 守卫按异常类型收口，`AttributeError` 若在未来由**其他** textual 内部 bug 产生也会被吞
（今日该路径上任何 `AttributeError` 都是整应用崩溃，吞事件严格优于崩溃；且不进任何日志面）。
② 不修 MouseMove/MouseUp 分支的同形解引用 —— 同一 `on_event` 边界已一并覆盖，无需独立处理。
③ 上游修复落地后本守卫自然变成空转（不冲突、不必拆）。
④ 承重用例以「从未挂载的 Static + 假命中」模拟竞态，非 compositor 真竞态时序
（真竞态无法确定性构造；模拟的是**崩溃形态** —— `parent=None` + offset 非空 —— 与真实逐字一致）。
