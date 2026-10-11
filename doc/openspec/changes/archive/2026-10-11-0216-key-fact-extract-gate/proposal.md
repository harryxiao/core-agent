# Proposal 0216 — 关键事实抽取门控（`memory.key_fact_extract`，缺省 True）

## Why（缺口）

同族的两个相邻开关都有配置键、唯关键事实抽取**无条件常开** —— 一处**不对称**：

| 能力 | 组合根接线 | 配置键 |
|---|---|---|
| 结构化关键事实抽取（`0155`） | `runtime.py:578` **无条件** `extract_with(_llm_text)` | **无** |
| 实体关系抽取（`0203`） | `if config.relation_extract() else None` | `memory.relation_extract`（缺省 False） |
| 写入侧重要度闸门（`0181`） | `if config.importance_gate() else None` | `memory.importance_gate`（缺省 False） |

关键事实抽取是**每次压实都跑一次模型**的能力（烧 token），却**无法关闭**；运维无法在不需要
结构化事实的场景（如纯对话会话）里省下这次调用。缺口 = **缺一个 kill-switch**。

## What Changes

新增配置键 `memory.key_fact_extract`（**缺省 `True`**）＋ 组合根接线闸 ＋ 规格末句扩写 ＋
新访问器 `key_fact_extract()`。

**缺省 True 的论证（ADR-0206 必写）**：本键是**既在用能力的 kill-switch**，**非** opt-in 新能力。
翻缺省为 False 等于**静默删除一个在用能力**（非缺陷修复）⇒ 违反「缺省关 ⇒ 逐字不变」纪律的**初衷**
（该纪律保护的是**既有行为不被新特性改变**，而非让既有能力默认消失）。
**字节不变**：缺省 True ⇒ 恒走原分支 `extract_with(_llm_text)` ⇒ 与今日逐字等价。
**非法取值回落 True**：一次拼写错误**不得**静默停用在用能力（方向恒为「保守 = 保持能力」）。

## Impact

- **代码**（`src/`）：`configuration/manager.py`（新 ConfigSpec ＋ 新访问器 `key_fact_extract()`）、
  `runtime.py:578`（`... if config.key_fact_extract() else None`）。
- **规格**：`memory` **MODIFIED**「结构化实体抽取（关键事实）」末句扩写为「未注入抽取器**或配置关闭**」，
  **既有 15 Scenario 逐字保留** ＋ **ADD Scenario ×2**。
- **测试**：+8（`tests/test_key_fact_gate.py`），基线 2433 → **2441**。
- **不做**：不补会话摘要 / SOP / 编排 / RAG 的同类门控（用户裁决「只补关键事实抽取」）；不改
  `memory` 段的**非结构化**口径（非法取值不阻断启动）；不动任何脱敏 / 有界 / 落库判据。
