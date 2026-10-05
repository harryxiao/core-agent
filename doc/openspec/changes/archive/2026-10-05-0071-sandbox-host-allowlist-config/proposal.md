# 出站白名单可配（sandbox-host-allowlist-config）

## Why

账本 **B5**（`coding-plan/phase-19.md` §1）。ADR-0057 §⑤ 早已登记「白名单配置化记后续」。

`SandboxPolicy(host_allowlist=...)` 的构造面**可注入**（`doc/03-interfaces/permission-interface.md` §4），
但**唯一生产构造点** `src/core/runtime.py:363` 此前写死 `SandboxPolicy()` ⇒ 生产白名单**恒为空**：

- 规格「沙箱执行颗粒度」场景「网络出站白名单」的**放行半边不可达** —— 只有「拦截」能被观察到；
- MCP 远端 http/streamable-http 传输（`transport.py:243` 的 `check_outbound`）在生产**永远打不开**，
  运维想让某个 MCP 服务出站**只能改代码**；
- `configuration/` 无 `permission.sandbox` 键 ⇒ `config show/set`、env、CLI flag 三条通道都够不着。

与 E15（熔断阈值/冷却，change `0068` 关闭）同型：**可注入但唯一调用点不传参 ⇒ 生产不可达**。

## What Changes

- `src/core/configuration/manager.py`
  - `_CONFIG_SPECS` 增一项：`permission.sandbox.host_allowlist`（缺省 `""`，
    exposure `ADVANCED`）—— 经 `ConfigSpec` 单一真源，CLI flag
    `--permission.sandbox.host-allowlist`、env `CORE_SANDBOX_HOST_ALLOWLIST`、yaml
    `permission.sandbox.host_allowlist`、「未知配置段」白名单**四者自动获得**。
  - 新增访问器 `sandbox_host_allowlist() -> list[str]`（缺省 `[]`），沿用
    `circuit_breaker()` / `permission_mode()` 的「寄居 `extra` + 访问器」先例。
  - 新增 `_split_hosts()`（逗号分隔 → 去空白 / 去空项 / 保序去重，兼容全角逗号）
    与 `_sandbox_errors()`（校验期拒绝非裸主机名条目，含非字符串取值），
    在 `validate_schema` 中被调用。
- `src/core/runtime.py`：`SandboxPolicy(host_allowlist=config.sandbox_host_allowlist())`，
  客户端与沙箱管理器**共用同一策略实例**（口径不变）。
- `tests/test_permission_sandbox_config.py`（新）：ConfigSpec 三面齐备 / 缺省全拒 /
  yaml CSV 归一（去重、全角逗号）/ env 覆盖 yaml / CLI 覆盖 env / 非法条目阻断启动 /
  非字符串取值阻断 / 组合根注入（同一实例）/ **端到端**（生产 http 守卫：白名单内越过守卫、
  白名单外 `PERMISSION_DENIED`）/ **缺省全拒回归**。
- 文档：`doc/03-interfaces/permission-interface.md`（§4 补 `SandboxPolicy` 与配置路径）、
  `doc/03-interfaces/configuration-interface.md`（段与访问器）、`doc/02-modules/permission.md`、
  `doc/01-architecture/adr.md`（ADR-0068 + 映射表行）、`doc/04-testing/test-cases.md`（用例号）。

## 规格 delta

`permission` spec「沙箱执行颗粒度」**MODIFIED**：正文增「出站主机白名单 SHALL 可经配置声明
（约束键 / 缺省空 fail-closed / ConfigSpec 单一真源 / 客户端与沙箱管理器共用策略 / 裸主机名约束）」；
新增三个场景（出站白名单经配置声明 / 未配置全拒 / 非法条目校验期拒绝）。

`configuration` spec **不改**：与 change `0068` 同理，键是 `ConfigSpec` 的**新实例**，
「配置项以 ConfigSpec 为单一真源」「取值受所属能力规格约束的配置项 SHALL 在校验期拒绝非法取值」
两条既有 Requirement 已完整覆盖。

## 决策要点（详见 design.md）

1. **取值形态 = 逗号分隔标量**（用户裁定）：`_parse_yaml_subset` 明文「不含列表」，
   三面（CLI / env / yaml）统一为标量最省且不动 yaml 解析 / 写回。
2. **非法条目校验期拒绝**（不静默忽略）：`check_outbound` 的实参是 `urlparse().hostname`，
   带 scheme/端口/路径的条目**永不匹配** —— 静默的后果是「配了却连不上」，与 E15 同口径。
3. **缺省空白名单 = fail-closed 不变**：本变更只把「恒空」变成「可声明」，默认安全姿态不动。

## 明确不在本变更内（仍记账）

- 文件系统白名单 `SandboxPolicy.fs_allowlist` 的配置化（无生产调用点需要，YAGNI）；
- 通配符 / 后缀匹配（规格只要求白名单，未要求模式匹配；裸主机名精确匹配是当前 `check_outbound` 契约）；
- `permission.sandbox` 段下其他键（无需求）。
