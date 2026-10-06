# 0136 · composition 覆盖可回退 + 覆盖值类型边界

> 账本：`coding-plan/phase-34.md` **E75**（覆盖不可回退）+ **E70**（bool 越界）
> 规格面：`composition/spec.md` **MODIFIED「层叠解析」** ｜ ADR：**0129**

## Why

`composition/spec.md`「层叠解析」已 SHALL「解析结果可逆、可回退」，Scenario「确定顺序解析」的
THEN 亦写明「卸载时可回退到覆盖前状态」；「patch.yml 用户覆盖」Scenario「覆盖冲突兜底」还要求
「报错并回退到覆盖前状态」。**但实现侧无任何回退路径**（E75）：

- `ProfileResolver.resolve()`（`resolver.py:106-108`）把 patch 覆盖应用到 `merged` 后，
  **覆盖前的分层结果 `merged` 直接被丢弃** —— 返回的 `ResolvedSet` 只留 `plugins`（覆盖后）
  与 `overrides`（覆盖值），无法还原「覆盖前」。
- 全包（`src/core/composition/`）**无 revert / undo / restore API**，调用方拿到 `ResolvedSet`
  后没有任何路径走回覆盖前状态 ⇒ 规格的「可回退」是**死条款**。

同处另有一处类型边界漏洞（E70）：`apply_patch` 以 `isinstance(override, int)` 判定覆盖值合法性，
而 Python 中 `bool` 是 `int` 的子类 ⇒ YAML 的 `true` / `false` 会**静默**落为 generation `1` / `0`，
既非用户本意，也绕过了「值类型不支持则报冲突」的兜底。

## What Changes

1. **规格先行**：`composition/spec.md` **MODIFIED「层叠解析」**——解析结果 SHALL 保留覆盖前分层结果
   与生效覆盖项、SHALL 提供回退（幂等）；patch 覆盖值 SHALL 为整数 generation，布尔 SHALL 按
   `PATCH_CONFLICT` 拒绝。新增 2 个 Scenario（「回退到覆盖前状态」「布尔覆盖值拒绝」），原
   「确定顺序解析」Scenario 逐字保留。
2. **实现（E75）**：`ResolvedSet` 增 `layered: list[PluginRef]`（覆盖前分层结果，必填字段）；
   `resolve()` 原样携带；新增 `ProfileResolver.revert(resolved) -> ResolvedSet` —— 返回**新**结果
   （`plugins` 取 `layered`、`overrides` 清空、`layered` 原样携带 ⇒ **幂等**），**不改实参**。
   门面 `CompositionEngine.revert` 透出。
3. **实现（E70）**：`apply_patch` 的 `isinstance(override, int)` 补 `and not isinstance(override, bool)`
   ⇒ 布尔按 `PATCH_CONFLICT` 拒绝，不再静默落为 `1` / `0`。

## 判据订正（相对计划）

- 计划写「保留 `layered` 于结果 + 加 `revert()`」，未指定 `layered` 的字段性。本 change 取
  **必填字段**（`ResolvedSet` 的构造点全仓仅 `resolver.py:108` 一处，无既有调用方受损）——
  若给默认值 `[]`，手工构造的 `ResolvedSet` 一旦漏传，`revert` 会**静默清空全部插件**；
  必填使「解析结果必然知道自己的覆盖前状态」成为类型层事实。
- 计划未定 bool 拒绝的错误码；沿用既有 `PATCH_CONFLICT`（值类型不支持的既有分支，不新增错误码）。

## Impact

- 代码：`src/core/composition/models.py`、`resolver.py`、`engine.py`。
- 测试：`tests/test_composition.py`（+5）。
- 文档：`doc/03-interfaces/composition-interface.md`（§2 数据类型 / §3 门面 / §5 约束）、
  `doc/04-testing/test-cases.md`（§52）。
- 兼容：`ResolvedSet` 增必填字段属**签名变更**，仓内无其它构造点（grep 实证），零回归。

## 已知局限

- `revert` 只回退 **patch 覆盖**（回到 bundle 层叠结果），**不**回退「层叠本身」（选 profile / 换 bundle）；
  bundle 级回退不在本账范围，规格「bundle 校验失败」Scenario 的「回退到引入前」由 `BundleDistributor` 面承载。
- `revert` 为**纯函数**（返回新 `ResolvedSet`），不产生副作用、不经 `EffectTracker`；
  需要跨调用持久回退的调用方自行持有 `ResolvedSet`（与 `resolve` 同为无状态代数）。
