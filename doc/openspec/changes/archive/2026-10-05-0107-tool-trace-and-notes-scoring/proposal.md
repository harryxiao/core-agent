# 提案 — 工具级 trace 生产方接线 + notes 检索字段加权 + E31 归因身份口径裁决（change 0107）

## 背景与缺陷

`coding-plan/phase-24.md` §1 一手核实的三个缺陷（E32 为本 Phase review 新发现）：

1. **E30 工具级 trace 缺失（P1，断在「供给」）**：`_to_traces` 只认 `kind == "tool_call"`，
   而唯一生产者 `TraceLogger.log_tool_call` **零生产调用方**；loop 把 `action_completed` 作为
   `LoopEvent` 外发却**不写 trace 流** ⇒ 两端各就各位、中间断了。后果：evolution 的 **skill 维度
   产线无证据**（技能维度主线未断，由 `turn_observer` → SOP/技能反馈承载，故档位低）。
2. **E31 内部模块「未纳入 `PluginRegistry`」（P1，实为口径问题）**：14 个内部核心模块的 `plugin_id`
   在 `INTERNAL_PLUGIN_IDS` 白名单里，但不在注册表内。**复核结论：不是待办接线，是需裁决的口径**
   —— 14 个模块里只有 8 个真有 Plugin 六件套，其 `load/unload` 全是 `return None`；`check()` 里
   7 个是 `return True`（真检查仅 `evolution.engine` / `composition.resolver`）；`PluginRegistry`
   全仓只被 `PluginInstaller` 内部构造（`installable.py:93`），组合根**没有 registry 变量** ⇒
   「纳入」买不到任何一条验收，只会给 5–6 个零 `generation/schema/coeffects` 的算法类补
   `load/unload = pass` 的**空转生命周期**（ADR-0094 决策①已明确否决此形态）。
3. **E32 notes 检索 `_score` 无字段权重（P2，Consult 精准度）**：`MarkdownBackend._score` 把
   `note_id / title / tags / search_queries / content` 拼进**同一个 haystack** 等权计数 ⇒ 标题精确
   命中与正文顺带命中同分，精心维护的语义浓缩元数据（`title` / `## Search Queries`）**买不到排名**。

## 变更目标

1. **E30 接线**：loop 在**非终止动作**完成后产出 `kind="tool_call"` 遥测（经 `TraceLogger`，
   使「唯一生产者」名副其实），载荷含工具 id / 参数 / 成败 / 耗时且**有界**（≤400 字符），使
   `_to_traces` 的 `tool_use` 通道在生产**首次有输入**。**消费侧与 `LoopEvent` 外发路径逐字不变。**
2. **E32 加权**：`_score` 改**分区加权**（标题 ×3 / tags ×2 / `## Search Queries` ×2 / 正文与 id ×1），
   仍为**纯词法**（不建向量库、不引入 embedding），`search` 签名 / 返回结构 / `MemoryBackend`
   契约**一概不变**。
3. **E31 裁决**：**不纳入 `PluginRegistry`**（附理由与**重开条件**），并把 `plugin_id` 在内部模块上
   承载的语义**写进规格**：它是**归因对象身份**（供进化引擎监控与缺陷归因），**不蕴含**注册表成员
   身份；内部模块的失败证据经遥测的**模块归因通道**（`module_id`）承载。

## 非目标 / 已否决

- **不纳入 / 不新建注册表**：不给内部模块补空转 `load/unload`，不动 `plugin_registry` 契约
  （E31 裁决，理由见 §背景 2；重开条件 = 出现「新一代 `Plugin` 生产者」）。
- **不做工具级 trace 的第二条通路**：不扩 `kind` 词表、不改 `_to_traces` 消费口径（ADR-0094 约束）。
- **不改 notes 数据模型 / 协议**：`NoteEntry`、`MemoryBackend` Protocol、`search` 返回结构不动；
  **不引入向量库 / RAG / embedding**（守护 phase-23 §1.2 第一性）。
- **不重复已列项**：E27（im）/ B2（mcp-http）/ C7（ui TTS）/ C8（Tauri 打包）/ observability / rag /
  skillhub / phase-23 缺口③（外部插件装载）。

## 风险

| 风险 | 缓解 |
|---|---|
| 每个工具动作多写一条遥测 ⇒ 事件量上升 | 载荷经既有节选函数**有界**（≤400 字符）；动作级事件数与既有 `action_completed` **同量级**（1:1），非新增维度 |
| 加权改变既有检索排序 ⇒ 既有用例回归 | 加权只改**排序**不改**过滤**（`>0` 判据与 `search` 返回结构不变）；既有 19 例 notes 用例全绿为准 |
| 「裁决不纳入」被读成「漏做」 | 在 `plugin_ids.py` docstring / evolution 规格 / `phase-19.md` §5 / `phase-21.md` §1.4 四处**同写裁决 + 重开条件** |
