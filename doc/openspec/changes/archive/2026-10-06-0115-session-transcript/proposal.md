# 提案 — 对话转录落盘与会话历史回灌（change 0115 / phase-28 E49，Change B 后端切片）

## 背景

用户原话的后半：「**webUI 右边是会话列表管理**——记录了当前已创建会话，可以选不同的会话**查看记录**
或者**继续聊天**，相互独立。也可以继续创建新会话。」（前半「会话之间内容严格隔离」已由 change `0114` 闭合。）

`0114` 让 `session_id` 成为**推理期记忆检索**的归属维度，但**多会话体验**仍缺三块，本切片解决**后端两块**：

| # | 一手事实 | 后果 |
|---|---|---|
| 1 | `loop/default.py:405-414` `perceive` 是 `ctx.messages` 的**唯一**构造点，只装 `[{"role":"user","content":user_input}]`；`planner.py:121-129` `_build_request` = 一条 system + 全部 `ctx.messages`、**零截断** | 每轮从**一条全新 user 消息**开始 ⇒ **关页面即失忆**，无法「继续聊天」 |
| 2 | 全仓**无转录存储**：`ui/sessions.py:37` 注册表条目只有 `{session_id, mode, created_at}`，**不存消息内容**；`Chat.svelte:6` 的 `lines` 是纯内存 `$state`；`api.js` 无 `listSessions` | 「查看记录」不可能，会话列表不可用（32 位 hex 不可辨、无最近活跃） |

⇒ 需要**独立的对话转录**（原始对话流）与**有界回灌**。按 SDD 规格先行。

**不可推翻的约束**（一手实证）：

- **不前置进 `ctx.messages`**：`ctx.messages[0]` 被四处当「本轮任务」（`default._task_text:86-91`、
  `default._echo:508-516`、`planner._task:180-187`），`ctx.messages[1:]` 被 `_action_steps:94-98` 当动作序列。
- **只存 (user 原话, 最终回复)**：`ctx.messages` 内含 `role="tool"` 观察（`default.py:450-461`），而
  `stdlib_provider.py:196` 是逐条 1:1 发 `{role, content}`、**不带 `tool_calls` 信封** ⇒ 回放历史 tool 消息
  给 OpenAI 兼容端点大概率 400。
- **`session_id == ""` 一律不落盘、不回灌**：既有 `DefaultLoop` 单测从不传 `session_id` ⇒ 逐字不变；
  且未归属轮不会挤进同一个 `""` 桶变成**幻影会话**。
- 不给每会话建 `(loop, memory)` 实例（phase-19 E2 / change `0048` 已裁）；不破 `exclude_source_prefixes=("beast.",)`。

## 变更目标

1. **转录持久化**（`memory/spec.md` ADDED「对话转录持久化（非记忆层级）」）：按轮追加单文件、
   带 `session_id`、按会话读取；**明写转录不是任何 L0–L4 条目**、不进 `MemoryStore.read`、
   不参与温度分层/排名/`reuse_count`/压实/固化/遗忘。
2. **收银台前的旧账**（`memory/spec.md` MODIFIED「分层记忆模型」）：canonical `:9` 写「L4（原始会话）」，
   与同文档 `:119/:131/:181` 的「**L4 归档层**」「检索优先级随之降低」及实现（`store.py:232/379` 迁 L4、
   `relevance.py:24` `"L4": 0.2` 降权）**自相矛盾** ⇒ 据实校正为「L4（归档层）」。这是引入「转录非记忆层级」的前提。
3. **有界回灌**（`loop/spec.md` MODIFIED「执行循环」）：`perceive` 载入本会话最近历史进 `LoopContext.history`
   （**新字段**，不碰 `ctx.messages`），请求按「系统提示 → 历史 → 本轮消息」组装；历史上界 =
   `min(最近 N 轮, 独立 token 切片)`，其 token 计入 `token_used`；收尾追加本轮 (user, reply)。
4. **回灌轮数可配**（`configuration/spec.md` MODIFIED「循环预算配置」）：新增 `loop.history_turns`
   （缺省 `20`，`0` = 关闭），三面可配。
5. **读取面**（`ui/spec.md` ADDED「会话转录的读取面」）：`GET /session/{id}/messages`；
   `GET /sessions` 条目附**派生** `title`/`updated_at`（不写注册表 ⇒ 无第二真源）。
6. **注册表据实收窄**（`ui/spec.md` MODIFIED「会话注册表持久化与跨入口共享」）：canonical `:200` 声称
   「并发创建不相互覆盖」，而 `sessions.py:33-40` 是**无锁**读-改-写 ⇒ 加进程内 `RLock` 并把断言
   限定为**同进程**，跨进程明确列为已知局限。

## Non-goals

- **前端右侧面板 / CLI `session show` / REPL 续聊**（→ Change B 的前端切片）。
- 会话**删除 / 重命名**；新建会话对话框。
- 子 Agent / 神兽 / 宠物 loop 的转录（只接主 loop）。
- 改检索行为（**不动** reason 阶段装配器的来源排除项）。
- `LoopResult` 增加转录字段；`GET /memory` 语义变更。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 历史自身 ≥ token 预算 ⇒ 第 1 轮立刻 `TOKEN_BUDGET_EXCEEDED`、`_should_compact` 误触发 | **独立 token 切片**（`token_budget // 2`）+ 轮数上界 |
| 落盘点被绕过（`astream` while 体无 try/except、SSE 断连 GeneratorExit） | **user 行在 `perceive` 落盘**（先于任何 `yield`），assistant 行在收尾补；两处**各自** try/except 降级，不继承 `remember` 全量重写的脆弱性 |
| 把合成终止文案当模型原话回灌 | 收尾追加**门控** `limit_reason` 为空（`default.py:283` 会覆盖 `ctx.reply`） |
| 逐字兼容被破坏 | 全部行为门控在 `session_id` 非空 + `transcript` 已注入；缺省路径逐字不变（既有 1415 测试全绿即证） |
| **既有的**历史与 L2 检索重复（`remember` 条目 `source="loop"` 同 `session_id`，装配器只排除 `beast.`） | **本 change 不修**（不改检索行为），ADR 记录为已知局限并附一行修法备查 |
| 转录单文件随会话数线性增长、读单会话需全扫；跨进程并发追加 | ADR 记录为已知局限；写入用 `O_APPEND` + 单次 `os.write` 整行（POSIX 追加原子） |
