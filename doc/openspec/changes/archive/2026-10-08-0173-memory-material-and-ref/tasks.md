# Tasks: memory-material-and-ref（记忆材料与引用语义）

> 顺序：**规格已先行**（§1）⇒ 测试先行（§2 红）⇒ 实现（§3）⇒ 门禁（§4）⇒ 文档/台账/记忆（§5）⇒ 提交（§6）。
> 每项可独立验收；四门禁**直连二进制、禁 `uv run`**。

## 1. 规格（已完成）

- [x] 1.1 `specs/memory/spec.md` delta：MODIFIED「结构化实体抽取（关键事实）」+2 Scenario
- [x] 1.2 `specs/loop/spec.md` delta：MODIFIED「执行循环」+3 Scenario
- [x] 1.3 `proposal.md` / `design.md`
- [x] 1.4 `openspec validate 2026-10-08-0173-memory-material-and-ref` ⇒ valid

## 2. 测试先行（红态证据）

- [x] 2.1 `tests/test_memory_ref_shape.py`：非 `coeffect:` `ref` + 正常取值 ⇒ 取值保留、不落 `ref:` 标签
- [x] 2.2 同文件：非 `coeffect:` `ref` + 密钥形态取值 ⇒ 整条丢弃 + warn（含实体名、不含取值）
- [x] 2.3 同文件：`coeffect:<名称>` 形态 ⇒ 取值 `<redacted>` + 落 `ref:` 标签（既有行为回归）
- [x] 2.4 同文件：`looks_like_secret` / `redact_secrets` 公开判据（命中替换、非命中逐字不变、多 pattern 同现）
- [x] 2.5 `tests/test_loop_memory_sequence.py`：有工具轮 ⇒ 轨迹条目 + 行动序列条目（轨迹条目逐字不变）
- [x] 2.6 同文件：纯文字回复轮 ⇒ 不另立条目
- [x] 2.7 同文件：行动序列含密钥形态串 ⇒ 子串为 `<redacted>`
- [x] 2.8 同文件：`steps` 缺省 ⇒ 只写轨迹条目（向后兼容回归）
- [x] 2.9 同文件：超长序列 ⇒ 条目 ≤ `_MAX_MEMORY_ENTRY`
- [x] 2.10 跑红：`git stash push -u -- src` ⇒ 上述用例全红（留证据）⇒ `git stash pop`

> 落地说明：§2.1–2.4 的引用形态与公开判据用例**并入既有** `tests/test_memory_key_facts.py`（追加 `# ---- 引用形态判据 + 公开脱敏判据 ----` 段落）—— 与既有脱敏用例同处一文件，便于「旧判据回归 + 新判据」并读；未另立 `test_memory_ref_shape.py`。红态证据形态为**收集期 ImportError**（`_MAX_MEMORY_ENTRY` / `looks_like_secret`），见 §5.3 记录。

## 3. 实现

- [x] 3.1 `extract.py`：`_looks_secret` → 公开 `looks_like_secret`；新增 `redact_secrets`、`_is_coeffect_ref`
- [x] 3.2 `extract.py`：`_PROMPT_HEAD` 收紧（`ref` 只允许 `coeffect:<名称>`，否则留空）
- [x] 3.3 `extract.py`：`scrub_key_fact` 第 2 步改 `if not _is_coeffect_ref(ref): ref = ""`
- [x] 3.4 `core/memory/__init__.py`：导出 `looks_like_secret` / `redact_secrets`
- [x] 3.5 `loop/default.py`：新增 `_MAX_MEMORY_ENTRY`（既有 `[:2048]` 一并改用）
- [x] 3.6 `loop/default.py`：`remember` 增仅关键字 `steps=()` ⇒ 另立 `loop.steps.<trace_id>` 条目（逐行脱敏 + 有界）
- [x] 3.7 `loop/default.py`：调用点传 `steps=_action_steps(ctx)`
- [x] 3.8 `loop/protocol.py`：`Loop.remember` 声明同步
- [x] 3.9 跑绿：§2 全部用例通过

## 4. 四门禁（直连二进制）

- [x] 4.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 4.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 / 0 / 0**
- [x] 4.4 `.venv/bin/pytest -q` ⇒ 全绿（基线 **1979**，记增量）

## 5. 文档 / 归档 / 台账 / 记忆

- [x] 5.1 `doc/01-architecture/adr.md`：**ADR-0164** + 变更追踪行
- [x] 5.2 `doc/02-modules/memory.md` §3.4、`doc/03-interfaces/memory-interface.md` §3、`doc/02-modules/loop.md` §记忆 相关段
- [x] 5.3 `doc/04-testing/test-cases.md` **§86**（TC-MEM-REF，含红态证据）
- [x] 5.4 `coding-plan/known-risk.md` §1 新行 **E110** + §3 ADR-0164 局限行
- [x] 5.5 手工归档：delta 并入 canonical（`memory` / `loop`）⇒ `mv` 到
      `doc/openspec/changes/archive/2026-10-08-0173-memory-material-and-ref/` ⇒
      `openspec validate --all` ⇒ **31/0**
- [x] 5.6 记忆：`MEMORY.md` 指针行 + `coding-plan-leftover-walkthrough.md` 追加 change `0173` 节

## 6. 提交

- [x] 6.1 单次提交 `fix(memory): 记忆材料与引用语义（change 0173 / ADR-0164 / 台账 E110）`
      （排除 `config.yaml` / `.claude/settings*.json` / `uv.lock` / `coding-plan/*.md` 等禁提项）

## 7. 端到端目视（用户）

- [ ] 7.1 跑一次含工具调用的会话 ⇒ `memory.jsonl` 出现 `loop.steps.<trace_id>` 条目（内容为可读行动序列、
      无明文密钥）；`loop.<trace_id>` 条目内容与变更前同形
- [ ] 7.2 触发压实（≥10 轮）⇒ 新抽出的 keyfact 中，正常取值**不再**被抹成 `<redacted>`；
      自造 `ref` 不再出现在 `ref:` 标签里
