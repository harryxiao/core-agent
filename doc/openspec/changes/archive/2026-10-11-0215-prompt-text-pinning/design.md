# Design 0215 — 提示词文本 pin

## 1. 缺口定位（P3）

审计（2026-10-11）确认 **9 条核心 prompt 头在 `tests/` 中零引用**：措辞是模块私有常量，
无测试锚 ⇒ 改一个约束句即静默改模型行为。既有唯一内容锚是 `tests/test_memory.py:399-449`
的 `build_prompt`（槽位 / 首尾保留 / 有界），覆盖**一条** builder 的**结构**，不覆盖**措辞**。

## 2. 设计

零 `src/` 改动；新 `tests/test_prompt_pinning.py`。两条互补的锚。

### 2.1 逐字头（9 用例）

对每条 prompt 头，**在测试里持有一份独立副本**并 `assert <module>._PROMPT_HEAD == _COPY`。
副本是**有意重复**（pin 的本质）：src 措辞一改，断言以清晰 diff 转红，逼改者**显式**确认
「这是有意的行为改动」。承重措辞逐字进副本，不只首句。

| # | 常量 | 承重措辞（副本必含） |
|---|---|---|
| 1 | `memory.extract._PROMPT_HEAD` | JSON 数组形状 / `value` 写 `<redacted>` / `ref` 只认 `coeffect:` / 给不出引用就不输出该条 |
| 2 | `memory.extract._RELATION_PROMPT_HEAD` | 三元组形状 / 谓词**必须**归入下表 / 归不入不输出 / 密钥含实体名亦不透传 |
| 3 | `memory.summarize._PROMPT_HEAD` | 保留结论·决策·未决 / 只输出更新后摘要 / 不复述过程 |
| 4 | `memory.importance._PROMPT_HEAD` | 只输出 0–1 数值 / 1 = 高度可复用 / 不解释 |
| 5 | `skills.sop._PROMPT_HEAD` | 多次成功轨迹 / 只输出编号步骤清单 / 不复述轨迹·不解释理由 |
| 6 | `skills.iteration._PROMPT_HEAD` | 现行步骤 ＋ 实际执行情况 / 针对失败给更稳健步骤 / 不复述原文 |
| 7 | `loop.planner._SYSTEM_PROMPT` | 二选一格式 / 工具 JSON **单独成块** / 不得混写 / 不得围栏包裹 |
| 8 | `orchestration.planner._DECOMPOSE_SYSTEM` | 2–6 子任务 DAG / 只输出 JSON / 不伪造依赖 / difficulty 三档 |
| 9 | `orchestration.planner._VERIFY_SYSTEM` | 只输出 JSON / 未达标准判 false 并给一句话理由 |

### 2.2 结构不变量（3 用例）

措辞之外，钉**渲染契约**（与既有 `build_prompt` 锚同口径）：

- **槽位与行前缀**：六个 builder（`build_prompt` / `build_extract_prompt` /
  `build_relation_prompt` / `build_score_prompt` / `build_sop_prompt` / `build_iterate_prompt`）
  的产物**恒以**其 `_PROMPT_HEAD` 开头；条目行以 `- ` 前缀逐条渲染。
- **模板占位符解析**：`build_extract_prompt(entries, max_facts=5)` ⇒ 产物含「最多 5 条」且
  **无** `{max}` 残留；`build_relation_prompt(entries)` ⇒ 产物**无** `{predicates}`/`{max}` 残留
  且 8 个规范谓词**全量**出现（闭合白名单是关系的可遍历性前提）。
- **节选有界**：超长正文（10× 上界）经任一 builder 渲染后，**单条**节选 ≤ 当条上界
  （`_MAX_ENTRY_CHARS` / `_MAX_STEP_CHARS`）⇒ prompt 长度不随正文爆炸。

### 2.3 反证（门禁非空过的证明）

逐条**临时改一字符**并确认转红（实测记录见 §4）：

| # | 改法 | 期望 |
|---|---|---|
| ① | `extract._PROMPT_HEAD` 的「绝不」→「请勿」 | 仅用例 1 红 |
| ② | `planner._SYSTEM_PROMPT` 删「不得用代码块围栏包裹」 | 仅用例 7 红 |
| ③ | `_CANONICAL_PREDICATES` 去掉 `related_to` | 仅结构锚 2 红（白名单不全） |
| ④ | `extract._MAX_ENTRY_CHARS` 400 → 4000 | 仅结构锚 3 红（越界不截） |

复原后 12 绿、`diff -q` 逐字节同。

## 3. 规格落点

**规格中性**（零行为改动、零 `src/` 改动）⇒ 无 spec delta；`.openspec.yaml` `skip_specs: true`
（先例 `0156` / `0189` / `0195` / `0199`）。

## 4. 验证

- 四门禁（直连二进制）；`openspec validate 2026-10-11-0215-prompt-text-pinning`；
  手工归档（规格中性 ⇒ 仅移入 `archive/`）。
- `git diff --stat src/` **为空**（零 `src/` 改动，本 change 的核心承诺）。
