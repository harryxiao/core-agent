# Design — 0304 召回多样性与注入统计

## D1 API：`recall()` 返回结果对象，`read()` 保持兼容

```python
@dataclass
class RecallResult:
    entries: list[MemoryEntry]
    matched_count: int = 0
    injected_count: int = 0
    excluded_by_budget: int = 0
    excluded_by_diversity: int = 0
    minimum_budget: int = 0
```

`MemoryStore.recall(...)` 使用与 `read()` 完全相同的参数；`read()` = `recall(...).entries`。
被拒：给 `read()` 加 `with_stats=True` 开关（返回类型不稳定）；把统计塞进条目字段
（把调用方信息污染进数据）。

## D2 管线位置

```
候选集 → 既有硬过滤（来源/会话/遗忘/层/status） → 排名 → 多样性过滤 → 预算截断 → 强化
```

多样性与 `_truncate` 同在排名之后；被多样性剔除的条目**不进入预算分配**、不被 `_reinforce`
强化。排序本身不变（不为凑配额重排）。被拒：在排名前按 kind 分桶（会改变相关性主序）。

## D3 近重复判据

`content_hash`（`0303` 写入时已算）相同 ⇒ 只保留排名最高的一条。旧行 `content_hash`
为空串时，用同一函数现算（不落盘）。`content.strip()` 为空 ⇒ **不参与**近重复抑制
（避免把所有空正文压成一条）。近重复跨层 / 跨 source 生效（完全同文即视为重复）。

## D4 同会话上限

`session_id` 非空时每会话最多 `_MAX_PER_SESSION = 3` 条；`session_id == ""` 的全局条目
（关键事实、摘要、L2 笔记等）不受限。计数在排名顺序上先到先得。

**收窄豁免**：调用方已用检索参数 `session_id` 收窄到单会话（`DynamicAssembler` 的事实面即如此）
时不施加该上限 —— 结果本就出自同一会话，施加上限只会截断该会话自身的事实面（`test_loop_causal_link`
暴露此交互）；上限只在跨会话混合结果中起多样性作用。近重复抑制不受此豁免影响。

## D5 统计口径

- `matched_count`：通过既有硬过滤后**进入排名**的候选数。
- `injected_count`：最终返回条目数。
- `excluded_by_diversity`：近重复 + 会话上限剔除数。
- `excluded_by_budget`：`_truncate` 因预算跳过的条目数。
- 不变式：`matched_count == injected_count + excluded_by_diversity + excluded_by_budget`。
- `minimum_budget`：`_truncate` 中**第一条**因预算被跳过者「已用预算 + 自身成本」；
  无预算剔除 ⇒ 0。`read()` 调用方不感知，`recall()` 调用方据此判断扩容收益。
- `_truncate` 签名与语义不变（既有直测仍有效）；新增内部 `_truncate_with_stats()` 返回
  选中列表 + 剔除数 + `minimum_budget`，`_truncate()` 委托取首项。

## D6 兼容与局限

- `read()` 签名 / 返回类型 / 排序 / 预算语义不变；变化仅在「返回集合可能更小」。
- 首条仍无条件保留（可能超过预算）——既有行为，不在本变更收紧。
- 会话上限是固定常量（无配置键）；SDD 的 kind 配额与 `maxPerSource` 因字段语义不匹配不做
  （见 proposal Non-goals）。
- 近重复是**完全同文**级，不做语义近重复（需 embedding 阈值，另行评估）。

## 测试与反证计划

新增 `tests/test_memory_recall_diversity.py`：

1. 同会话 4 条 + 其他会话 1 条 ⇒ 该会话最多 3 条，其他会话可见；
2. 全局条目（`session_id=""`）不受会话上限；
3. 完全同文两条 ⇒ 只回排名最高一条；空白不同视为同文；空正文不合并；
4. `recall()` 统计不变式与 `injected_count`；
5. 小预算 ⇒ `excluded_by_budget > 0` 且 `minimum_budget` 可让下一条入选；
6. `read()` 与 `recall().entries` 一致。

反证（`cp` + `md5sum`）：去近重复抑制 ⇒ 用例 3 红；去会话上限 ⇒ 用例 1 红；
把多样性放到预算后 ⇒ 用例 5 的「不吃预算」断言红；统计返回条目数硬编码 ⇒ 用例 4 红。
