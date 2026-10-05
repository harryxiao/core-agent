# tasks — rag 主链路接线（change 0104）

## 1. 规格（先行）
- [x] 1.1 `specs/rag/spec.md`：MODIFIED「本地向量库存储」——默认实现订正为 stdlib `sqlite3`（零三方依赖、
      落盘 `$CORE_STATE_DIR`、跨进程复用）；索引记录向量维度、不一致以结构化错误拒绝；+2 场景
- [x] 1.2 `specs/cli-ops/spec.md`：MODIFIED「运维命令集」——一次性子命令纳入 `rag ingest` / `rag search` /
      `rag ask`；+3 场景
- [x] 1.3 `openspec validate 2026-10-05-0104-rag-mainline-wiring` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_rag.py` 追加：`SqliteVectorStore` put/get/delete/search（复用 `InMemoryVectorStore`
      语义）；**跨实例复用**（同一文件重开装载到已写块）
- [x] 2.2 `tests/test_rag.py` 追加：维度不一致 —— 按 128 维建档后以 64 维 `put`/`search` ⇒ `INDEX_CORRUPT`
- [x] 2.3 `tests/test_rag.py` 追加：`RagService.ingest/search/ask` 三面（含未装配生成器 ⇒ 
      `GENERATION_UNAVAILABLE`；空命中 ⇒ 降级纯 LLM）
- [x] 2.4 新 `tests/test_rag_wiring.py`：`build_runtime` 装配后 `runtime.rag` 可用（未配 `llm.embedding_model`
      ⇒ `HashEmbedder` 降级）；**端到端** ingest → search 命中 → ask 生成（生成器注入 fake provider，
      **不出网**）
- [x] 2.5 新 `tests/test_rag_wiring.py`：CLI 三子命令走 `entry.main(["rag", ...])`（状态目录由 conftest
      的 `CORE_STATE_DIR` 隔离）；`rag search` 不调生成器亦可运行；**结构化错误面**：`rag ask` 在生成器缺失时
      退出码 1 + 提示（monkeypatch `entry.build_runtime`，照 `test_entry.py` 先例），`rag search` 命中维度不一致的
      索引 ⇒ 退出码 1 + 「重建索引」提示（真实可达路径）
- [x] 2.6 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `rag/vector_store.py`：新增 `SqliteVectorStore`（stdlib `sqlite3`；`chunks` 表 + `meta` 表记
      `dim`；BLOB 向量；`put`=UPSERT、`delete`=按 `doc_id`、`search`=进程内余弦 top-k）；`VectorStore`
      抽象补 `record_document` / `document_hash`（两实现同步）
- [x] 3.2 `rag/ingest.py`：`ingest` 合并为 upsert（返回写入块数；hash 判定改由存储侧承载，删 `_hashes`）、
      `refresh` 退化为布尔外壳
- [x] 3.3 `rag/service.py`（新）+ `rag/errors.py`（+`GENERATION_UNAVAILABLE`）+ `rag/__init__.py` 导出
- [x] 3.4 `runtime.py`：`_rag_index_path()` + 装配 `RagService` 挂 `runtime.rag`（embedder 语义优先、
      离线降级 `HashEmbedder`）
- [x] 3.5 `entry.py`：`rag` 命令族（`ingest --doc-id` / `search --top-k` / `ask --top-k`）+ `_HANDLERS`
- [x] 3.6 四门全绿（直连二进制不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/rag-interface.md` §1（`SqliteVectorStore` 落盘/维度口径）/§6/§7（新错误码）
- [x] 4.2 `doc/02-modules/rag.md`：订正失真的「既有 SQLite 生态」；标记主链路已接线
- [x] 4.3 `doc/01-architecture/adr.md`：**ADR-0097**（stdlib sqlite3 而非三方扩展 / 维度一致性拒绝 /
      门面收口 / embedding 语义优先离线降级）+ 末尾映射表行
- [x] 4.4 `doc/04-testing/test-cases.md`：`TC-RAG-11..13` / `TC-CLI-xx`
- [x] 4.5 `coding-plan/phase-22.md` §3 落地状态；`coding-plan/README.md` §2 第 22 行

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/{rag,cli-ops}/spec.md` + tick tasks + `shutil.move`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填
- [x] 5.4 记忆更新 + 提交（`feat(rag): 主链路接线与落盘向量库（change 0104）`）
