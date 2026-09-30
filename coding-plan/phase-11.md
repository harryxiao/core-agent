# Phase 11 — 决策模型接入（judgment / JEV System One）

> 里程碑：**M8 决策模型接入**
> 位置：横切能力（决策原语路由）+ 能力层（JEVProvider 接入）+ 配置（judgment.* ConfigSpec）+ 观测（决策轨迹）
> 上游：observability（轨迹落盘）+ configuration（ConfigSpec 单一真源）+ permission（guardrail 消费）+ llm_provider（主 LLM 回退兜底）
> 对应 change：`openspec/changes/0035-judgment-decision`（13 tasks，契约层已全就绪，本 Phase 只写代码）

---

## 1. 范围与定位

本 Phase 把 core-agent 的决策点从「全部压在通用生成式 LLM」补齐为「**System One 决策小模型（JEV/TypeSafe）+ 主 LLM 回退**」双轨，交付 1 个 capability `judgment`（决策），内含 4 个组件：

| 组件 | 职责一句话 | 分层 |
|---|---|---|
| `DecisionRouter` | choice/decide 决策原语路由（统一决策入口） | 横切能力 |
| `JEVProvider` | 经 TypeSafe `POST /v1/systemone` 挂接 JEV，适配 typed questions/answers | 能力层 |
| `Compactor` | score 评分筛选（记忆压实决策点） | 横切能力 |
| `Guardrail` | noul 布尔判断（约束守卫决策点） | 横切能力 |

**核心机制（三条铁律）**：

1. **三原语统一入口**。`choice`（选项路由）/ `score`（评分筛选）/ `noul`（布尔判断）三类决策原语统一走 `DecisionRouter.decide()`，禁止散落在生成式 prompt 里。
2. **置信度回退主 LLM**。choice/score 以 `confidence < judgment.confidence_threshold` 判定回退；noul 无 confidence，以是/否概率接近 0.5 判定；JEV 不可达（`JUDGMENT_PROVIDER_UNREACHABLE`）/ 超时（`JUDGMENT_TIMEOUT`）亦回退。未配置 judgment 段时决策能力关闭、主 LLM 兜底。
3. **决策审计可进化**。每次决策轨迹（state + 原语 + 选项 + 结果 + 置信度 + 是否回退）落 observability 链路，供进化/审批消费。

## 2. 契约红线（实证现状 vs 契约）

### 2.1 已就绪契约（契约层全绿，禁止重复造）

| 契约 | 实证落点 |
|---|---|
| judgment spec 4 需求（决策原语路由 / JEV 接入 / 置信度回退 / 决策审计） | `openspec/specs/judgment/spec.md` 已存在 |
| configuration spec「决策模型配置」（judgment.* 5 键） | `openspec/specs/configuration/spec.md` 已存在 |
| `judgment-interface.md`（4 实体 + 4 接口 + 5 错误码） | `doc/03-interfaces/judgment-interface.md` 已定稿 |
| requirements 1.29（CORE-JDG-R1~R4） | `doc/00-product/requirements.md` |

### 2.2 契约缺口（须走 OpenSpec 变更补齐）

| 缺口 | 现状 | 补法 |
|---|---|---|
| 0035 change 未归档 | `openspec/changes/0035-judgment-decision/` 仍在（0/13 tasks） | 代码落地后 `openspec archive 0035-judgment-decision --yes --skip-specs`（spec 已同步，归档仅做移动） |
| 无 `src/core/judgment/` 代码 | 目录不存在 | 新建 6 文件（errors / models / router / provider / compactor / guardrail） |
| judgment.* 不在 ConfigSpec | `_CONFIG_SPECS` 无 judgment 键 | 补 5 条 ConfigSpec（provider/model/base_url/api_key/confidence_threshold，api_key `exposure=HIDDEN` + `${VAR}` 引用） |

## 3. 验收口径（M8 决策模型接入）

- **三原语**：`DecisionRouter.decide()` 按原语分发，choice 返回唯一选中项 + 概率分布 + 置信度；score 返回各条目评分；noul 返回放行/拦截（是/否）。
- **JEV 接入**：`JEVProvider.query(state, questions)` 经 `/v1/systemone` 提交 state + typed questions，返回按原语分形的 typed answers（`map<id, Answer>`）。
- **置信度回退**：confidence 低于阈值 → 回退主 LLM，`DecisionResult.fallback=True` + 轨迹标注；noul 以概率接近 0.5 判定；JEV 不可达/超时亦回退。
- **决策审计**：每次决策产出 `DecisionTrace`（trace_id / request / result / ts）落 observability，供进化/审批消费。
- **配置收口**：judgment.provider/model/base_url/api_key/confidence_threshold 经 ConfigSpec 单一真源（CLI > env > yaml > default）；api_key 走 `${VAR}` 引用分级；未配置时决策能力关闭、主 LLM 兜底。

## 4. 首步任务（开工前）

1. **读接口原文**：`doc/03-interfaces/judgment-interface.md`（4 实体 + 4 接口签名 + 5 错误码）为唯一真源，不复述重造；并在 `coding-plan/contracts_summary.md` 增补 judgment 契约明细（§judgment 当前缺失，本 Phase 回填；同表 beast-mode 亦未回填，可顺带补齐）。
2. **补 judgment.* ConfigSpec**：在 `src/core/configuration/manager.py` 的 `_CONFIG_SPECS` 补 5 条（`judgment.provider` / `judgment.model` / `judgment.base_url` / `judgment.api_key` / `judgment.confidence_threshold`），`api_key` 走 `exposure=HIDDEN` + `${VAR}` 引用（对齐 llm.api_key 写法），`confidence_threshold` 默认值（如 0.7）。
3. **定 JEV HTTP 客户端选型**：stdlib `urllib.request`（**零新依赖**，契合「litellm 唯一运行时三方依赖」红线）vs `httpx`（litellm 传递依赖，非直接声明）；按 ADR-0040 MAL 函数内懒 import。**默认取 stdlib urllib**（避免依赖传递假设），除非实测有硬需。
4. **核对 observability 落盘契约**：读 `doc/03-interfaces/observability-interface.md`，确认 `DecisionTrace` 走既有 trace/事件链（不另造观测真源）。
5. **决策点接线边界**（本 Phase 仅定义边界，实际 DI 接线 deferred 至后续 Phase）：loop（choice）/ memory 压实（score）/ permission guardrail（noul）三决策点经 **DI seam 注入** `DecisionRouter`/`Compactor`/`Guardrail`，不内联 JEV 调用（对齐 beast/pet「抽象不锁选型」立场）。

## 5. 依赖与顺序

```
configuration(ConfigSpec 单一真源) ─┐
observability(轨迹落盘) ─────────────┼─► judgment.* ConfigSpec ─► errors/models ─► provider(JEV 接入)
permission(guardrail 消费) ──────────┘                                    ─► router(choice/decide) ─► compactor(score) ─► guardrail(noul)
llm_provider(主 LLM 回退) ────────────────────────────────────────────────► 置信度回退 + 决策轨迹落 observability
```

- **硬依赖**：configuration / observability / permission / llm_provider 均已落地（Phase 0/1/2）；本 Phase 零新增三方依赖（JEV 为 HTTP API）。
- **顺序**：ConfigSpec → errors + models（4 实体 + 5 错误码）→ provider（JEV 接入 + typed questions/answers 适配）→ router（choice/decide + 置信度回退）→ compactor（score）→ guardrail（noul）→ DecisionTrace 落 observability（决策点 DI 接线 deferred 至后续 Phase）。
- **并行**：compactor / guardrail 互不依赖，可与 provider/router 并行推进；决策点 DI 接线（deferred）依赖三组件全部就绪后于后续 Phase 收口。

## 6. 里程碑验收清单

- [x] `openspec/changes/0035-judgment-decision/` 归档完成（spec 已同步，`--skip-specs` 仅移动）；`openspec validate` 全绿
- [x] `src/core/judgment/` 6 文件落地：errors（5 码 `JUDGMENT_PROVIDER_UNREACHABLE / JUDGMENT_SCHEMA_MISMATCH / JUDGMENT_LOW_CONFIDENCE / JUDGMENT_TIMEOUT / JUDGMENT_INVALID_PRIMITIVE`）+ models（`DecisionPrimitive` / `DecisionRequest` / `DecisionResult` / `DecisionTrace`）+ router + provider + compactor + guardrail
- [x] `DecisionRouter.decide()` 按原语分发；`choose()` 返回唯一选中项 + 概率分布 + 置信度
- [x] `JEVProvider.query(state, questions)` 经 `/v1/systemone` 适配 typed questions/answers（答案按原语分形：noul→noul / choice→choice+probabilities+confidence / score→score+legend+probabilities+confidence）
- [x] 置信度回退：confidence < 阈值 → 主 LLM + `DecisionResult.fallback=True` + 轨迹标注；noul 概率接近 0.5 判定；JEV 不可达/超时回退
- [x] 决策轨迹 `DecisionTrace` 落 observability（含置信度 + 回退标记）
- [x] judgment.* 5 键纳入 ConfigSpec 单一真源；api_key 走 `${VAR}` 引用分级；未配置时决策能力关闭、主 LLM 兜底
- [ ] 决策点 DI seam：loop（choice）/ memory 压实（score）/ permission guardrail（noul）三决策点经注入接 judgment，不内联 JEV 调用（deferred：三组件已落地并提供三原语，loop/memory/permission 三决策点的实际 DI 接线为后续 Phase）
- [x] 门禁四件套全绿：ruff check ✓ · ruff format --check ✓ · pyright 0 errors · pytest 全通过（含本 Phase 新增用例）

## 7. 测试要点

- [x] 三原语分发：choice 返回唯一选中项 + 置信度；score 返回各条目评分；noul 返回是/否（均对齐 `judgment-interface.md` 分形）
- [x] JEV 协议适配：state + typed questions → typed answers（按原语分形），答案与问题 schema 不匹配 → `JUDGMENT_SCHEMA_MISMATCH`
- [x] 置信度回退：confidence < 阈值 → `fallback=True` 且回退主 LLM；noul 概率 ≈0.5 → 回退；JEV 不可达 → `JUDGMENT_PROVIDER_UNREACHABLE` 回退；超时 → `JUDGMENT_TIMEOUT` 回退
- [x] 未识别原语 → `JUDGMENT_INVALID_PRIMITIVE`
- [x] 决策轨迹：每次决策产出 `DecisionTrace`，落 observability，含置信度与回退标记（单测断言轨迹字段完整）
- [x] ConfigSpec：judgment.* 5 键三面一致（CLI flag / env / yaml）；api_key 明文 yaml 拒绝；未配置 provider → 决策能力关闭、主 LLM 兜底
- [ ] 决策点 DI：loop/memory/permission 注入 fake `DecisionRouter`/`Compactor`/`Guardrail` 断言调用（deferred：随 DI 接线后续 Phase 补测，不碰真实 JEV）

## 8. 提交规范

- **一个 Phase 一个 commit**：judgment 六文件 + judgment.* ConfigSpec + observability 轨迹 + 契约归档（0035）+ 门禁全绿后单次提交（决策点 DI 接线 deferred，不纳入本 Phase commit）。
- commit message 形如：`feat(phase11): 决策模型接入 judgment/JEV System One（M8）`
- 提交后更新 `README.md` §2 总览表 Phase 11 行状态列为「完成」。
- 契约变更走 openspec 归档（changes/0035，spec 已同步故 `--skip-specs`），与代码同 commit 或紧邻提交。
