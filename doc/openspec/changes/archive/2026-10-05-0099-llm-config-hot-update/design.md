# 设计 — LLM 配置热生效与落盘持久化（change 0099）

## 1. 两个入口，不是一个

`set_llm_config` 现被**两条路**调用：① `entry._build_ui`（启动期，`entry.py:371`）把 runtime 解析出的
LLM 配置 **hydrate** 进 API 层；② `PUT /llm-config`（用户保存）。二者意图相反：

| 入口 | 语义 | 该落盘吗 |
|---|---|---|
| `set_llm_config(cfg)` | 启动期 hydrate（值可能来自 env/CLI，**yaml 里未必有**） | **否** —— 否则每次 `core-agent run` 都重写 config.yaml |
| `apply_llm_config(cfg, *, output_reserve=None, max_rounds=None)` | 用户显式保存 | **是** |

故**保留 `set_llm_config` 语义不变**，新增 `apply_llm_config`。HTTP `PUT` 走后者。
（若强行让 `set_llm_config` 落盘，`_build_ui` 会在**每次启动**把 env/CLI 覆盖值物化进 yaml ⇒
「读配置」变成「写配置」，真回归。）

## 2. 一次 patch、一次原子落盘 = 「不留半写状态」由构造满足

`apply_llm_config` 组**单个** patch：

```
{"llm": {api_key: cfg.api_key_ref, provider, model, endpoint,
         reasoning_effort, embedding_model, context_window},
 "loop": {output_reserve?, max_rounds?}}
```

（注意 yaml 键是 `llm.api_key`，映射到 `LLMConfig.api_key_ref` —— 与 `_build_config:527` 同源。）

然后按 `entry._config_set`（`entry.py:471`）的既有范式：`apply_change`（校验+内存生效）→ `write_patch`
（落盘）→ `load`（重读重校验）。**单 patch** ⇒ 不存在「llm 写了、loop 没写」的中间态。

**为何 `write_patch` 须先改原子**：原实现 `self._yaml_path.write_text(...)`（`manager.py:495`）是
**先截断再整写** —— 写盘中途失败留空/半写文件，此时再 `load()` 回滚读到的是**坏文件**（回滚路径自身失效）。
改 tmp + `os.replace`（`0062` 的 `CheckpointStore`、`0074` 的端点注册表同款，stdlib 零依赖）：
成功路径字节不变，失败路径**旧文件原样**。

## 3. 热生效：`set_limits` + `runtime_checkable` Protocol

`DefaultLoop` 的 `self._max_rounds` / `self._token_budget` 在**每轮**判定处读取
（`:199` 轮数、`:243` 硬停、`:305` 压实）⇒ **赋值即生效**，无缓存、无需重建循环。故 `set_limits` 是
纯赋值（`None` = 不改该项）。

`UIAPILayer._loop` 的类型是 `LoopPlugin`（协议）—— 不能假定它是 `DefaultLoop`（本仓有
ReAct / Plan-Execute 等可替换策略）。故在 `core/loop` 定义：

```python
@runtime_checkable
class LimitsConfigurable(Protocol):
    def set_limits(self, *, max_rounds: int | None = None,
                   token_budget: int | None = None) -> None: ...
```

`UIAPILayer` 用 `isinstance(self._loop, LimitsConfigurable)` 判定后调用。**依赖方向不变**
（`ui/api.py:17` 已 `from core.loop import ...`）；不把 UI 焊死在 `DefaultLoop`；不支持者**跳过**
（不抛 —— 换策略插件不该让保存失败）。

**推给 loop 的值取 `config.loop_limits()` 的派生结果**（0098 单一派生点）—— **不在 UI 层重算**
`context_window - output_reserve`（否则就是第二个派生真源）。

## 4. GET 回显「生效值」，PUT 接受「旋钮」

- **PUT** 收 `output_reserve`（旋钮，缺省不改）。
- **GET** 回 `context_window` + `token_budget`（**派生后的生效预算**）+ `max_rounds`。

理由：旋钮是输入、预算是可观测结果；让 UI 显示「当前预算 122880」比回显「预留 8192」更贴近用户问的
「Context Window Size 生效了吗」。且免在 `ConfigManager` 上再开一个「读 `output_reserve` 原文」的访问器
（第二派生/读真源）。

## 5. 失败语义

- 非法取值（`context_window` ≤ 预留、`max_rounds` < 1…）⇒ `apply_change` 内的 0098 校验器抛
  `ConfigurationError` ⇒ `apply_llm_config` 归一为 `UiError(UI_LLM_CONFIG_INVALID)`；**内存与 yaml 均不变**
  （`apply_change` 先校验后替换，失败不改 `self._config`）。
- 写盘失败 ⇒ 原子写保证 yaml 原样；随后 `load()` 把内存回到落盘态。

## 6. 与 0098 / 0100 的边界

0098 给「可配」；0099 给「改了立即生效且不丢」；0100 给「点得着的界面」。
**顺序不可换**：无可配项则无物可热更；无热更 API 则前端只是摆设。
