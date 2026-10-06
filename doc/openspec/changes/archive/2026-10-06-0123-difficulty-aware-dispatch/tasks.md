# tasks — 难易度感知的同波次调度策略（change 0123 / phase-29 change C：E50）

## 1. 规格（先行）
- [x] 1.1 `specs/orchestration/spec.md`：ADDED「难易度感知的调度策略」——`difficulty` 三档 + 缺省 `medium` +
      集合外归一；`off`（缺省）⇒ 逐字并发 / `difficulty` ⇒ 含 hard 波次串行；依赖拓扑仍为硬约束；
      `max_concurrency` 由组合根注入（不依赖构造缺省）
- [x] 1.2 同 delta：**7** 个 Scenario（缺省并发 / 含 hard 串行 / 无 hard 并发 / 缺省与归一 /
      **大小写与空白归一** / 持久化往返 / 配置注入）—— 收口时补第 5 条（`"HARD"` / `" hard "` 归一律）
- [x] 1.3 `specs/orchestration/spec.md`：MODIFIED「子任务拆解」——仅订正 `LLM 拆解产出子任务 DAG` 场景的字段
      枚举（+`difficulty`），Requirement 正文逐字保留
- [x] 1.4 `specs/configuration/spec.md`：ADDED「编排调度配置」——两个配置键 + 三面 + 缺省 + 校验期拒绝
- [x] 1.5 用户裁决记录：§4①「缺省 = 全串行」**字面订正**为「缺省沿用拓扑并发」（保留其「不得把不可靠信号
      直连并发开关」的用意）——已写入 proposal「缺省语义」节 + ADR-0116 决策①
- [x] 1.6 `openspec validate 0123-difficulty-aware-dispatch` 通过

## 2. 测试（先红）
- [x] 2.1 `tests/test_orchestration_difficulty.py`（新）：
      - 缺省（不传策略）⇒ 并发峰值 = `max_concurrency`（与 `test_run_fanout_bounded_concurrency` 同型）
      - `policy=difficulty` + 波次含 `hard` ⇒ 并发峰值 **1**、按优先级降序逐个
      - `policy=difficulty` + 波次全 `easy/medium` ⇒ 并发峰值 = `max_concurrency`
      - `hard` 与 `easy` 混编在**不同波次**（依赖分隔）⇒ 只有含 hard 的波次串行
      - 非法 `difficulty` 取值（模型输出 `"HARD!"` / `"1"` / `""` / `"中"` / **非字符串**）⇒ 归一 `medium`
      - `plan_to_dict` / `plan_from_dict` 往返保留 `difficulty`；**缺键**的旧 dict ⇒ 回落 `medium`
      - 构造器策略取值非法 ⇒ `OrchestrationError(INVALID_DISPATCH_POLICY)`
- [x] 2.2 同文件：LLM planner 输出含 `difficulty` 时被解析（打桩 `LLMProvider` 的 `acompletion`）
- [x] 2.3 `tests/test_orchestration_config.py`（新，`test_loop_budget_config.py` 同型）：两键三面解析
      （CLI/env/yaml）+ 优先级链；缺省 `off` / `4`；`max_concurrency` ∈ `0`/`-1`/`2.5`/`abc`/`true` 与
      `difficulty_policy` ∈ `fast`/`parallel`/`OFF`/`1` ⇒ 校验失败（**阻断启动**）
- [x] 2.4 组合根接线用例：`runtime` 装配的 `TaskScheduler` 取配置值（非构造缺省）
- [x] 2.5 红：以上用例在实现前**必失败** —— 实测 **34 failed**（红态用例数；后补大小写/非字符串
      参数化至 **44** 例）：`Subtask(..., difficulty=…)` 与 `TaskScheduler(..., difficulty_policy=…)`
      均为 unexpected keyword（`TypeError`），`ConfigManager.orchestration_*()` 不存在（`AttributeError`）

## 3. 实现
- [x] 3.1 `orchestration/models.py`：`Subtask.difficulty: str = "medium"` + `DIFFICULTY_LEVELS` /
      `normalize_difficulty()`（单一真源，去空白 + 小写）/ `__post_init__` 归一；
      `plan_to_dict` / `plan_from_dict` 同改（缺键回落 `medium`）
- [x] 3.2 `orchestration/errors.py`：新错误码 `INVALID_DISPATCH_POLICY`（构造器策略取值非法）
- [x] 3.3 `orchestration/scheduler.py`：`__init__` 增 keyword-only `difficulty_policy: str = "off"`（校验取值）
      + `_wave_limit(subtasks)`（`off` ⇒ `max_concurrency`；`difficulty` 且含 `hard` ⇒ `1`）+ `_fan_out` 用其建
      `Semaphore`（**其余逐字不动**）
- [x] 3.4 `orchestration/planner.py`：`_DECOMPOSE_SYSTEM` 增 `difficulty` 输出要求；`_parse` 读取并归一
- [x] 3.5 `configuration/manager.py`：两个 ConfigSpec + `orchestration_difficulty_policy()` /
      `orchestration_max_concurrency()` 两个独立访问器 + `_orchestration_errors()` 校验（挂进 `validate`）
- [x] 3.6 `runtime.py`：装配 `TaskScheduler` 时传 `max_concurrency=config.orchestration_max_concurrency()` 与
      `difficulty_policy=config.orchestration_difficulty_policy()`

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests` —— All checks passed
- [x] 4.2 `.venv/bin/ruff format --check src tests` —— 352 files already formatted
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` —— **0 errors, 0 warnings, 0 informations**
- [x] 4.4 `.venv/bin/pytest -q` —— **1589 passed**（基线 1545 ⇒ 新增 44 例，两文件全绿）
- [x] 4.5 `openspec validate --all` —— 归档前 **31 passed / 0 failed**（30 + 在途 change 0123）；
      归档后 **30 passed / 0 failed**
- [x] 4.6 端到端（离线）：临时 `config.yaml` 置 `orchestration.difficulty_policy=difficulty` 经 `build_runtime`
      装配**真** runtime，打桩拆解器（1 hard + 2 easy 同波次）+ 记录并发的子 Agent loop ⇒
      时间线 `+hard-1,-hard-1,+easy-1,-easy-1,+easy-2,-easy-2`、峰值 **1**、三子任务全 `ok`（不触网）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/{orchestration,configuration}/spec.md`
      （orchestration：订正 LLM 场景字段枚举 + 追加 ADDED 块；configuration：插在「循环预算配置」之后、
      「功能开关」之前，与 change `0098` 先例同位）
- [x] 5.2 `shutil.move` 进 `doc/openspec/changes/archive/2026-10-06-0123-difficulty-aware-dispatch/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：ADR-0116 + 变更追踪行（缺省语义订正 / 波次级粒度 / 依赖拓扑硬约束 /
      归一 vs 校验口径 / `max_concurrency` 接线）
- [x] 6.2 `doc/03-interfaces/orchestration-interface.md`（`Subtask.difficulty` 字段 + `difficulty_policy`
      构造参 + §2.3 策略语义 + 新错误码 + 拆解 prompt 字段枚举）
- [x] 6.3 `doc/03-interfaces/configuration-interface.md`（§2.8 两个配置键 + `config set` 白名单**不含**
      `orchestration.` 的据实说明）
- [x] 6.4 `doc/02-modules/orchestration.md`（§3.4 增「同波次调度策略」段）；
      `doc/02-modules/configuration.md` **无键表** ⇒ 无需同步
- [x] 6.5 `doc/04-testing/test-cases.md`：新 TC 节 **TC-DIFF-01 ~ 13** + 端到端离线冒烟说明
- [x] 6.6 `coding-plan/phase-29.md` §3.1 / §6 表 C 行 / 状态行（**编辑落盘不提交** —— 含他人未提交 §0.5 改动）+
      `coding-plan/README.md` 三处（**随提交**）

## 7. 提交
- [ ] 7.1 单次提交：`feat(orchestration,configuration,runtime): 难易度感知的同波次调度策略（change 0123）`
- [ ] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`coding-plan/phase-21-findings.md`、
      `src-tauri/Cargo.lock`、`node_modules/`、`frontend/dist/`
