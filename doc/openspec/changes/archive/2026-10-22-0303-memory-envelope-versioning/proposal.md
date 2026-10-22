# 0303 记忆条目治理信封与关键事实版本链（memory-sdd P1-1 子集 + P1-2）

## Why

对照 `ai-arch/docs/memory-sdd.md` v1.0 走查（P1-1 / P1-2）：

1. **P1-1 信封缺治理字段** —— `MemoryEntry` 只有 10 个字段，无内容哈希、无状态、无版本。
   SDD §4.1 要求的治理面在数据模型层**无法表达** ⇒ 去重（A3）、取代（A4）、污染防护（A10）
   都缺承重字段（`src/core/memory/protocol.py`）。
2. **P1-2 语义事实原地覆盖** —— 关键事实固定 id `keyfact.<slug>` **覆盖式更新**
   （`store.py::_write_key_fact`）。SDD §4.3 / §5.5 明确要求：同一
   `(namespace, subject, predicate)` 的新值 SHALL **新增记录**、旧记录转 `superseded`，
   **不得原地覆盖**。现状下旧值不可查 ——「当时为什么这么记」永远回答不了，A4 场景失败。

## What Changes

- `MemoryEntry` 增治理信封字段（**旧行兼容，全部有默认值**）：
  - `content_hash: str = ""` —— 正文归一化后的 SHA-256（写入时自动计算）；
  - `status: Literal["active", "superseded"] = "active"`；
  - `version: int = 1`；
  - `parent_id: str = ""`（被本版本替代的条目 id）；
  - `superseded_by: str = ""`（仅旧版本填写，指向替代它的新版本 id）。
- **关键事实版本链**：同实体取值变化 ⇒ 新增版本条目 `keyfact.<slug>.v<N>`
  （`version` 递增、`parent_id` 指向旧版），旧版置 `status="superseded"` /
  `superseded_by`；**取值未变** ⇒ 仍在原条目就地刷新溯源（幂等，不增长、不升版）。
- **读取面默认只见最新**：`read()` 在排名与预算之前剔除 `status != "active"` 的条目；
  `audit()` 仍返回全部（历史可追溯）。
- 取代动作记可逆效应（`memory.supersede`），随同一 `compaction.<session>` trace 回滚。

## 明确的取舍（本 change 不做）

- **不加** `namespace` / `trust` / `confidence`：当前**无消费方**（租户隔离、信任分级、
  置信度生产者均未落地），加了只是死字段 —— 待对应能力立项时一并加。
- **关系条目不做版本链**：关系 id 已编码完整三元组 `(head, predicate, tail)`，
  **同一 id ⇒ 同一事实**，覆盖写不丢信息；changed tail 天然是新 id。关系仅获得信封字段
  （`content_hash` 等默认值）。
- 不引入保留期 / 墓碑 `retracted` 状态（P2-3 面）；不改摘要 / 情景归纳的覆盖写语义。

## Impact

- 规格：`memory` **ADDED** ×1（条目治理信封）+ **MODIFIED** ×2（关键事实落库 / 跨压实合并）。
- 代码：`src/core/memory/protocol.py`、`src/core/memory/store.py`。
- 测试：新增版本链用例；改写两条「覆盖式更新」既有用例。
- 文档：`doc/02-modules/memory.md`、`doc/03-interfaces/memory-interface.md`、ADR、台账。
- 落盘兼容：旧 `memory.jsonl` 行缺新键 ⇒ 默认值加载；新行旧代码不识别（单向兼容，可回退）。
