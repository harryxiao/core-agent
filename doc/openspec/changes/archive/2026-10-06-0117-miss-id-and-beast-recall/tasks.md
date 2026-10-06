# tasks — 未命中记录 id 唯一化 + 神兽可召回自身轨迹（change 0117 / phase-30 分支 A）

## 1. 规格（先行）
- [x] 1.1 `specs/skills/spec.md`：MODIFIED「技能路由」——未命中记录 id **内容派生**（跨进程不覆盖）+
  同任务重复**幂等** + 诊断窗口**有界**（3 条新 Scenario）
- [x] 1.2 `specs/memory/spec.md`：ADDED「来源前缀排除与放行（读取面）」——`allow_source_prefixes` 为排除面
  的**例外面**，缺省空逐字不变、无排除时无效果（4 条 Scenario）
- [x] 1.3 `specs/beast-mode/spec.md`：MODIFIED「Independent Sub-Agent with Shared Capability」——神兽
  **自身**命名空间可召回、**他兽**仍排除、主侧封存逐字不动（2 条新 Scenario）
- [x] 1.4 `openspec validate 0117-miss-id-and-beast-recall` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_skills.py`：**跨进程重启不覆盖** —— 两个 `SkillRouter` 共享同一 `MemoryStore`
      （模拟重启，计数器归零），同会话两条不同任务的未命中条目**同时存在**
- [x] 2.2 同文件：**重复未命中同一任务幂等** —— 同会话同任务两次 ⇒ 只有一条条目
- [x] 2.3 同文件：**诊断窗口有界** —— 500 次未命中后 `len(router.misses)` 远小于 500 且 `[-1]` 为最近一条
- [x] 2.4 `tests/test_memory_namespace.py`：`read(..., exclude=("beast.",), allow=("beast.qinglong",))`
      ⇒ 含自身、**不含他兽**、含主线；`allow` 单独给出（无排除）⇒ 语义逐字不变
- [x] 2.5 同文件：`DynamicAssembler.with_allow_source_prefixes(...)` 派生实例放行自身且**不改**原装配器
- [x] 2.6 `tests/test_beast_wiring.py`：**生产接线** —— 召唤后的神兽 loop 真实装配器检索**含自身**
      `beast.qinglong` 条目、**不含** `beast.baihu`；主 loop 装配器仍**不含**任何 `beast.*`

## 3. 实现
- [x] 3.1 `src/core/skills/router.py`：`from hashlib import blake2b` + `_MISS_WINDOW` 常量；`_record_miss`
      id 改 `f"skills.miss.{key}.{blake2b(task.encode('utf-8'), digest_size=8).hexdigest()}"`；
      `misses` **原地裁剪**（`del self.misses[:n]`，保持 `list` 类型与对象身份）
- [x] 3.2 `src/core/memory/store.py`：`read` 增 `allow_source_prefixes: tuple[str, ...] = ()`；
      排除判定改「命中排除**且**未命中放行」（同点：排名与预算之前）
- [x] 3.3 `src/core/memory/protocol.py`：`read` 签名补 `session_id`（对齐 change `0114` 的实现漂移）+
      新增 `allow_source_prefixes`（同一方法签名面）
- [x] 3.4 `src/core/context/assembler.py`：构造参数 `allow_source_prefixes`（缺省空）+ `_gather_facts` 透传
      + `with_allow_source_prefixes(*prefixes)` 派生新实例（配置逐字继承，放行面替换）
- [x] 3.5 `src/core/runtime.py`：`_beast_loop` 的 `planner` 装配器改
      `assembler.with_allow_source_prefixes(beast.agent_id)`；**主装配器 `:559-567` 逐字不动**

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1470 passed ⇒ 新增用例后应全绿）
- [x] 4.5 `openspec validate --all`（归档前后各一次，须 30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并三份 delta 进 canonical（`doc/openspec/specs/{skills,memory,beast-mode}/spec.md`，
      逐文件对齐既有排版：`#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0117-miss-id-and-beast-recall/`

## 6. 文档与账本
- [x] 6.1 `doc/03-interfaces/memory-interface.md`（`read` 签名 + 放行面）；`context-interface.md`（装配器参数/派生）
- [x] 6.2 `doc/03-interfaces/skills-interface.md`（未命中记录 id 口径）；`beast-mode-interface.md`（自身可召回）
- [x] 6.3 `doc/02-modules/{memory,skills,context}.md` 对应段落
- [x] 6.4 `doc/04-testing/test-cases.md` 增 TC 行
- [x] 6.5 `doc/01-architecture/adr.md`：**ADR-0110**（决策 + 已知局限）+ 变更追踪表行
- [x] 6.6 `coding-plan/phase-30.md`：状态 → 已闭、§0/§3/§4 回填、§6 下一步；
      `coding-plan/phase-28.md` §7/§8 指针；`coding-plan/README.md` 状态列

## 7. 提交
- [x] 7.1 单次提交：`feat(skills,memory,context,beast): 未命中记录 id 唯一化 + 神兽可召回自身轨迹（change 0117）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-3-prompt.md`、`AI-SoftwareEngineer-4.md`、`src-tauri/Cargo.lock`、
      `node_modules/`、`frontend/dist/`
