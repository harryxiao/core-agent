# tasks — 按会话隔离记忆（change 0114 / phase-28 E47）

## 1. 规格（先行）
- [x] 1.1 `specs/memory/spec.md`：ADDED「按会话隔离的检索」——非空标识只返回「本会话 + 全局层」、
      空标识不过滤（逐字兼容）、过滤先于排名/预算/复用计数、与来源排除可叠加；**全局层**定义
      （未归属 + L0 人格 + 笔记层）（5 场景）
- [x] 1.2 `specs/context/spec.md`：MODIFIED「动态上下文构建」（透传会话维度）+ MODIFIED「上下文自动压实」
      （产物按会话归属 + id 带会话键）（共 4 新场景）
- [x] 1.3 `specs/loop/spec.md`：MODIFIED「执行循环」——标识**经上下文包**传至推理（装配）与技能路由，
      SHALL NOT 只用于记忆写入（+1 场景）
- [x] 1.4 `specs/skills/spec.md`：MODIFIED「技能路由」——未命中记录按会话归属（+2 场景）
- [x] 1.5 `specs/pet-mode/spec.md`：MODIFIED「Pet Session Runtime Wiring」——宠物轨迹按宠物会话归属、
      偏好仍留全局（+1 场景）
- [x] 1.6 `specs/orchestration/spec.md`：MODIFIED「子任务拆解」——子 Agent 执行携带发起方会话标识（+2 场景）
- [x] 1.7 `specs/ui/spec.md`：MODIFIED「三模统一内核启动」——`run_task` 透传会话标识至编排器（+1 场景）
- [x] 1.8 `specs/notes/spec.md`：MODIFIED「Consult → Build → Update 循环纪律」——**明写**笔记为全局文档层、
      不参与会话隔离（+1 场景）
- [x] 1.9 `openspec validate 0114-session-scoped-memory` 通过

## 2. 测试（先写，红）
- [x] 2.1 新 `tests/test_session_isolation.py` §read：三组可见性（A / B / 未归属全局层）
- [x] 2.2 同文件：**反例守门** —— B 会话检索不到 A 会话沉淀的事实
- [x] 2.3 同文件：空标识不过滤（三组都可出现，逐字兼容）
- [x] 2.4 同文件：**过滤先于预算** —— 被滤项不吃预算、`reuse_count` 不递增
- [x] 2.5 同文件：会话过滤 × 来源前缀排除**可叠加**
- [x] 2.6 同文件：端到端反向守门（真 `DynamicAssembler` + 真 `MemoryStore`）——A 的事实不进 B 的 system prompt
- [x] 2.7 同文件：`astream(session_id=…)` 真落到 `read` 的 `session_id` 实参（spy store）
- [x] 2.8 同文件：`perceive()` 默认仍**一参**调用面（既有替身不破）
- [x] 2.9 同文件：`Compactor.persist(session_id=…)` ⇒ 条目 `session_id` + id 带会话键；空标识 ⇒ 缺省键
- [x] 2.10 同文件：`SkillRouter.match(task, session_id=…)` 未命中记录归属；空标识仍只传 1 实参
- [x] 2.11 同文件：宠物 `run` 收到 `session_id=pet.session_id`（spy loop）；偏好写入仍为全局层
- [x] 2.12 同文件：编排 `arun` 收到发起方 `session_id`（spy loop）
- [x] 2.13 同文件：**notes 守门** —— `NoteStore.digest` / `consult` 不接受会话维度（可执行的全局层钉住）
- [x] 2.14 更新 `tests/test_loop.py:551-552`：`compaction.fact.0` → `compaction.fact.default.0`
- [x] 2.15 运行确认**红**（新增用例失败、既有用例除 2.14 外全绿）

## 3. 实现
- [x] 3.1 `memory/store.py`：`read()` 增仅关键字 `session_id: str = ""` + 会话过滤分支（与来源排除同点、先于排名）
- [x] 3.2 `context/assembler.py`：`build()` 增 `session_id` 仅关键字参数并透传 `_gather_facts`
- [x] 3.3 `loop/protocol.py`：`LoopContext` 增 `session_id: str = ""`（**不动** `perceive` 协议签名）
- [x] 3.4 `loop/default.py`：`perceive(user_input, *, session_id="")`；`astream` 传；`_compact` 传 `ctx.session_id`
- [x] 3.5 `loop/planner.py`：`_system_prompt` 传 `session_id`；`_skill_hints(task, session_id)` 非空才传第二实参；
      `skill_router` 注解放宽为 `Callable[..., list[SkillHint]]`
- [x] 3.6 `context/compactor.py`：`persist(c, *, session_id="")` + 会话键 id + 条目 `session_id`
- [x] 3.7 `skills/router.py`：`match(..., session_id="")` → `_record_miss(task, session_id)`（会话键 id + 条目归属）
- [x] 3.8 `runtime.py`：`_loop_hooks` 的 `hints` 闭包透传 `session_id` 至 `skill_router.match`
- [x] 3.9 `pet/core/session.py`：两处 `self._loop.run(...)` 补 `session_id=self.session_id`（偏好写入不动）
- [x] 3.10 `orchestration/scheduler.py`：`astream` / `run` 增 `session_id` 仅关键字参数并透传至 `profile.loop.arun`
- [x] 3.11 `ui/api.py`：`run_task` 把 `session_id` 传给 `orchestrator.astream`
- [x] 3.12 四门全绿（直连二进制，**不用** `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/`：`memory-interface.md`（`read` 签名 + 全局层定义）、`context-interface.md`
      （`build` / `Compactor.persist`）、`loop-interface.md`（`LoopContext.session_id`）、`skills-interface.md`
      （`match(session_id=)`）、`pet-mode-interface.md`、`orchestration-interface.md`
- [x] 4.2 `doc/02-modules/{memory,context,loop}.md` 各补一段
- [x] 4.3 `doc/04-testing/test-cases.md`：TC-MEM-* / TC-CTX-* / TC-LOOP-* / TC-NOTE-*
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0107 —— 隔离点、空标识不过滤（承认 fail-open）、归属原则、
      会话键 id、不动协议签名、否决每会话实例 + 已知局限

## 5. 收口
- [x] 5.1 手工归档（delta 合进八个 `doc/openspec/specs/<cap>/spec.md`（9 个需求块） + tick tasks + `shutil.move`
      进 `archive/2026-10-06-0114-session-scoped-memory/`）
- [x] 5.2 `openspec validate --all` 全绿（30 passed / 0 failed，归档后复验）
- [x] 5.3 账本回填（`phase-28.md`：E47 → 已闭 + 判据订正 + 新登记 id 复用残留面；`README.md` 同步）
- [x] 5.4 记忆更新 + 提交（`feat(memory,context,loop,skills,pet,orchestration): …`，一个 Phase 一个 commit）（`feat(memory,context,loop,skills,pet,orchestration): …`，一个 Phase 一个 commit）
