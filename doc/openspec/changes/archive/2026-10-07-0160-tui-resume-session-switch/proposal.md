# 0160 · TUI 会话切换（`/resume`）

## Why

用户 2026-10-07 实测诉求：TUI 里 `/resume` 应**列出会话清单**，选中后**恢复还原该会话的内容**
（承 change `0159` / E99 的同一诉求 —— 0159 只做了命令浮层，`/resume` 刻意未进表，见其「单一真源
可执行守护」）。今日 TUI 的会话只能靠**启动旗标** `--session <id>` 选定；**运行中无切换手段**，
且操作者事先无从得知有哪些会话标识可用（`list_sessions()` 已有数据，但 TUI 未消费）。

## What Changes

- **`/resume` 进命令真源**（`arg_source="session"`）：浮层二级候选取**既有** `UIAPILayer.list_sessions()`
  （显示行 = 标题 + 标识 + 最近时间），采纳后只**改写输入框**为 `/resume <标识>`（承「采纳不提交」）。
- **`/resume <标识>` 切换会话并还原内容**：清空时间线 → 复用**与 `--session` 续聊同一**的铺入路径
  （把 `on_mount` 的历史循环提成方法，两处同源）→ 复位跨会话无意义的呈现态 → 后续轮次落**新**会话。
- **`session_id` 由闭包变量改实例字段**（原按轮读取的**两处**改读 `self._session_id`）。
- `_palette_options` 增 `sessions` 参数（二级候选的**第二个**来源，与 `subtask_ids` 同构）；
  `_candidates` 按**真源登记项**的 `arg_source` 决定是否取会话面（不按字面量判命令名；无谓的
  会话面读取被挡在按键路径之外）。

## Non-goals

- **不引三方库**；不引 `Screen`/`ModalScreen`/`push_screen`（承 0159：沿 `#panel` 的 `display` 翻转惯用法）。
- **不改** 0159 的浮层交互（采纳只改写输入框、不提交；`↑`/`↓`/`Tab`/`Esc` 接管范围不变）。
- **不新增** 会话相关 api（只用既有 `list_sessions()` / `session_messages()`）；**不新建**会话（切换只切既有）。
- 不做「会话删除 / 重命名 / 新建会话」；不做 Web / Desktop 端（属另一端）。

## 风险

1. **切会话期间的重入**：切换**只允许在非忙碌时**发生（否则在途轮次与会话状态并发改写）。
   这与既有「忙态拒绝新消息」同口径（`/resume` 排在忙态检查**之后**）。
2. **半切换态（最危险）**：若「先清时间线、后读转录」，读取失败就会留下**空时间线**却仍是旧会话。
   ⇒ **先验证、后落地**：`session_messages(sid)`（未登记即 `UiError`）**先于任何状态改动**调用。
3. **悬挂句柄**：切会话后时间线子节点被销毁，`_open` / `_actions` / `_focus_box` 等持有的是**已卸载**
   widget ⇒ 必须复位（否则下一次 `update()` 落进死对象）。**焦点视图同步回主视图**。
4. **`/summon` 与 `/resume` 的前缀歧义**：`_parse_beast_command` 只认 `/summon` / `/recall`
   （按首 token **精确**判），`/resume` 不落其手；分发次序上 `/resume` 排在神兽入口**之前**，无歧义。
5. **幽灵补全的既有断言**：`/re` 今日补全为 `/recall` —— `_COMMANDS` **追加** `/resume` 于表尾
   ⇒ `/recall` 仍先命中，既有断言（`test_ghost_completion_shows_and_accepts_remainder`）零回归。
