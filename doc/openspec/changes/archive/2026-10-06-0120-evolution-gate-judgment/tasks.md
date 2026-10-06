# tasks — 结晶面门的判定面：真实 review + 真实运行时测试（change 0120 / phase-31 切片 2：G1 + G2）

## 1. 规格（先行）
- [x] 1.1 `specs/evolution/spec.md`：MODIFIED「验证门」——**review 的生产者**（结构化审查者 +
      组合根注入、evolution 不 import LLM 抽象、判定 fail-closed、未过即 fail-fast 不跑测试）
- [x] 1.2 同 delta：MODIFIED 同 Requirement——**运行时测试的生产者**（门禁命令**单一真源**
      `GATE_COMMANDS` **按标记派生**子集；结晶面跑 `lint` + `test` 并**明文写出为什么**；
      `typecheck` / `build` 不进结晶面；标记命中未注册门名 ⇒ 派生失败；任一门未过 ⇒ 门未过）
- [x] 1.3 同 delta：MODIFIED 同 Requirement——**未注入生产者 ⇒ 不得放行** + **门的面（诚实）**
      （结晶面 = 仓库级回归门 ≠ 实施面候选专属验证，两门不同源不互替）+ **执行面**（子进程、
      组合根注入；「跑不起来」与「跑失败」同归为该门未通过、不外抛）
- [x] 1.4 `openspec validate 0120-evolution-gate-judgment` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_evolution_gate_judgment.py`（新）：**子集按标记从单一真源派生** ——
      `crystallization_gates() == ("lint", "test")`、顺序随真源、命令字符串仍只有一份
- [x] 2.2 同文件：**交付面门禁不入结晶面** —— `typecheck` / `build` 不在子集里（子集 ∪ 二者 = 全集）
- [x] 2.3 同文件：**标记漂移 fail-closed** —— 标记命中 `GATE_COMMANDS` 里不存在的门名 ⇒ `CiCdError`
- [x] 2.4 同文件：**标记只带门名不带命令** —— 标记键 ⊆ 真源键、值不是门禁命令字符串
- [x] 2.5 同文件：**review 的生产者** —— prompt 带候选自洽性判据面（kind / target / delta + 判定词表）
- [x] 2.6 同文件：**review 判定 fail-closed** —— 词表外 / 空 / 含糊输出一律 `False`（参数化表）；
      `review_with`：PASS ⇒ 真、不可解析 ⇒ 假、调用抛异常 ⇒ 假（不外抛）
- [x] 2.7 同文件：**运行时测试的生产者** —— 只跑传入的标记子集、结果按门名收集且值恒布尔；
      某门未过 ⇒ 该门 `False`；执行面抛异常 ⇒ 该门 `False`（fail-closed、不外抛）
- [x] 2.8 同文件：**未注入生产者不得放行**（G1/G2 根因）—— 缺省 `Validator()` ⇒ `passed=False`、
      理由含「未注入」；只注入一半判据 ⇒ 仍不放行；空测试集 ⇒ 不放行（`all({})` 为真即 G2 成因）
- [x] 2.9 同文件：**两判据都过才过** —— review 拒绝 ⇒ 门未过且**不跑**子进程门禁（fail-fast）；
      任一门禁未过 ⇒ 门未过且 `test_results` 据实标出
- [x] 2.10 同文件：**端到端 `rejected`（G5 锚点）** —— 装真判据后 `run_cycle` 在未过门时确实返
      `status="rejected"`（不再恒 `pending`）；门过 ⇒ 进留出评测（无基准 ⇒ `frozen`，非 `rejected`）
- [x] 2.11 同文件：**生产装配走真 review + 真门禁子集** —— `build_runtime` 后 `run_cycle` 实际
      跑 `["lint", "test"]`（模型面与子进程面打桩，装配面不打桩）；模型端点不可用 ⇒ `rejected`
      且门禁**零调用**
- [x] 2.12 同文件：**口径版本递增** —— `GATE_CALIBER == 2`（落地为 `>= 2`，避免钉死未来递增）
- [x] 2.13 回归改判：既有依赖「缺省 `Validator()` 即通过」的用例（`test_evolution_pending.py` /
      `test_evolution.py` / `test_phase14.py` / `test_phase15.py` / `test_evolution_wiring.py` /
      `test_evolution_attribution.py` / `test_evolution_gate_data.py`）改为**显式注入**过门替身
      （读数器仍是真门）；改判理由写进 ADR；`test_evolution_gate_data.py` 的**生产形状**用例
      须同时打桩模型面与门禁执行面（**不得**在生产用例里真跑 `pytest` 子进程）

## 3. 实现
- [x] 3.1 `src/core/ci_cd/pipeline.py`：`CRYSTALLIZATION_GATE_MARKS: dict[str, str]`（门名 → 可读
      理由，**不复制命令字符串**）+ `crystallization_gates() -> tuple[str, ...]`（按真源顺序派生；
      标记命中未注册门名 ⇒ `CiCdError(GATE_FAILED)`，fail-closed）；`src/core/ci_cd/__init__.py` 导出
- [x] 3.2 `src/core/evolution/validator.py`：`build_review_prompt(candidate)`（自洽性判据面 + 判定
      词表）、`parse_review(text) -> bool`（词表外一律 `False`）、`review_with(llm_text)`（调用异常 ⇒
      `False`）、`run_gate_tests(*, run_gate, gates)`（逐门跑、值恒 `bool`、异常 ⇒ 该门 `False`）、
      本地 `GateOutcome` 结构 Protocol（不新造跨层依赖）；`Validator`：缺省**未注入 ⇒ 不得放行**、
      review 未过 **fail-fast**（不跑测试）、空测试集不通过
- [x] 3.3 `src/core/evolution/models.py`：`GATE_CALIBER = 1` → **2**（判定面口径变更；递增规则
      docstring 同步）
- [x] 3.4 `src/core/runtime.py:596`：`validator=Validator(review=review_with(_llm_text),
      tests=run_gate_tests(run_gate=_run_gate, gates=crystallization_gates()))`
      （复用既有 `_llm_text` 接缝与 `gate_executor` 执行面，**不新造依赖边**）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1503 passed ⇒ 改判 + 新增后 1535 passed 全绿）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/evolution/spec.md`（逐文件对齐既有排版：
      `#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0120-evolution-gate-judgment/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0113**（决策 + 判据订正 3 条：判定面位置 = `run_cycle`
      冷路径与阻塞代价 / 缺省 fail-closed 与切片 1 同型 / 结果载体 `dict[str,bool]`）+ 已知局限：
      冷路径同步跑子进程门禁（reopen：冷路径异步化）／review 质量取决于模型与词表／仓库级门禁与
      候选内容无关（实施面另有其门）／生产未配模型 ⇒ 候选恒 `rejected`（有意）+ 变更追踪表行
- [x] 6.2 `doc/03-interfaces/evolution-interface.md`（`Validator` 生产者签名、`GateReport`、删陈旧
      「生产 `Validator`/`Evaluator` 仍是恒通过桩」注）；`doc/02-modules/evolution.md` §3.3
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行（TC-EVGJ-01..05）
- [x] 6.4 `coding-plan/phase-31.md`：状态 → 切片 2 已落地（change `0120` / ADR-0113）+ §1 表
      G1/G2/G5 措辞同步 + §7 下一步；`coding-plan/README.md`
- [ ] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [ ] 7.1 单次提交：`feat(evolution,ci_cd,runtime): 结晶面门判定面真实化（真实 review + 真实运行时测试）（change 0120）`
- [ ] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-29.md`（**他人**未提交改动）、`coding-plan/phase-3-prompt.md`、
      `AI-SoftwareEngineer-4.md`、`coding-plan/phase-21-findings.md`、`src-tauri/Cargo.lock`、
      `node_modules/`、`frontend/dist/`
