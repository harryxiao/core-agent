# 设计：沉淀质量重构

## 1. 核心裁决

| 问题 | 裁决 | 理由 |
|---|---|---|
| 对话何时进入 canonical | **两段式**：成功轮 → 候选；显式 `candidate-promote` → canonical | 对话原文不是知识；晋升前的 review 是质量闸门 |
| 谁判定「值得沉淀」 | 确定性预滤 + 注入式 LLM 判定（严格 JSON） | 预滤挡住闲聊/纯读；LLM 只做语义判定，不接触 canonical |
| 候选是否进上下文 | **否**：独立 JSON，`digest/list/search` 不读 | 未晋升内容不得污染每轮注入 |
| SOP 发布状态 | **draft**；`skill activate` 唯一生效入口 | 路由只放行 active/gray，draft 天然无行为影响 |
| 旧 SOP 样本 | 移入回收目录 | 新准入闸无法区分存量垃圾与正常样本 |
| 存量清理 | 移动 + manifest，不删除 | 可逆；用户明确要求 |
| reply 如何交给观察者 | `TurnObserver` 第 4 参 | 不污染 `steps`（`has_write_effect` / SOP 步骤格式都依赖它） |

## 2. notes 数据流

```
loop 收尾
  └─ TurnObserver(task, steps, ok, reply)
       └─ Sedimenter.observe_turn
            ├─ 预滤：ok / steps 非空 / 写效应 / 任务≥6 非空白字符 / writer 存在
            ├─ 脱敏 → 有界 prompt（附已有 topic，引导复用）
            ├─ writer(prompt) → 严格 JSON
            ├─ durable=false / 解析失败 / 空 content → 丢弃（零落盘）
            └─ CandidateStore.upsert(topic)   ← $CORE_STATE_DIR/notes-candidates.json
                 ├─ 同 topic：support+1（仅当 trace_digest 新）/ 刷新内容
                 └─ auto_promote && support≥2 → promote（冲突则保留候选）

notes candidate-promote <id>
  └─ Sedimenter.promote
       ├─ 目标 note 不存在 → create
       ├─ 来源=notes.sediment 且 sediment:<本候选> → 覆盖（保留 pinned/priority）
       ├─ 来源≠notes.sediment 或 sediment:<别的候选> → NoteError(TOPIC_EXISTS)，候选保留
       └─ 成功后移除候选
```

### 候选字段（JSON）

`{candidate_id, title, content, tags, queries, kind, support, first_seen, last_seen,
trace_digests, evidence}`；上限 128 条，按 `last_seen` 淘汰；文件 0600、原子替换、损坏容忍。

### 提炼 JSON（模型输出）

`{durable: bool, topic: str, title: str, content: str, tags: [str], queries: [str], kind: str}`。
`topic` 经 `slug_topic` 归一；title≤120、content≤4000、tags≤8、queries≤8；kind 白名单
`decision|procedure|fact|preference|pitfall`。代码围栏容忍（取首 `{` 至末 `}`）。任一步失败 ⇒
warn（只报长度/组键，不回显内容）+ 丢弃（fail-closed）。

## 3. skills 数据流

```
observe(task, steps, ok)
  ├─ RLock（主/子/beast loop 共享实例）
  ├─ 准入：ok / steps 非空 / 任务≥6 非空白 / 单轮面含 tools. 动作（任务级面 ≥2 步）
  ├─ 组内逐字重复轨迹 → 忽略（不累积）
  ├─ 达阈值 → writer(prompt) → 确定性门 → 自动质量门
  ├─ 已有同 id：active/gray → 跳过清组；deprecated → 粘性；draft → 覆盖
  └─ register(Skill(status="draft"))
```

prompt 改为结构化 Markdown 模板（适用场景 / 前置条件 / 步骤 / 验证 / 失败模式），并明确
「轨迹间无共同可复用步骤（如闲聊）输出空字符串」。不引入 JSON：`Skill` 无对应字段、无消费方。

确定性门新增拒绝文本短语（`未提供有效的执行轨迹` / `无法提炼` / `抱歉` / `无法协助`），
正好覆盖 `hi` 垃圾技能的成因。

## 4. 兼容与迁移

- `NoteStore.observe_turn` 保留为低层原语（现有单测与来源守护用例仍覆盖），但 **runtime 不再接线**；
  `notes.turn` 来源常量保留供 `prune --source` 识别存量。
- 新增 `NoteStore.raw(note_id)` / `remove(note_id)` 两个窄接口，供 prune 按原始字节移动。
- `skills.json` 中 3 条垃圾 SOP 以 `skill deprecate` 退役（不物理删除，可 `activate` 复活）。
- `sop-samples.json` 与 34 篇 `notes.turn` 一并移入 `~/.core/state/notes-trash/<stamp>/`。

## 5. 风险

- 候选区跨进程无文件锁：CLI 与运行中 agent 同时写可能后写覆盖。登记 known-risk E231；
  prune 建议在 agent 空闲时执行。
- 每个成功写效应轮一次 LLM 调用：确定性预滤 + trace 去重控制成本；`notes.candidate_distill=false`
  可整体关闭。
- LLM topic 漂移：prompt 附已有 topic 引导复用；漂移只会产生多个候选，不会直写 canonical。
