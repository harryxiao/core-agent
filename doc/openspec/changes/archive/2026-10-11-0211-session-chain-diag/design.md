# Design 0211 — session_chain 读侧进只读诊断面

## D1 为什么落 `core.diagnostics` 而非 `core.memory` / `core.ui`

诊断包是 0162 立的**只读诊断源**（`doctor` / `status` / 六张列表视图的**单一**产出方，
「SHALL NOT 各写一份检查逻辑」）。`session_chain` 是**读取面**、无行为开关 ⇒ 它属于「呈现」而不属于
「能力」：加在 `memory` 包内会多一个无人消费的公开方法；加在 `ui` 包内则 CLI 侧拿不到（且 `ui`
反向引用 diagnostics，写进去即成环）。故落 `views.py`，与 `render_sessions` / `render_notes` **同形**。

## D2 句柄是**可调用**而非 store 对象

`Deps` 的既有惯例是**注入可调用**（`SessionsHandle = Callable[[], list[dict]]`，`deps.py:30`），
理由是诊断包**不引 `core.ui`**（`ui` 反向引用本包 ⇒ 互相引用成环）。本 change 沿同一惯例：
`chain: Callable[[str], list[ChainNode]] | None` ⇒ 注入的是 `runtime.memory.session_chain` **本身**
（一个 bound method），诊断包只认**签名**，不认实例。

`ChainNode` 是 `core.memory` 的公开类型（`memory/__init__.py:68` 已导出）—— 为**类型标注**引入该
import 是允许的（`diagnostics` 与 `memory` **同属** `CAPABILITY_MODULES`，
`tests/test_architecture.py:63-90`；`deps.py` 早已 import `core.notes` / `core.skills`）。
被禁止的是 import `core.runtime`（组合根唯一性红线）。

## D3 呈现**有界**且**不含正文**

- `ChainNode` 契约刻意**不含正文**（`store.py:121-125`「本类不得成为第二条注入通道」）⇒ 视图天然
  只有链路语义（`ts` / `trace_id` / 失败 / `after`），**不需要**再设脱敏闸。
- **有界**：单会话只取**最近** `_MAX_CHAIN_ROWS = 20` 节（`nodes[-20:]`）。理由同 `0210` 的文档数
  上限 —— 只读视图的输出会**整体进时间线块**，长会话的链可以无界增长；「最近 N 节」是诊断视角的
  正确默认（最新状态最有用）。
- **按会话分组**：链的语义是**会话内**的（`after:` 只指向**同会话**前驱）。分组来源用**既有**
  `Deps.sessions` 句柄（`_diag_deps` 恒注入 `SessionRegistry(...).list`）⇒ 零新增管线；
  会话面缺失（某调用方只注入了 `chain`）⇒ 退回**不过滤**的一节（`session_id=""`）。

## D4 呈现不引入新的副作用路径

`session_chain` 走 `_all_entries()`（冷区 + 热区）而**非** `read()` ⇒ 不触发 `_reinforce`。
本 change **不触碰** `memory` 包任何一行 ⇒ (f) 的零效应保证由既有实现**原样**承载；
新视图只是**消费方**。测试以「调用前后 store 无写入效应 + `reuse_count` 不变」为锚（承规格 Scenario）。

## D5 为何不扩 `ChainNode` 带 `session_id`

规格 (f) 钉的节点字段是 `id / trace_id / ts / failed / after`；`ChainNode` 是 `0202` 交付的**不变量
载体**（写侧标注与读侧重建立在那里）。为一张**只读视图**去改类型契约 = 把呈现需求反向渗进能力层，
且 `0202` 的 (f) 会不得不重写。改用**已有的** `Deps.sessions` 分组即可取得同一效果 ⇒ 类型零变更。
（若未来出现**第二个**消费者需要节点自带会话维度，再单独立 change 改 `ChainNode`。）

## D6 已知局限（如实记）

- **`/chain` 无参数**：只读命令族（0163）的 `handler` 直分发**无参数面** ⇒ 只能看「全局各会话的
  最近 N 节」；按会话钻取需带参命令（未做）。
- **只呈现**：视图不提供跳转到条目正文的入口（`fetch_detail` 类能力不在本 change）。
- **CLI 侧无独立子命令**：`render_chain` 由 TUI `/chain` 消费；CLI 没有 `chain` 子命令
  （`_diag_deps` 的句柄在 CLI 入口同样被注入 ⇒ 未来加子命令是**一行**）。
