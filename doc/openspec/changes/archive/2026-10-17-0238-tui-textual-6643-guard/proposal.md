# Proposal 0238: TUI 点击与流式 Markdown 换段竞态崩溃兜底（textual#6643）

## 为什么

用户实跑（Windows `D:\work\AI\core-agent`）报 Textual 崩溃：
`textual/app.py:4082 on_event → screen.py:1914 _forward_event → AttributeError:
'NoneType' object has no attribute 'region'`（locals：`container=None`、
`content_widget=MarkdownParagraph(name='paragraph_open', classes='level-0')`、
`event=MouseDown`）。

根因在**三方库 textual**（上游 issue [Textualize/textual#6643](https://github.com/Textualize/textual/issues/6643)，仍 OPEN）：

- 本仓 TUI 流式回复以 `_tail_widget.update(text)`（`repl.py`）合帧热更新 Markdown ——
  正是该 issue 报告的触发方式（issue 下另一用户：流式 `Markdown.update()` 期间点击表格头，同崩）。
- `Markdown.update()` 换段瞬间，旧 `MarkdownParagraph` 已从 DOM 摘除（`parent=None`）但
  compositor 命中测试仍返回它 ⇒ `Screen._forward_event` 选择初始化里
  `container = content_widget.parent` 得 `None` 后直接解引用 `container.region` ⇒ 整应用崩溃。
- 已逐行核对安装的 textual **8.2.8**（`screen.py:1885-1920`）无 None 守卫；用户 traceback 行号与本仓
  安装副本逐字吻合。上游最新 release 即 v8.2.8（`gh` 实查）⇒ **升级不可修复**。

## 做什么

`ReplApp` 覆写 `on_event`：对 `await super().on_event(event)` 包
`contextlib.suppress(AttributeError)` —— 竞态命中时丢弃**该单个事件**（本次点击不形成
选择，用户再点即可），应用不崩；**只收 `AttributeError`**，其他异常照常冒泡
（真缺陷的崩溃语义不变，与 0231「不吞 turn body 异常」同口径）。

## 能力

- ui（**规格中性**：`ui` spec 无任何 Requirement 约束事件转发 / 鼠标选择；本 change 只把
  「三方库竞态不得杀死整个应用」收为呈现层不变式 —— 判例 `0228`/`0229`/`0231`）

## 影响

| 面 | 影响 |
|---|---|
| `src/core/ui/repl.py` | `ReplApp` 新增 `on_event` 覆写（+9 行，含 docstring） |
| 测试 | 新 `tests/test_ui_event_guard.py`（3 用例：承重 / 透传守护锚 / 非吞守护锚） |
| 缺陷修复 | **无条件生效、不设配置门**（判例 0206/0210/0228） |
| 显式不做 | 不 monkeypatch textual 内部；不关 `ALLOW_SELECT`（保留应用内文本选择）；不改流式渲染设计（0147 合帧节流不动）；不追 MouseMove/MouseUp 分支的独立守卫（同一 `on_event` 边界已覆盖） |
