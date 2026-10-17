# Design — 批次 B：prompt 对齐与技能内容容错/有界

## 背景

批次 A（change 0241）收口了高危正确性/安全缺口；本 change 处理 review 中「提示词与执行口径
不一致 / 模型输出形态不设防」的中优先级问题。全部为**缺陷修复**，不新增配置开关：缺省路径
的行为向「规格已声明的上界」对齐，而非引入新策略。

## D1 摘要 prompt 与 `MAX_SUMMARY_CHARS` 同源

`summarize._PROMPT_HEAD` 中「总长不超过 800 字」是固定死值，与落库/滚动合并上界
`MAX_SUMMARY_CHARS = 2000` 不一致。修法：提示词由 `MAX_SUMMARY_CHARS` 插值生成（模块导入时
一次性渲染为字符串），不引入新常量、不再维护第二份数字。

**为什么不是保留 800**：800 不是任何规格上界，只会让模型过早压缩；滚动合并的「尾部保留」
恰恰是为了不丢最新结论，提示词却要求截短到 800，二者方向相反。

## D2 抽取 prompt 名额随 `cap(n)` 自适应

落库名额由 store 按 `key_fact_cap(len(entries))` / `relation_cap(...)` 计算（8~16），但
`extract_with` / `extract_relations_with` 的工厂缺省把 `max_facts` / `max_relations` 固定为
`KEY_FACTS_MIN`（8），prompt 永远只要求 8 条。修法：工厂的 `max_facts` / `max_relations` 缺省
改为 `None`，表示「按本次调用条目数计算 `cap(n)`」；显式传值仍按传值渲染（测试/运维用例）。
`build_extract_prompt` / `build_relation_prompt` 的显式参数语义不变。

**边界**：抽取器契约仍是 `list[MemoryEntry] -> list[KeyFact]`，名额计算不依赖 LLM 判断；
store 侧落库名额不变，本 change 只让 prompt 与落库同源。

## D3 关系 prompt 展示中文变体

`_RELATION_PROMPT_HEAD` 的 `{predicates}` 只填 `_CANONICAL_PREDICATES`（英文），而正文声称
「可用中英任一变体」。修法：谓词表由 `RELATION_PREDICATES`（= 规范谓词 + `_PREDICATE_VARIANTS`）
按规范谓词分组派生，渲染为 `depends_on（依赖/依赖于/取决于/depend on/...）`；不另写词表，
变体集合与归一化白名单**同源**。渲染顺序按 `_CANONICAL_PREDICATES` 与 `_PREDICATE_VARIANTS`
的声明顺序（确定性，prompt pin 可复现）。

## D4 技能内容 writer 容忍代码围栏与前后杂文

`skill_content_writer_with` 只做 `json.loads(raw)`。模型常见输出 ` ```json ... ``` ` 或
「解释 + JSON」⇒ 整条内容丢弃。修法：先直接解析；失败时截取首个 `{` 至末个 `}` 再解析
（与 `extract._json_array` 同型的容错，但对象形状独立实现——evolution 不 import memory）。
仍不可解析 / 非对象 ⇒ `None`（fail-closed 语义不变）。

## D5 `SkillContent` 有界

新增实现常量（说明：均为**内容生成**的有界旋钮，与诊断 `failure_notes` 的 3×400 独立）：

| 字段 | 上界 |
|---|---|
| `instructions` | 4000 字符 |
| `description` | 400 字符 |
| `task_types` | 16 项，每项 80 字符 |
| `preconditions` | 8 项，每项 200 字符 |

- writer 在解析后**裁剪**到上界（超界不整条丢弃：保留可用内容，避免退化为空壳）。
- `validate_skill_content` **拒绝**超界内容：持久化 delta / 外部注入的 `SkillContent` 不经
  writer 时**不构成信任边界**；engine 的 `_crystallize_skill` 随后按原 dict 写入 Skill，
  因此校验必须按原始内容判定，而不是按裁剪后的副本。
- `param_schema` 为结构化对象，不做文本截断（截断会破坏 schema）；其大小不设新上界，
  登记为局限。

## 规格先行

`memory` 三条 Requirement 与 `evolution` 一条 Requirement 均先改规格（新增行为句 + Scenario），
再写红测试，再实现。

## 测试与反证

- memory：摘要 prompt 含 `MAX_SUMMARY_CHARS` 且不含 800；默认抽取器对 200 条请求 16、对 20 条
  请求 8；关系 prompt 同；关系 prompt 含全部中文变体。
- evolution：围栏 JSON / 前后杂文均能解析；超长字段被裁剪；`validate_skill_content` 拒绝超界。
- 反证：把摘要 prompt 还原为 800 ⇒ 1 红；抽取器缺省还原为 `KEY_FACTS_MIN` ⇒ 2 红；谓词表还原
  为纯英文 ⇒ 1 红；writer 去掉容错 ⇒ 2 红；去掉裁剪 ⇒ 1 红。复原后 md5 同。

## 局限

- prompt 字数/名额对齐不保证模型遵守（提示词非强制约束）；落库仍按上界截断/计额。
- 内容裁剪是「就近截断」，可能截在句子中间；对技能可读性有影响但不破坏结构。
- `param_schema` 仍未设大小上界。
- 中文变体表是闭合白名单的镜像维护面（新增变体需同时改 `_PREDICATE_VARIANTS`）。
