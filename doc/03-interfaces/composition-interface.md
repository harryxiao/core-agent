# 接口设计：组合与分发接口（Composition Interface）

> 层：L5 ｜ 对应规格 `composition/spec.md` ｜ 模块 `02-modules/composition.md`

---

## 1. 组合解析插件接口

```python
class ProfileResolver(Plugin):
    plugin_id = "composition.resolver"
    def resolve(self, profile: str) -> ResolvedSet:
        """按 profile 名解析出最终插件集（bundle 层叠 → patch.yml 覆盖）。"""
    def revert(self, resolved: ResolvedSet) -> ResolvedSet:
        """移除 patch 覆盖，回退至覆盖前分层结果（幂等，返回新结果，不改实参）。"""

class BundlePackager(Plugin):
    plugin_id = "composition.packager"
    def pack(self, plugins: list[PluginRef]) -> Bundle:
        """把一组插件打包为跨部署可复用的 bundle。"""
    def unpack(self, bundle: Bundle) -> list[PluginRef]:
        """解包 bundle，校验版本 / 哈希后返回插件引用。"""
```

---

## 2. 核心数据结构

```python
@dataclass
class Profile:
    name: str                 # 命名组合，如 web / headless / sdk-minimal
    bundles: list[str]        # 引用的 bundle 名（层叠顺序即列表顺序）
    patch: PatchSpec          # 用户覆盖，属 profile 内部

@dataclass
class Bundle:
    name: str
    version: str
    hash: str                 # 内容哈希，保证跨部署一致
    plugin_refs: list[PluginRef]
    deps: list[str]           # 依赖的 bundle 名（用于循环依赖检测）

@dataclass
class PatchSpec:
    overrides: dict           # plugin_id -> 覆盖配置

@dataclass
class ResolvedSet:
    profile: str
    plugins: list[PluginRef]  # 层叠 + 覆盖后的最终插件集
    layered: list[PluginRef]  # 覆盖前（bundle 层叠后）分层结果 = revert 的恢复目标（change 0136）
    overrides: dict           # 生效的覆盖项（可回退）
```

---

## 3. 编排器（Composition Engine）

```python
class CompositionEngine(Plugin):
    plugin_id = "composition.engine"

    def resolve(self, profile: str) -> ResolvedSet:
        p = self.load_profile(profile)
        bundles = [self.packager.unpack(b) for b in p.bundles]
        merged = self.layer(bundles)          # bundle 层叠：后层覆盖前层
        final = self.apply_patch(merged, p.patch)   # patch.yml 覆盖
        return ResolvedSet(profile=profile, plugins=final, layered=merged, overrides=p.patch.overrides)

    def revert(self, resolved: ResolvedSet) -> ResolvedSet:
        """移除 patch 覆盖 ⇒ 覆盖前分层结果（门面透出 resolver.revert）。"""
```

---

## 4. 分发接口

```python
class BundleDistributor:
    def publish(self, bundle: Bundle, registry: Registry) -> str:
        """发布 bundle 到插件仓库，返回可寻址引用。"""
    def fetch(self, name: str, version: str = "latest") -> Bundle:
        """按名/版本拉取 bundle，校验哈希。"""
```

---

## 5. 约束

- 组合层**无业务逻辑、永不进化**，只消费插件引用，不改造插件实现。
- 解析顺序确定：bundle 层叠 → patch.yml 覆盖，同名项由 patch.yml 覆盖。
- profile 引用不存在的插件 → 解析失败并报缺失插件名，不静默跳过。
- bundle 哈希 / 版本不符 → 拒绝引入，避免脏分发。
- 卸载 patch.yml → 回退到覆盖前状态，可逆：`resolve` 的结果携带覆盖前分层结果（`layered`），
  `revert(resolved)` 返回**新**结果（`plugins = layered`、`overrides` 清空）且**幂等**，不改实参（change `0136`）。
- patch 覆盖值须为整数 generation；**布尔**（YAML `true` / `false`）按 `PATCH_CONFLICT` 拒绝
  —— `bool` 虽为 `int` 子类，SHALL NOT 静默落为 1 / 0（change `0136` / 账本 E70）。

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `BUNDLE_INVALID` | bundle 校验和 / 哈希 / 版本不符或格式损坏 |
| `CIRCULAR_DEPENDENCY` | bundle 依赖构成环 |
| `PATCH_CONFLICT` | patch.yml 覆盖冲突无法唯一判定 |
| `PLUGIN_MISSING` | profile / patch 引用了不存在的插件 |

## 7. 关联

- 模块：`02-modules/composition.md`
- 插件来源：`plugin-registry-interface.md`
- 进化产物入口：`evolution-interface.md`（结晶产物经此进入插件仓库，组合层消费）
- 规格：`openspec/specs/composition/spec.md`
