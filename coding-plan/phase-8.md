# Phase 8 — 宠物模式（pet-mode）

> 里程碑：**无独立里程碑，随 M5 增值发布**（对齐 phase-2.5 / phase-6 先例）
> 位置：后台自主增值层（pet.core/pet.library/pet.explore/pet.safety/pet.notify/pet.microtask）
> 上游：Phase 0（底座）+ Phase 1（能力）+ Phase 2（横切中间件）+ Phase 3（loop）+ Phase 4（orchestration）

---

## 1. 范围与定位

本 Phase 交付 **6 个模块，为 core-agent 增加「后台宠物模式」增值能力**：

| 模块 | 职责一句话 | 分层 |
|---|---|---|
| pet.core | 四层架构（基础属性/自主目标循环/探索工具集/安全边界）+ 多宠物生命周期与调度 | 核心 |
| pet.library | 人格模型（pet.md/prompt）+ 角色库（模板/自定义/导入导出） | 核心 |
| pet.explore | 受限探索工具集（只读优先、可配置、需授权） | 核心 |
| pet.safety | 安全边界（只读优先/不可逆禁止/爆炸半径/越界暂停通知） | 横切 |
| pet.notify | 异步通知主人（不阻塞主循环） | 横切 |
| pet.microtask | 日常随机微任务（可配置关闭侵入性任务） | 增值 |

**里程碑口径**：无独立里程碑，随 M5 增值发布（对齐 phase-2.5 / phase-6 先例）。capability 数保持 27 不变（pet-mode 已在列，本 Phase 仅补 R7~R14 八条需求的落地说明）。

**三入口**（R5 已定义，本 Phase 复用不改）：`/pet` 斜杠命令、`pet <verb>` CLI argv、WebUI 自然语言「启动宠物 + 任务」。

---

## 2. 契约红线（contracts_summary §26 原文）

**pet-mode（§26）**：
- 能力：后台宠物模式——四层架构（基础属性/自主目标循环/探索工具集/安全边界）、多宠物并行、人格驱动、角色库、受限探索、安全边界、异步通知、日常微任务
- 契约：四层解耦各层独立配置与替换（R7）；多宠物独立会话/人格/任务队列互不干扰可独立启停（R8）；pet.md/prompt 设定角色/性格/喜好，行为与输出受人格约束（R9）；角色库模板创建/自定义/导入导出（R10）；探索工具只读优先、可配置、需授权（R11）；安全边界只读优先、不可逆禁止、爆炸半径可控、越界暂停并通知主人（R12）；通知异步投递不阻塞主循环（R13）；微任务（终端散步/系统提示/无厘头注释）侵入性可配置关闭（R14）
- 接口：`PetSession`、`PetActivator`、`PetTask`；数据类型 `PetSessionState`/`PetTaskKind`
- 方法：`start()`、`wake()`、`suspend()`、`resume()`、`backoff()`、`terminate()`、`dispatch()`、`observe()`、`prefer()`、`report()`、`surprise()`、`activate_from_slash()`、`activate_from_cli()`、`activate_from_nl()`
- 错误码：`PET_ALREADY_ACTIVE`、`PET_NOT_ACTIVE`、`PET_BACKOFF`、`PET_YIELDING`、`PET_PREFERENCE_WRITE_FAILED`
- 依赖复用：`Loop.run()` 同步薄壳（R1）、orchestration 任务状态机 `SUSPENDED`（R3）、`MemoryEntry.source=user` 落 L2 facts（R4）、三入口（R5）

---

## 3. 验收口径（随 M5 增值发布）

- 四层架构可独立配置与替换（替换任一层不影响其余层）
- 多宠物并行：独立会话/人格/任务队列，A 宠物异常不影响 B 宠物
- pet.md/prompt 人格生效，行为与输出风格符合角色/性格/喜好
- 角色库：模板创建/自定义/导入导出闭环
- 探索工具集：只读优先、需授权、清单可配置
- 安全边界：越界/不可逆操作被阻断、宠物暂停并通知主人
- 通知异步投递，主循环不被阻塞
- 微任务：侵入性任务（无厘头注释）可配置关闭

---

## 4. 首步任务

**首步补 2 项对齐**（宠物模式无既有契约缺口，R1~R6 已定稿于 spec，仅需对齐命令面边界 + 循环复用）：

1. **对齐 /pet 三入口 ↔ cli-ops 命令面边界**：pet 的交互会话面走三入口（`/pet` 斜杠经 plugin-registry `list_tools`、`pet <verb>` CLI argv 经 cli-ops-interface `CommandGroup` 扩展、WebUI 自然语言经 `UIAPILayer`/`IMGateway.on_message`），均复用 Loop 同步薄壳；运维命令面（status/doctor/logs/install/mcp/auth/gateway）**不并入 pet**，仍归 cli-ops。pet 不得另起命令解析（与 phase-7「CLIBridge 只承载交互会话面」同一原则）。
2. **Loop.run() 同步薄壳复用说明**：pet 的后台自治循环复用 loop 模块 `Loop.run()` 同步薄壳（asyncio.run 桥接），每次唤醒逐次执行；pet 的「自主目标循环层」是 Loop 的目标注入扩展，不另起独立循环；多宠物调度复用 orchestration 任务状态机 `SUSPENDED`（R3），主循环 busy 时宠物不抢锁。

**启动前核对**（按顺序执行）：
1. 读 contracts_summary §26（pet-mode）+ §11（git，供微任务「加无厘头注释」经 git 安全接口）+ §12（im，供通知通道）原文。
2. 确认 8 条需求（R7~R14）在 delta spec 与当前 spec 逐字一致（本计划步骤 2/3 已保证）。

---

## 5. 依赖与顺序

- pet.core 依赖：Phase 3（loop 同步薄壳）+ Phase 4（orchestration `SUSPENDED`）+ Phase 2（memory L2 facts）
- pet.library 依赖：pet.core（四层架构基础属性层）+ Phase 1（llm-provider 人格 prompt）
- pet.explore 依赖：pet.core（探索工具集层）+ Phase 1（tool-use 只读工具）
- pet.safety 依赖：pet.core（安全边界层）+ Phase 2（permission 审批）
- pet.notify 依赖：Phase 7（im 通知通道）
- pet.microtask 依赖：pet.core + pet.safety（越界检查）+ Phase 7（git 安全操作）
- 建议顺序：R7 四层架构 → R8 多宠物 → R9 人格 → R10 角色库 → R11 探索工具集 → R12 安全边界 → R13 通知 → R14 微任务

---

## 6. 里程碑验收清单

- [x] 四层架构独立配置与替换，替换任一层不影响其余层（R7）
- [x] 多宠物并行调度，A 宠物异常不影响 B 宠物（R8）
- [x] pet.md/prompt 人格生效，行为与输出风格符合设定（R9）
- [x] 角色库模板创建/自定义/导入导出闭环（R10）
- [x] 探索工具集只读优先、需授权、清单可配置（R11；真实工具执行 deferred）
- [x] 安全边界阻断越界/不可逆操作，宠物暂停并通知主人（R12；通知真实通道 deferred）
- [x] 通知异步投递，主循环不被阻塞（R13；真实通道 im 注入 deferred）
- [x] 微任务只执行已启用任务，侵入性任务可配置关闭（R14；无厘头注释 git 写回 deferred）
- [x] 三入口 + 8 条需求单元级覆盖；真实后端全链路冒烟随 M5 集成 deferred

---

## 7. 测试要点

- [x] pet.core：四层独立配置/替换；多宠物独立会话/任务队列；异常退避不残留半运行状态；权威错误码全覆盖——`PET_ALREADY_ACTIVE`/`PET_NOT_ACTIVE`（激活生命周期）、`PET_BACKOFF`（异常退避隔离）、`PET_YIELDING`（主循环 busy 让行）、`PET_PREFERENCE_WRITE_FAILED`（偏好落 L2 facts 失败）
- [x] pet.library：pet.md/prompt 人格约束行为；模板创建/自定义/导入导出
- [x] pet.explore：只读优先；未授权工具阻断；清单可配置
- [x] pet.safety：越界/不可逆操作阻断；爆炸半径可控；暂停并通知主人
- [x] pet.notify：异步投递不阻塞主循环
- [x] pet.microtask：侵入性任务（无厘头注释）可配置关闭

---

## 8. 提交规范

- **一个 Phase 一个 commit**：pet.core + pet.library + pet.explore + pet.safety + pet.notify + pet.microtask 六模块 + 门禁全绿后单次提交。
- commit message 形如：`feat(phase8): pet-mode 宠物模式六模块（随 M5 增值发布）`
- 提交后更新 `README.md` §2 总览表 Phase 8 行状态列为「完成」（无独立里程碑，随 M5）。
