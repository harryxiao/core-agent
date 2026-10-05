# design — 出站白名单可配

## 决策

### ① 取值形态：逗号分隔标量（三面统一）

`_parse_yaml_subset` 明文「不含列表 / 锚点 / 多行块」（`manager.py:650`），`_dump_yaml` 与之对称
（仅标量与映射）。若用原生 yaml 列表，须改解析器 + 写回 + 三面归一，**改动面远超收益**。
故取值统一为**标量**：`host_allowlist: a.example.com,b.example.com`（三面同形），
由 `_split_hosts()` 归一到裸主机名列表。

**全角逗号一并接受**：中文输入法下的常见误输，静默失配的代价与「配了却连不上」同。

**已否决**：yaml 原生列表（须改解析器 / 写回，且三面形态不一）；
JSON 数组字符串（与 `_parse_scalar` 不匹配，等于把解析器搬进访问器）。

### ② 非法条目校验期拒绝（不静默忽略）

`check_outbound(host)` 的实参是 `urlparse(url).hostname`（`transport.py:243`）—— **不含 scheme、
端口、路径**。因此 `https://a.example.com` / `a.example.com:443` / `a.example.com/v1` 这些
**看起来对**的条目**永不匹配**：配了却连不上，且没有任何提示。

与 E15（change `0068`）同口径：**校验期拒绝并阻断启动，不静默兜底**。
校验在 `validate_schema` 内（`_sandbox_errors(perm)`），错误信息指明键名与合法形态。

**已否决**：容错归一（自动剥 scheme / 端口 / 路径）—— 会掩盖输入错误，
且「用户到底配的是哪个主机」在带路径时不可判定（`a.example.com/v1` 剥路径后语义可疑）。

### ③ 缺省空白名单 = fail-closed 不变

本变更只把「恒空」变成「可声明」：缺省仍为 `[]` ⇒ 出站全拒。
新增测试 `test_unconfigured_production_policy_denies_all_outbound` 明确锁住该姿态，
防「配置化顺手把默认打开」的回归。

### ④ 访问器形态：寄居 `extra` + 单一真源

`ConfigSpec` 声明 `map_to = permission.sandbox.host_allowlist` ⇒ `_apply_env` / `_apply_cli`
自动把三面覆盖写进嵌套 `extra`（与 `constraints.*` 同路），访问器直接读嵌套路径、
只做拆分归一（不做二次兜底）。

**不做**：让 `sandbox_host_allowlist()` 走 `config_value()` 的单键解析 —— `config_value` 返回
各层**原文**（字符串），适合「装配前单键前置判定」（E21），而此处需要归一后的列表，
且须与 `permission.mode` / `constraints.*` 的「寄居 extra」先例保持一种口径。

### ⑤ 与沙箱管理器共用策略实例

`runtime.py` 原本就是 `SandboxPolicy()` 单实例分发给 `SandboxManager` 与 `MCPClient`
（change `0054`）—— 本变更只把构造参数接上，**不加新实例、不改分发**。

## 影响面

| 面 | 处置 |
|---|---|
| yaml 解析 / 写回 | **不动**（标量形态天然落进既有子集） |
| 分层红线（`test_architecture.py`） | 不动分层：`configuration` 与 `permission` 互不 import，取值经 `extra` dict 传递（与 `constraints` 同路） |
| 密钥安全 | 白名单**非密钥**（主机名），与「只引用不读取」约束无关；不进日志的约束不受影响 |
| 既有用例 | `test_phase15.py:183` / `test_mcp_stdio.py:116` 直接构造 `SandboxPolicy`，不经配置 ⇒ 不受影响 |
