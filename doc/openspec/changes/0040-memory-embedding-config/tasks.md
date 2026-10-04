# Tasks: 记忆 embedding 来源配置与装配

## 1. 规格先行

- [ ] 1.1 `specs/configuration/spec.md` delta：MODIFIED「LLM 提供商配置（必选）」（可选
      `embedding_model` 子项 + 未设置回退词法场景）
- [ ] 1.2 `openspec validate 0040-memory-embedding-config` 全绿

## 2. 契约与接口文档

- [ ] 2.1 `03-interfaces/configuration-interface.md`：`llm` 段增可选 `embedding_model`

## 3. 测试先行（先红）

- [ ] 3.1 `tests/test_phase13.py`：配置 `llm.embedding_model` 时 `memory._embedder` 为
      批量可调用（伪造 provider，不触网）；未配置时为 `None`
- [ ] 3.2 `tests/test_phase13.py`：embedding 不可达时启动不阻断、检索降级词法

## 4. 实现

- [ ] 4.1 `configuration/models.py` + manager：`LLMConfig.embedding_model: str = ""`
      （入 ConfigSpec 单一真源，暴露面 hidden）
- [ ] 4.2 `runtime.py`：`embedding_model` 非空时构造独立 provider → `LLMEmbedder` →
      `batch_embed` → `MemoryStore(embedder=...)`；密钥经 `resolve_secret` 注入并登记脱敏

## 5. 门禁

- [ ] 5.1 ruff check / format 全绿
- [ ] 5.2 pyright（src）0 error
- [ ] 5.3 `.venv/bin/pytest -q` 全绿
- [ ] 5.4 `openspec validate --all` 全绿 → 归档（delta 合并进 specs/ + 同步
      `04-testing/test-cases.md` 追踪号）
