## Why

记忆与 evolution 全量 review 的**批次 B（prompt 对齐）**暴露两类「提示词与执行口径不一致」：

1. **摘要 prompt 与落库上界不一致**：摘要 prompt 要求「总长不超过 800 字」，而滚动合并上界
   `MAX_SUMMARY_CHARS = 2000` —— 模型被要求产出远小于可承载上限的摘要，长任务的最新结论更易被
   压缩丢失。
2. **抽取 prompt 名额与落库名额不一致**：关键事实 / 关系的落库名额已随会话长度自适应
   （`key_fact_cap(n)`，8~16），但注入的抽取器工厂缺省仍把 prompt 固定为「最多 8 条」——
   长会话的提示词名额永远停在下限，自适应放宽在 prompt 侧不生效；关系 prompt 还只列出规范
   英文谓词，纯中文会话只能猜中文变体（白名单已支持却未展示）。
3. **技能内容生成容忍度与有界性不足**：`skill_content_writer_with` 只接受「纯 JSON 文本」，
   模型输出包在代码围栏或前后杂文中即整条丢弃（与关键事实解析器的容错口径不一致）；同时
   `SkillContent` 的文本字段**无长度上界**，模型可产出无界内容直接进入技能库。

## What Changes

- **memory**：摘要 prompt 的产出长度要求改为与 `MAX_SUMMARY_CHARS` **同源**（2000 字）；
  关键事实 / 关系抽取器在未显式覆盖名额时，按**本次调用**的聚合条数计算 `cap(n)` 并写入 prompt；
  关系 prompt 的谓词表由闭合白名单**派生**，展示每个规范谓词的全部中文变体。
- **evolution**：技能内容 writer 容忍代码围栏与前后杂文（直接解析失败时截取首个 `{` 至末个 `}`
  再解析）；`SkillContent` 文本字段有界（超界裁剪），`validate_skill_content` 拒绝超界内容
  （持久化 delta 不经 writer 时不构成信任边界）。

## Impact

- 规格：memory「记忆压实」「结构化实体抽取（关键事实）」「实体关系抽取（relations）」
  MODIFIED；evolution「技能候选内容生成」MODIFIED。
- 代码：`src/core/memory/summarize.py`、`src/core/memory/extract.py`、
  `src/core/evolution/content.py`。
- 行为：缺省下 prompt 字数/名额与既有落库上界对齐（更长会话可抽更多、摘要可写到 2000）；
  围栏包裹的合法内容不再被丢弃；超长技能内容被裁剪而非无界落库。无配置开关（缺陷修复）。
- 不做：批次 C 的规模/决策质量问题（pending 终态化、观察期窗口、benchmark 记忆隔离、
  `_reinforce` 写放大、CJK token 估计、failure lessons 独立预算等）。
