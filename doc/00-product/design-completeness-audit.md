# CORE-Harness 架构设计文档 · 系统级完整度审计报告

> 审计对象：`doc/` 全量（196 md / 11,385 行）
> 审计性质：只读审计（未修改任何受审文件）
> 审计方法：工具实证（`openspec validate` 实跑 + grep 交叉比对 + 文件树 diff），非抽样、非记忆断言
> 审计标准：openspec 规范符合度 + 架构六维度完整性 + 交付就绪度 + 交叉一致性

## 一、审计基线（实测规模）

| 维度 | 实测值 |
|---|---|
| Markdown 总量 | 196 个 / 11,385 行 |
| 一级目录 | 14 个（00-product ~ 12-git + openspec + paper） |
| 能力模块 | **21 个**（PLG/LOOP/MEM/TOOL/MCP/EVO/PERM/ORCH/OBS/CONS/SKILL/CTX/UI/IM/LLM/COMP/DIST/RAG/GIT/DEP/PROF） |
| 接口文档 | 19 个（03-interfaces） |
| 模块实现文档 | 17 个（02-modules） |
| OpenSpec specs | 21 个（1,733 行） |
| OpenSpec changes | 22 个 active（0001~0022 连续）+ 1 个 archive 空骨架 |
| ADR | **31 个**（ADR-0001 ~ ADR-0031，连续无跳号） |
| 功能需求 FR | **115 条**（21 模块，`CORE-<模块>-R<n>` 格式） |
| 源代码 src | **0**（纯设计文档，无实现代码） |

## 二、总体结论

**完整度判定：设计文档「可落地」级，整体 PASS，存在 6 项真实缺陷（P1×3 + P2×3）需修正，不影响整体架构完整性。**

六维度（系统架构 / 模块设计 / 异常处理 / 数据结构 / 接口设计 / 前后端交互）**全部有实质内容覆盖**，非仅有文件占位。核心短板集中在**测试文档与需求/覆盖矩阵的过期失配**，属"交付就绪度"与"交叉一致性"范畴，非架构设计本身的缺陷。

## 三、四维度逐项审计

### 维度 A：OpenSpec 规范符合度 ✅（硬检查全过）

| 检查项 | 结果 |
|---|---|
| `openspec validate` 实跑 | **43 passed / 0 failed**（21 spec + 22 change） |
| change 三件套（proposal/tasks/design/specs_dir） | 22 个 **全部齐全** |
| 21 个 spec 标准头部（`# X Specification` + `## Purpose` + `## Requirements`） | **全部齐全**，无 ADDED 残留 |

**规范瑕疵（不阻断，但需知）**：
- ⚠️ 2× WARNING：`distributed/spec.md`「可选 P2P 传输优化」缺 SHALL/MUST（change 0009 与 merged spec 各一次）
- ℹ️ 2× INFO：`0010-rag` 与 `0017-orchestration` 的 delta `## ADDED Requirements` 与 merged spec 头部**逐字重名** → 未来执行 `openspec archive` 时会被拒绝

### 维度 B：架构六维度完整性 ✅

| 维度 | 覆盖情况 |
|---|---|
| 系统架构 | 分层插件化架构 + 31 条 ADR 决策记录，末尾含 ADR→文档映射表（L256-277） |
| 模块设计 | 21 能力模块，17 模块实现文档 + 21 spec |
| 异常处理 | 20/21 spec 已含异常处理（前序「查漏补缺」已补齐） |
| 数据结构 | 各接口文档含 schema/数据契约定义 |
| 接口设计 | 19 接口文档，README 树与实际 100% 一致 |
| 前后端交互 | UI 三模（CLI/Web/Desktop）+ Harness Host 分离方案 |

### 维度 C：交付就绪度 ⚠️（主要缺陷集中区）

MVP 里程碑已定义，但**测试文档与需求规模脱节**（详见缺陷清单 P1）。

### 维度 D：交叉一致性 ⚠️

**PASS 项**：
- ✅ README `03-interfaces` 目录树 vs 实际 19 接口文件：**完全一致**（无遗漏、无悬空引用）
- ✅ ADR 编号连续 + 映射表齐全
- ✅ 数字口径已修正：ADR 实为 31（非此前误记 23）、active change 22（+1 archive）

**失配项**：见缺陷清单 P1/P2。

## 四、缺陷清单

### 🔴 P1 — 应修正（测试文档与需求脱节）

| # | 位置 | 缺陷 | 证据 |
|---|---|---|---|
| 1 | `test-strategy.md` §4.2 | 覆盖矩阵自标「19 模块」，但实际 21 业务模块，**缺 deployment、core-profile 两行** | 矩阵列 19 行，requirements 有 21 模块 |
| 2 | `test-strategy.md` §4.2 | 矩阵 R 编号范围 **8 处过期**，与 requirements 实际不符 | MCP 写 R1~R4（实 R9）、ORCH R1~R4（实 R7）、UI R1~R6（实 R9）、OBS R1~R4（实 R5）、SKILL R1~R4（实 R5）、LLM R1~R5（实 R6）、DIST R1~R7（实 R8）、GIT R1~R4（实 R5） |
| 3 | `test-cases.md` | 仅覆盖 **17 模块**，**缺 RAG/GIT/DEP/PROF 4 模块用例**（grep 全库无任何对应 TC-*） | `TC-*` 分组统计仅 17 组，且无 TC-RAG/GIT/DEP/PROF |

> 注：缺陷 3 与 test-strategy §4.2 矛盾——矩阵声称 RAG/GIT「均有用例覆盖」（TC-RAG-*、TC-GIT-*），但 test-cases.md 实际无此二组用例，属**自相矛盾**。

### 🟡 P2 — 宜修正（规范/格式瑕疵）

| # | 位置 | 缺陷 |
|---|---|---|
| 4 | `requirements.md` deployment 节（L211-216） | 编号乱序：R1, R2, R3, **R6**, R4, R5 |
| 5 | `distributed/spec.md` | 「可选 P2P 传输优化」缺 SHALL/MUST 规范动词（validate WARNING） |
| 6 | `0010-rag` / `0017-orchestration` delta | ADDED 与 merged spec 头重名，`openspec archive` 会被拒绝（validate INFO） |

### ⚪ P3 — 观察项（设计允许，无需改）

| # | 项 | 说明 |
|---|---|---|
| 7 | src = 0 | 纯设计文档、无实现代码——属「设计完整度审计」的定位边界，非缺陷 |
| 8 | spec Requirement 数与 requirements R 数非严格同号 | README L167 已明示「通过命名与编号区间建立追踪映射（非严格同号）」，符合规范 |

## 五、建议处置

1. **P1（测试文档脱节）** 单开一个 openspec change 修复：补 test-strategy 矩阵 2 行 + 更新 8 处 R 范围 + 补 test-cases 4 模块用例组。
2. **P2** 低成本小修，随 P1 一并处理（deployment 编号重排、distributed 补 SHALL/MUST、delta 去重名）。
3. **P3** 无需动作。
