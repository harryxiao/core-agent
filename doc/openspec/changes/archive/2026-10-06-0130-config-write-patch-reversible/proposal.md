# 变更提案：配置写回的可逆效应（change 0130 / 账本 E68）

## 背景（缺陷）

`ConfigManager.apply_change` 把内存配置变更记为可逆效应（`Effect(op="config_apply", undo=self._restore(previous), trace_id="config")`），
但**落盘**的 `write_patch` **完全不记账**：

- `src/core/configuration/manager.py:555-569`：`tmp.write_text(...)` + `os.replace(...)` 直接改文件，无 `EffectTracker.record`。

后果：配置变更实际作用于**两处状态**（内存 `AppConfig` + `config.yaml` 文件），而可逆账只覆盖其中一处。任何按 `trace_id="config"`
回滚的动作（`EffectTracker.rollback("config")`）**只回退内存**，磁盘仍是新值 ⇒ **内存/磁盘不一致**；下一次 `load()` 会把已"回滚"的
变更**复活**。违反 P2（一切副作用可逆）。

不是「原子写没做」——`0099` 已用 tmp + `os.replace` 保证**不留半写**；缺的是**写回这件事本身没有撤销记录**。

## 决策

`write_patch` 在 `os.replace` **之前**向同一个 `EffectTracker` 记一条 `Effect(op="config_write_patch", target=<yaml 路径>,
undo=恢复写盘前原文, trace_id="config")`：

- 与 `apply_change` **同 trace**（`"config"`）⇒ 一次 `rollback("config")` 同时回退**内存与磁盘**，二者一致；
- undo 恢复写盘前的 **yaml 原文字节**（不是重新 dump —— 原文含用户注释之外的一切原样格式，重 dump 会改写文件）；
- 记录时机在 `os.replace` **之前**：`os.replace` 是原子的，若它在记账后抛出，yaml 仍是旧值，undo 写回旧值即幂等 no-op。

### 不做

- **不改** `write_patch` 的原子写策略（`0099` 已定，`os.replace` 保持）。
- **不新增** 配置回滚的生产入口（本 change 只补齐**可逆契约**；无回滚入口时不产生行为差异，见 ADR-0123 已知局限）。
- **不**把 undo 实现为「重新 `_dump_yaml` 内存配置」——内存配置叠加了 env/cli 覆盖，会污染 yaml（`write_patch` docstring 早已写明只落用户 patch）。

## 规格 delta

`configuration` **MODIFIED**「配置校验与生效」：追加「写回 yaml 的变更 SHALL 记录可逆效应，undo 恢复写盘前原文，使按 trace 回滚时
磁盘态与内存态一致」+ 1 Scenario。

## 影响面

| 面 | 改动 |
|---|---|
| `src/core/configuration/manager.py` | `write_patch` 记账 + 新增 `_restore_yaml` |
| `tests/test_configuration.py` | 3 新用例（磁盘+内存一并回滚 / trace 单一 / 记录先于替换） |
| 文档 | ADR-0123 + `configuration-interface.md` §2 + `02-modules/configuration.md` + TC 节 |
