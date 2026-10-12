# Tasks 0232

- [x] 规格 delta：`configuration`「LLM 提供商配置（必选）」MODIFIED ＋ 2 Scenario；
      `llm-provider`「模型调用可靠性」MODIFIED ＋ 1 Scenario
- [x] 测试先行：新 `tests/test_llm_reliability_config.py`（红）
- [x] `models.py`：`LLMConfig` 加 `timeout` / `max_retries`
- [x] `manager.py`：`_CONFIG_SPECS` ＋2；`_build_config` / `apply_change` 两处接线；
      新增 `_llm_timeout` / `_llm_max_retries`
- [x] `runtime.py`：注入主 `StdlibLLMProvider`
- [x] 测试转绿（17）；连带修 `test_rag_wiring.py` / `test_phase13.py` 桩签名
- [x] 四门禁：`ruff check` ✓ / `ruff format --check` ✓ / `pyright`（无参，0-0-0）✓ /
      `pytest -q` **2597 passed**
- [x] 反证 A / B1 / B2（复原 md5 逐字节同）
- [x] `openspec validate --all`（归档期 32 passed）→ 归档（31 passed）
- [x] 台账：ADR-0221、E168、测试节 §144、接口文档 §2.11、模块文档 §3.3
- [x] 提交
