# Tasks 0276 — 记忆检索延迟修复

> 验证目标：1 万条语料 `read` 中位 <100ms（参考机）、recall@5 / MRR@5 仍为 1.000；
> `estimate_tokens` 输出逐位不变；缓存复用 / 失效 / 有界均有确定性测试。

## 1. 规格与测试先行

- [x] 1.1 `doc/openspec/changes/.../specs/memory/spec.md`：MODIFIED 基准 req + ADDED 词元缓存 req。
- [x] 1.2 `tests/test_token_estimate.py`：补 CJK 区间边界等价（每区间上下界/界外/混合）。
- [x] 1.3 `tests/test_memory_token_cache.py`（新）：复用（分词调用计数）/ 内容变更失效 / 有界淘汰。
- [x] 1.4 `tests/test_memory_scale_benchmark.py`：p95 上限 5000 → 1000。

## 2. 实现

- [x] 2.1 `src/core/tokens.py`：`estimate_tokens` 改预编译正则 `sub` 计数；删除 `_is_cjk`。
- [x] 2.2 `src/core/memory/relevance.py`：`build_lexical_stats` 增可选 `token_cache`（内容校验）。
- [x] 2.3 `src/core/memory/store.py`：`_token_cache` + `_TOKEN_CACHE_MAX = 20_000` + FIFO 裁剪；
      `read` 传入缓存。

## 3. 验证

- [x] 3.1 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 3.2 `pytest -q tests/test_memory_scale_benchmark.py -s`：记录新中位/p95；确认 recall/MRR 1.000。
- [x] 3.3 反证：① 不传缓存 ⇒ 复用用例红；② 去内容校验 ⇒ 失效用例红；复原 `md5sum` 同。
- [x] 3.4 `openspec validate --all` 全绿后归档。

## 4. 文档与登记

- [x] 4.1 ADR-0266（含实测表、反证、局限）。
- [x] 4.2 台账 E212（`coding-plan/known-risk.md`）。
- [x] 4.3 `doc/04-testing/test-cases.md` §188；`doc/02-modules/memory.md` 延迟段更新；
      `doc/00-product/requirements.md` CORE-NFR-PERF2 标注改为已达标。
- [x] 4.4 `coding-plan/Pending-Arbitration.md`（PA-09 B 后续：延迟修复已闭，C 可进）。
- [x] 4.5 单次提交 `feat(memory): ...` + Co-Authored-By。
