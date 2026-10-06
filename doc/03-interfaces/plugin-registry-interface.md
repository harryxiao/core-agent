# 接口设计：插件契约（Plugin Registry Interface）

> 层：L0 ｜ 对应规格 `plugin-registry/spec.md` ｜ 模块 `02-modules/plugin-registry.md`

---

## 1. 插件契约（四要素）

所有插件（含 loop、记忆、进化、工具、模型适配器）必须满足以下契约：

```python
class Plugin(Protocol):
    plugin_id: str            # 全局唯一，命名空间点分：tools.code_run / memory.store / loop.default
    generation: int           # 世代号，过验证门后 +1
    schema: dict              # JSON Schema：描述该插件可调用的动作/参数
    coeffects: list[str]      # 执行前需注入的环境约束（权限/宪章/配置）

    def load(self) -> None: ...
    def unload(self) -> None: ...
    def check(self) -> bool: ...   # 自检：声明与实现是否一致
```

---

## 2. Coeffect 声明规范

| coeffect 键 | 含义 | 缺失时 |
|---|---|---|
| `filesystem:read` | 读文件权限 | 拒绝执行 |
| `filesystem:write` | 写文件权限 | 拒绝执行 |
| `network:outbound` | 出网权限 | 拒绝执行 |
| `constitution:v1` | 宪章约束注入 | 拒绝执行 |
| `model:adapter` | 模型适配器 | 拒绝执行 |
| `memory:store` | 记忆存储后端 | 拒绝执行 |
| `tools:provider` | 工具聚合器 | 拒绝执行 |
| `secret:<name>` | 密钥引用（只注入句柄） | 拒绝执行 |

---

## 3. 生命周期（Lifecycle）

```
register ─► load ─► active ─► suspend ─► unload ─► archive
                ▲                    │
                └──── resume ◄───────┘
```

| 状态 | 说明 |
|---|---|
| registered | 已注册（含 schema/coeffect 声明），未实例化 |
| loaded | 已实例化，可被查找 |
| active | 当前 profile 激活，参与运行 |
| suspended | 暂停（如进化候选评审中） |
| unloaded | 已卸载，undo 栈已回滚 |
| archived | 归档（保留元数据，不再加载） |
| faulted | 运行时异常，已标记故障并隔离（不拖垮宿主） |

---

## 4. EffectTracker 接口

```python
class EffectTracker:
    def record(self, effect: Effect) -> EffectId:
        """记录一个可逆效应及其撤销闭包。"""

    def rollback(self, trace_id: str | None = None) -> RollbackReport:
        """回滚：按 trace_id 逆序回滚单轮；None 则全局回滚。撤销成功即**出账**。"""

    def clear(self, trace_id: str | None = None) -> None:
        """显式清账：移除账目（trace 级 / 全局），**不**触发任何 undo。"""

    def replay(self, effect_id: EffectId) -> None:
        """重放（复现）某效应，用于可观测性。"""

    def audit(self, trace_id: str) -> list[Effect]:
        """审计：某轮**尚未了结**（未出账）的效应记录；回滚成功后为空。"""
```

**清账与幂等（change `0128` / ADR-0121 / E67）**：回滚 SHALL 清账 —— 撤销**成功**的效应与
**不可逆**效应随即出账（`EffectId` 离账、trace 映射同步清理、空键删除），故同一 trace **重复回滚
SHALL NOT 二次撤销**、账目 SHALL NOT 无界增长（`EffectTracker` 在进程中为长驻单例）。撤销**失败**者
**留账隔离**（`audit` 仍可见，并由 `RollbackReport.undo_failed` 报告），SHALL NOT 静默丢弃；单条失败
不中断其余撤销。已出账的 `EffectId` 再 `replay` 抛 `KeyError`。

`Effect` 结构：

```python
@dataclass
class Effect:
    op: str                    # "file_write" / "proc_start" / ...
    target: str                # 作用对象
    undo: Callable[[], None]   # 撤销闭包
    reversible: bool
    coeffect: list[str]
    trace_id: str
    ts: float
```

---

## 5. CoeffectResolver 接口

```python
class CoeffectResolver:
    def resolve(self, required: list[str]) -> ResolvedContext:
        """解析注入 coeffect；缺失则抛 CoeffectMissing(required)。"""

    def register(self, key: str, value: Any, *, secret: bool = False) -> None:
        """注册 coeffect 来源；secret=True 时只注入句柄，不进日志。"""
```

---

## 6. 组合接口（Bundle / Profile / Patch）

```python
class Bundle:    # 能力集
    plugins: list[str]                    # plugin_id 列表
    def compose(self) -> Composition: ...

class Profile:   # 配置集
    active: dict[str, int]                # plugin_id -> generation
    coeffect_sources: dict[str, str]      # coeffect -> 来源
    def activate(self, registry) -> None: ...

class Patch:     # 进化补丁
    target: str                           # 目标插件
    delta: dict                           # 变更内容
    gate_report: dict                     # 验证门报告
    def apply(self) -> None: ...
    def undo(self) -> None: ...
```

---

## 7. 错误码

| 错误码 | 含义 |
|---|---|
| `COEFFECT_MISSING` | 必需 coeffect 缺失 |
| `INVALID_SCHEMA` | 插件 schema 非法 |
| `INVALID_MANIFEST` | 插件 manifest 非法（版本/依赖/入口） |
| `GENERATION_CONFLICT` | 世代冲突 |
| `NOT_ACTIVE` | 插件未激活 |
| `UNDO_FAILED` | 撤销失败（进入 QUARANTINE） |
| `CIRCULAR_DEPENDENCY` | 插件依赖存在循环 |
| `REGISTER_TIMEOUT` | 插件注册超时 |
| `SOURCE_NOT_FOUND` | 插件来源不可达（安装 discover 阶段） |
| `SIGNATURE_INVALID` | 插件签名校验失败（安装 verify 阶段） |
| `INSTALL_FAILED` | 插件安装失败（安装 install 阶段） |
| `UNINSTALL_NOT_FOUND` | 卸载的插件不存在（未安装） |

---

## 8. 插件安装抽象（Installable）

三方插件（skill / mcp / cli）的安装生命周期收敛到 registry 层，与运行时插件生命周期（§3）分离：

```python
class PluginSource(str, Enum):
    LOCAL_PATH = "local-path"            # 本地路径
    GIT_REPO = "git-repo"                # git 仓库
    MARKET_REGISTRY = "market-registry"  # 市场注册表
    MCP_ENDPOINT = "mcp-endpoint"        # MCP 端点

class PluginKind(str, Enum):
    SKILL = "skill"
    MCP = "mcp"
    CLI = "cli"

@dataclass(frozen=True)
class InstallableAsset:
    kind: PluginKind
    source: PluginSource
    manifest: dict
    lifecycle: str = "discover"

class PluginInstaller:
    def discover(self, source, location, kind) -> InstallableAsset: ...  # 来源不可达 → SOURCE_NOT_FOUND
    def verify(self, asset, signature) -> None: ...                      # 签名非法 → SIGNATURE_INVALID
    def install(self, asset) -> None: ...                                # 失败 → INSTALL_FAILED
    def register(self, asset, plugin) -> None: ...                       # → REGISTERED（有 store 则同批落盘）
    def activate(self, plugin_id) -> None: ...                           # load + activate → ACTIVE
    def deactivate(self, plugin_id) -> None: ...                         # → LOADED
    def installed(self) -> list[dict[str, str]]: ...                     # 已安装清单（plugin_id/kind/source）
    def uninstall(self, plugin_id) -> None: ...                          # unload + 释放 + 清账 → 移除
```

- `SourceResolver` / `SignatureVerifier` / `Installer` / `Uninstaller` 均可注入，缺省提供「未接入 / 无签名要求 /
  无副作用」实现；`store`（§8.2）亦为可选注入。
- 签名校验与多源路由语义上提到此统一层，执行实现按 kind 适配（不合并 skillhub/mcp/cli 的执行实现）。

### 8.1 四源发现契约（执行层 `core/plugins/sources.py`，change `0093`）

`plugin_registry` 侧保持「未接入」空壳（底座零外部依赖）；四源的**真实发现**由执行层承担，
`InstallDispatcher.resolve` 分派：

| 来源 | `location` 语义 | 发现方式 | 外部边（可注入 / 缺省） |
|---|---|---|---|
| `local-path` | manifest 文件路径 | 读该文件 | — |
| `git-repo` | 仓库地址（URL 或本地路径） | 克隆到**临时工作区** → 读仓库**根目录** `core-plugin.json` → 清理工作区 | `Cloner = (url, dest) -> None`／缺省 `core.git` stdlib subprocess 后端 |
| `market-registry` | manifest 文档地址 | 取该文档（JSON） | `Fetcher = (url) -> dict`／缺省 stdlib `urllib.request` |
| `mcp-endpoint` | MCP 端点串 | 由端点串**合成** `{"name", "url"}`（解析期**零网络**） | — |

- **`MANIFEST_FILENAME = "core-plugin.json"`** 是 git-repo 来源的对外契约（仓库根目录）。
- **凭据**：市场鉴权经注入的 `fetcher` 携带，**不写进 URL**；任何回显（异常文本）经 `_safe` **剥掉 userinfo 与 query**。
- **错误归一**：任一来源不可达 / manifest 非法 ⇒ `SOURCE_NOT_FOUND`（注入边抛出的 `DomainError` 原样透传，不二次包装）。
- **可达性时机**：`mcp-endpoint` 的端点可达性在 **install 期**由 `MCPClient.add` 判定（与 `mcp add`「先连通验证再落盘」同口径），解析期不探测。
- **CLI**：`plugin install <asset> --kind K --source S`（`S ∈` 四源，缺省 `local-path`）；`skill install --source` 亦可达市场源
  （见 skillhub 接口文档）。

### 8.2 安装账本与 `InstallStore`（执行层 `core/plugins/installs.py`，change `0109`）

`PluginInstaller` 的**安装账本不落盘**时，`plugin list` / `plugin uninstall` 跨进程恒为空 / `UNINSTALL_NOT_FOUND`
（CLI 是一次性进程）。持久化钩子以 **Protocol** 声明在 `installable.py`（`plugin_registry` 是 L0 基底、
**不得** import 上层的 `core.plugins` 实现），由组合根注入执行层实现：

```python
class InstallStore(Protocol):
    def records(self) -> dict[str, InstallableAsset]: ...        # 键为 plugin_id；构造期水合的唯一来源
    def put(self, plugin_id, asset) -> None: ...                 # register 后调用；同 id 覆盖（重装即升级）
    def remove(self, plugin_id) -> bool: ...                     # uninstall 时调用；返回是否确有该条目
```

- **注入点**：`PluginInstaller(..., store=...)`。构造期 `records()` → `_hydrate`（进程内账本 `_assets` +
  `PluginRegistry.register(_HydratedPlugin(...))`，**水合必须登记**，否则走生命周期时 `state` / `unload` 抛
  「插件未注册」）；`register` **先落盘再入内存**（落盘失败则整体失败、不留半份登记）；`uninstall` **物化回退成功才清账**。
- **默认实现 `PluginInstallStore`**（按 `kind` 路由的**单一视图**）：
  `kind=mcp` → `MCPEndpointRegistry`（`mcp-endpoints.json`，委派，不两处记账）；`kind=skill|cli` → 本账本
  `$CORE_STATE_DIR/plugin-installs.json`。`records()` 合并两处的**并集**，`remove()` 两处都覆盖。
- **账本形状**：单文件 JSON `{"version": 1, "installs": {<plugin_id>: {plugin_id, kind, source, manifest}}}`，
  **原子写**（tmp + `os.replace`）；文件缺失 = 正常态（空且不告警）；**损坏 / 条目残缺** → `warnings.warn`
  **降级跳过**（不静默丢弃、不阻断启动）。与 `mcp-endpoints.json`（ADR-0071）逐条同口径。
- **装配期重建**：`build_runtime` 在既有 MCP 端点循环**之后**读本账本逐条 `dispatcher.install`（skill → 技能库
  upsert；cli → 工具面注册），**单条失败只告警跳过**；mcp 归端点循环。使 `plugin list` 的「已安装」与运行时
  工具面 / 技能库**一致**（不谎报）。
- **已知局限**：`installed()` 读**构造期水合的内存副本** ⇒ 同进程运行中别处新装的不可见（跨进程可见性的口径是
  「新进程读盘」）；mcp 类资产的账本身份即**端点名**（`plugin_id` 与 manifest `name` 不一时以端点名为准）。
- 决策与反例（为何按 kind 委派 / 为何写点收在 `PluginInstaller`）见 **ADR-0102**；行为规格见
  `openspec/specs/plugin-registry/spec.md`「插件安装持久化」。

---

## 9. 关联

- 模块：`02-modules/plugin-registry.md`
- 规格：`openspec/specs/plugin-registry/spec.md`
