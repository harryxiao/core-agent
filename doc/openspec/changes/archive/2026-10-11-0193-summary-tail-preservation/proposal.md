# Change 0193 — 滚动摘要首尾保留（尾部不销毁）+ 价值闸留痕

## Why

长任务评估取证（2026-10-11）——**滚动摘要越界即销毁尾部（结论所在）**：

1. **头截断销毁尾部**：`build_prompt`（`src/core/memory/summarize.py:48`）把既有摘要投喂摘要器时
   用 `prior.content[:MAX_SUMMARY_CHARS]` —— **纯头部截断**。长任务里摘要持续滚动增长，一旦越过
   `MAX_SUMMARY_CHARS=2000`，**尾部**（最新结论 / 决策所在）**永不再进 LLM** ⇒ 下一轮滚动合并
   产出的是「前半段 + 新事件」的摘要，尾部内容被**无声、不可逆地销毁**（长任务失忆的隐蔽来源）。
2. **越界同时是提升触发器**：`store.py:700-703`（`_deliver_promotion`）以「既有摘要首越上界」
   为交付 canonical 真相层的判据 ⇒ 修法**必须保触发语义逐字不变**（判据读**全体长度**，不受节选形式影响）。
3. **价值闸静默跳过无留痕**：`_below_gate`（`store.py:118-125`）判低价值时 `_summarize_sessions`
   直接 `continue`（`store.py:579-580`）—— 会话被跳过**无任何留痕**（运维无法判断「为何我的会话没产摘要」）。

## What Changes

- **首尾保留**：`build_prompt` 的既有摘要槽改 `_elide_summary()` —— 未越界**逐字**投喂全文；
  越界时投喂「**首部**（约 `1200` 字）＋**省略标记**（标明中略字数）＋**尾部**（约 `800` 字）」，
  总节选长度 SHALL **不超过** `MAX_SUMMARY_CHARS`（token 有界不破）。
- **触发语义逐字不动**：`_deliver_promotion` 的越界判据仍读 `len(prior.content)` **全体长度**
  （不读节选）⇒「首次越过上界交付钩子一次」行为**逐字不变**。
- **价值闸留痕**：`_summarize_sessions` 因 `_below_gate` 跳过会话时补 `warnings.warn`
  —— **只报会话键**，SHALL NOT 回显摘要 / 事件正文（承密钥红线）。
- 规格变更：`memory`「记忆压实」（节选首尾保留条款 + 价值门控留痕条款 + 2 Scenario）。

## Impact

- **改动面**：`src/core/memory/summarize.py`（`_elide_summary` + `build_prompt` 用 + 常量）、
  `src/core/memory/store.py`（价值闸跳过补 `warnings.warn`，`warnings` 已 import）；测试面
  `tests/test_memory.py`（首尾保留 / 逐字不变 / 触发仍准点 / 留痕）、`tests/test_notes_promote.py`
  （越界提升回归）。
- **零改动面**：`MAX_SUMMARY_CHARS` 常量值（仍 `2000`）；`_commit_summary` 落库**不截断**
  （承接既有语义：canonical 完整、投喂有界）；`_deliver_promotion` 逻辑；mid 摘要通道
  （`summarize_slice` 的 `max_chars` 预截断**逐字不动**）。
- **兼容性**：未越界的既有摘要**逐字不变**（`len <= MAX_SUMMARY_CHARS` ⇒ 原样返回）⇒ 既有
  滚动合并测试（用拼接 summarizer，材料短、不越界）**不受影响**。

## Non-goals

- **不**改 `MAX_SUMMARY_CHARS` 的值，也**不**新增配置键（与 `0182` 触发阈值是另一面同理）。
- **不**给 mid（中期）摘要加提升通道 —— mid 是**有界瞬态层**（`summarize_slice` 的 `max_chars`
  预截断 `store.py:477`）；canonical 逃逸由**长期摘要提升**（change `0153`）承载，本条保其
  「不销毁」后该路径成立。
- **不**改越界判据（仍以**全体长度** × `MAX_SUMMARY_CHARS` 为准）。
- **不**让价值闸留痕携带正文（密钥红线：只报会话键）。
