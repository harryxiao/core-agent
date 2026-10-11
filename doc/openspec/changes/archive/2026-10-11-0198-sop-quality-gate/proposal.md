# Proposal 0198 — SOP 自动质量门（quality gate）

## 为什么

`doc/03-interfaces/skills-interface.md` §6 明文登记的**已知缺口**：「无 judgment 质量门」。
现状是 `SopExtractor.observe` 提炼出非空文本后**直接** `status="active"` 发布（`skills/sop.py`）
—— 技能库是**全自动**面（红线：维度1 技能库/SOP **全自动**，不得引入人工确认，
`coding-plan/phase-21.md:5`），因此缺的是一个**自动**判定闸门，而非人工复核。

长任务过程输入接通后（change `0197`），任务级 SOP 的**样本更长、语义更不可控**（子任务骨架
由多个子任务步序拼成）⇒ 「自动发布 + 无任何质量判定」的组合风险随之上升：一次低质提炼会把
**空泛 / 不可复用**的文本以 `active` 身份推进路由放行集，且**不可追溯其被拒**（无留痕）。

## 做什么

- `SopExtractor.__init__` 增可选 keyword-only `gate: SopGate | None = None`
  （`SopGate = Callable[[str, str], bool]`，**纯 callable** ⇒ skills **不** import judgment，
  守 ADR-0048 的依赖方向，与 `SopWriter` 同构）。
- `observe` 中：非空文本产出后、构造 `Skill` 前过门；**未过** ⇒ 不入库 + 清空该组 + 留痕
  （`warnings.warn`，**只报组键，绝不回显提炼正文**）。
- `judgment/skills.py` 新增 `SopGate` / `sop_gate_with(router)`：以 **noul** 原语做「该 SOP 是否
  可发布」的自动判定，**镜像 `Guardrail`**（同模块、同原语、同 `DecisionRouter` 统一决策）；
  判定异常 / 缺答案 ⇒ **放行**（fail-open）。
- `runtime.build_runtime`：给**任务级**实例接线 `gate=sop_gate_with(router) if jev is not None else None`
  （沿仓内既有惯例：judgment 背书的接缝**仅在 JEV 配置时启用**）。

## 不改什么

- **judgment 规格零改动** —— 门是**已规格化** `noul` 原语的**纯消费方**（新用途、不新增能力）。
- **不引入人工确认**（红线）；**不**改 `observe` 签名之外的既有语义；**不**动单轮实例的接线
  （门只挂在任务级实例上，单轮面发布行为逐字不变）。
- **不**新增错误码、**不**新增第三方依赖。

## 规格影响

`skills`「SOP 提炼（skill extraction）」**MODIFIED**：新增「自动质量门」bullet + 2 Scenario
（「质量门未过不入库」/「未注入质量门时发布行为不变」）；既有 9 Scenario **逐字保留**。
canonical `skills` scen **47 → 49**、req **10 不变**。

## 风险

- **判定调用成本**：每次**达阈值提炼**（非每轮）多一次判定调用；门未过即清组 ⇒ 同批样本不会
  反复触发（有界）。
- **`noul` 的**close-to-0.5** 判定**：`DecisionRouter` 的概率窗口会把「无信息量」的判定转回退链，
  回退不可用时给 `probability=0.5` + 文本启发式 ⇒ 属**既有**原语语义，本 change 只消费。
- **fail-open 的方向性**：判定故障时**放行**（宁发布不误拒）—— 与「门未过即拒」并列时，方向由
  「拒」占优（判定**有结论**时）；仅**无结论**时放行。
- **留痕只报组键**：绝不回显提炼正文（密钥红线；正文经模型生成，仍按「不回显正文」从严处置）。
