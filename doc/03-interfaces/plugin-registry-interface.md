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

---

## 4. EffectTracker 接口

```python
class EffectTracker:
    def record(self, effect: Effect) -> EffectId:
        """记录一个可逆效应及其撤销闭包。"""

    def rollback(self, trace_id: str | None = None) -> RollbackReport:
        """回滚：按 trace_id 回滚单轮；None 则全局回滚。"""

    def replay(self, effect_id: EffectId) -> None:
        """重放（复现）某效应，用于可观测性。"""

    def audit(self, trace_id: str) -> list[Effect]:
        """审计：某轮的所有效应记录。"""
```

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
| `GENERATION_CONFLICT` | 世代冲突 |
| `UNDO_FAILED` | 撤销失败（进入 QUARANTINE） |
| `NOT_ACTIVE` | 插件未激活 |

---

## 8. 关联

- 模块：`02-modules/plugin-registry.md`
- 规格：`openspec/specs/plugin-registry/spec.md`
