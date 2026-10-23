# Design — 记忆指标与效果评测（0311 / P2-5）

## 目标与非目标

补齐 SDD §11.1 / §11.2 / §11.3 的**可观测面**：运行指标快照、只读运维统计、按查询的召回
解释、有/无记忆的离线效果评测。**不改**检索排序、预算、多样性、写入、压实与遗忘语义。

## D1 指标放在进程内计数，不落盘

**决策**：`MemoryStore` 内新增 `MemoryMetrics` 累计计数器，`metrics_snapshot()` 返回
`dict[str, float]`；**不**新建指标文件、**不**在检索/读取路径做任何 I/O。

理由：
- 读路径每轮调用一次，落盘会造成与 0308 同类的「读放大」；0308 已明确拒绝读路径审计。
- 运行时指标的消费方是宿主/测试（进程内查询），不是跨进程离线分析；持久聚合由
  `memory stats` 从既有持久数据（条目 + 审计日志 + 文件大小）导出，两者分工不重叠。
- 与 0253 的裁决一致：巩固耗时已通过 `maintenance` / `compaction` **trace 事件**
  （`elapsed_ms` + `steps`）跨进程留痕；本 change 只补进程内计数，不重复建第二条导出面。

**被拒**：
- 每条 recall 追加一行 metrics JSONL —— 读放大、无界、且需要新的并发追加协议。
- 复用 `MetricsCollector`（observability） —— 需给 `MemoryStore` 增加注入面并接组合根，
  而它当前无消费方（0253 同因拒绝）。
- 定时快照文件 —— 需新增配置键与合写/锁语义，收益不抵复杂度。

**口径**：
- `memory.writes.<kind>`：`write()` **成功落库**（`_persist` 之后、含闸门降层）的条数；
  `kind` 规范化（非 `[a-z0-9_]` → `_`，空 → `unknown`）。闸门拒收与无行动拒收不计。
- `memory.writes.deduped`：幂等重放快路径命中数（change 0306）。
- `memory.writes.rejected`：重要度闸门拒收数。
- `memory.recall.*`：仅在**公共** `recall()` 入口累计；`read()` 委托 `recall()` ⇒ 计入；
  压实内部为决策打分调用 `self.read(...)` ⇒ 改走不经计数的私有检索体，避免虚增。
- `memory.consolidation.runs/.failures/.elapsed_ms`：进入 `_compact_locked` 前开始计时
  （`self._clock` 单调钟），异常 ⇒ `failures+1` 后照常抛；开关关闭 / 并发跳过
  （`compact()` 早返回）不计。`elapsed_ms` 为累计毫秒（整数）。
- `reinforce=False` 的检索**照常**计入 `memory.recall.*`（仍是一次真实召回），只是不写回。

## D2 `memory stats` 的数据形状

`collect_stats(entries, audit_rows, storage_bytes)` 为**纯函数**（`src/core/memory/stats.py`），
返回 `MemoryStats`；CLI 只负责取数、格式化与 `--json` 序列化。

来源：
| 字段 | 来源 |
|---|---|
| `storage_bytes` | `$CORE_STATE_DIR/memory.jsonl` 的 `stat().st_size`（缺失 ⇒ 0） |
| `entries` / `by_layer` / `by_status` / `forgotten` | `MemoryStore.audit(None)`（全层全状态） |
| `content_bytes` | `status == "active"` 条目 `content.encode("utf-8")` 长度之和 |
| `writes_by_kind` | 审计行 `op == "write"` 按 `kind` 计数 |
| `deletes_by_reason` | 审计行 `op == "delete"` 按 `reason` 计数（`tombstone` / `retention`） |
| `forgets_by_reason` | 审计行 `op == "forget"` 按 `reason` 计数（`decay`） |
| `exports` | 审计行 `op == "export"` 计数 |

- **零强化**：只读 `audit(None)`，不调用 `read()` / `recall()`。
- 审计关闭 ⇒ 审计派生计数全为 0（不报错）；正文/查询**不进入任何输出**。
- `by_layer` 只统计 `active`（被取代/墓碑不计入可注入面）；`by_status` 统计全量。
- JSON 输出为**固定键**的对象：数字 + 两个字符串键映射（`by_layer` / `by_status` /
  `writes_by_kind` / `deletes_by_reason` / `forgets_by_reason`），映射内按 key 排序。
- 文本输出按「storage → entries → layers → writes → governance」五行，字段以 `\t` 分隔，
  便于 grep/awk；空映射打印 `-`。

## D3 `memory why`：零强化诊断检索

**决策**：`recall(..., reinforce=False)` 支持诊断面；`why` 用 rank 序 + 分值解释注入。

- 统计行与 `RecallResult` 字段一一对应，`injected_tokens` 给预算压力一个可量化读数；
  `minimum_budget` 说明「再加多少预算可多注入一条」。
- 条目行：`#rank score=%.3f layer/kind source session id importance reuse | 摘要`；
  摘要走既有 `_one_line_summary`（先 `redact_secrets` 再截断）。
- **不返回被剔除条目明细**：返回全部候选会让输出无界，且与 `injected_count` 的口径混淆；
  计数 + `minimum_budget` 足以回答「为什么没进来」。若未来需要逐条剔除原因，另立
  `why --all` 设计（本 change 明确不做）。
- `--session` 透传会话过滤（与装配器同口径）；`--budget` 缺省 4096（与 `read()` 缺省一致）。
- 输出**不含查询原文以外的内容**；查询原文取自命令行，不落盘。

## D4 `RecallResult` 的加性字段

- `injected_tokens: int = 0`：`_truncate_with_stats` 已维护 `used`，直接返回；空结果 ⇒ 0。
- `scores: list[float] = field(default_factory=list)`：与 `entries` 等长、同序。
  实现上把 `sorted(values, key=rank...)` 改为「先算 (score, entry) 再稳定排序」，排序键
  与稳定性**逐字不变**（同分保持原候选顺序）；仅额外保留分值映射。
- 既有构造方（测试/调用方）不传新字段 ⇒ 缺省 0 / 空列表，行为不变。

## D5 效果评测 harness

`tests/test_memory_effectiveness.py`：

- **语料**：6 个任务，每个 `(question, gold_answer, gold_fact, distractors)`；事实以
  `source="bench.eff"`、`session_id="eff-bench"`、`kind="semantic"` 写入；干扰事实同源同会话。
- **两臂**：
  - 有记忆：`MemoryStore` 灌入 gold 事实 + 干扰事实，`DynamicAssembler(memory=store)`；
  - 无记忆：同构空 `MemoryStore`（同一装配器/planner/loop 代码路径）。
- **真实链路**：`LLMPlanner(stub, assembler=assembler)` → `DefaultLoop(planner, memory=store)`；
  桩 provider 读取 `request.messages` 的系统提示：含 gold 事实的**特征词** ⇒ 返回 gold 答案，
  否则返回 `未知`。因此「成功率」检验的是 **写入 → 检索 → 注入 → 规划器可见** 全链路。
- **度量**：成功率（gold 出现在最终 `result.reply`）、`LLMPlanner.last_prompt_tokens()`、
  `LoopResult` 轮数（由 `loop.run` 返回的 reply 稳定性推断为单轮）、墙钟
  `perf_counter`（只报告）。每任务新建 store/loop，避免跨任务污染。
- **断言**（确定性）：有记忆成功率 `== 1.0`（≥ 0.9 门）、无记忆成功率 `< 有记忆`（按构造
  为 0）、有记忆 prompt token **大于**无记忆（事实确实进入了提示词）；**不**对墙钟设阈值。
- 运行 `pytest -q tests/test_memory_effectiveness.py -s` 打印指标表。

## D6 兼容与边界

- 默认行为不变：计数器只增不减、无 I/O；`stats` / `why` 为新增子命令；`reinforce` 缺省
  True；`RecallResult` 加性字段有缺省。
- 并发：计数器是进程内普通属性（与 `_hot` / `_token_cache` 同级）；多进程各自计数，
  `metrics_snapshot()` 明确是**进程作用域**。
- 脱敏：指标与统计**零正文**；`why` 的摘要行先脱敏再截断（复用 `_one_line_summary`）。
- 失败隔离：`memory stats` 的文件/审计读取失败降级为 0；`why` 的检索失败由 `recall()`
  既有降级路径处理（冷区失败 ⇒ 空候选），不新增异常面。

## 风险与已知局限

1. 进程内计数在进程结束即丢失；短进程（`memory why` / `task`）看不到累计值 —— 持久聚合看
   `memory stats`（仅覆盖写入/治理/存储，不含 recall/consolidation）。
2. `memory.writes.*` 依赖审计日志开启（缺省开）；关闭后统计只余条目与体积。
3. 效果评测是**机制级**（gold 事实注入 ⇒ 桩模型可答），不代表真实模型的任务收益；真实
   收益需人工/在线评测（无反馈通道，SDD `hit_rate` 不实现）。
4. 分值 `scores` 的尺度随 embedder/词法降级切换（0304/0290 既有行为），跨运行不可直接比较。
5. 压实内部读不再计入指标，但其他内部调用（如摘要器材料收集）若未来改用 `read()` 需同样
   走私有检索体，否则会虚增 recall 计数（代码注释登记）。
