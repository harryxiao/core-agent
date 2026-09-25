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
