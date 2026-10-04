# 接口设计：技能封装（Skills Interface）

> 模块：`02-modules/skills.md` ｜ 规格：`openspec/specs/skills/spec.md`

---

## 1. 技能定义

```python
@dataclass
class Skill:
    skill_id: str               # 全局唯一，如 "skills.data_analysis.summarize"
    description: str
    task_types: list[str]       # 适用任务类型
    preconditions: list[str]    # 前置条件
    param_schema: dict
    instructions: str           # 执行说明
    version: str                # 世代版本 v1/v2...
    status: str                 # "draft" | "active" | "gray" | "deprecated"
```

---

## 2. SkillLibrary 接口

```python
class SkillLibrary:
    def __init__(self, path: Path | None = None) -> None:
        """``path`` 注入落盘位置（``None`` = 纯内存）；启动即恢复（见 §7）。"""

    def register(self, skill: Skill) -> None:
        """入库；schema 非法抛 INVALID_SKILL_SCHEMA；注入 path 时落盘。"""

    def lookup(self, skill_id: str) -> Skill: ...

    def list_by_domain(self, domain: str) -> list[Skill]: ...

    def check_preconditions(self, skill: Skill, ctx: dict) -> bool:
        """前置条件不满足返回 False（PRECONDITION_FAILED）。"""
```

---

## 3. VersionManager 接口

```python
class VersionManager:
    def __init__(self, library=None, *, metrics=None, rng=None, path: Path | None = None) -> None:
        """``path`` 注入落盘位置（``None`` = 纯内存）；灰度/A-B/稳定版随变更落盘（见 §7）。"""

    def promote(self, skill_id: str, version: str, ratio: float) -> None:
        """灰度发布：新版本仅对 ratio 比例任务生效。"""

    def ab_test(self, skill_id: str, v_a: str, v_b: str) -> ABResult:
        """A/B 并行，用 observability 指标量化对比。"""

    def select(self, skill_id: str, ctx: dict) -> str:
        """按灰度/A/B 结果返回应使用的版本。"""

@dataclass
class ABResult:
    winner: str | None
    metric_delta: dict          # 各指标对比
    decision: str               # "promote" | "revert" | "keep"
```

| 维度 | 口径 |
|---|---|
| **调用方** | `SkillIterator`（0045）——灰度 `promote`、选版 `select`、A/B `ab_test` 的唯一生产调用者；此前三段能力齐备但无调用方（ADR-0048 决策 ⑥ 记的缺口） |
| **A/B 指标** | 各版本**成功率**——`VersionManager(library, metrics=lambda sid, ver: feedback.success_rate(sid, ver))`，越高越好，与 `b > a → promote` 语义一致 |
| **stable 优先** | `select` 按 A/B 胜者 > 灰度 > 稳定版 > 技能当前版本取序，草稿仅按灰度比例分流 |

---

## 4. SkillRouter 接口

```python
# 语义打分器接缝：(任务文本, 候选技能快照) → {skill_id: 分值}；缺省不启用（纯词法）
# 快照为 dict（不含 skills 类型）——实现侧（judgment.SkillMatcher）不依赖本模块
SkillScorer = Callable[[str, list[dict]], dict[str, float]]

class SkillRouter:
    def __init__(
        self,
        library: SkillLibrary,
        *,
        memory: MemoryStore | None = None,
        scorer: SkillScorer | None = None,
        threshold: float = 0.5,
    ) -> None: ...

    def match(self, task: str, *, domain: str | None = None, top_k: int = 3) -> list[SkillMatch]:
        """按任务类型匹配，返回匹配度排序的 Top-K；domain 为专属技能作用域。"""

@dataclass
class SkillMatch:
    skill: Skill
    score: float                # 匹配度（词法命中率 / 语义分；历史成功率见 #8 缺口）
```

无匹配时返回空列表，由 loop 回退通用流程并记录未命中（供新技能沉淀）。

| 维度 | 口径 |
|---|---|
| **词法 fast path** | 词元包含匹配（命中率 = 命中词元 / 任务词元）；**命中即返回，零模型调用** |
| **语义兜底触发** | 仅当词法**全无命中**时才调打分器（避免把辅助决策成本抬到每个推理轮） |
| **候选集** | 仅 `active` / `gray` 技能（`draft` / `deprecated` 不打分） |
| **专属作用域** | 三节 `beast.<域>.<技能>` 形式的 skill_id 为**专属技能**，仅当 `domain == "beast.<域>"` 时进候选（`domain=None` = 通用视角，默认）；形状即约定，不另建注册表 |
| **阈值** | 语义分 ≥ `threshold`（缺省 0.5）才采纳，按分降序取 Top-K |
| **降级** | 未注入打分器 / 打分器抛错 / 分值低于阈值 → 行为与纯词法一致（空结果 + 记 miss）；`match` 不向调用方抛异常 |
| **miss 口径** | 有命中（词法或语义）则不记 miss；两者皆无才记（miss 是「无技能可用」信号，供新技能沉淀） |
| **接线** | `build_runtime`：`scorer=SkillMatcher(router) if jev is not None else None`（未配置 JEV → 纯词法） |

### 4.1 命中注入与迭代闭环（0045）

```python
# 命中快照：**纯 dict**（loop 渲染用，不暴露 skills 类型）+ 步骤节选上界（token 有界）
def skill_hint(skill_id: str, version: str, instructions: str) -> dict[str, str]:
    """{"skill_id", "version", "instructions"(≤ _MAX_HINT_CHARS=400)}"""

@dataclass
class SkillStats:
    hits: int = 0; ok: int = 0; fail: int = 0   # total / failure_rate 为派生属性
    # total = ok + fail（命中但未收尾不计）；failure_rate 无样本 → 0.0

class SkillFeedback:
    def __init__(self, path: Path | None = None) -> None:
        """``path`` 注入落盘位置（``None`` = 纯内存）；计数随写入落盘（见 §7）。"""

    def record_hit(self, skill_id: str, *, version: str) -> None: ...
    def record_outcome(self, skill_id: str, *, version: str, ok: bool) -> None: ...
    def stats(self, skill_id: str, *, version: str | None = None) -> SkillStats: ...
    def success_rate(self, skill_id: str, version: str) -> float: ...

class SkillIterator:
    def resolve(self, skill: Skill) -> tuple[str, str]:   # (版本, instructions)
    def consider(self, skill: Skill) -> str | None:       # 不达标 → 草稿 + 灰度
    def decide(self, skill: Skill) -> ABResult | None:    # 双版本样本齐 → A/B 定夺

def build_iterate_prompt(skill: Skill, stats: SkillStats) -> str: ...
```

| 维度 | 口径 |
|---|---|
| **命中口径** | 技能进入 prompt 的那一轮记一次命中；结果按该轮**实际注入的版本**记成功/失败（版本维是 A/B 的前提） |
| **反馈存储** | 缺省仅进程内（不写记忆）；注入 `path` 时落盘 `$CORE_STATE_DIR/skill-feedback.json` 并在启动恢复（0050，见 §7）。不影响本轮推理结果与终止语义；未注入记录器 → 零行为变化 |
| **触发门** | 样本数 ≥ `_ITERATE_MIN_SAMPLES`(3) **且** 失败率 ≥ `_ITERATE_FAILURE_RATE`(0.5)，且已注入 writer，且改写文本非空——任一不满足即不迭代（零额外模型调用） |
| **灰度** | 草稿以 `_GRAY_RATIO`(0.3) 比例分流：`resolve` 按 `VersionManager.select` 返回版本，其余任务仍用原版本 |
| **定夺** | 两版本样本各 ≥ 下限才 `ab_test`；胜者为草稿则落地（版本号 + `instructions` 一并写回），否则**只丢草稿**——草稿版本非库中 `Skill.version`，`_deprecate` 自然 no-op，**技能不被误标 deprecated** |
| **可逆** | 落地登记 `Effect(op="skills.iterate", undo=恢复原版本与原 instructions)`（`trace_id="skills.iterate"`）；已被后续迭代覆盖则不回溯（幂等） |
| **接线** | `build_runtime`：命中钩子（路由 → 版本解析 → 记命中/快照）与收尾钩子（记结果 → `decide` → 失败再 `consider` → 转交 SOP 观察者）**每 loop 一组闭包**，状态不跨 loop 共享 |

已知缺口（如实记录）：改写 prompt 无失败轨迹（只有现行 steps + 计数，轨迹级诊断属 evolution 维度2）；
草稿被丢弃后需重新累计样本（无 cooldown）；成功率只区分成败，不检测 `instructions` 是否被模型实际采纳；
反馈/样本/灰度状态虽已落盘（0050），但**不做跨进程并发写入的合并**（沿用整文件覆盖语义）。

---

## 5. 结晶/溶解接口

```python
class SkillCrystallizer:
    def crystallize(self, skill: Skill) -> bool:
        """复用次数达阈值 + 过验证门 → 结晶为 L1 插件（联动 evolution）。"""

    def dissolve(self, skill_id: str, reason: str) -> None:
        """失效/退化 → 溶解回 L3 技能，教训写回记忆。"""
```

---

## 6. SOP 提炼接口

把**同一类任务的多次成功轨迹**聚合、提炼为一条 `Skill`（技能库的产出入口；此前只有
注册 / 路由 / 版本三段，没有任何产生技能的路径）。

```python
# 提炼接缝：prompt → SOP 文本（skills 不 import LLM 抽象，组合根注入模型调用）
SopWriter = Callable[[str], str]

def build_sop_prompt(task: str, steps: Sequence[str]) -> str:
    """把一组成功轨迹渲染为提炼 prompt（逐条节选，token 有界）。"""

def sop_writer_with(llm: Callable[[str], str]) -> SopWriter:
    """把「prompt → 文本」的模型调用适配为提炼契约（同 memory.Summarizer 方向）。"""

class SopExtractor:
    def __init__(self, library, *, writer=None, threshold=3, effect_tracker=None,
                 path: Path | None = None) -> None:
        """``path`` 注入样本落盘位置（``None`` = 纯内存）；样本随提交/清组落盘（见 §7）。"""

    def observe(self, task: str, steps: Sequence[str], *, ok: bool = True) -> Skill | None:
        """提交一条轨迹；达阈值则提炼入库并返回技能，否则返回 None。"""
```

| 维度 | 口径 |
|---|---|
| **调用方** | `DefaultLoop` 收尾钩子（`TurnObserver`）——每轮收尾都提交（任务文本, 行动/结果序列, ok）；`observe` 对 `ok=False` 直接丢弃（失败轨迹不是 SOP），由组合根再转交技能反馈 |
| **归组键** | 优先词法命中已有技能的 `task_types` 并复用其作组键，否则「任务词元签名」（`terms_of` 与 SkillRouter 同口径）——确定性、离线可断言 |
| **阈值** | 同组累计达 3 条（`_SOP_MIN_SAMPLES`）提炼一次，提炼后**清空该组**（下批重新累积） |
| **产物** | `skill_id="skills.sop.<组键 blake2b-8hex>"`（确定性、同组重复提炼覆盖同一条）、`description="SOP：<组键>"`、`task_types=[组键]`、`instructions=<提炼文本>`、`status="active"` |
| **发布口径** | `active`（维度1 技能库层属低风险自动发布）；`draft` 对路由不可见 → 不置 draft |
| **降级** | 未注入 writer：不累积、不提炼（零额外模型调用）；提炼文本为空：不入库、样本保留待下轮 |
| **可逆** | 入库登记 `Effect(op="skills.register", undo=移除)`（`trace_id="skills.extract"`）；回滚即移除，重复回滚幂等 |

已知缺口（如实记录）：无 judgment 质量门（质量门与版本迭代归 Phase 18 #8）。技能库与样本
已可落盘（0050，见 §7），缺省仍纯内存——生产由 `build_runtime` 注入路径。

---

## 7. 技能态持久化（0050）

技能态是**可变快照**（技能字段会被迭代改写、灰度状态会被覆盖、样本组提炼后清空），故用
**单文件 JSON 整体重写**而非追加日志；四个状态组件各持自己的 `path` 与序列化形状，只把
「字节进字节出」交给 `core/persistence.py` 的两个纯函数（标准库 JSON，零第三方依赖；**change `0051` 转入中立模块**，见下）。

```python
# core/persistence.py —— 无状态纯函数：read/write 都接受 path=None（= 不落盘）
def read_state(path: Path | None) -> Any:
    """读快照；None / 文件缺失 / 非法 JSON → None（不抛）。"""

def write_state(path: Path | None, data: Any) -> None:
    """原子写快照（同目录临时文件 + os.replace）；None → 不写盘。"""
```

| 落盘文件（`$CORE_STATE_DIR/`） | 组件 | 形状 |
|---|---|---|
| `skills.json` | `SkillLibrary` | `[Skill 字段全量]`（`asdict`） |
| `skill-feedback.json` | `SkillFeedback` | `{skill_id: {version: {hits, ok, fail}}}` |
| `sop-samples.json` | `SopExtractor` | `{组键: [[步骤…]…]}` |
| `skill-versions.json` | `VersionManager` | `{gray, stable, ab}` |

| 维度 | 口径 |
|---|---|
| **缺省纯内存** | `path=None` → 不落盘（既有纯内存构造零改动）；生产由 `build_runtime` 注入 `$CORE_STATE_DIR` 路径（同 `_memory_path()` 约定，env 可覆盖） |
| **损坏降级** | 落盘缺失 / 非法 JSON / 结构不符 → 空态启动（不抛、不阻断）；技能态是可重建的派生数据，不为它拒绝启动 |
| **原子性** | 临时文件 + `os.replace` 整文件替换，避免半写文件被读到 |
| **口径不变** | 持久化只跨进程保态，**不改变**路由 / 版本选择 / 迭代判定语义 |

> **helper 归属（change `0051`）**：两个纯函数原在 `src/core/skills/persist.py`；进化侧（`ObservationRegistry`）
> 成为第二个消费者后，留在 skills 包会迫使 evolution 反向 import skills 内部模块（依赖方向错），故提升到
> `src/core/persistence.py`——中性模块，**不 import 任何能力包、不构成横切能力**（决策记 ADR-0054）。

---

## 8. 错误码

| 错误码 | 含义 |
|---|---|
| `PRECONDITION_FAILED` | 前置条件不满足 |
| `INVALID_SKILL_SCHEMA` | 技能 schema 非法 |
| `NO_SKILL_MATCH` | 路由无匹配 |

---

## 9. 关联

- 模块：`02-modules/skills.md`
- 规格：`openspec/specs/skills/spec.md`
