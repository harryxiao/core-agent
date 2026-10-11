# Design 0198 — SOP 自动质量门

## 决策 ①：门的形状 = **纯 callable**（`Callable[[str, str], bool]`），skills 不 import judgment

沿用 `SopWriter = Callable[[str], str]` 的既有方向（`skills/sop.py:32`）：skills 定义**契约**
（类型别名 `SopGate`），judgment 提供**实现**，组合根**注入**。skills 侧**不**出现任何
judgment / LLM 符号（ADR-0048 依赖方向：`memory.Summarizer` / `SopWriter` / `_steps_lookup`
同一范式）。**否**：在 skills 内侧内联 `DecisionRouter`（会把判定依赖下沉进技能层）。

## 决策 ②：判定用 **noul**（布尔），镜像 `Guardrail`

门的语义是「**是否**可发布」= 布尔，故取 noul 原语（`DecisionPrimitive.NOUL`）。实现落在
`judgment/skills.py`（**该模块已是「判定原语 × skills 概念」的适配层**：`SkillMatcher` 用 score
做语义路由），形态为一个 **`__call__(task, sop) -> bool`** 的小类 + 一个 `sop_gate_with(router)`
工厂 —— 与 `SkillMatcher.score` 一样：**经注入的 `DecisionRouter` 统一决策，不内联 JEV 调用**。

- `state` 携带**任务文本**（帮助判定上下文）；`questions["noul"]["action"]` 携带
  `{"kind": "publish_sop", "sop": <提炼文本>}`（判定**必须**看到正文，否则无从判质量）。
- 该载荷进 `DecisionTrace`（既有观测面：`Guardrail` 同样把 `action` 交给 trace）⇒ 与既有判定
  面的暴露口径**一致**，未新增面。
- **不新增 `DecisionPrimitive`**、**不改 `DecisionRouter`**、**不改 judgment 规格**。

## 决策 ③：fail-open（异常 / 缺答案 / 非布尔 ⇒ 放行）

```python
try:
    answer = router.decide(request).answers["noul"]
    return bool(answer["noul"])
except Exception:  # noqa: BLE001 — 判定故障不阻断发布
    return True
```

**方向判据**：门有两类失败 —— ①「判定**有结论**：不可复用」⇒ **拒**（本 change 的收益面）；
②「判定**无结论**：调用炸 / 答案缺失」⇒ **放行**。理由：门是**新增**的刹车，不能让一次判定
故障把「此前一直正常发布」的路径变成**静默不发布**（那正是本批要消灭的「静默」缺陷类）；
且规格明文「提炼失败 SHALL NOT 中断 Agent 主流程」。**拒**的方向仍占优（有结论时以结论为准）。

**两层各有守卫职责**（不是重复）：`SopGate` 守着**自身**的判定故障（路由抛异常 / 答案结构
不符 ⇒ `KeyError` 被吞 ⇒ `True`，镜像 `SkillMatcher._score_one` 的既有范式）；`observe._gate_ok`
守着**契约边界**（门是**任意注入**的可调用，其故障不得冒泡进 `_finalize` → 编排收尾回路）。

**已知边界（诚实记录）**：`DecisionRouter` **自身**的降级链**不产生异常** —— provider 不可达时
回退主 LLM，其答案（含主 LLM 亦不可用时给出的 `False`）都是一次**「有结论」** ⇒ 该情形下门
**拒**而非放行（每拒一次有 `warnings.warn` 留痕，故不致静默）。本 change **不**改路由语义
（属既有已规格化行为），只把「路由层**之外**的故障」定为 fail-open。

## 决策 ④：未过 ⇒ **清组** + 留痕**只报组键**

- **清组**（`del self._samples[key]` + `_persist()`）：与「达阈值提炼后清组」同构 —— 否则同一批
  已判定不合格的样本会在下一条到达时**再触发一次**（模型 + 判定各一次），反复无效调用。
  **代价**：该组需**重新**累积（有意的：宁可重攒，不做无效重判）。
- **留痕**：`warnings.warn(f"SOP 质量门未过，不入库（组键 {key}）", stacklevel=2)` ——
  **只报组键**，**绝不**回显提炼正文（密钥红线；正文由模型从脱敏材料生成，仍按「不回显正文」
  从严处置）。**否**：把正文写进告警（可读性收益 < 红线风险）。
- **不登记效应**：门未过时**没有**入库，故**无** `Effect` 可回滚（与「入库登记撤销」不冲突）。

## 决策 ⑤：接线只在**任务级**实例、且**仅在 JEV 配置时**

```python
sop_task_extractor = SopExtractor(
    ..., namespace="task",
    gate=sop_gate_with(router) if jev is not None else None,
)
```

- 沿仓内惯例（`Guardrail(router) if jev is not None else None`、`SkillMatcher(router).score if
  jev is not None else None`）：**judgment 未配置 ⇒ 门不存在** ⇒ 发布路径**逐字不变**。
- **只挂任务级**：本 change 的动因是 0197 新接的任务级面（样本更长、语义更不可控）；单轮面是
  既有行为，改它属**超范围**（P3：改一条、可归因一条）。若要给单轮面加门，是**独立**决策。

## 落点

| 文件 | 改动 |
|---|---|
| `src/core/skills/sop.py` | `SopGate` 类型别名；`__init__` + `gate` kwarg；`observe` 中「清组 + 留痕 + 返回 None」 |
| `src/core/judgment/skills.py` | `SopGate` 类（`__call__`，noul，fail-open）+ `sop_gate_with(router)` 工厂 |
| `src/core/runtime.py` | 任务级实例接线（一行 + 注释） |

## 测试（红 → 绿）

`tests/test_skills.py`（提炼器侧，不引 judgment）：

1. **门拒绝 ⇒ 不入库 + 清组 + 留痕只报组键**：`gate=lambda *_: False`，达阈值提炼 ⇒
   `library.all_skills()` 不含该产物；`warnings.catch_warnings(record=True)` 抓到告警且
   **正文不在**告警文本中；再次提交一条同组样本**不**立即提炼（组已清、计数从 1 起）。
2. **门放行 ⇒ 照常入库**（`gate=lambda *_: True` ⇒ `active` 入库）。
3. **未注入门 ⇒ 发布行为不变**（缺省路径）。
4. **门抛异常 ⇒ fail-open 放行**（`gate=_boom`）。

`tests/test_judgment.py`（judgment 侧）：`SopGate.__call__` 经**真 `DecisionRouter`**+桩 provider ⇒
真/假各自映射，且断言载荷（`state` 带任务、`action.sop` 带正文）；`decide` 抛异常 / 答案缺 `noul`
⇒ **True**（fail-open）。**实测订正**：初版两条 fail-open 用例走「provider 抛错」路径 ⇒ **转红** ——
因为 `DecisionRouter` 不冒泡异常而是**回退主 LLM**（桩回退返回空串 ⇒ `_parse_yes("")` = `False`）。
⇒ 改为直接桩**路由层**（`_RaisingRouter` / `_ShapelessRouter`），并据此在决策 ③ 补记该边界。
