# design — 0089 observability 生产导出器装配

## 决策

### ① 缺省导出面 = `BufferedExporter(JSONLExporter(traces.jsonl))`

规格两条要求同时落到一处装配：
- **「全链路日志」**：结构化 JSONL ⇒ `JSONLExporter`（已实现，追加写）；
- **「遥测缓冲与导出重试」/「遥测故障不阻塞主循环」**：`BufferedExporter.emit` 内部对 `inner.emit` 的
  异常 `except` 降级 + 指数退避（`exporter.py`），**绝不抛出** ⇒ 主循环 `end_trace → emit` 不会因落盘失败中断。

不套缓冲（裸 `JSONLExporter`）会在磁盘满 / 权限不足时**从 `end_trace` 抛进 loop** —— 直接违反规格场景
「遥测故障不阻塞主循环」。故**必须**套 `BufferedExporter`；这不是装饰，是规格要求的失败隔离层。

### ② 落 `$CORE_STATE_DIR/traces.jsonl`（复用既有约定）

新增 `_trace_path()`，与 `_checkpoint_path` / `_memory_path` / `_skill_state_path` / `_pet_state_path` /
`mcp.endpoints` 的 `$CORE_STATE_DIR`（缺省 `~/.core/state`）约定**同源**：env 覆盖便于测试隔离
（`tests/conftest.py` 的 autouse 夹具已把 `CORE_STATE_DIR` 指向每测试 tmp）。**不新增目录约定**。

> 说明：既有各 `_*_path` 是**各自计算 base** 的同型小函数（历史风格），本变更**随其风格**新增一个，不顺手
> 抽公共 helper —— 抽取会改 5 处既有函数，属「改动超出本请求」的越界（CLAUDE.md §3）。

### ③ 注入优先（`tracer=` 形参不动）

`build_runtime(..., tracer: Tracer | None = None)` 已存在（宿主/SUT 替换导出面的接缝）。本变更**只填
`else` 分支**：`tracer = tracer if tracer is not None else Tracer(exporter=…)`。显式注入者**不被覆盖**，
既有注入调用（若有）行为不变。

### ④ 不扩面

- **不加配置开关**（`observability.exporter = jsonl|console|noop`）：规格未要求可配；YAGNI（CLAUDE.md §2）。
  要换导出面走 `tracer=` 注入。
- **不加 `Runtime` 字段**：`Runtime` 字段集被多测试隐式断言（`0088` design 已记同理），不动。
- **不引入 OTel/Prometheus SDK**：属「指标导出协议」的第三方依赖半，与 ADR-0044「核心零三方依赖」红线相关，
  另案裁决。

## 影响面

- **既有测试**：`conftest` 已隔离 `CORE_STATE_DIR` ⇒ 缺省导出落 tmp，不污染真实 home、不跨测试串。
  驱动完整 loop 的测试会**多写一个 tmp `traces.jsonl`**（无害；无测试断言「未产生该文件」）。
- **`--feature` 门控**：observability 不在 `runtime.GATABLE_MODULES`（`pet`/`beast`/`evolution`）内，
  导出器装配**不受开关影响**（规格「全链路日志」无条件）。
- **性能**：每 `end_trace` 追加一次 JSONL（缓冲层内即刷）；与既有 `checkpoints.jsonl` / `memory.jsonl`
  落盘同级，无新增数量级。
- **`0086`/`0087`/`0088`（pet）**：pet 专属 loop 复用**同一** tracer（`runtime.py:717`）⇒ 宠物事件一并落盘，行为一致。
