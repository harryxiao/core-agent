# Change 0254 — 记忆写回脱敏与压实硬伤（P0）

## Why

记忆审计（2026-10-17，三方向只读）确认：默认部署下「写入路径默认开、质量门默认关」，且三条
明文路径绕过既有脱敏，两项压实硬伤会保存垃圾/陈旧条目：

1. **`notes.turn` 写回正文不脱敏**：`NoteStore.observe_turn` 直接拼接行动行（`notes/store.py:290`），
   参数/结果中的密钥形态可进全局 canonical 知识层。
2. **上下文压实产物不脱敏、无长度上界**：`Compactor.compact` 把整段消息写入结论/决策/未决
   （`context/compactor.py:57-75`），`persist` 原样落 L2（`:101-128`），不脱敏、不截断；工具输出
   无界会放大该面。
3. **技能路由未命中记录不脱敏、无长度上界**：`_record_miss` 把任务原文写入 L2（`skills/router.py:166`）。
4. **SOP 提炼正文不脱敏**：`SopExtractor.observe` 把模型文本直接入库（`skills/sop.py:132-147`）。
5. **压实产物陈旧序号残留**：产物 id 按 `.<i>` 下标覆盖；本轮条目少于上一轮时，多出的旧序号
   永久残留为陈旧事实。
6. **关键事实空取值落库**：`parse_key_facts` 只做类型检查（`memory/extract.py:233-236`），空 value
   会写 `实体: ` 并覆盖同实体既有事实。

本变更只修「写入前的机械约束」（脱敏 / 有界 / 空值拒收 / 陈旧清理），不新增模型调用、不改
触发判据与关键词分类口径。

## What Changes

- **`NoteStore.observe_turn`**：正文逐行 `redact_secrets` 后再落盘；闸门判据仍基于原行动行。
- **`Compactor`**：
  - 产物逐条 `redact_secrets`，单条字符上界 `_MAX_PRODUCT_CHARS = 400`（脱敏后截断）；
  - `persist` 写完后清理同会话同前缀下超出本轮条数的旧序号条目（走新增
    `MemoryStore.discard`，记可撤销删除效应）；
  - 关键词分类仍用原始消息（口径逐字不变）。
- **`SkillRouter._record_miss`**：`content` 先脱敏再截断（`_MAX_MISS_CHARS = 400`）；id 仍由原始任务
  派生（幂等/去重语义逐字不变）。
- **`SopExtractor`**：提炼文本在空文本判定、质量门与入库前统一 `redact_secrets`。
- **`scrub_key_fact`**：`entity` 或 `value` strip 后为空 ⇒ 丢弃（即便给出 `ref`）。

## 影响面

- 规格：`notes` / `context` / `skills` / `memory` 各 **ADDED** 1 条聚焦 Requirement（含场景）。
- 代码：`src/core/notes/store.py`、`src/core/context/compactor.py`、`src/core/memory/store.py`
  （`discard`）、`src/core/memory/extract.py`、`src/core/skills/router.py`、`src/core/skills/sop.py`。
- 测试：新增 `tests/test_memory_write_hygiene.py`（6 例）。
- 缺省行为：未含密钥的文本逐字不变（除超长压实产物按新上界截断）；无陈旧序号时无删除。

## 不做

- 不引入内容质量评分或 LLM 判定（P1）。
- 不改重要性闸门默认值、SOP 发布门、evolution 评测口径（P1~P4）。
- 不物理清理 L4 / 转录原文。
