# Proposal — 上下文淘汰的情景检查点（P2-4）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 §4.5 / §6.7 Tier 3 与走查 **P2-4**（A5 不通过）：

1. **淘汰即失踪**：三层滑窗每轮按 `plan_window` 切转录，滑出短带 ∪ 中带的轮次**直接离开
   注入面**——转录日志里还在，但记忆里没有任何记录指向它们。SDD §6.7 要求「被折叠或淘汰的
   轮次**立即**写 `context_checkpoint`：摘要 + `(logId, seqFrom, seqTo)` + 工件引用」，
   G4 把这条定义为「被上下文淘汰的内容形成情景检查点，而不是直接消失」。
2. **无水位、无工件引用**：本仓只有 `TurnCheckpoint` 回调（轮级在途/完结外发，`0214`），
   它不带日志水位也不带工件引用；转录行本身也没有 `seq` / `artifacts` 列。
3. **A5 验收不通过**：「触发淘汰后存在 `context_checkpoint`，带日志水位和工件引用」——
   当前不存在任何 `context_checkpoint` 记录。

本 change 只做**淘汰回写**：滑窗淘汰发生时写一条 L2 episodic 检查点，内容 = 有界确定性摘要，
标签携带 `(seq_from, seq_to)` 水位与 `artifact:<path>` 工件引用；原文仍留在转录日志（检查点
只承载摘要 + 指针，符合 §4.5「episodic 默认只注入摘要和证据指针」）。不做异步巩固器、不做
LLM 摘要、不改注入面。

## What Changes

- **转录行可选工件列**：`TranscriptStore.append(..., artifacts=())` 追加 `artifacts` 键
  （缺省不写 ⇒ 旧行与旧格式逐字不变）；`DefaultLoop` 在轮末 assistant 行登记本轮
  `tools.file_write` / `tools.file_patch` 的 `path`（去重、每轮有界）。
- **淘汰前缀读取**：`TranscriptStore.evicted_prefix(session_id, *, short_turns, mid_turns,
  short_tokens) -> (int, list[dict])` —— 与 `window()` **同一口径**（一次读取）给出保留窗口
  首行下标及之前的全部行。
- **水位读取**：`MemoryStore.checkpoint_watermark(session_id) -> int` —— 本会话已写检查点的
  最大 `seq_to`（无 ⇒ `-1`）；只读、零效应；**跨层跨状态单调**（墓碑 / 归档 / forgotten 的
  检查点仍计入，避免水位回退后重复回写）。
- **检查点写入**：`DefaultLoop.perceive` 在读取历史之后、追加本轮 user 行之前调用
  `_checkpoint_evicted`：只写**新增**淘汰区间 `[watermark+1, retained_from-1]`，落
  `kind="episodic"`、`source="context"`、id/trace `context_checkpoint.<key>.<seq_to>` 的 L2
  条目（写前 `redact_secrets`、有界 800 字符、行截断 120 字符）。
- **配置面**：`memory.context_checkpoint`（`--memory-context-checkpoint` /
  `CORE_MEMORY_CONTEXT_CHECKPOINT`），缺省 **`true`**（kill-switch：显式 `false` ⇒ 零写入）；
  `DefaultLoop(context_checkpoint: bool = False)` —— 直接构造逐字不变，组合根注入配置值。
- **失败隔离**：水位读 / 转录读 / 写入任一步失败 ⇒ 只告警并跳过本次检查点，**不阻断本轮**
  （SDD §5.1 捕获失败只告警）。

## 不做（非目标）

- 不做 LLM 摘要：`perceive` 是每轮热路径，模型往返会拖慢轮首且离线不可测；确定性抽取式摘要
  已满足「摘要 + 水位 + 工件引用」的验收面，原文可经转录日志按需取。
- 不做异步巩固器 / `context_checkpoint` 晋升流水线（SDD 巩固器仍是后续项）。
- 不改注入面：检查点按普通 L2 episodic 条目参与既有检索 / 压实材料 / L2 软上限 / 保留期。
- 不新增转录 `seq` 落盘列：水位取**该会话行序**（派生，跨进程稳定），避免改历史文件格式。
- 不改 `TurnCheckpoint` 回调契约。
