# Design 0199 — Procedural 端到端门禁

## 1. 缺口定位（P3）

批次 `Phase 37` 的 `0196`~`0198` 是**两条独立 change**（0196 只改执行线程、0197 改采集面、
0198 改发布面），各自只有**单元锚** ⇒ 无「真编排器 + 真组合根」视角的锚：

| 链路 | 既有锚 | 缺口 |
|---|---|---|
| 完成回调 → 任务级提炼 | 无（0196 只测线程） | **未接**真编排器 |
| 任务级提炼 → 技能库 | `test_task_sop.py`（纯函数） | 纯函数**未接**真组合根 |
| 质量门 → 发布 | `test_skills.py`（单测门分支） | 单测**未接**真提炼器实例 |

## 2. 设计

### 2.1 真材实料（只桩两个外部面）

| 面 | 真 / 桩 | 说明 |
|---|---|---|
| 组合根 | **真** | `build_runtime(ConfigManager(yaml_path=…))` |
| `TaskScheduler` | **真** | 保留真实例与真注入的 `on_done=_finalize` |
| `MemoryStore` | **真** | 步序走 `runtime.memory.write("L2", …)`（真实写入路径） |
| 模型接缝 | 桩 | `runtime.llm.completion` → 固定 SOP 正文 |
| 子 Agent 执行单元 | 桩 | `LoopPlugin.astream` → 固定终态 + 确定性 trace_id |
| decomposer 的 planner | 桩 | 固定两子任务（桩的是**外部面**，`SubtaskDecomposer` 本身仍真） |

> `TaskScheduler._decomposer` / `._router` 是**编排器的外部依赖**（planner 是模型面、loop 是执行面）
> ⇒ 桩它们等于桩模型与执行单元，**不**桩被测链路。

**刻意的非桩项**：`_finalize`（组合根闭包）、任务级 `SopExtractor` 实例、`compose_task_steps`、
`_steps_lookup`、`SkillLibrary`、质量门接线 —— 这五处正是 0197/0198 的改动面。

### 2.2 四条锚

1. **任务过程 → 技能资产**（`test_task_done_registers_task_level_sop`）：先跑 2 次断言**不入库**
   （防空过），第 3 次 ⇒ 入库一条 `instructions` = 桩模型文本、`status="active"`、
   `task_types[0].startswith("task::")`。
2. **质量门在真链路上生效**（`test_rejecting_gate_blocks_registration_in_real_chain`）：
   `judgment` 段开 JEV + `monkeypatch.setattr("core.runtime.sop_gate_with", 拒绝门)` ⇒
   `pytest.warns(UserWarning, match="质量门未过")` **恰一次**（清组 ⇒ 不重复触发）+ 零入库。
3. **无门 ⇒ 发布不变**（`test_absent_gate_publishes_unchanged`）：无 `judgment` 段 ⇒
   `gate=None` ⇒ 照常入库。与锚 2 成对 ⇒ 二者差异**只**在门。
4. **过程取自记忆步序、非 `reply`**（`test_sop_prompt_carries_memory_steps_not_subtask_reply`）：
   捕获真实投喂提炼器的 prompt ⇒ 含 `loop.steps.<trace>` 条目正文（`读取输入` / `校验结论`）、
   **不含** 子 Agent 回复 `_REPLY`。

### 2.3 反证（门禁非空过的证明）

端到端门禁最大风险是**空过**（无论实现如何都绿）。逐条**临时回退**并确认转红（实测记录）：

| # | 回退手法 | 实测结果 |
|---|---|---|
| ① | `_finalize` 的 `sop_task_extractor.observe(...)` → `pass` | 锚 1/2/3/4 **全红**（链路断开） |
| ② | 任务级实例去 `namespace="task"` | **仅**锚 1 红（`task_types[0]` = `quarterly report run`，无 `task::`） |
| ③ | 任务级实例 `gate=None` | **仅**锚 2 红（`Emitted warnings: []` ⇒ 门没跑） |
| ④ | `compose_task_steps` 的 `lookup(...)` → `[outcome.reply]` | **仅**锚 4 红（prompt 含 `子任务回复-不应进提炼prompt`） |

复原后 4 绿 ⇒ 每条锚**均能咬住**其目标行为。

### 2.4 桩漂移的两处坑（实测踩到并已解决）

- **状态机身份是 `task_id`**：同一编排器实例复用已 `DONE` 的 `task_id` 会抛
  `INVALID_TRANSITION: done → verifying`。⇒ 每次 `run` 用新 `task_id`（归组键取自**目标**，
  与 `task_id` 无关 ⇒ 样本仍累加同组）。
- **子任务 trace_id 需确定性**：桩 `LoopPlugin` 按**目标文本**映射 trace_id（`{"run alpha": "t1", …}`）
  ⇒ 与 `loop.steps.<trace_id>` 条目一一对应；兼容波次内并发（同波次两子任务并发扇出）。

## 3. 规格落点

**规格中性**（零行为改动、零 `src/` 改动）⇒ 无 spec delta；`.openspec.yaml` `skip_specs: true`
（先例 `0156` / `0189` / `0195`）。

## 4. 验证

- 四门禁（直连二进制）；`openspec validate` → 手工归档（规格中性 ⇒ 仅移入 `archive/`）。
- `git diff --stat src/` **为空**（零 `src/` 改动，本 change 的核心承诺）。
