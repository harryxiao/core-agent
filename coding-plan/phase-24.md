# Phase 24：进化引擎「内部核心插件」接线收尾 + notes 检索质量优化账本（E30 工具级 trace + E31 内部模块注册表生命周期 + E32 notes _score 加权）

> **定位**：本 Phase 是 `phase-21.md`（进化引擎「架构模块维度」归因接线）与 `phase-23.md`（notes 新 capability）收口后，**剩余两处「内部核心插件真实覆盖」断裂**的排期账本，外加 **E32 一处 notes 检索质量优化**（review 新发现，非转出账本）。E30/E31 均已在此前 Phase 的**转出账本**中登记为待办，本 Phase 只做收尾接线；E32 为纯词法打分优化，**不新增能力、不重开已裁决事项**。
>
> **来源**：`phase-19.md` §5 登记 E30 / E31；`phase-21.md` §1.4 转出账本两项均「仍待办、已登记」；`phase-23.md` claude 汇报第三类遗留明确「下一条自然 change = 把 14 个内部模块纳入注册表生命周期，需单独立项」。**E32 来源**：`phase-23.md` 局限②（notes 检索 `_score` 无字段权重），本 Phase review 对 `backend.py` 实况复核确认。
>
> **去重口径（红线）**：`phase-20.md` 已列 E27（im）/ B2（mcp-http）/ C7（ui TTS）/ C8（ui Tauri）**不写**；`phase-22.md` 已修 observability/rag/skillhub **不写**；`phase-23.md` 缺口③（外部插件装载）已裁决「不修」**不写**。**E32（notes `_score` 加权）为本次 review 新发现，非去重对象**（phase-20/22/23 均未列该打分问题）。

---

## 0. 结论总览

| 编号 | 缺陷 | 现状 | 归属 | 档位 | 建议 |
|---|---|---|---|---|---|
| E30 | 工具级 trace 缺失（`action_completed` 未 `_trace`） | ✅ **已闭**（change `0107` / ADR-0100：生产者接线到 loop 非终止动作分支） | evolution 的 **skill 维度**产线输入 | 低（技能维度主线未断，由 `turn_observer` → SOP/技能反馈承载） | 接线：为工具执行补 `_trace` 生产方 |
| E31 | 14 个内部核心模块未纳入 `PluginRegistry` 生命周期 | ⚖️ **裁决：不纳入**（change `0107` / ADR-0100；规格口径钉死 + 重开条件记录） | evolution 的 **plugin 维度**世代语义 | 低（「确认后晋升世代」退化为登记批准 + 诚实 `status` + 观察期） | ~~把 14 模块纳入注册表 `load/unload/check` 生命周期~~ ⇒ 不补空转形态 |
| E32 | notes 检索 `_score` 无字段权重（五字段拼单一 haystack） | ✅ **已闭**（change `0107` / ADR-0100：分区加权） | notes 的 **Consult 精准度** | 低（质量优化，不挡核心回路） | `_score` 分区加权：title ×3 / tags ×2 / search_queries ×2 / content ×1 |

> **共同口径**：两条都不挡核心回路（M4 自进化的「真能收集、真能提案、真能结晶」已由 phase-18/21 打通），属**覆盖完整性收尾**，非功能性断裂。

---

## 1. 缺陷清单

### 1.1 E30 工具级 trace 缺失（skill 维度产线无输入）

**现象**：evolution 的 **skill 分支在产线无输入**——工具执行的 trace 事件从不在 trace 流中产出，导致依赖工具级 trace 的 skill 维度归因/提案拿不到证据。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `src/core/observability/tracer.py:69-82` | `TraceLogger.log_tool_call` | 工具 trace 的**唯一生产者**，但**零生产调用方** |
| `src/core/loop/worker.py:97`（`_to_traces`） | 只认 `kind == "tool_call"` | 消费侧已就绪，供给侧无人产 |
| `src/core/loop/default.py:235-244` | loop 把 `action_completed` 作为 `LoopEvent` 外发却**不 `_trace`** | 工具执行完成事件**不落 trace 流** |

**根因**：`action_completed`（工具执行结果）被 loop 作为 `LoopEvent` 外发（供监听者消费），但**没有调用 `TraceLogger.log_tool_call` 写进 trace 流**；`_to_traces` 侧只认 `kind == "tool_call"`，供给侧却无人产。两端各就各位、中间断了。

**后果**：模块归因通道（phase-21 已通，走 `TraceEvent.module_id`）只覆盖**架构模块维度**；**工具/技能维度**的 trace 证据链在产线为 0。技能维度主线本身未断（由 `turn_observer` → SOP/技能反馈承载），故档位为**低**。

**登记源**：`phase-19.md` L114（E30）；`phase-21.md` §1.4①。

---

### 1.2 E31 14 个内部核心模块未纳入 `PluginRegistry` 生命周期

**现象**：仓内 **14 个内部核心模块**的 `plugin_id` 已列入归因白名单 `INTERNAL_PLUGIN_IDS`，但**未纳入 `PluginRegistry`**（无注册表驱动的 `load`/`unload`/`check` 生命周期）⇒ 其「确认后晋升世代」退化为「登记批准 + 诚实 `status` + 观察期」。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `src/core/evolution/plugin_ids.py:7-9` | docstring 明写「**这不是 `PluginRegistry` 的成员名单**：本仓内部核心模块**未**纳入注册表（无注册表驱动的 `load`/`unload` 生命周期）…相关欠账见 `coding-plan/phase-21.md` §1.4②」 | 白名单只声明**归因对象身份**，不承载装配/世代语义 |
| `src/core/runtime.py:517` | `diagnoser=Diagnoser()` **无参装配** | `Diagnoser` 拿不到任何 `Plugin` 信号（`plugin_signals` 空） |
| `src/core/plugin_registry/registry.py:153/171/182/192` | `load` / `unload` / `check` / `activate` / `deactivate` 方法齐全 | 但 14 模块一个都没走这套生命周期 |

**14 个模块 `plugin_id` 清单**（`plugin_ids.py:18-34`）：

```
composition.engine, composition.packager, composition.resolver,
evolution.collector, evolution.diagnoser, evolution.engine,
evolution.evaluator, evolution.proposer, evolution.validator,
evolution.worker, im.gateway, loop.default, memory.store, notes.store
```

**根因**：phase-21 采用口径 **(b) 信号走既有 trace 通道（不纳入 `PluginRegistry`）**（见 `phase-21.md` §1.3 / ADR-0094），刻意把「内部模块纳入注册表」留到「有新一代 `Plugin` 对象生产者」的 Phase。phase-23 汇报第三类遗留明确此为该 Phase 的下一步。

**后果**：
- `promote()` 仍是空转（无新一代 `Plugin` 生产者，见 `phase-21.md` §1.3 验收⑥）；
- `Diagnoser` 无参装配 ⇒ `plugin_signals` 空 ⇒ 内部模块的健康/质量信号无法作为归因证据进诊断回路（诊断信号源只覆盖 trace 通道，不覆盖注册表质量信号）。

**档位**：低——诚实降级为「登记批准、不谎报」，未谎报 `published`（phase-21 已保证）。

**登记源**：`phase-19.md` L871（E31）；`phase-21.md` §1.4②；`phase-23.md` claude 汇报第三类遗留。

---

### 1.3 E32 notes 检索 `_score` 无字段权重（Consult 精准度受损）

**现象**：`MarkdownBackend.search` 的 `_score` 把五类字段（`note_id`/`title`/`tags`/`search_queries`/`content`）拼进**同一个 haystack**，term 命中即 +1，**零字段权重**——title 精确命中与 content 全文顺带命中得分相同，精心维护的语义浓缩元数据无法优先。

**证据（行号）**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `src/core/notes/backend.py:136-142` | `_score` 把 `[note.note_id, note.title, *note.tags, *note.search_queries, note.content]` join 成单一 `haystack`；`hits = sum(1 for term in terms if term in haystack)`；`return hits / len(terms)` | 五字段等权，无任何字段区分 |

**根因**：MVP 阶段 `_score` 只求「命中率」`hits/terms`，未做字段加权——这符合 phase-23 §1.2「不建向量库、走标题/tags/头部关键词匹配」的第一性，但把语义浓缩字段（`title`/`tags`/`## Search Queries`）与正文 `content` 同权，浪费了 notes 头部 metadata 的检索价值。

**后果**：Consult 检索时，title 精确命中的 note 可能被 content 里顺带提到该词的 note 挤掉排名，Consult 精准度受损。search 仍可用、不挡核心回路，故档位**低**，属**质量优化**而非功能断裂。

**登记源**：`phase-23.md` 局限②；本 Phase review 对 `backend.py` 实况复核确认。

---

## 2. 修复方案

### 2.1 E30：为工具执行接线 `_trace` 生产方

**目标**：让 `action_completed` 落到 trace 流，使 `_to_traces` 的 `kind == "tool_call"` 消费侧有输入。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. 在 loop 处理 `action_completed`（`default.py:235-244` 附近）处，于外发 `LoopEvent` 之外，调用 `TraceLogger.log_tool_call(...)` 写 trace 流，字段对齐 `_to_traces` 期望（`kind="tool_call"`、工具名、成败、耗时等）。
2. 确认 `log_tool_call`（`tracer.py:69-82`）的入参与 `_to_traces`（`worker.py:97`）消费字段一致，缺失字段补默认值，避免写入死数据。
3. 保持 `LoopEvent` 外发路径**不变**（现有监听者不受影响），只**新增** trace 写入。

**红线**：不改 `_to_traces` 的消费口径；不引入新的 trace kind；不破坏 phase-21 已通的模块归因通道。

### 2.2 E31：14 内部模块纳入 `PluginRegistry` 生命周期

**目标**：把 14 个内部核心模块注册进 `PluginRegistry`，使 `load`/`unload`/`check` 生命周期生效，并让 `Diagnoser` 能拿到注册表质量信号。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. 为 14 个内部模块构建满足 `Plugin` 契约的**内部插件包装**（`plugin_id` + 健康/质量信号 source + `load`/`unload` 空转或最小实现），注册进组合根唯一的 `PluginRegistry`。
   - ⚠️ phase-21 §1.3「代价」已警示：给 5 个 evolution 子模块补 plugin 形状时 `load/unload` 只能 `pass` 空转，是该形态**被明确拒绝**的——**订正**：此否决的实质出处是 **ADR-0094 决策①**（原稿同 ADR-0094 括注一并误引为 ADR-0054；ADR-0054 讲冷路径驱动面，全文无该裁决）。落地方案须**重新评估**：要么接受「登记式」最小实现并诚实标注，要么改走 `check()` 只读健康状态、不接 `load/unload` 生命周期，避免空转。
2. `Diagnoser` 装配改为注入注册表质量信号（或经参数流传入），使其 `plugin_signals` 非空。
3. `promote()` 语义在「无新一代生产者」前提下**保持诚实**：内部模块的世代晋升仍走「登记批准 + 观察期」，不谎报 `published`。
4. 同步 `plugin_ids.py` docstring 的「不是成员名单」措辞（纳入后需订正），并更新 `INTERNAL_PLUGIN_IDS` 说明。

**红线**：不引入外部插件装载路径（`plugin_registry` 仍是进程内注册表，phase-23 缺口③已裁决不修）；不改 `kind="plugin"` 默认 `pending`、confirm 必审的红线；绝不自动改架构代码。

### 2.3 E32：`_score` 分区加权（纯词法，不动架构）

**目标**：让 Consult 检索优先命中语义浓缩字段，明显改善精准度。

**方案（供 claude code 参考，具体实现以代码实况为准）**：
1. 重写 `_score`（`backend.py:136-142`）为**分区加权求和**：`title ×3`、`tags ×2`、`search_queries ×2`、`content ×1`（`note_id` 一般不被 query 命中，可保持 ×1 或不参与）。
2. 命中判定仍走「term 是否出现在该字段文本中」的纯词法匹配，**不引入 embedding / 向量库**。
3. 保留 `hits > 0` 过滤与降序排序逻辑（`backend.py:84-86`）不变，只改打分函数。

**红线**：不建向量库、不引入 RAG（守护 phase-23 §1.2 第一性）；不改 `NoteEntry` 数据模型、不改 `MemoryBackend` Protocol 契约、不改 search 返回结构；不动 `Consult → Build → Update` 循环指令。

---

## 3. 验收清单

- [x] ① 工具执行 trace 事件在产线可见：`_to_traces` 能收到 `kind == "tool_call"` 的事件（`log_tool_call` 有生产调用方）。
- [x] ② `LoopEvent` 外发路径行为不变（现有监听者无回归）。
- [x] ③ ~~14 个内部模块在 `PluginRegistry` 可见：`registry.check(plugin_id)` 返回诚实状态。~~ ⇒ **改判为「裁决：不纳入」**（详见 §6）。
- [x] ④ ~~`Diagnoser` 装配后 `plugin_signals` 非空~~ ⇒ 同 ③（改动无消费者，`plugin_signals` 保持为空是**诚实**的）。
- [x] ⑤ `promote()` 诚实语义不破：内部模块世代晋升仍「登记批准 + 观察期」，不谎报 `published`。
- [x] ⑥ `plugin_ids.py` docstring 与 `INTERNAL_PLUGIN_IDS` 说明同步订正（「欠账」→「裁决 + 重开条件」）。
- [x] ⑦ 门禁三件套全绿：pytest 全过（1243 passed）、pyright 0 error、openspec 校验通过（30 passed / 0 failed）。
- [x] ⑧ git diff 证明**未引入外部插件装载路径**（守护 phase-23 缺口③裁决）。
- [x] ⑨ `_score` 分区加权生效：title 精确命中的 note 排名高于 content 顺带命中的 note（单测断言构造 title 命中 vs content 命中的两个 note，search 后 title note 在前）。

---

## 4. 契约对齐

- 本 Phase **不新增 capability**、**不新增 spec 段落**（E30/E31 均属既有 `evolution` / `plugin_registry` 契约内的接线收尾；E32 属 `notes` capability 内部的检索打分实现优化，search 签名/返回结构/协议契约不变）。
- 若 E31 落地涉及 `Plugin` 契约的 `load`/`unload` 语义订正（如「登记式」最小实现 vs 空转），须在 `plugin_registry` 对应 spec/接口文档同步，且**明确诚实标注**，不虚假宣称生命周期完备。
- 相关 ADR 参照：ADR-0094（trace 通道 + 模块归因，不纳入 `PluginRegistry`）——本 Phase 曾预设**打破该 ADR「不纳入」前提**，落地须**新增 ADR** 记录口径变更（E31）；**订正**：ADR-0054 与「拒绝空转形态」无关（该否决实质出处 = ADR-0094 决策①，旁证 ADR-0065「不造空转闭包」）。⇒ 本 Phase 新增 **ADR-0100**（E30 生产方接线 + E31 裁决 + E32 加权 + 引用订正）。

---

## 5. 门禁与红线

- **红线**：`kind="plugin"` 默认 `pending`、confirm 必审，绝不自动改架构代码。
- **红线**：不引入外部插件装载路径（`plugin_registry` 零改动为进程内注册表的语义）。
- **红线**：不重复 phase-20（E27/B2/C7/C8）、phase-22（observability/rag/skillhub）已列/已修项。
- **红线**：E32 只改 `_score` 打分实现，不引入向量库/RAG，不改 notes 数据模型与协议契约。
- **门禁**：提交前三件套全绿；一个 Phase 一个 commit；更新 `README.md` §2 总览表状态列。

---

## 6. 收口（change `0107` / ADR-0100）

**交付**：`doc/openspec/changes/archive/2026-10-05-0107-tool-trace-and-notes-scoring/` —— 三 capability
delta（loop「异步流式执行」/ evolution「经验采集」/ notes「canonical Markdown 真相层与可插拔后端」）；
**不新增 capability、不改 `MemoryBackend` 协议、不改 `PluginRegistry`**。

| 缺陷 | 落地 | 证据 |
|---|---|---|
| E30 | `DefaultLoop` ctor 建 `TraceLogger`（未注入 `tracer` ⇒ `None`）；`astream` **非终止动作**分支调 `_log_tool_call`（与 `action_completed` **同判据同点**、遥测先于 `yield`、载荷复用节选函数 ⇒ 有界，消费侧 `_to_traces` 零改动） | `tests/test_tool_trace.py` 5 例 |
| E31 | **裁决：不纳入 `PluginRegistry`**、不补空转形态；`plugin_id` = **归因对象身份**（不蕴含注册表成员身份）写入 evolution 规格；`plugin_ids.py` docstring 由「欠账」改**裁决 + 重开条件** | 规格 +2 场景；`phase-19.md` §5 / `phase-21.md` §1.4 同步 |
| E32 | `_score` 分区加权（`title 3× / tags 2× / search_queries 2× / note_id 1× / content 1×`），命中判据与返回结构不变、**只影响排序**、分数不外露 | `tests/test_notes.py` +3 例 |

**门禁**：`ruff check` / `ruff format --check` / `pyright`（0 errors, 0 warnings）/ `pytest`（1243 passed）
四门全绿；`openspec validate --all` 30 passed / 0 failed。

**E31 裁决的三条依据**：①**零消费者**（`PluginRegistry` 全仓仅 `PluginInstaller` 内部默认构造，组合根无
`registry` 变量 ⇒ 注册进去无代码路径读取）；②**形态即空转**（14 模块中仅 8 个具 Plugin 六件套，
`load`/`unload` 全 `return None`、`check()` 7/8 恒真）；③**前置条件未满足且更远**（重开条件 = 出现
「真的会产出新一代 `Plugin` 对象」的生产者，而 change `0102` 刚把架构级结晶裁决为 `accepted`
待人工实施）。重开条件已写入 ADR-0100 与 `plugin_ids.py` docstring。

**引用订正**：ADR-0094 决策①括注、`phase-21.md` §1.3 与本文件 §2.2/§4 均把「拒绝空转形态」误引为
ADR-0054（**一手核实 ADR-0054 全文无此裁决**，其主题是冷路径驱动面）⇒ 三处订正为 **ADR-0094 决策①**
（旁证 ADR-0065「不造空转闭包」）。

**未做（明示）**：E31 的注册表纳入本身（裁决不做）；随之搁置的 `Diagnoser` 质量信号注入
（`plugin_signals` 保持为空是**诚实**的 —— 无信号源，不如实登记空转更糟）。
