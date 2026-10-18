# 任务 — 0293 供应商输出上限能力适配与终止原因归一

## 1. 规格

- [x] 1.1 `specs/llm-provider/spec.md`：MODIFIED「请求侧输出上限按预留注入」——能力表查询、
      向下钳制、字段选择、未收录逐字不变；新增三个 Scenario。
- [x] 1.2 同 delta：MODIFIED「流式增量携带终止原因」——截断别名归一为 `length`，
      非截断取值原样；新增两个 Scenario。
- [x] 1.3 `specs/configuration/spec.md`：ADDED「已知模型能力告警」（预留超上限 / 已知不支持
      reasoning_effort，仅告警不阻断；未知模型不告警）。
- [x] 1.4 `openspec validate 2026-10-19-0293-provider-output-capability` 全绿。

## 2. 测试先行

- [x] 2.1 新建 `tests/test_model_capabilities.py`：族命中与顺序、大小写、未收录 `None`、
      钳制（低于/等于/高于/未知/None）、字段选择（`max_tokens` / `max_completion_tokens`）。
- [x] 2.2 `tests/test_llm_provider.py`：`gpt-4-turbo` + 8192 ⇒ `max_tokens: 4096`；
      `o1` + 8192 ⇒ `max_completion_tokens: 8192` 且无 `max_tokens`；未收录模型逐字不变。
- [x] 2.3 同文件：非流式 `finish_reason=MAX_TOKENS`、流式 `max_tokens` ⇒ `length`；
      `stop` / 未知值 / 缺失口径逐字不变。
- [x] 2.4 `tests/test_loop_budget_config.py`：预留超已知上限 ⇒ 校验通过且告警；
      已知不支持 `reasoning_effort` ⇒ 告警；未收录模型无能力告警。

## 3. 实现

- [x] 3.1 新建 `src/core/configuration/model_capabilities.py`（`ModelCapability` 表 +
      `known_capability` / `effective_output_tokens` / `max_tokens_field`）。
- [x] 3.2 `src/core/llm_provider/stdlib_provider.py`：`_build_body` 钳制 + 字段选择；
      `_map_response` / `_map_chunk` 终止原因别名归一。
- [x] 3.3 `src/core/configuration/manager.py`：`validate_schema` 追加能力告警。

## 4. 文档与台账

- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0283（能力表、钳制、归一、被拒方案、局限）。
- [x] 4.2 `coding-plan/known-risk.md`：E229 行 + ADR-0283 局限索引。
- [x] 4.3 `doc/04-testing/test-cases.md`：§206。
- [x] 4.4 `doc/02-modules/llm-provider.md`、`doc/03-interfaces/llm-provider-interface.md`：
      请求上限适配与终止原因归一。
- [x] 4.5 `doc/03-interfaces/configuration-interface.md`：能力告警口径。

## 5. 门禁

- [x] 5.1 `.venv/bin/ruff check src tests`
- [x] 5.2 `.venv/bin/ruff format --check src tests`
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright`（0 errors, 0 warnings）
- [x] 5.4 `.venv/bin/pytest -q`（3254 → **3270 passed**，绿色）
- [x] 5.5 反证 3/3（cp 到 /tmp，禁 `git checkout`；复原后 md5sum 一致）：
      去掉钳制/字段选择 ⇒ 2.2 两例红；去掉别名归一 ⇒ 2.3 两例红（非截断保留例仍绿）；
      去掉能力告警 ⇒ 2.4 两例红（未收录模型例仍绿）。
- [x] 5.6 `openspec validate --all` 全绿（**32 passed, 0 failed**，含本 change）。
- [x] 5.7 真实冒烟：GLM-5.3（未收录上限、字段 `max_tokens`）单轮请求仍成功（`exit=0`，
      reply `1+1 等于 2。`）。

## 6. 收尾

- [x] 6.1 `openspec archive -y 2026-10-19-0293-provider-output-capability`
      （归档后 `validate --all` 31 passed, 0 failed）
- [x] 6.2 仅暂存本 change 路径与实现/测试/文档路径并提交（不 `git add -A`）。
