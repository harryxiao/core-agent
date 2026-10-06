# 接口设计：核心画像（Core Profile Interface）

> 模块：`02-modules/core-profile.md` ｜ 规格：`openspec/specs/core-profile/spec.md`

---

## 1. CoreProfile 数据模型

```python
@dataclass
class CoreProfile:
    constitution: list[str]     # 宪法与全局规则 → constitution:v1 coeffect
    personality: list[str]      # 人格 → L0 记忆层
    project_info: list[str]     # 项目信息 → ContextEngine 注入上下文
    source: str                 # 来源：~/.core/Core.md | <project>/Core.md | merged
```

---

## 2. CoreProfileEngine 接口

```python
class CoreProfileEngine:
    def __init__(self, resolver: CoeffectResolver | None = None):
        """resolver 缺省自建；可传入上层共享的 CoeffectResolver 以桥接注入。"""

    def load_global(self, path: str = "~/.core/Core.md") -> CoreProfile:
        """启动时读取全局级 Core.md，解析双语义分区。缺失静默降级。"""

    def load_project(self, cwd: str | None = None) -> CoreProfile:
        """载入项目时读取项目级 Core.md（cwd 向上查找），注入项目信息。"""

    def assemble(self) -> AssembledProfile:
        """合并全局级与项目级，产出运行时注入单元；并把 constitution:v1 注册进 resolver。"""

    @property
    def resolver(self) -> CoeffectResolver:
        """宪法 coeffect 注入的 resolver，供上层模块 resolve(["constitution:v1"]) 取用。"""

@dataclass
class AssembledProfile:
    coeffect: dict              # constitution:v1 coeffect 内容
    personality: list[str]      # 写回 L0 记忆层
    context: list[str]          # 项目信息注入 ContextEngine
```

---

## 3. Loader 接口

```python
class GlobalProfileLoader:
    def load(self) -> CoreProfile:
        """读取 ~/.core/Core.md；文件缺失返回空画像，不报错。"""

class ProjectProfileLoader:
    def find_upwards(self, cwd: str) -> str | None:
        """从 cwd 逐级向上查找 Core.md，返回最靠近的项目根文件路径；未命中返回 None。"""

    def load(self) -> CoreProfile:
        """读取命中的项目级 Core.md，提取项目信息分区。"""
```

---

## 4. SectionParser 接口

```python
class SectionParser:
    def parse(self, raw: str) -> list[Section]:
        """按分区标记解析（宪法与全局规则 / 人格），忽略无法识别的内容。"""

@dataclass
class Section:
    kind: str                   # "constitution" | "personality"
    lines: list[str]
```

---

## 5. Merger 接口

```python
class Merger:
    def merge(self, global_p: CoreProfile, project_p: CoreProfile) -> CoreProfile:
        """合并两级画像：项目级覆盖全局级同名配置项；source 标记为 merged。"""
```

---

## 6. Validator 接口

```python
class Validator:
    def validate(self, sections: list[Section]) -> list[Section]:
        """格式校验：非法分区告警并跳过，返回合法分区；不阻断启动或载入。"""
```

---

## 7. 错误码

| 错误码 | 含义 |
|---|---|
| `PROFILE_MISSING` | 文件缺失（静默降级，按无该级别预设继续） |
| `SECTION_INVALID` | 分区标记格式非法或无法解析（告警跳过，加载其余合法分区） |

---

## 8. 题词模板（骨架产出物）

规格「题词模板」的产出物为仓库内**可直接复制**的两份骨架文件（change 0142 / 账本 E85）：

| 骨架 | 落向 | 分区（标题**逐字**约定） |
|---|---|---|
| `templates/Core.global.md` | `~/.core/Core.md` | `## 宪法与全局规则`、`## 人格` |
| `templates/Core.project.md` | `<project>/Core.md` | `## 项目信息` |

- **标题即契约**：分区标题取自运行时解析器 `SectionParser` 的 `_SECTION_HEADERS`（`profile.py`）——
  未知标题落 `unknown`、空分区一并 ⇒ `SECTION_INVALID` 告警并**跳过该分区**（用户难察觉），
  故骨架标题与解析器**逐字对齐**，且每个分区保留可被接受的**占位内容行**（空分区会被跳过）。
- **注入说明注释**：各分区以 HTML 注释注明落向的运行时通道（`constitution:v1` coeffect / L0 记忆层 /
  ContextEngine 上下文）。注释形式是**有意的** —— `_is_content` 会跳过 `<!--` 与 `>` 开头的行，
  说明因此**不进**注入内容。
- **门禁**：`tests/test_core_profile_templates.py` 以骨架**原文**跑 `SectionParser` + `Validator`，
  断言分区 kind 正确且**零告警**（复制即用）。

---

## 9. 关联

- 模块：`02-modules/core-profile.md`
- 规格：`openspec/specs/core-profile/spec.md`
- 变更：`openspec/changes/0142-core-profile-template/`
