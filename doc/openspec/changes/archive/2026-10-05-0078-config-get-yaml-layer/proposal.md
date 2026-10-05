# 0078 `config get` 接入配置链 yaml 层（账本 E22）

## Why

账本 **E22**：`entry._config` 的 `get` 分支把优先级链**当成两层**用 ——

```python
value = resolve(args.key, cli=_cli_overrides(args), env=os.environ)   # 漏 yaml=
```

`resolve` 的 `yaml=` 缺省为空映射（ADR-0067 背景）⇒ `config get` **永远看不到 config.yaml**：
配置里写了非缺省值，命令仍打印内置缺省（或 `(未配置)`）。**同一进程**里其余读配置的路径
（`config show` / 装配 `build_runtime`）都走 `load()`（含 yaml 层）⇒ 单键读取与整体装配**判据不一致**。

与 **E21 同型**（同一处 `resolve` 漏参），E21 已修 `entry._pet` 门控（change `0070`／ADR-0067），
`config get` 因「改它变更该命令输出语义」单独转出为本项，用户裁决**同口径修复**。

规格 `doc/openspec/specs/configuration/spec.md`「配置源与分层」明文：
「优先级链为 **CLI flag > env > config.yaml > 默认值**」⇒ 属「**规格要求 X、实现没有**」型
（同 E11②/E12/E15/E21）：**改代码向规格靠拢，规格不动**（`skip_specs`，同 change `0070`）。

## What Changes

- `src/core/entry.py`：
  - `_config` 先构造 `ConfigManager(yaml_path=args.config, cli=_cli_overrides(args))`，
    `get` 分支改用 **`mgr.config_value(args.key)`** —— 与 `pet` 门控**同一通路**（ADR-0067：
    只读单键、缺文件容错、键名经单一真源回填）。
  - 因此变得未使用的 `resolve` 导入**删除**（`entry.py` 内已无第二调用方）。
- 测试 `tests/test_entry.py`：
  - `test_config_get_default` 改 **hermetic**：显式 `--config <不存在>`，不再依赖
    「开发机恰好没有本地 config.yaml」（`_default_yaml_path()` 优先 cwd `config.yaml`）。
  - 新增：`config get` **读到 yaml 层**；**CLI flag 压过 yaml**（优先级链）。

## Non-goals

- **不**改 `config show` / `validate` / `set`（本就走 `load()`，含 yaml 层）。
- **不**改语法层 `resolve` 的 `yaml=` 缺省（仍为空映射）：语法层不该有 I/O 副作用，
  且会隐式改变 `ParamMapper` 等既有调用方语义（ADR-0067 已否决此项）。
- **不**加 spec delta：规格既有条款（「配置源与分层」优先级链）已覆盖，同 change `0070` 判 `skip_specs`。

## 风险

- **对外可观测**：`config get` 的输出会**变**（此前漏 yaml 层显示的缺省值，改为 yaml 真值）
  —— 这正是修复目标；`user-guide.md` 的示例（`permission.mode` → `interactive`）在无 yaml 时不变。
- **既有用例**：仅 `test_config_get_default` 触及该命令，已改为 hermetic（显式无 yaml），
  不因开发机/CI 环境差异漂移。
