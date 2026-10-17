# Design 0251 — L2 活跃层软上限的组合根接线

## 决策

### D1 新键 `memory.l2_soft_max_entries`（缺省 `None`）

- `ConfigSpec("memory.l2_soft_max_entries", "--memory-l2-soft-max-entries",
  "CORE_MEMORY_L2_SOFT_MAX_ENTRIES", default=None, map_to="memory.l2_soft_max_entries",
  exposure=ConfigExposure.ADVANCED)`。
- **缺省 `None` = 能力关闭**：与 `MemoryStore` 形参语义一一对应，避免一个缺省数字在升级后
  静默归档用户数据。是否设默认上限是运维决策。
- `memory` 是**非结构化段**（`_build_config` 落 `extra`）⇒ 不参与 schema 校验，非法取值
  由访问器归一（对齐 `importance_gate()` / `relation_extract()` 先例）。

### D2 访问器 `ConfigManager.l2_soft_max_entries() -> int | None`

```python
if self._config is None:
    return None
raw = cast("dict[str, Any]", self._config.extra.get("memory") or {})
value = _parse_int(raw["l2_soft_max_entries"]) if "l2_soft_max_entries" in raw else None
return value if value is not None and value >= 1 else None
```

- `_parse_int` 已拒绝 `bool`、小数、非数值（对齐 `_as_number` 口径）。
- `0` / 负数 ⇒ `None`：`0` 若直通会**清空 L2**（每次写入都迁走可遗忘条目），是危险的
  配置笔误方向；归一为「关闭」不丢数据。
- 返回 `int | None`（不返回 `MemoryStore` 类型）——`configuration` 是底座模块，不得 import
  能力层 `memory`（`test_architecture.py` 约束）。

### D3 组合根接线

`build_runtime` 的 `MemoryStore(...)` 增 `l2_soft_max_entries=config.l2_soft_max_entries()`。
`_enforce_l2_cap` 在 `write()` 落库后调用（`store.py:423`），先走 `forget()` 衰减归档、
再按 `ts` 最旧迁移可遗忘条目至 L4（`l2_cap.<id>` trace，可撤销）——本变更**不碰**该实现。

### D4 文档订正（L1 索引口径）

`memory.md` 的 L1 行改为事实口径：「后端维护的 `id → layer` 索引（`list_index()`），
用于迁移/审计定位，**不参与检索打分**」。避免把「索引未用于召回」误读为「L1 未实现」。

## 反证设计

| 探针 | 摘除 | 预期红测试 |
|---|---|---|
| P1 | `build_runtime` 的 `l2_soft_max_entries=` 实参 | 接线断言 + 端到端收口用例 |
| P2 | `ConfigSpec` 条目 | 三面元组用例（CLI flag / env / map_to 不存在） |
| P3 | 访问器的 `>= 1` 归一 | 非法取值 `0` / 负数用例（会返回 0/负数） |
| P4 | env 面的 `map_to`（改键名） | env 覆盖用例 |

## 局限

1. 软上限只在**写入后**收口：启动时已超限的存量库要等下一次写入才收敛（不在 `load()`
   里跑，避免启动即迁移）。登记。
2. 仅收口 L2；L4 归档只增不减（「不物理删除」规格的必然结果）。
3. `FileBackend` 仍整份加载 JSONL，上限降低的是**活跃条目数**与检索扫描面，不改变文件总体量。
4. 非法取值静默归一为关闭（`memory` 段非阻断口径），不给出启动期错误 —— 与同段其余键一致。
