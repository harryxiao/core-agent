# Proposal: 失败经验的独立沉淀面 —— 轮级失败另立一条不被压实吸收的 L2 条目

> 规格：`loop` / `memory`（**MODIFIED × 2**）

## Why

用户 2026-10-10 复盘四类记忆分类（会话动态滑窗 / 语义记忆=notes / 程序记忆=技能 / 情景记忆=错误与成功经验），
问「是否有遗漏」。审计结论：**情景记忆里的「失败」没有独立沉淀面**——三处逐行取证：

1. **失败信息被压成散文、无判据。** `remember()`（`src/core/loop/default.py:738`）每轮只写两条：
   `loop.<trace_id>`（`tags=["loop","trajectory"]`，内容含 `round N failed <error>`）与
   `loop.steps.<trace_id>`（`tags=["loop","steps"]`）。失败**没有**独立 tag / 独立条目 ⇒ 无法把
   「失败」当作一类可检索对象。`grep` 全 `src/` **无任何** `fail`/`failed`/`failure`/`error` tag。
2. **一条承诺了却不存在的那条通道。** `SopExtractor.observe`（`src/core/skills/sop.py:84`）对 `ok=False`
   **直接丢弃**，docstring 自陈「教训沉淀走 **memory/evolution 通道**」——而该 memory 通道**根本没有**
   承载失败的一类条目；evolution 侧也不读 L2（`Diagnoser.diagnose` 只吃 `Trace.success`，
   `src/core/evolution/diagnoser.py:30`；`src/core/evolution/` 全树对 memory **只写不读**）。
3. **失败证据会被下一次压实吞掉。** 压实材料唯一来源 `_episodic_groups()`
   （`src/core/memory/store.py:600-612`）只按 `kind=="episodic" and layer=="L2"` 筛，**无 source / tags 判据**
   ⇒ 失败轮条目必被摘要吸收，随即由 `_commit_summary` 迁 L4（`store.py:644-645`），检索层权重由 `0.6` 降 `0.2`。

**用户已裁决**（AskUserQuestion，2026-10-10）：① 范围＝**只记轮级失败**；② 寿命＝**只豁免压实、仍走遗忘**；
③ 注入面＝**不新增系统块**。

## What Changes

1. **另立失败条目**（loop 侧）：`DefaultLoop.remember` 增三个 **keyword-only** 参数
   （`failed` / `reason` / `task`，缺省 ⇒ 逐字一致）；`failed=True` 时在既有两条之外**再立第三条**
   `loop.failure.<trace_id>`（`tags=["loop","failure"]`、`kind="episodic"`、同 `source`/`trace_id`/`session_id`），
   内容＝任务文本 + 失败原因 + 失败轮次行 + 失败动作行，**逐行脱敏 + 整体有界**。**未失败 ⇒ 不写**。
2. **压实材料豁免**（memory 侧）：新增模块常量 `_PRESERVE_TAGS = frozenset({"failure"})`，
   `_episodic_groups()` 一处 `continue` ⇒ 失败条目**不被摘要/关键事实吸收、不被迁 L4**。
   `forget()` **不动**（仍按自然衰减归档 ⇒ 有界）。选 **tag 判据**而非 source 前缀：`rank()` / `_decay_score`
   **完全不看 tags**（零排序副作用），且 `source` 是命名空间，碰它等于碰 `exclude_source_prefixes=("beast.","pet")`
   （`runtime.py:603`，phase-26 红线）。
3. **注入面零改动**：不加 planner 块、不加上下文预算记账（失败条目靠既有按相关度检索命中）。

## Impact

- **specs**：
  - `loop/spec.md`——**MODIFIED**「执行循环」（追加失败另立条目句 + 3 Scenario；既有 36 条逐字保留 ⇒ 39）。
  - `memory/spec.md`——**MODIFIED**「记忆压实」（追加材料排除 `failure` 标签句 + 2 Scenario；既有 17 条逐字保留 ⇒ 19）。
  - `skills/spec.md` **不动**：失败仍不进 SOP —— 本 change 让 `sop.py` docstring 承诺的那条 memory 通道
    **第一次真实存在**。
- **src**：`loop/default.py`（新增纯函数 `failure_digest` + `remember` 三参数 + 第三条写入 + 调用点传参）、
  `loop/protocol.py`（`remember` 签名同步）、`memory/store.py`（`_PRESERVE_TAGS` + `_episodic_groups` 判据）。
  **无新增 import、无配置键、无跨域依赖**。
- **风险**：低。成功轮路径**零扰动**（新条目只在失败时写；既有守卫与两条条目逐字不变）；
  失败条目为 L2 episodic，写入即记可撤销效应（`store.py:275-282`），按 `trace_id` 回滚即消失。
- **已知局限**（详见 `design.md` / `coding-plan/known-risk.md`）：记忆面→诊断面的桥仍缺（`Diagnoser` 不读 L2）；
  失败条目最终仍会被遗忘归档 L4；任务原文首次进入 L2 记忆面。
