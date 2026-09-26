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
