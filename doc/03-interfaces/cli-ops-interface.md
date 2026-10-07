# 接口设计：CLI 运维命令面（CLI Ops Interface）

> 模块：`01-architecture/architecture-overview.md`（横切 cli-ops） ｜ 规格：`openspec/specs/cli-ops/spec.md`

---

## 1. 实体模型

```python
class CommandGroup(StrEnum):
    """命令分组（六组）。"""
    LIFECYCLE = "lifecycle"     # start / stop / restart / kill
    STATUS = "status"           # status / doctor / logs / version / help
    ASSET = "asset"             # install / uninstall / list / info
    CONNECTION = "connection"   # mcp add / mcp remove / mcp list
    SECURITY = "security"       # auth / permission-mode
    GATEWAY = "gateway"         # gateway
```

> 配置项单一真源 `ConfigSpec`（`key` / `cli_flag` / `env_var` / `default` / `map_to` / `exposure`）的权威定义见 `configuration-interface.md`；本接口的 ParamMapper 消费它，不重复定义。

---

## 2. CLICommandDispatcher 接口

```python
class CLICommandDispatcher:
    def dispatch(self, argv: list[str]) -> int:
        """解析命令行，路由到六组命令之一，返回进程退出码。"""

    def lifecycle(self, action: str) -> int:
        """start / stop / restart / kill 进程守护。"""

    def status(self, sub: str) -> str:
        """status / doctor / logs / version / help 状态查询，不改变运行态。"""

    def asset(self, action: str, source: str | None = None) -> str:
        """install / uninstall / list / info，复用 plugin-registry 插件来源与安装生命周期。"""

    def connection(self, action: str, name: str | None = None) -> str:
        """mcp add / mcp remove / mcp list，复用 mcp 安装/移除生命周期。"""

    def security(self, action: str) -> str:
        """auth / permission-mode。"""

    def gateway(self) -> str:
        """启停本地服务网关。"""
```

---

## 3. ParamMapper 接口

```python
class ParamMapper:
    def resolve(self, key: str, *, cli: dict | None, env: dict, yaml: dict) -> object:
        """按优先级链 CLI flag > env > config.yaml > 默认值 解析配置项。"""

    def generate_cli(self) -> list[str]:
        """由 ConfigSpec 生成 CLI 参数面（含 core/advanced/hidden 分级）。"""

    def generate_env(self) -> dict[str, str]:
        """由 ConfigSpec 生成 env 变量面。"""

    def generate_yaml_schema(self) -> dict:
        """由 ConfigSpec 生成 yaml schema。"""
```

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| UNKNOWN_COMMAND | 未识别的 CLI 命令 |
| INVALID_MAP_TO | ConfigSpec 中 map_to 非法（目标不存在或冲突），阻断启动 |

---

## 5. 只读诊断面（change `0162` / ADR-0153）

`status` / `doctor` 两个动词**不再**经 `CLICommandDispatcher`（§2）分发，改由 `src/core/diagnostics/`
（**只读诊断源**）承载 —— `cli-ops` 规格「状态查询命令」Scenario 承诺的「返回运行状态 / 健康诊断」
自此**为真**（此前 `dispatcher.py` 对二者一律 `return "ok"`，是桩）。

```python
class CheckStatus(StrEnum):
    OK = "ok"; WARN = "warn"; FAIL = "fail"

@dataclass(frozen=True)
class Check:
    name: str; status: CheckStatus; detail: str = ""

@dataclass(frozen=True)
class Report:
    title: str; checks: tuple[Check, ...] = (); lines: tuple[str, ...] = ()
    @property
    def ok(self) -> bool: ...   # 无 `fail` 项即真（`warn` 不阻断）

@dataclass(frozen=True)
class Deps:   # 全部可选句柄，**由调用方装配**（包内不猜路径）
    config: ConfigManager | None; tools: ToolProvider | None; sessions: SessionsHandle | None
    notes: NoteStore | None; mcp: MCPEndpointRegistry | None; library: SkillLibrary | None
    market: MarketIndex | None; installer: PluginInstaller | None; state_dir: Path | None

def collect_doctor(deps: Deps) -> Report: ...   # 逐项：配置 / 密钥引用 / 状态目录 / 工具 / 笔记 / MCP / 资产 / 技能
def collect_status(deps: Deps) -> Report: ...   # 概览行：模型 / 循环预算 / 会话数 / 内置工具 / 资产 / MCP / 技能 / 笔记
def render(report: Report) -> list[str]: ...    # 标题 + `✓` / `!` / `✗` 逐项 + 自由行

def render_sessions / render_config / render_mcp / render_skills / render_notes(deps: Deps) -> Report: ...
```

| 面 | 命令 | 退出码 | 产出 |
|---|---|---|---|
| 自检诊断 | `core-agent doctor` | **有 `fail` 项 ⇒ 1**，否则 `0` | `collect_doctor` + `render` |
| 运行状态 | `core-agent status` | 恒 `0`（信息面，不是判据） | `collect_status` + `render` |

契约要点：

- **单一产出、多消费面**：`collect_*` 产 `Report`、`render` 产行；CLI 今天打印，TUI（change `0163`）
  复用同一份 —— SHALL NOT 各写一份检查逻辑。
- **密钥只出「引用名 + 布尔结论」**：`SHALL NOT` 打印任何解析结果；诊断项经 `ConfigManager.is_resolvable(ref)`
  （见 `configuration-interface.md` §2）取**布尔**，呈现用 `${VAR}` **引用名**。MCP 端点视图
  `SHALL NOT` 打印 `EndpointRecord.args`（可能是 `--token <value>` 形态），只出 name / transport / source。
- **零副作用**：全部诊断项**只读** —— 「状态目录可写」走**既有祖先目录**的 `os.access` 探测，**不建目录**。
- **不引组合根**：包内**不** `import core.runtime`（`test_runtime_is_sole_composition_root` 硬红线）、
  **不** `import core.ui`（后者反向引用诊断源）⇒ 句柄全经 `Deps` 注入，`_diag_deps` 在 `entry.py` 装配。
- **未注册动词**（`kill` / `logs` / `version` / `help` / `install` / `uninstall` / `list` / `info` / `auth` /
  `permission-mode` / `gateway`）仍**不在** argparse 子命令面 —— 台账 `coding-plan/known-risk.md` §1 **E100** 挂账。
