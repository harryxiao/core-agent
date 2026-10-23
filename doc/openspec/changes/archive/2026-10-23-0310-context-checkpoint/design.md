# Design — 上下文淘汰的情景检查点（0310）

## D1 淘汰的定义：滑出「保留窗口」

每轮 `perceive` 的三层滑窗口径（`DefaultLoop._window_plan`）：

| 带 | 判据 | 去向 |
|---|---|---|
| 短带 | 末 `short_turns` 轮（按 `short_tokens` 从新到旧截断、丢开头孤儿 assistant 行） | 原文回灌 |
| 中带 | 紧邻短带之前的 `mid_turns` 轮（不截断） | 中层摘要（`_materialize_mid`） |
| **淘汰** | **短带 ∪ 中带之前**的转录行 | **本 change：写 `context_checkpoint`** |

保留窗口首行下标由**单一真源**给出：`TranscriptStore.evicted_prefix()` 复用 `window()` 的
切分与 `_truncate_newest()` 的 token 截断语义（中带非空 ⇒ 首行即中带首行；否则取短带截断后
的首行）。一次读取同时返回「首行下标 + 之前全部行」，避免为算边界再读一遍。

**为什么不在 `_compact` 里写**：压实输入是**本轮** `ctx.messages`（多轮历史由滑窗与记忆压实
承载，`_compact` 已明确不折入历史）⇒ 压实看不到被淘汰的历史轮。淘汰是 `perceive` 的切分结果，
写入点必须与切分同地同源。

## D2 水位：`(logId, seqFrom, seqTo)`

- `logId` = `session_id`（转录单店 + `session_id` 列，会话即日志身份）；
- `seq` = 该会话**转录行序**（`read(session_id)` 的下标，派生值）；不新增落盘列 ——
  追加是原子的，行序跨进程稳定，坏行由既有 `_all()` 跳过（同一派生口径 ⇒ 自洽）。
- 已写水位 = 本会话 `context_checkpoint` 条目的最大 `seq_to`（`MemoryStore.checkpoint_watermark`）。
- 只写 `[watermark+1, retained_from-1]`；区间为空 ⇒ 零写入。

**水位单调性**：getter **不过滤** layer / status / forgotten —— 检查点被遗忘迁 L4、被保留期
墓碑化（`0309`）后标签仍在，必须继续计入；否则水位回退会把同一区间重复回写。

## D3 记录形状

```text
id        = context_checkpoint.<session 或 "default">.<seq_to>
layer     = L2
kind      = episodic            # SDD §4.2 eventType=context_checkpoint ⇒ 情景记录
source    = context             # 系统管道派生产物（importance 闸门豁免面）
trace_id  = 同 id               # 可整条回滚（write 的可逆效应）
tags      = ["context_checkpoint", "seq_from:<n>", "seq_to:<m>", "artifact:<path>"...]
content   = 有界摘要（见 D4）
session_id= 本会话
```

**为什么 `kind="episodic"`**：SDD 的 `context_checkpoint` 是 episodic 记录；这也让检查点自动
进入既有压实材料（`_episodic_groups`）与情景归纳 ⇒ 后续可被巩固器晋升（§6.7 Tier 3 的
「随后可被巩固器晋升」），无需新流水线。副作用（参与 L2 软上限 / 保留期墓碑化）与普通情景
记录一致，是期望行为。

## D4 摘要：确定性抽取 + 脱敏 + 有界

```text
会话检查点 seq A-B（N 行）
- user: <content 截断 120 字符>
- assistant: ...
```

- 写前 `redact_secrets`（记忆红线：密钥只引用不读取）；总长 `_CHECKPOINT_MAX_CHARS = 800`，
  超出按尾部截断（头部水位行恒在）。
- 原文**不复制**进检查点：转录日志仍是原文真源，检查点只承载摘要与指针（§4.5）。
- **拒绝 LLM 摘要**：`perceive` 是每轮热路径，模型往返会拖慢轮首、离线不可测；且失败面
  会扩大到模型端点。确定性摘要满足 A5 的「摘要 + 水位 + 工件引用」。

## D5 工件引用：转录行可选列

```text
TranscriptStore.append(session_id, role, content, *, created_at=None, artifacts=())
  record["artifacts"] = list(artifacts)      # 仅非空时写入 ⇒ 旧格式行逐字不变
```

- 来源：轮末 assistant 行登记本轮 `tools.file_write` / `tools.file_patch` 的 `args.path`
  （工件 = 被产出/修改的 workspace 路径；读文件不算工件），去重、每轮 ≤ 8、单路径 ≤ 200 字符。
- 检查点聚合区间内全部行的 `artifacts`：去重（保序）、总计 ≤ 16，写入 `artifact:<path>` 标签。
- 无引用 ⇒ 不写 `artifact:` 标签（不伪造）。

## D6 门控与失败隔离

写入点：`perceive`，顺序为「读摘要 → 算计划 → 读历史 → **写检查点** → 建上下文 → 追加本轮
user 行」（先于本轮追加 ⇒ 本轮永不被判为淘汰）。

零写入条件（任一）：开关关 / 未注入转录 / 未注入记忆 / 会话为空 / `plan.short_turns <= 0`
（`history_turns=0` 回放关闭 ⇒ 无保留窗口，避免每轮把全量历史当「淘汰」）。

失败面：转录读、水位读、记忆写各自 `try/except` ⇒ `warnings.warn` 并跳过本次，**不阻断本轮**
（SDD §5.1 捕获失败只告警）。记忆写返回 `None`（被闸门拒收等）⇒ 无异常，水位不前进 ⇒ 下轮
重试同一区间（at-least-once + 确定性 id ⇒ 落库幂等，`0306`）。

## D7 防重

- 水位 + 确定性 id 双重防重：同区间重放 ⇒ 区间为空（水位已前进）或同 id 同载荷（`0306` 幂等
  重放，零落盘/零效应）。
- 跨进程并发：两进程可能算出同一区间，同 id 同载荷写 ⇒ 后到者幂等重放；内容由转录行确定，
  不存在不同载荷的同 id（行序稳定）。

## D8 配置三面

| 面 | 值 |
|---|---|
| ConfigSpec | `memory.context_checkpoint` / `--memory-context-checkpoint` / `CORE_MEMORY_CONTEXT_CHECKPOINT` |
| 缺省 | `True`（kill-switch 语义，同 `memory.audit_log`） |
| 非法值 | 非 bool 字符串归一为**开**（`_FEATURE_FALSE` 集合外 ⇒ 开；笔误不得静默关闭） |
| 未加载配置 | 访问器返回 `True` |
| 直接构造 | `DefaultLoop(context_checkpoint: bool = False)` ⇒ 既有单测/嵌入方逐字不变 |

## D9 可观测性 / 可逆性

- 检查点写入走 `MemoryStore.write` ⇒ 既有可撤销效应（`_undo_write`），trace id 可回滚。
- 不新增 trace 事件、不新增配置键以外的可观测面；`compaction` / `maintenance` 的 payload
  逐字不变（不把检查点塞进既有步骤）。
- 审计（`0308`）：检查点写入按既有 `op="write"` 记元数据（不记正文）。

## D10 被拒方案

| 方案 | 理由 |
|---|---|
| LLM 摘要（复用 `summarize_slice`） | 每轮热路径同步模型调用；离线不可测；失败面扩大 |
| 转录落 `seq` 列 | 改历史文件格式 + 跨进程计数竞态；行序派生已足够且无写入成本 |
| 把检查点写进 `TurnCheckpoint` 回调 | 契约是「外发不落库」，且回调不带转录水位 |
| 每次回写整个淘汰前缀 | O(n²) 内容冗余；水位 + 增量区间语义更准 |
| 异步巩固器 / 晋升流水线 | 超出 P2-4 验收面（A5 只要求检查点存在且带水位/工件） |
