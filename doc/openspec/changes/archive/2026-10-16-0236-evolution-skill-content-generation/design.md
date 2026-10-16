# Design 0236: 技能候选内容生成

> 承接原 `1306` 草稿；按评审收口：writer 工厂签名对齐 SOP、validate 接受 dict、
> writer=`None` 不写 content 键、failure_notes 有界常量钉死、description 优先 content 回退
> issue、GATE_CALIBER 注释轨迹不断档。

## D0 目标与边界

- 目标：技能级候选携带可执行 content；装配内容级验证（fail-closed / fail-fast）。
- 边界：不碰 0234；不碰诊断信号面 / 触发节拍 / 评测粒度；不内置 LLM。

## D1 数据模型

`SkillContent`（`content.py`）：

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `task_types` | 是 | `list[str]` | 非空 |
| `instructions` | 是 | `str` | 非空（strip）；写库前 `redact_secrets` |
| `param_schema` | 是 | `dict` | 必须为 dict（允许 `{}`） |
| `preconditions` | 否 | `list[str]` | 缺省 `[]` |
| `description` | 否 | `str` | 缺省 `""` |

`validate_skill_content(content: SkillContent | Mapping[str, Any] | None) -> bool`：

1. `None` / 无法 hydrate 为字段齐全的对象 ⇒ `False`；
2. `task_types` 空 ⇒ `False`；
3. `instructions` 空（strip 后）⇒ `False`；
4. `param_schema` 非 dict ⇒ `False`；
   否则 ⇒ `True`。

**为何接受 Mapping**：Proposer 写入 `delta["content"] = asdict(...)`；Validator /
`_crystallize_skill` 读到的是 dict，不得要求调用方先手工构造 dataclass。

## D2 生成器（DI，对齐 `sop_writer_with`）

```python
SkillContentWriter = Callable[[str], SkillContent | None]

def skill_content_writer_with(llm: Callable[[str], str]) -> SkillContentWriter:
    """工厂：把 prompt→文本 的模型调用适配为「prompt→SkillContent|None」。"""
    ...
```

- 内层 writer：`llm(prompt)` → `json.loads` → 字段校验 / 构造 `SkillContent`；
  非法 JSON、结构不符、`llm` 抛错 ⇒ 捕获并返回 `None`（不抛）。
- **禁止**把工厂本身当作 writer 注入（D7 必须先调用工厂）。

`build_skill_content_prompt(issue, failure_notes)`：

- `failure_notes` 有界（与 diagnoser **同口径字面量**，本模块自持常量、不 import diagnoser）：
  - `_MAX_FAILURE_NOTES = 3`
  - `_MAX_NOTE_CHARS = 400`
- 只取前 N 条，每条截断到 `_MAX_NOTE_CHARS`；要求模型只输出 JSON 对象
  （含 `task_types` / `instructions` / `param_schema`）。

## D3 Proposer

- 构造：`Proposer(*, kind=..., writer: SkillContentWriter | None = None)`
- `kind == "skill"` 且 `writer is not None`：
  - `content = writer(build_skill_content_prompt(issue, diagnosis.failure_notes))`
  - `content is not None` ⇒ `delta = {"issue": ..., "content": asdict(content)}`
  - `content is None` ⇒ `delta = {"issue": ...}`（**不**出现 `content` 键）
- plugin / `writer is None`：delta 仍只 `{"issue": ...}`（逐字不变）

## D4 Validator

- 构造：`Validator(..., require_skill_content: bool = False)`
- `require_skill_content=True` 且 `kind == "skill"`：
  - `validate_skill_content(delta.get("content"))` 为假 ⇒ `passed=False`、
    review 含「空壳」、`test_results={}`、**不跑**运行时测试；
  - 为真 ⇒ 既有 review + tests；
- plugin 不受影响；缺省 `False` ⇒ 逐字不变。

## D5 结晶

- 有效 content ⇒ `Skill` 映射各字段；`instructions` 写前 `redact_secrets`；
- **`description` 来源**：优先 `content.description`（非空 strip 后）；缺省 / 空串 ⇒
  **回退** `delta.get("issue", "")`（与今日空壳路径取 issue 的语义衔接，避免有 content
  却丢掉可读描述）。
- 缺省 / 无效 content ⇒ 既有空壳回退（回归锚点；`description` 仍取 issue）。

## D6 GATE_CALIBER 与 spec

- `GATE_CALIBER = 3`（判据集合含「技能内容有效」）。
- `models.py` 顶部版本轨迹注释 SHALL 同步追加：
  `3 = 技能内容判据（change 0236）`，避免轨迹断档。
- caliber 2 已确认候选 ⇒ `GATE_CALIBER_STALE`，须重提案（不重判历史）。

## D7 runtime 装配

```python
writer = skill_content_writer_with(_llm_text)  # 先工厂，再注入
Proposer(writer=writer)
Validator(require_skill_content=True)
```

- 同开同关：有 writer ⇒ `require_skill_content=True`；无 writer ⇒ 保持 `False`。
- 装配期不调 LLM。

## D8 测试表

| # | 断言 |
|---|---|
| 2.1 | validate 四态（含 dict 入参）；prompt 有界 notes |
| 2.2 | writer 合法 JSON ⇒ SkillContent；非法/异常 ⇒ None |
| 2.3 | 注入+skill ⇒ content；writer None / 未注入 ⇒ 无 content 键；plugin 不生成 |
| 2.4 | require 开：空壳拒 + fail-fast；有 content 走既有；缺省关逐字不变 |
| 2.5 | 结晶真技能（description 优先 content、空回退 issue）vs 空壳回退 |
| 2.6 | caliber 2 STALE / caliber 3 正常 |
| 2.7 | runtime 同开同关不抛 + evolution 回归绿 |
