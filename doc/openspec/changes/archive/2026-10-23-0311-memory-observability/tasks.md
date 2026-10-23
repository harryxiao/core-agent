# Tasks — 记忆指标与效果评测（0311）

## 1. 规格与红灯

- [x] 1.1 写 `specs/memory/spec.md` delta（MODIFIED「召回的多样性控制与注入统计」；
      ADDED「记忆运行指标快照」「记忆运维统计」「召回解释」「记忆效果离线评测」）
- [x] 1.2 新增 `tests/test_memory_metrics.py`：写入 / 重放 / 拒收计数、recall 统计累计、
      压实内部读不计、压实耗时与失败计数、`reinforce=False` 零写回、快照键名与零 I/O
- [x] 1.3 新增 `tests/test_memory_stats.py`：纯函数聚合（层/状态/泛 forgotten/体积/审计派生）、
      缺文件与坏行降级、有序 JSON 形状
- [x] 1.4 新增 `tests/test_memory_stats_cli.py`：`memory stats` 文本与 `--json`、零强化、
      空库输出；`memory why` 统计行/条目序/分值/脱敏/零强化/无命中退出 0
- [x] 1.5 新增 `tests/test_memory_effectiveness.py`：有/无记忆回放成功率、token 对比、
      确定性重放
- [x] 1.6 扩充 `tests/test_memory_recall_diversity.py`：`injected_tokens` / `scores` 与既有
      不变式共存；`reinforce=False` 的 `reuse_count` 不变
- [x] 1.7 跑新用例确认全红（`metrics_snapshot` / `collect_stats` / `reinforce` /
      `injected_tokens` / `scores` / CLI 子命令缺失）

## 2. 实现

- [x] 2.1 `src/core/memory/protocol.py`：`RecallResult` + `injected_tokens` / `scores`；
      `read()` / `recall()` + `reinforce: bool = True`
- [x] 2.2 `src/core/memory/stats.py`：`MemoryMetrics`（进程内计数 + `snapshot()`）与
      `MemoryStats` / `collect_stats()`（纯函数）
- [x] 2.3 `src/core/memory/store.py`：
      - `MemoryStore.metrics_snapshot()`；`write()` / `recall()` / `compact()` 计数接线
      - `recall()` 拆出不经计数的私有检索体（压实内部打分读改用它）
      - `reinforce=False` 跳过 `_reinforce`（零写回/零效应）
      - `_truncate_with_stats` 返回 `used`；`recall()` 捕获分值与注入 token
- [x] 2.4 `src/core/memory/__init__.py`：导出 `MemoryMetrics` / `MemoryStats` / `collect_stats`
- [x] 2.5 `src/core/entry.py`：`memory stats [--json]` 与 `memory why <query> [--budget N]
      [--session S]` 解析器、处理器、注册与用法串
- [x] 2.6 新用例转绿；全量 `uv run pytest` 基线 +新增

## 3. 门禁与反证

- [x] 3.1 `uv run ruff check`、`uv run ruff format --check`、`uv run pyright`（0 errors）
- [x] 3.2 反证（`cp` 到 `/tmp` + `md5sum` 复原），逐条至少一红：
      - 去掉 `reinforce=False` 门控 ⇒ 零强化用例红；
      - 去掉压实内部读的私有检索体 ⇒ recall 计数用例红；
      - 去掉 `injected_tokens` 传递 ⇒ recall 统计用例红；
      - 去掉审计派生计数 ⇒ stats 用例红；
      - 无记忆臂误用有记忆库 ⇒ 效果评测红
- [x] 3.3 `openspec validate 0311-memory-observability` 通过；`openspec validate --all`

## 4. 文档

- [x] 4.1 `doc/02-modules/memory.md`：新增 §3.24「指标、统计与召回解释」（数据来源、口径、
      进程作用域、局限）+ §3.25「有/无记忆效果评测」或并入 §3.24
- [x] 4.2 `doc/03-interfaces/memory-interface.md`：`RecallResult` 新字段、`reinforce`、
      `metrics_snapshot()`、`memory stats` / `why` 输出形状
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0301（指标进程内 + 持久统计从既有数据派生；
      被拒：读路径 metrics 落盘 / 复用 MetricsCollector / 定时快照）
- [x] 4.4 `coding-plan/known-risk.md`：E247 行（§1）+ ADR-0301 局限（§3）
- [x] 4.5 `doc/04-testing/test-cases.md`：§224（TC-MEMOBS-01~N、TC-MEMEFF-01~N）
- [x] 4.6 `coding-plan/cli-contract-baseline.md`：登记 `memory stats` / `memory why`
- [ ] 4.7 归档（用户确认后）+ 提交 + 推送
