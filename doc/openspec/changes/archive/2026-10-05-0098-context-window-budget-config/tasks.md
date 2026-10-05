# tasks — 上下文窗口与预算三层可配（change 0098）

## 1. 规格（先行）
- [x] 1.1 `specs/loop/spec.md`：MODIFIED「错误与预算控制」（可配 + 派生 + 缺省回落 + 交叉校验）
- [x] 1.2 `specs/configuration/spec.md`：MODIFIED「LLM 提供商配置（必选）」（+`context_window`）
- [x] 1.3 `specs/configuration/spec.md`：ADDED「循环预算配置」（`loop.max_rounds` / `loop.output_reserve`）
- [x] 1.4 `openspec validate 2026-10-05-0098-context-window-budget-config` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_loop_budget_config.py`（新，28 例）：三键三面 / 缺省回落 / 派生边界 / `bool` 非法 /
      交叉校验 / `loop:` 段不进未知告警 / `config set loop.*` 落盘往返 / 组合根装配 + 端到端 `LOOP_LIMIT_EXCEEDED`
      （**合并原 2.1+2.2**：配置面与组合根装配同源于一对 `loop_limits()`，同一文件内聚更清晰；
      `tests/test_configuration.py` 不另加，避免同一行为两处断言漂移）
- [x] 2.2 运行确认**红**（实现前 25 失败 / 1 通过）

## 3. 实现
- [x] 3.1 `configuration/models.py`：`LLMConfig.context_window: int = 0`
- [x] 3.2 `configuration/manager.py`：三条 `ConfigSpec` + `_KNOWN_EXTRA_SECTIONS` 加 `"loop"`
- [x] 3.3 `configuration/manager.py`：两处 `LLMConfig(...)` 构造点（`_build_config` / `_merge_patch`）补字段
- [x] 3.4 `configuration/manager.py`：`_llm_context_window` / `_loop_errors` / `_window_reserve_errors`
      （照 `_circuit_breaker_errors` 形状，经 `_as_number` 排除 `bool`）
- [x] 3.5 `configuration/manager.py`：`validate_schema` 挂两校验器 + 交叉校验
- [x] 3.6 `configuration/manager.py`：`loop_limits() -> tuple[int, int]`（照 `circuit_breaker()` 形状）
- [x] 3.7 `runtime.py`：`max_rounds, token_budget = config.loop_limits()` + 四处 `DefaultLoop(...)` 传参
- [x] 3.8 `entry.py` `_key_to_patch`：接受 `loop.` 前缀；`_merge_patch` 对 `extra.loop` **浅合并**（否则静默丢弃）
- [x] 3.9 运行确认**绿**（28 通过）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/configuration-interface.md`：新键三面表（§2.7）+ `LLMConfig.context_window` +
      `loop_limits()` 接口 + §2.3 已知段补 `loop`
- [x] 4.2 `doc/01-architecture/adr.md`：ADR-0091（派生口径取舍 + `token_used` 粗估的已知边界）+ 映射表行
- [x] 4.3 `doc/04-testing/test-cases.md`：TC-LOOP-06 + TC-CONF-10/11

## 5. 收口
- [x] 5.1 四门全绿（ruff check / ruff format --check / pyright 0/0/0 / pytest 1133 passed），**直连二进制不用 `uv run`**
- [ ] 5.2 手工归档（delta 合入 `specs/{configuration,loop}/spec.md` + `shutil.move` 进 archive）+ `openspec validate --all`
- [ ] 5.3 账本 `coding-plan/phase-19.md` 补行
- [ ] 5.4 记忆更新 + 提交（`feat(configuration): 上下文窗口与预算三层可配（change 0098）`）
