# 0070 pet 前置判定接入 ConfigSpec 三层链（yaml 层）（账本 E21）

## Why

账本 E21：`entry._pet` 的宠物门控把三层链**当成两层**用 ——

```python
if not _as_bool(resolve("pet.enabled", cli=cli, env=os.environ)): ...   # 漏 yaml=
persons_dir = str(resolve("pet.persons_dir", cli=cli, env=os.environ) or "persons")
```

`resolve` 的 `yaml=` 缺省为空 ⇒ 前置判定**永远看不到 config.yaml**：用户在配置里写
`pet.enabled: true` 仍被判为未启用（`pet` CLI 直接退出 0），`pet.persons_dir` 被静默忽略、
回落 cwd 下的 `./persons`。而**同一进程**稍后的 `build_runtime(ConfigManager(...))` 走
`load()`（含 yaml 层），二者判据不一致。

规格 `doc/openspec/specs/configuration/spec.md`「宠物模式配置」明文要求：
「…经 `resolve()` 优先级链（CLI flag > env > config.yaml > 默认值）读取对应 pet.md 人格，
**禁止 pet 配置绕过 ConfigSpec 另起解析**」；场景「pet 配置经 ConfigSpec 声明」要求
「CLI flag / env / yaml **三面一一对应**」。

⇒ 属「规格要求 X、实现没有」型（同 E11②/E12/E15）：**改代码向规格靠拢**，规格不动。

## What Changes

**① `ConfigManager.config_value(key)`（配置层，新公开方法）**
装配前的**只读单键**解析通路：CLI > env > config.yaml > 缺省，内部即
`resolve(key, cli=self._cli, env=self._environ, yaml=<yaml 层>, specs=self._specs)` ——
与 `load()` 共用 ConfigSpec 单一真源。与 `load()` 的分工：

- **不校验 / 不阻断 / 不缓存**：只读单键，不构造 `AppConfig`；
- **config.yaml 缺失按「无 yaml 层」处理**（不抛 `ConfigurationError`）—— 前置判定发生在整份配置
  校验之前，且配置文件本就可能不存在；此性质被 `tests/test_entry.py::test_pet_disabled_by_default`
  与 `::test_pet_missing_config_file_is_tolerated` 钉住（**若不如此，CI 无 config.yaml 时 `pet gather`
  会由退出 0 变退出 1**）。

配套私有 helper `_flatten_by_specs(raw, specs)`：`resolve` 的 yaml 层以 **`ConfigSpec.key`** 为键，
而 yaml 文件按 **`map_to`** 点分路径嵌套，两者对 `im.corp-id`（map_to `im.corp_id`）等键**不同名**，
故经单一真源逐键取路径回填，不按点分拼键。

**② `entry._pet`（CLI 层）**：门控与 `persons_dir` 改用 `mgr.config_value(...)`；
`ConfigManager` 提前构造一次并**复用**给 `build_runtime`（同一实例，避免重复读盘）。
`_as_bool` 归一化保留（`config_value` 返回各层原文，env 为字符串）。

## 规格 delta

**规格中性**：规格早已要求含 yaml 层的三层链，本次是**实现追平规格**，无 spec 改动
（`.openspec.yaml` 声明 `skip_specs: true`，先例 change `0066`）。

架构决策记入 **ADR-0067**（只读单键 / 缺文件容错 / yaml 层经 `map_to`→`key` 回填）。

## 不在本变更内（记账本后续行）

- `entry.py:372` `config get` 同型缺陷（`resolve(args.key, cli=..., env=...)` 亦漏 `yaml=`）：
  登记为账本新行 **E22**，本变更不改（既有 `test_config_get_default` 断言的是缺省值，
  而开发机存在本地 `config.yaml`，贸然改动会改变该命令在开发机的输出语义 —— 单独裁决）。
- `cli_ops.ParamMapper.resolve` 与 `config get` 的 yaml 层提供方：随 E22 一并裁决。
