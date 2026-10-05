# design — `config get` 接入配置链 yaml 层（change 0078 / 账本 E22）

## 一手事实

```python
def _config(args):
    if args.config_cmd == "get":
        value = resolve(args.key, cli=_cli_overrides(args), env=os.environ)   # 无 yaml=
```

- `resolve(key, cli=, env=, yaml=..., specs=...)` 的 `yaml=` **缺省为空映射** ⇒ 漏传即**静默少一层**。
- `_default_yaml_path()` = cwd `config.yaml` → `~/.core-agent/config.yaml`；
  故「开发机 grep 到本地 config.yaml」正是病灶可见的环境。

红证（新增用例实现前）：

```
assert '(未配置)' == 'test-model'   # config get llm.model，config.yaml 写了 model: test-model
```

## 决策

### D1 `config get` 改用 `ConfigManager.config_value`
与 `entry._pet` 门控**同一通路**（ADR-0067）—— CLI > env > config.yaml > 缺省，
内部即 `resolve(key, cli=self._cli, env=self._environ, yaml=<yaml 层>, specs=self._specs)`。
**不另起解析**、与 `load()` 共用 ConfigSpec 单一真源。

- 语义收益：单键读取与整体装配（`load()`）**判据一致**（E21 的同类收益）。
- 缺文件容错（`config.yaml` 不存在按「无 yaml 层」处理）沿用 —— `config get` 在无配置文件机器上
  行为不变（仍打缺省），故 CI 不炸。

**已否决**：在 `_config` 内自读 yaml（第二条解析真源，违反规格「禁止另起解析」）。

### D2 构造前移
`mgr = ConfigManager(...)` 从 `get` 之后**提到函数开头**（`yaml_path=args.config`），
`get` / `show` / `set` 共用同一实例 —— 三行改动，无分支重复。

### D3 `resolve` 导入删除
`entry.py:390` 是 `resolve(` 的**唯一**调用点（已 grep 核实），迁走后导入成为孤儿 ⇒ 删（本变更造成）。

### D4 `test_config_get_default` 改 hermetic
原用例 `main(["config", "get", "permission.mode"])` 走**默认发现链** ⇒ 结果取决于开发机是否存在
cwd `config.yaml`。改用 `--config <不存在>` 走「无 yaml 层」路径 ⇒ 断言与机器无关。
（这不是「为了测试而改语义」：缺文件容错本就是被断言的契约行为。）

### D5 无 spec delta
规格「配置源与分层」已明文优先级链；本变更使**实现**向之靠拢，规格不动（同 change `0070` 判 `skip_specs`）。

## 兼容性代价

- 破坏面：`config get` 的输出（更准）；`src/` 仅 `entry.py` 一处。
- `config show/validate/set`、`ConfigManager`、语法层 `resolve`、组合根**均不变**。

## 转出

无。
