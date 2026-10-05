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

**凭证半**：真实市场 fetcher（网络 + 市场凭据）未接。缺省 `fetcher=None` ⇒ `skill install` **如实**报
「无法下载技能（市场缺失或未接入拉取）」；缺省 `MarketIndex` 只有空的 `official` 源 ⇒ `skill search` 如实返回空。

---

## 3. MarketIndex 接口

```python
class MarketIndex:
    def list(self, *, source: str = "official") -> list[MarketSkill]:
        """列出指定源的技能目录元数据。"""

    def route(self, source: str) -> MarketSource:
        """按 source 路由到对应市场源；源不存在抛 SOURCE_NOT_FOUND。"""

    def health(self, source: str) -> SourceHealth:
        """源健康探测；不可达标记不健康并回退官方源（SOURCE_UNHEALTHY）。"""

@dataclass
class SourceHealth:
    source: str
    healthy: bool
    last_check: str             # ISO 时间戳
```

---

## 4. SkillPublisher 接口

```python
class SkillPublisher:
    def publish(self, skill: Skill, *, source: str = "official") -> str:
        """上传技能 → status=uploaded，进入审核流 pending。"""

    def review(self, skill_id: str, decision: str) -> None:
        """审核：approved → published（VersionManager v1→v2）；
        rejected → 状态回退，允许修改后重传。"""
```

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
