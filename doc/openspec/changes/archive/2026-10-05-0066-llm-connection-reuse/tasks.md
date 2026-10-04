# 任务：llm-connection-reuse（E11②）

## 1. 事实核对（先行）

- [x] 1.1 规格逐字核对：`specs/llm-provider/spec.md` Requirement「模型调用可靠性」已声明连接复用 + 场景「连接复用」
      （复用 + 失效自动重建）⇒ **不得订正规格**，须实现
- [x] 1.2 实现核对：`stdlib_provider.py` 三处 `urlopen`（`_post_json` / `_post_embedding` / SSE `_produce`）每次新建连接
- [x] 1.3 生产接线核对：`runtime.py:198/231` 与 `registry.py:47` 默认构造 `StdlibLLMProvider`（无参 ⇒ 走默认传输）
- [x] 1.4 用户裁决：**实现（stdlib 零依赖）** → 变更目录 `schema: spec-driven + skip_specs: true`

## 2. 测试先行（红 → 绿）

- [x] 2.1 `tests/test_llm_provider_reuse.py`（9 例，真实本地 `http.server` 桩计 accept 数）：先红（`http_pool` 不存在）
- [x] 2.2 覆盖：复用 1 条连接 / embeddings 共用 / 按 origin 分键 / 失效重建 / 429 归一 / 拒绝连接归一 /
      3xx 与代理回落 / SSE 走同一传输层

## 3. 实现

- [x] 3.1 新增 `src/core/llm_provider/http_pool.py`：`HTTPTransport` 协议 + `HTTPConnectionPool`
      （线程本地按 origin 复用 / 代理与 3xx 回落 / 失效重建一次 / 读尽才归还 / 非 2xx 转 `HTTPError`）
- [x] 3.2 `stdlib_provider.py`：三处传输改走 `self._transport.send(...)`；新增 `transport=` 注入接缝；
      `map_http_error` 补 `(OSError, http.client.HTTPException) → LLMNetworkError`（顺序在 `URLError` 之后）
- [x] 3.3 `tests/test_llm_provider.py`：8 个 mock `urlopen` 用例平移为注入 `_FakeTransport`（断言口径不变）

## 4. 文档

- [x] 4.1 ADR-0064 + 变更追踪表行
- [x] 4.2 `doc/03-interfaces/llm-provider-interface.md` §3.1（传输层与连接复用 / 回落 / 重建 / 错误口径）
- [x] 4.3 `doc/02-modules/llm-provider.md` §3.6 + §4 错误处理表 + §5 ADR 行
- [x] 4.4 `doc/04-testing/test-cases.md` TC-LLM-06 去掉「连接复用未实现，未覆盖」

## 5. 验证与收尾

- [x] 5.1 四门全绿（ruff / format / pyright / pytest 805 passed）
- [x] 5.2 `openspec validate 0066-llm-connection-reuse` → 手动归档 → `openspec validate --all`
- [x] 5.3 账本 E11② 行关闭 + §3 E11 段 + §9 步骤 9
- [x] 5.4 `coding-plan/README.md` 同步
- [x] 5.5 提交 `feat(llm-provider): 传输层连接复用与失效重建（change 0066）`
