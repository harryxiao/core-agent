# Proposal 0273 — 里程碑报告锚定（PA-08 方案 B）

## Why

长任务的硬约束会丢：会话摘要被后续内容稀释（ADR-0208③）、零复用记忆约 19 天被归档 L4
（ADR-0170③），而阶段结论主要靠模型自觉写进摘要。仓内已有「常驻（pinned）笔记」通道——
整篇纳入、逐轮无条件注入、紧随宪法块、超预算整篇排除且可见——但**置位靠人**：要么人工
`notes pin`，要么 `notes promote`（只搬运会话摘要，不装配决策/硬约束，且显式触发才常驻）。

结果就是 PA-08 记录的现象：**忘了 pin** 等于硬约束没锚住；`promote` 的产物也不含结构化的
「关键决策 / 硬约束 / 关键事实」。本 change 走 PA-08 **方案 B**：复用 pinned 通道，新增
「里程碑报告」动词，把「人工置常驻」升级为「结构化里程碑报告 + 一键常驻」，**零新注入块**。

## What Changes

- 新增 `core.notes.close_milestone(...)`：**确定性、零 LLM** 的里程碑报告装配器。正文按固定
  次序分节：**结论 / 关键决策 / 硬约束 / 关键事实**；只输出非空节。
- 数据来源（全部可选、可组合）：
  - 显式 `conclusions` / `decisions` / `constraints` 列表；
  - `session_id` 对应的记忆压实摘要（正文并入「结论」节）；
  - 该会话的 keyfact 条目（`key_fact` 标签 + `session:<id>`，按 id 排序 ⇒ 确定性）。
- 产出 SHALL 置 `pinned=True`、`pin_priority` 缺省 **100**（高于人工 `notes pin` 的缺省 0，
  「里程碑硬约束」优先在场；可用 `--priority` 覆盖）。
- 幂等覆盖：`note_id` 由里程碑名确定性派生（`milestone-<slug>`，`--as` 可覆盖），重复收口
  命中同一篇、不增长。
- **来源守护**：派生 id 撞上来源非 `notes.milestone` 的既有笔记且未给 `--as` ⇒ 不写盘、非零退出。
- **有界与脱敏**：所有内容先经 `redact_secrets`，正文 3000 字符上限（保留头部 + 截断标记）。
- CLI `notes milestone <name> [--session SID] [--as ID] [--title TITLE] [--priority N]
  [--conclusion TEXT]... [--decision TEXT]... [--constraint TEXT]...`。
- 复用 `NoteStore.update()`（唯一写路径）；**不**新增注入块、**不**改 loop、**不**接 `EffectTracker`。

## Impact

- 代码：新增 `src/core/notes/milestone.py`；导出 `src/core/notes/__init__.py`；
  CLI `src/core/entry.py`（`notes milestone` + `_notes_milestone` + `_session_key_facts`）。
- 测试：新增 `tests/test_notes_milestone.py`；补 `tests/test_entry.py` 的 CLI 面断言。
- 规格：`notes` ADDED「里程碑报告锚定」。
- 兼容：不改变任何既有命令与注入行为；里程碑缺省优先级只影响其**自身**在场次序
  （人工笔记仍可 `pin --priority` 高于它）。

## 不做（明确边界）

- **不自动触发**：阶段结束仍由人 / 上层显式调用（与 ADR-0142①「notes 是刻意知识」一致）。
  自动推断阶段、自动写入并用未 review 内容每轮注入，与 ADR-0141① 的密钥红线冲突（PA-08 方案 C 已否决）。
- **不新增注入块**：只走既有「常驻笔记」通道（整篇纳入 + 优先级语义），不改 loop / prompt 装配。
- 不引入待办任务实体（PA-08 方案 D）、不引第三方依赖、不改 `exclude_source_prefixes`。
- 不做 LLM 摘要/归纳：报告内容只来自显式输入、压实摘要与既有 keyfact，**零模型调用**。
