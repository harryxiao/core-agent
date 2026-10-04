# evolution spec delta — evolution-confirm-surface

人工确认队列从「进程内、只增不减、身份绑对象」改为**可跨进程驱动**：候选带稳定身份，
门禁与评测结论随候选落盘，操作面（CLI）承担签发审批单、确认放行与拒绝。
（来源：账本 `phase-19.md` §2 A4 —— `EvolutionEngine.confirm` / `crystallize` 无生产调用方，2026-10-04）

## ADDED Requirements

### Requirement: 人工确认队列的持久化与操作面
系统 SHALL 让进化候选的人工确认队列**可跨进程驱动**：候选 SHALL 携带**稳定身份**（不依赖进程内对象标识），过门候选 SHALL 连同其验证门报告与留出评测报告**作为一条记录**落盘为 JSON 并在启动时恢复；未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。系统 SHALL 提供操作面以**列出**待确认候选、**确认放行**（确认后即发布结晶）与**拒绝**候选；对 `risk_level="high"` 的候选，操作面 SHALL 作为审批流的**签发端**构造目标一致的权限审批单并经人工批准后再调用 `confirm`。

- **稳定身份**：`GenerationCandidate` SHALL 携带构造即固化、进程内唯一的标识；验证门/留出评测报告的检索 SHALL NOT 依赖 `id(obj)`。
- **随候选留痕**：落盘记录 SHALL 含候选及其门禁与评测结论，使重启后 `confirm` → `crystallize` 仍可判定（不得因重启而误判未过门/退化）。
- **队列语义**：待确认快照 SHALL 只包含 `status="pending"` 的候选；`confirm` 与 `reject` SHALL 落盘并在快照中移除该候选。
- **拒绝语义**：拒绝 SHALL 置候选 `status="rejected"`（可附理由）并落盘；被拒候选 SHALL NOT 可发布。
- **降级**：落盘缺失或损坏 SHALL 降级为**空队列**（不抛异常、不阻断启动）。

#### Scenario: 待确认队列跨进程恢复
- **GIVEN** 一轮冷路径产出过门候选并已落盘
- **WHEN** 以同一路径在新进程中装配引擎
- **THEN** 待确认队列含该候选，且其验证门/留出评测结论一并恢复，可继续确认并发布

#### Scenario: 未注入路径纯内存
- **GIVEN** 引擎未注入落盘路径
- **WHEN** 跑一轮后确认并发布
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

#### Scenario: 操作面列出与确认放行
- **GIVEN** 待确认队列中有一个候选项
- **WHEN** 操作面列出并确认该候选
- **THEN** 候选被放行并发布结晶（结局 `published`），且随即从待确认队列移除

#### Scenario: 操作面拒绝候选
- **GIVEN** 待确认队列中有一个候选项
- **WHEN** 操作面拒绝该候选
- **THEN** 候选置 `rejected` 并从待确认队列移除，后续发布被拒

#### Scenario: 架构级候选的审批单由操作面签发
- **GIVEN** 待确认队列中有一个 `risk_level="high"` 的候选
- **WHEN** 操作面以人工身份确认
- **THEN** 操作面构造目标一致的审批单并经审批流批准后调用 `confirm`，候选被放行

#### Scenario: 候选不存在时的操作面反馈
- **GIVEN** 待确认队列中不含某标识
- **WHEN** 操作面以该标识确认或拒绝
- **THEN** 操作面给出明确反馈并非零退出，队列状态不变
