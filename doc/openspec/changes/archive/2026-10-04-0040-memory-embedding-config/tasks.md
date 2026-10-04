# Tasks: 记忆 embedding 来源配置与装配

## 1. 规格先行

- [x] 1.1 `specs/configuration/spec.md` delta：MODIFIED「LLM 提供商配置（必选）」（可选
      `embedding_model` 子项 + 未设置回退词法场景）
- [x] 1.2 `openspec validate 0040-memory-embedding-config` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/configuration-interface.md`：`llm` 段增可选 `embedding_model`

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_phase13.py`：配置 `llm.embedding_model` 时 `memory._embedder` 为
      批量可调用（伪造 provider，不触网）；未配置时为 `None`
- [x] 3.2 `tests/test_phase13.py`：embedding 不可达时启动不阻断、检索降级词法

## 4. 实现

- [x] 4.1 `configuration/models.py` + manager：`LLMConfig.embedding_model: str = ""`
      （入 ConfigSpec 单一真源，暴露面 **advanced**——非密钥，与 `im.gateway` 同级；
      修正原稿误写的 hidden，hidden 仅用于密钥类）
- [x] 4.2 `runtime.py`：`embedding_model` 非空时构造独立 provider → `LLMEmbedder` →
      `batch_embed` → `MemoryStore(embedder=...)`；密钥经 `resolve_secret` 注入并登记脱敏

## 5. 门禁

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 归档（delta 合并进 specs/）
      —— `04-testing/test-cases.md` **无 TC-CFG 章节**（configuration 能力未入表，0039 亦未加），
      本次不单独新增章节以免破坏既有结构；追踪仍由 configuration spec 场景承担
