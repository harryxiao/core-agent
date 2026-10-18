# 任务 — 0289 PA-09 D/E

## 1. 规格

- [x] 1.1 `specs/configuration/spec.md`：MODIFIED「LLM 提供商配置（必选）」，加入
      `embedding_required` 子项、三个 Scenario。
- [x] 1.2 `specs/memory/spec.md`：MODIFIED「温度分层检索」，补 required 的启动阻断与
      「调用期仍降级」边界、两个 Scenario。
- [x] 1.3 `openspec validate 2026-10-18-0289-pa09-d-e` 与 `validate --all` 全绿。

## 2. 代码（先写测试）

- [x] 2.1 `tests/test_semantic_default.py`：三面解析（yaml/env/cli）、缺省 false、非法值
      阻断、required + 空有效模型阻断（错误不含 endpoint）、required + 显式/推导模型通过、
      热更新校验。
- [x] 2.2 `src/core/configuration/models.py`：`LLMConfig.embedding_required: bool = False`。
- [x] 2.3 `src/core/configuration/manager.py`：ConfigSpec、`_llm_embedding_required`、
      `_build_config`、`_merge_patch`、`validate_schema` 检查。
- [x] 2.4 `tests/test_memory_graph_benchmark.py`：20 链多跳基准 + 流水线覆盖度量；
      扁平 recall@5 = 0、模拟轻图 recall@5 = 1.0。
- [x] 2.5 `tests/test_semantic_benchmark.py`：概念 embedder；词法 vs 语义 recall/MRR。

## 3. 文档

- [x] 3.1 `doc/03-interfaces/configuration-interface.md`：§2.14 增
      `embedding_required` 行与语义边界。
- [x] 3.2 `doc/03-interfaces/memory-interface.md`：检索降级段补 required 例外与基准指针。
- [x] 3.3 `doc/01-architecture/adr.md`：ADR-0279（D 不建图 / E 可选强制 / 基准局限）。
- [x] 3.4 `coding-plan/known-risk.md`：E225 行 + §3 ADR-0279 局限索引。
- [x] 3.5 `doc/04-testing/test-cases.md`：§201 语义基准、§202 多跳/覆盖基准。
- [x] 3.6 `coding-plan/Pending-Arbitration.md`：PA-09 D/E 收口记录与裁决。

## 4. 门禁

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`（基线 3201 + 新增）
- [x] 4.5 反证 3/3（cp 到 /tmp，禁 `git checkout`；复原后 md5sum 一致）。
- [x] 4.6 端到端：required 开 + 未知端点 ⇒ CLI 启动失败且错误不含 endpoint；required 关
      ⇒ 既有词法提示不变。
- [x] 4.7 `openspec archive -y 2026-10-18-0289-pa09-d-e` 后再跑 `validate --all`。
- [x] 4.8 仅暂存本 change 路径并提交。
