# Design 0195 — 长任务端到端门禁

## 1. 缺口定位（P3）

| 链路 | 既有锚 | 缺口 |
|---|---|---|
| 压实 → 注入 | `test_loop.py` 只断言记忆态；`test_history_replay.py` 手播摘要 | **两端分离**，无「产物进下一轮 prompt」的锚 |
| 越界首尾保留（`0193`） | `_elide_summary` / `build_prompt` 单元层 | **装配路径**无锚 |
| 解耦（`0194`） | `ctx.summary_long` 对象层 | **装配后 prompt** 无锚 |

## 2. 设计

### 2.1 真材实料（不引入 mock 泄漏）

用**真** `DefaultLoop` + **真** `MemoryStore`（假摘要器离线）+ **真** `TranscriptStore` +
**桩** `LLMProvider`（捕获装配后请求）。桩 provider 只做「记录请求 + 返回定稿回复」，
不模拟推理；摘要器为纯本地函数（不触网）⇒ 零三方依赖、零网络。

### 2.2 三条锚

1. **压实产物 → 下一轮 system prompt**：turn1 以 `token_budget=1` 触发**轮内压实**
   （`Compactor(step_threshold=100)` ⇒ 步数维度不满足，走预算维度），`memory.compact(session_id="s1")`
   产出 `compaction.summary.s1`；turn2 复用同一 loop/memory ⇒ 断言 system prompt 含该产物字串。
2. **越界尾部 → 摘要器 prompt**：捕获 `build_prompt(entries)`（包在假摘要器里）⇒ 断言
   投喂摘要器的既有摘要槽含**尾部锚点**与**中略标记**。
   **锚点位置订正**：`_elide_summary` 约束的是**摘要器 prompt**（压实**输入**），
   **不是**循环注入 system prompt 的内容（后者逐字注入既有摘要，只受预算记账约束）——
   初版用例误把锚点放在注入面，实测证明注入面是**逐字**的，已订正。
3. **关历史回放 → 摘要仍进 prompt**：`history_turns=0` + 既有摘要 ⇒ 断言装配后 system prompt
   含摘要块 **且** 历史原文不回灌。

### 2.3 反证（门禁非空过的证明）

端到端门禁的最大风险是**空过**（无论实现如何都绿）。逐条**临时回退**目标行为验证转红：

| 锚 | 回退手法 | 结果 |
|---|---|---|
| ① | `_compact` 内 `memory.compact(...)` → `pass` | 转红（摘要不产出） |
| ③ | `_elide_summary` 改回 `content[:MAX_SUMMARY_CHARS]` 纯头截断 | 转红（尾部消失） |
| ④ | `_load_summaries` 恢复 `history_turns <= 0` 闸 | 转红（摘要不注入） |

复原后全绿 ⇒ 三条锚**均能咬住**其目标行为。

## 3. 规格落点

**规格中性**（零行为改动）⇒ 无 spec delta；`.openspec.yaml` `skip_specs: true`（先例 `0156` / `0189`）。

## 4. 验证

- 四门禁（直连二进制）；`openspec validate` → 手工归档（规格中性 ⇒ 仅移入 `archive/`）。
- `git diff --stat src/` **为空**（零 `src/` 改动，本 change 的核心承诺）。
