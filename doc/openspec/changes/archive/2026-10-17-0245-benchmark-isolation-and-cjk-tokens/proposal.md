# Proposal — 基准会话隔离与 CJK token 估算（change 0245）

## 为什么

记忆 / evolution 全量 review 的批次 C（M4 / M8）：

1. **M4 基准执行污染全局记忆层**：`_run_bench_sample` 以 `session_id="bench"` 跑主 loop
   （`runtime.py:322-329`），会话隔离只覆盖 `read` 的会话过滤；但该 loop 的维护节拍会
   `memory.compact(session_id="bench")`，而 `_summarize_sessions` 的关键事实 / 关系 /
   episodic 派生**都以 `session_id=""` 全局层落库**，摘要提升还会写 canonical 笔记
   （`store.py:785-789`）。基准样本（合成任务）经抽取进入用户会话的全局检索面，违背
   `evolution` spec「评测基建」的既有承诺（「会话隔离，SHALL NOT 污染全局记忆层」）。
2. **M8 CJK token 低估**：共享估计器 `estimate_tokens` 与记忆读预算都用 `len // 4`
   （`context/budget.py:17-19`、`memory/store.py:43,743`）。中文约 1 token/字符 ⇒ 低估
   2–4 倍：中文会话下事实预算、历史预算与中层摘要预算实际用量远超名义值，压实触发
   与预算裁剪的事前判断失真。

## 改什么

- `MemoryStore` 新增 `ephemeral_sessions`（缺省空 ⇒ 行为逐字不变）；实现侧对**该集合内**
  的会话**只做会话级摘要与归档**，SHALL NOT 产出全局派生（关键事实 / 关系 / 情景归纳）
  与 canonical 摘要提升。组合根仅在 `features.evolution_benchmark_runner` 开启时把
  `"bench"` 传入（该路径只在执行面开启时生效）。
- 新增中性模块 `core/tokens.py`（CJK 感知估计：CJK 字符 ≈1 token/字符，其余 4 字符 ≈1
  token；空串仍至少 1），`context.budget` 与 `memory._truncate` 共用；三层窗口的
  「token → 字符」换算由 4 收到 2（review 建议的中日韩混合口径），避免中文摘要按 4 倍
  token 预算产出。

## 影响面

- `src/core/memory/store.py`（ctor / `_truncate` / `_summarize_sessions`）
- `src/core/context/budget.py`、`src/core/context/window.py`
- `src/core/tokens.py`（新增）
- `src/core/runtime.py`（组合根接线：`ephemeral_sessions`）
- 规格：`evolution`「评测基建」**MODIFIED**（＋1 Scenario；Requirement 正文不改）
- 测试：`test_memory.py`、`test_context.py` / `test_context_window.py`、
  `test_benchmark_runner.py`

## 不做

- 不改基准样本执行本身的**读面**（skills / SOP / notes 注入仍在，属独立隔离议题，登记局限）。
- 不改 `exclude_source_prefixes=("beast.","pet")`。
- 不引入本地 tokenizer / 第三方依赖；估算是粗估，不承诺与供应商 tokenizer 一致。
- 不调整 `margin` / 评测采样等 M6 决策面（另一批次）。
