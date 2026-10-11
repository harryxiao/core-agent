# Design 0206 — 记忆后端落盘耐久

## 决策

1. **不复用 `persistence.write_state` 本体**：它对 payload 做 `json.dumps`，而 JSONL 已是拼接
   串——复用会二次编码。只镜像其 **tmp ＋ `os.replace`** 写法（与 `CheckpointStore._persist`
   `durability/store.py:97-99` 同型）。
2. **容错面收 `ValueError | TypeError`**：`json.JSONDecodeError` ⊂ `ValueError`（半行/坏 JSON）；
   `MemoryEntry(**record)` 对缺字段/多字段抛 `TypeError`（结构不符行）。不收 `OSError`——读失败
   （权限/IO）仍应炸启动（环境问题 ≠ 数据损坏）。
3. **告警单次、只报计数**：`_load` 末尾汇总 `损坏 N 行`＋文件名；不回显行内容（条目可能含
   敏感信息）。与 `CheckpointStore` 的静默跳行、`BenchmarkRegistry` 的降级告警同族但更吵一点
   （记忆库损坏用户应知晓）。
4. **无开关**：修复的是「损坏文件 ⇒ 起不来」这条缺陷路径；完好文件行为逐字不变。给它加开关
   等于允许用户把「起得来」关掉——荒谬。本批唯一缺省生效的 change。
5. **反证锚**：半写用例以「monkeypatch `Path.write_text` → 截断自身再抛 `OSError`」注入失败点
   （镜像 `tests/test_durability_crash.py:50-71`）——旧实现失败点落在**目标文件**上（截断即
   全丢 ⇒ 红）；新实现失败点落在 **tmp** 上（目标不动 ⇒ 绿）。
