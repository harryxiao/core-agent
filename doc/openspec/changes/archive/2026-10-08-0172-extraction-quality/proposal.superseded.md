# Proposal: add-extraction-topic-merge

## Why

Canonical notes 提炼的抽取端存在质量缺陷：`src/core/memory/extract.py` 只做原子化 entity→value 抽取，无主题归纳与去重合并，且存在过度脱敏误伤、截断有损、静默降级等问题，导致笔记内容碎片化、重复、不完整。

## What Changes

1. **主题聚类层**：在 entity→value 抽取之上增加主题级归并（复用 notes 层 `slug_topic` 口径），碎片事实归并到主题笔记下。
2. **同实体/同 slug 去重合并**：`extract_with` 结果按 `slug_entity` 归并，多次压缩不重复累积。
3. **收窄兜底密钥规则**：`_SECRET_PATTERNS` 长随机串规则增加白名单（URL / commit hash 形态先放行）。
4. **截断改首尾保留**：`content[:200] + "…" + content[-200:]` 替代 `content[:400]` 硬截断。
5. **解析失败可观测**：抽取条数为 0 但输入非空时记录 warn 事件（observability）。
6. **提升 max_facts 上界**：`MAX_KEY_FACTS_PER_COMPACT` 8 → 适当放宽。

## Impact

- Spec delta：`doc/openspec/specs/memory/spec.md`（提炼抽取行为）
- 代码：`src/core/memory/extract.py` 及相关测试
- 风险：低（抽取端独立于写回侧，change 0171 已单独处理写回质量）
