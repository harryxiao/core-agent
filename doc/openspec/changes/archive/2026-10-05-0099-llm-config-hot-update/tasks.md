# tasks — LLM 配置热生效与落盘持久化（change 0099）

## 1. 规格（先行）
- [x] 1.1 `specs/ui/spec.md`：MODIFIED「LLM API 可配置」（字段扩展 + 热生效 + 原子落盘 + 回滚）
- [x] 1.2 `openspec validate 2026-10-05-0099-llm-config-hot-update` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_llm_config_hot_update.py`（新）：保存 ⇒ yaml 落盘 + 重开进程可见 /
      运行中 loop 上限实际变化 / 非法值拒绝且**原值不被破坏** / 写盘失败 ⇒ 内存与 yaml 均不变
- [x] 2.2 `tests/test_ui.py` 追加：`apply_llm_config` 协议调用 + 无 config 时纯内存
- [x] 2.3 `tests/test_serve.py` 追加：`PUT /llm-config` 带 `context_window`/`output_reserve`；
      `GET` 回显 `context_window`/`token_budget`/`max_rounds`（并补 400 反例）
- [x] 2.4 运行确认**红**

## 3. 实现
- [x] 3.1 `core/loop/protocol.py`：`@runtime_checkable LimitsConfigurable`（仅 `set_limits`）+ 导出
- [x] 3.2 `core/loop/default.py`：`DefaultLoop.set_limits(*, max_rounds=None, token_budget=None)`
- [x] 3.3 `configuration/manager.py`：`write_patch` 改原子提交（tmp + `os.replace`）
- [x] 3.4 `ui/errors.py`：`UI_LLM_CONFIG_INVALID`
- [x] 3.5 `ui/api.py`：`apply_llm_config(...)` + `get_loop_limits()`
- [x] 3.6 `ui/fastapi_serve.py`：`PUT`/`GET /llm-config` 字段扩展
- [x] 3.7 运行确认**绿**

## 4. 文档
- [x] 4.1 `doc/03-interfaces/ui-interface.md`：`/llm-config` 字段口径 + 热生效/落盘
- [x] 4.2 `doc/04-testing/test-cases.md`：新用例编号（TC-UI-*）
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0092（两入口分离 + 原子写 + Protocol 热生效）

## 5. 收口
- [x] 5.1 四门全绿（直连二进制不用 `uv run`）
- [x] 5.2 手工归档 + `openspec validate --all`
- [x] 5.3 账本 `coding-plan/phase-19.md` 补行
- [x] 5.4 记忆更新 + 提交（`feat(ui): LLM 配置热生效与落盘持久化（change 0099）`）
