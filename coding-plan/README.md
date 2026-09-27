# Core-Agent Coding Plan（编码落地总索引）

> **定位**：这是「架构设计 → 编码实现」开始前的最后一环规划产物，供 Claude Code / 开发 Agent 按序推进编码时使用。
> 本目录 `coding-plan/` 承载 10 份文档：本 README（总索引）+ `phase-0.md` ~ `phase-8.md`（9 个 Phase 的可执行落地说明）。
> **规则**：严格按依赖拓扑序推进；每 Phase 完成须 100% 通过门禁三件套；所有 spec/interface 契约以仓库原文为准，速查见契约速查表。

---

## 0. 全局背景（一次说清，后续 Phase 不再重复）

| 维度 | 现状（已实证） |
|---|---|
| 架构定稿物 | 27 specs / 27 changes / 36 ADR / 25 interfaces（`doc/03-interfaces/*-interface.md`） |
| 实现语言 | Python 3.11（`requires-python = ">=3.11"`，可用 `X \| None`、`list[T]`） |
| 代码现状 | `src/` 仅协议骨架（10 个 .py，211 行），几乎无实现，tests 极少 → **「骨架阶段」基线** |
| 分层架构 | `substrate(L0) → tools(L1) → memory(L2) → loop(L3) → evolution(L4) → composition(L5)`，横切 `mcp` 可被各层消费 |
| 工程规范基线 | Phase -1 已闭环：`doc/05-development/development-standards.md`（12 主题）+ ruff/pyright/pre-commit/pytest 门禁可运行 |

> ⚠ **命名注意**：分层图里的 L0 `substrate` 在 Phase 3 落地时**重命名为 `context`**（已拍板决策 D2）；读历史文档时二者同义。

---

## 1. 文档清单（本目录 10 份）

| 文档 | 内容 | 对应里程碑 |
|---|---|---|
| `README.md`（本文件） | 总索引、Phase 映射、门禁、决策点 | — |
| `phase-0.md` | 底座与配置 | M0 底座就绪 |
| `phase-1.md` | 能力提供层 | M1 能力可调 |
| `phase-2.md` | 横切中间件 | —（随 M2 推进） |
| `phase-2.5.md` | 紧急补充：三方插件安装 + CLI 命令面契约回填 | —（无独立里程碑） |
| `phase-3.md` | 引擎主轴 | M2 单 Agent 闭环 |
| `phase-4.md` | 编排与检索 | M3 多 Agent 编排 |
| `phase-5.md` | 进化 | M4 自进化 |
| `phase-6.md` | 组合分发与部署 | —（随 M5 推进） |
| `phase-7.md` | 工程交付与用户入口 | M5 可发布产品 |
| `phase-8.md` | 宠物模式（后台自主增值） | —（随 M5 增值发布） |

**契约速查**：`contracts_summary.md`（27 capability 的 spec 目标 + interface 核心方法签名 + 模块路径，写代码前先查它）。

---

## 2. Phase 总览与依赖拓扑

> 顺序即依赖序：先无依赖底座 → 能力层 → 横切中间件 → 引擎主轴 → 编排 → 进化 → 组合分发 → 入口。

| Phase | 状态 | 模块（实现顺序） | 里程碑验收 | 关键前置动作 |
|---|---|---|---|---|
| 0 底座与配置 | ✅ 完成 | plugin-registry → configuration → observability → core-profile | M0：可注册/卸载插件、配置单源、遥测可观测、宪法 coeffect 注入 | 无（首个无上游） |
| 1 能力提供层 | ✅ 完成 | llm-provider → tool-use → memory | M1：真实模型调用跑通、工具可定义/调用/校验、记忆可读写与结晶 | 依赖 Phase 0 |
| 2 横切中间件 | ✅ 完成 | constraints → permission → durability → mcp | —（无独立里程碑） | 依赖 tool-use；permission 另依赖 configuration |
| 2.5 紧急补充 | ✅ 完成 | plugin-registry 安装抽象 → configuration CLI 覆盖 → mcp add/remove → permission-mode | —（无独立里程碑） | 依赖 Phase 0/1/2；契约含 0028/0029（M3/M4 代码随 P3） |
| 3 引擎主轴（L3） | ✅ 完成 | context → loop → skills → skillhub | M2：单 Agent 端到端「观察→推理→行动→记忆」闭环 | 依赖 memory/llm-provider + 全部横切；**首步 substrate→context 重命名** |
| 4 编排与检索（L3.5） | ✅ 完成 | orchestration → rag | M3：多 Agent 协同编排、RAG 检索可用 | 依赖 loop/llm-provider/tool-use/durability/distributed |
| 5 进化（L4） | ✅ 完成 | evolution | M4：故障/反馈可触发诊断→提案→验证→结晶全链路 | 依赖 observability/memory/skills/plugin-registry；**evolution↔memory 钩子解耦** |
| 6 组合分发与部署（L5） | ✅ 完成 | composition → distributed → deployment | —（无独立里程碑） | distributed 依赖 mcp/permission；deployment 依赖 composition/configuration |
| 7 工程交付与用户入口 | ⬜ 待开始 | ci-cd → ui/im/git | M5：完整产品形态可发布 | ci-cd 依赖 composition；ui/im/git 依赖 loop/configuration/permission；**首步补 git 契约** |
| 8 宠物模式（后台自主增值） | ⬜ 待开始 | pet-core → pet-library → pet-explore → pet-safety → pet-notify → pet-microtask | —（随 M5 增值发布） | 依赖 Phase 0/1/2/3/4；**首步对齐 /pet 三入口↔cli-ops 命令面边界 + Loop.run 同步薄壳复用** |

> **里程碑口径（M0~M5）**：M0 底座就绪（P0）→ M1 能力可调（P1）→ M2 单 Agent 闭环（P3）→ M3 多 Agent 编排（P4）→ M4 自进化（P5）→ M5 可发布产品（P7）。
> Phase 2（横切中间件）、Phase 6（组合分发部署）为**贯穿阶段**，不单设里程碑，其成果在 M2/M5 验收中一并体现。

---

## 3. 工程规范基线（Phase -1 已闭环，全程硬约束）

门禁命令（**提交前四者必须全绿**，否则该 Phase 视为未完成）：

```bash
ruff check src tests            # lint（select 规则集）
ruff format --check src tests   # 格式（行宽 100、双引号）
pyright                         # 类型（strict，include=src）
pytest -q                       # 单元 + 架构测试
```

12 条编码规范主题（详见 `../doc/05-development/development-standards.md`）：
1. Python 编码规范（PEP8 + ruff format/check + pyright strict，目标 py311）
2. 命名约定（类 PascalCase / 函数 snake_case / 常量 UPPER_SNAKE / 私有 `_` 前缀，禁止缩写）
3. 多线程安全（锁/队列/asyncio 三选一，明确线程归属，禁止裸锁跨 async 边界）
4. if/else 最大嵌套 ≤3 层（超限抽函数/卫语句/字典分发）
5. 低耦合高内聚（单一职责、依赖倒置、禁止跨层 import 实现类）
6. 串行/并行规范（默认串行，仅独立 I/O + 无共享状态才并行，禁止裸 fork）
7. 异常处理（DomainError/SystemError 分层、禁止裸 except、跨边界记录 trace_id）
8. 状态机设计（enum + 迁移表显式建模、非法迁移抛错、状态持久化）
9. 模块设计（L0-L5 分层、`__init__.py` 白名单导出、接口与实现分离）
10. 函数复用（DRY，≥3 处重复即抽取，复用优先于新写）
11. 最小化实现（KISS + YAGNI，每个类/函数可解释「为什么存在」）
12. CPU 性能（先 cProfile/py-spy 定位热点再优化，禁止无依据预优化）

> **离线工具链**：ruff 0.15.6 / pyright / pytest 均已缓存；**勿用 `uv run`**（会触发环境解析超时），直接调缓存二进制（路径见 development-standards.md 附录）。

---

## 4. 已拍板决策点（D1~D4，各 Phase 文档须遵守）

| 决策 | 内容 | 影响 Phase |
|---|---|---|
| D1 | `rag`、`git` 两个 capability 补契约（spec 已有，缺 interface） | P4 / P7 首步 |
| D2 | 分层 L0 `substrate` → 重命名 `context` | P3 首步 |
| D3 | `evolution` ↔ `memory` 的 Protocol 钩子解耦（避免循环依赖） | P5 |
| D4 | 全程按 M0~M5 里程碑口径推进，全量覆盖 Phase 0~7 | 全部 |

---

## 5. 每 Phase 文档统一模板

各 `phase-N.md` 一律采用以下 8 段结构，保证跨 Phase 可读性与可执行性：

1. **范围与定位**：本 Phase 覆盖哪些 capability，在分层图 L0~L5 中的位置
2. **里程碑验收**：对应 M 里程碑 + 具体验收标准（可勾选清单）
3. **依赖与前置**：上游 Phase / capability，无上游则明示「首个」
4. **首步任务**（如有）：补契约 / 重命名 / 钩子解耦等先行动作
5. **实现顺序**：模块级拓扑序 + 每个模块的关键类/接口
6. **契约对齐**：引用 `contracts_summary.md` 对应章节 + 关键方法签名
7. **门禁验收**：ruff / pyright / pytest 四命令全绿 + 本 Phase 专属校验
8. **提交规范**：一个 Phase 一个 commit，更新 `README.md` §2 状态列

---

## 6. 使用方式（给 Claude Code / 开发 Agent）

1. **总则**：从 `phase-0.md` 开始，按 Phase 0 → 1 → … → 7 顺序推进，**完成一个再开下一个**，禁止跳跃。
2. **每 Phase 的三件套动作**：
   - 读对应 `phase-N.md` + `contracts_summary.md` 中该 Phase 涉及的 capability 契约；
   - 实现代码，并逐一对齐 interface 契约（方法签名/语义）；
   - 跑门禁四命令全绿 + 单测/契约校验通过后，方视为完成该 Phase。
3. **跨 Phase 一致性**：接口引用以 `doc/03-interfaces/*-interface.md` 为准；出现契约冲突时，回读 spec 原文裁决，不要凭记忆改接口。
4. **回填**：每 Phase 完成后更新 `README.md` §2 总览表状态列并 commit（一个 Phase 一个 commit，便于回溯）。

---

## 7. 快速入口索引

| 想查什么 | 去哪 |
|---|---|
| 27 capability 的契约（方法签名/模块路径） | `contracts_summary.md` |
| 开发路线图（M0~M5 全貌） | `/home/harry/work/generic-agent/GenericAgent/temp/plan_devroadmap/plan.md` |
| 编码规范 + 门禁 | `../doc/05-development/development-standards.md` |
| 接口契约原文 | `../doc/03-interfaces/*-interface.md` |
| spec 目标原文 | `../doc/02-modules/*/spec.md` |
