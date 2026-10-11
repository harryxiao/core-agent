# Proposal 0206 — 记忆后端落盘耐久（原子写 + 逐行容错，缺省生效）

## 为什么

六能力走查（2026-10-11）发现的**唯一启动级硬伤**：`memory.jsonl` 是动态记忆主库，却是全仓
唯一「写非原子＋读不容错」双无防护的落盘面：

- `FileBackend._persist`（`src/core/memory/backend.py:81-86`）`path.write_text` 全量重写
  **非原子**——写中途进程被杀 ⇒ 文件半写/截断；
- `_load`（`:70-79`）对 `json.loads` **无任何容错**——半写后的下次启动 `MemoryEntry(**json.loads(line))`
  直接抛异常 ⇒ `build_runtime` 起不来 ⇒ **客户端整体不可用**。

对照组：`CheckpointStore` 早已双防护（`durability/store.py:97-99` tmp＋`os.replace`；`:107-110`
坏行跳过）；`BenchmarkRegistry` / `SkillLibrary` 等单文件态均走 `write_state` 原子写。记忆库恰是
**写入频率最高**的那个（每轮 `remember`、压实、抽取都写），暴露度最大。

## 做什么

- `_persist` 改 **tmp ＋ `os.replace`** 原子替换（镜像 `persistence.write_state` 的写法；JSONL
  是拼接串，不复用 `write_state` 本体以免二次编码）。
- `_load` 逐行 `try/except (ValueError, TypeError)` 跳坏行 ＋ `warnings.warn` **只报损坏行数**
  （不回显内容——条目可能含敏感信息，守密钥红线）。
- **缺省生效，无开关**：这是缺陷修复而非新行为——完好文件的行为**逐字不变**；损坏文件从
  「启动崩溃」变为「跳过坏行」。本批 9 个 change 中唯一不开门控的例外，ADR-0196 明写理由。

## 规格影响

`memory` **ADDED** 一条要求「记忆后端落盘耐久（backend durability）」（4 Scenario：半写不损坏 /
坏行跳过 / 完好往返逐字节不变 / SIGKILL 后重载可读）。canonical Requirement **15 → 16**，
Scenario **111 → 115（+4）**。其余 15 条 Requirement 逐字保留。

## 风险

- **原子替换留 `.tmp` 残骸**：替换未发生时 tmp 文件可能残留（下次写入覆盖）——与
  `CheckpointStore` 同口径，不额外清理。
- **坏行被永久跳过后又被全量重写覆盖**：坏行不会自行修复，下一次 `_persist`（任一写操作）
  即以完好集合覆盖之——「坏行寿命 = 到下次写为止」，可接受（修复面另有 0174 运维动词）。
- **告警噪音**：每次构造后端只告警一次（`__init__` 的 `_load` 路径），不刷屏。
