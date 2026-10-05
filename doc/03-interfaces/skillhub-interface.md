# 接口设计：技能市场（SkillHub Interface）

> 模块：`02-modules/skillhub.md` ｜ 规格：`openspec/specs/skillhub/spec.md`

---

## 1. 市场与技能定义

```python
@dataclass
class MarketSkill:
    skill_id: str               # 全局唯一，如 "skills.data_analysis.summarize"
    name: str
    description: str
    version: str                # 市场版本 v1/v2...
    signature: str              # 签名摘要（TrustVerifier 校验用）
    source: str                 # 来源，默认 "official"（预留第三方源）
    status: str                 # "uploaded" | "pending" | "published" | "rejected"
```

---

## 2. SkillHubClient 接口

```python
class SkillHubClient:
    def search(self, query: str, *, source: str = "official",
               top_k: int = 20) -> list[MarketSkill]:
        """按 query 搜索市场技能，返回元数据列表（不拉取完整技能体）。"""

    def download(self, skill_id: str, *, source: str = "official") -> Skill:
        """校验签名 → SkillLibrary.register(status="draft")；签名失败抛 SIGNATURE_INVALID。"""
```

下载的初始状态恒为 `draft`，**不自动启用**；需本地显式激活后才进入可用技能集。

**生产触达点**（`src/core/entry.py`）：`skill search <query> [--source S]` → `SkillHubClient.search`（输出版本化
元数据，不拉技能体）；`skill install <name> [--source S]` → `SkillHubClient.download`（先签名校验后注册 draft）。
`SkillHubError`（源不可达 / 源不存在 / 签名失败 / 市场未接）归一为 stderr + 退出码 1。

**技能库与组合根同源**：CLI 侧经 `entry._build_skill_library()` 使用 `SkillLibrary(path=$CORE_STATE_DIR/skills.json)`
（与 `runtime._skill_state_path` 同一约定）—— 否则下载只落在进程内一次性库，下个进程即消失（「已安装」成谎报），
`skill remove` 也永远删不掉运行时注册的技能。

**技能体拉取**：CLI 缺省 `fetcher` 为 `entry._market_fetcher` —— 从**本地市场制品库**
（`SkillLibrary(path=$CORE_STATE_DIR/skillhub-artifacts.json)`，即本地 `skill publish` 入库的技能体）拉取；
离线、零凭据。制品缺失或目录无该条目 ⇒ `download` 如实抛 `SIGNATURE_INVALID`，**不静默成功**。

**凭证半**：远端市场 fetcher（网络 + 市场凭据）仍未接；接入时替换 `fetcher` 即可，接口面不变。

---

## 3. MarketIndex 接口

```python
class MarketIndex:
    def __init__(self, sources: dict[str, MarketSource] | None = None, *,
                 health_probe: HealthProbe | None = None, path: Path | None = None) -> None: ...

    def list(self, *, source: str = "official") -> list[MarketSkill]:
        """列出指定源的技能目录元数据。"""

    def route(self, source: str) -> MarketSource:
        """按 source 路由到对应市场源；源不存在抛 SOURCE_NOT_FOUND。"""

    def health(self, source: str) -> SourceHealth:
        """源健康探测；不可达标记不健康并回退官方源（SOURCE_UNHEALTHY）。"""

    def put(self, source: str, skill: MarketSkill) -> None:
        """写入目录条目（**唯一写路径**：发布与审核共用）；源不存在抛 SOURCE_NOT_FOUND。"""

    def get(self, source: str, skill_id: str) -> MarketSkill | None:
        """按源取目录条目；源或技能不存在返回 None。"""

    def locate(self, skill_id: str) -> tuple[str, MarketSkill] | None:
        """**跨源**按 skill_id 定位条目（携带源名）；不存在返回 None。查找而非路由，不做健康探测。"""

@dataclass
class SourceHealth:
    source: str
    healthy: bool
    last_check: str             # ISO 时间戳
```

**目录落盘**（注入 `path`）：形状 `{"sources": {<name>: {"skills": {<skill_id>: <MarketSkill dict>}}}}`，
经 `core.persistence.write_state`（原子 tmp + `os.replace`）在 `put()` 时整体重写；装载时缺失 → 空态、
损坏 / 结构不符 → `warnings.warn` 降级为空目录（状态损坏不阻断启动）；装载后恒 `setdefault("official", …)`。
缺省 `path=None` ⇒ 纯内存目录（既有单测与组合根行为不变）。CLI 侧落盘于
`$CORE_STATE_DIR/skillhub-index.json` —— 目录是市场真源，发布 / 审核 / 搜索 / 安装跨进程可见。
---

## 4. SkillPublisher 接口

```python
class SkillPublisher:
    def __init__(self, *, index: MarketIndex | None = None, verifier: TrustVerifier | None = None,
                 version_manager: VersionManager | None = None,
                 artifacts: SkillLibrary | None = None) -> None: ...

    def publish(self, skill: Skill, *, source: str = "official") -> str:
        """上传技能 → status=pending；技能体（副本）入本地市场制品库；返回 skill_id。"""

    def review(self, skill_id: str, decision: str) -> None:
        """审核：approved → published（市场版本 v1→v2，制品本体同步提升并**重新签名**）；
        rejected → 状态回退，允许修改后重传。"""
```

- **审核定位真源是目录**：`review` 经 `self._index.locate(skill_id)` 找到发布源（不存在 ⇒ `SKILL_NOT_ACTIVE`），
  改动后经 `index.put` 回写 —— 不再维护进程内 `skill_id → source` 映射（那是第二真源，跨进程必失效）。
- **发布 = 元数据上架 + 制品入库**：先 `index.put`（源不存在即 `SOURCE_NOT_FOUND`，**此时不入制品**）再
  `artifacts.register(replace(skill))`（存副本，避免审核改写波及其他持有者）。
- **生产触达点**（`src/core/entry.py`）：`skill publish <skill_id> [--source S]` → `SkillPublisher.publish`
  （本地技能未注册 ⇒ stderr + 退出码 1）；`skill review <skill_id> <approved|rejected>` → `SkillPublisher.review`
  （驳回亦为退出码 1，状态已落盘为 rejected）。缺省装配经 `entry._build_publisher()`：落盘目录 + 本地市场制品库 +
  `VersionManager(path=$CORE_STATE_DIR/skill-versions.json)`（与组合根 `runtime._skill_state_path` 同源）。

---

## 5. TrustVerifier 接口

```python
class TrustVerifier:
    def verify(self, skill: Skill, signature: str) -> bool:
        """校验技能签名与来源可信度；失败返回 False（下载方据此拒绝）。"""
```

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `SIGNATURE_INVALID` | 技能签名校验失败 |
| `SOURCE_UNHEALTHY` | 来源不可达（回退官方源） |
| `SOURCE_NOT_FOUND` | source 不存在 |
| `PUBLISH_REJECTED` | 发布审核被驳回 |
| `SKILL_NOT_ACTIVE` | 技能处于 draft 未激活 |

---

## 7. 关联

- 模块：`02-modules/skillhub.md`
- 规格：`openspec/specs/skillhub/spec.md`
