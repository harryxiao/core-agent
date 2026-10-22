# Design — 0305 结晶 / 溶解钩子可用化

## D1 复用阈值与显式豁免

```python
CRYSTALLIZE_MIN_REUSE = 3

def crystallize(self, skill_entry: MemoryEntry, *, force: bool = False) -> PluginCandidate | None:
    if not force and skill_entry.reuse_count < CRYSTALLIZE_MIN_REUSE:
        return None
    ...
```

阈值取 **3**：SDD §「默认阈值」写明「技能晋级至少 3 次成功或 1 次显式用户要求」；`force`
即「显式要求 / 已获人工批准」。**被拒**：把阈值做成配置键（当前无第二个消费方，配置面只会
制造未测试组合）；低于阈值抛异常（钩子是可选的资格判定，`None` 更易组合）。

## D2 引擎不再丢弃产物

`EvolutionOutcome` 新增可选字段 `artifact: PluginCandidate | None = None`。
`_crystallize_plugin()` 以 `force=True` 调用钩子并保存返回值；未注入 crystallizer ⇒ `None`。
`status` 仍为 `accepted`（「已批准、待人工实施」语义不变）。

`force=True` 的依据：`EvolutionEngine.crystallize()` 到达 `_crystallize_plugin()` 前已强制
`confirm`（架构级候选还需匹配的已批准审批单）⇒ 属于「显式用户要求」豁免，而非绕过门禁。

**被拒**：给 `GenerationCandidate` 补 `reuse_count`（进化候选没有复用计数语义，硬造会造假证据）；
把 `PluginCandidate` 写入记忆或技能库（钩子契约是「交 L4 Validator」，落盘由调用方决定）。

## D3 溶解条目可入库

`Crystallizer.dissolve()` 的 `trace_id` 改为 `f"evolution.dissolve.{plugin_id}"`（非空、可审计、
与引擎自身 `evolution.dissolve.*` 的 L2 教训 id 前缀同域但不冲突：钩子产物 id 为
`dissolved.<plugin_id>`，层 L3）。

**被拒**：让钩子接收 store 自动落盘（把存储依赖塞进纯函数）；删除该钩子（`memory-interface`
§4 仍是对外契约，保留并修正其可用性）。

## D4 兼容与局限

- `crystallize()` 返回类型变为可空：直接调用方须处理 `None`；引擎路径已处理。
- `EvolutionOutcome` 新增默认字段 ⇒ 既有构造 / 相等 / 序列化零变化。
- 阈值 3 无配置开关；`force` 只应由「已确认 / 显式要求」路径使用，钩子本身无法验证该前提
  （纯函数无审批上下文）—— 依赖调用方纪律，已在接口文档写明。

## 测试与反证计划

新增 `tests/test_memory_crystallizer.py`：

1. `reuse_count=2` ⇒ `None`；`=3` ⇒ 候选，`source_entry_id` 正确；
2. `reuse_count=0, force=True` ⇒ 候选；
3. `dissolve()` 产物 `trace_id` 非空，`store.write("L3", lesson)` 成功且 `audit()` 可见；
4. 引擎 plugin 候选：`outcome.artifact` 为钩子产物、`source_entry_id` 指向合成条目、状态仍
   `accepted`；未注入 crystallizer ⇒ `artifact is None`。

反证（`cp` + `md5sum`）：去复用门 ⇒ 用例 1 红；去掉 `force` 豁免 ⇒ 用例 2 红；`dissolve` 仍用
空 `trace_id` ⇒ 用例 3 红；引擎仍丢弃返回值 ⇒ 用例 4 红。
