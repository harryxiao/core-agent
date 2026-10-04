# 设计：llm-connection-reuse（E11②）

## 1. 接缝选型：为什么在 **transport** 而不是包一层 Provider

| 方案 | 代价 | 否决理由 |
|---|---|---|
| 新增 `PooledProvider(LLMProvider)` 包住 StdlibLLMProvider | 复制协议映射 / 重试 / 降级 / SSE 组装 | 抽象层级错位：复用是**传输**问题，不是 provider 语义问题；且「协议映射」会被实现两遍 |
| 在 `_make_request` 里改 URL（http.client 直连拼装） | 请求构建与传输耦合 | 请求构建（`_make_request`）与传输（谁发、怎么发）本就该分层；测试替身也无处可插 |
| **`transport.send(req, timeout)` 注入接缝（采纳）** | 需把 3 处 `urlopen` 改成 1 个上下文管理器 | 恰是 DI 边界（ADR-0040）：换连接策略 / 测试替身均不改 provider 本体；既有 8 个 mock `urlopen` 用例平移到 `_FakeTransport`，**断言口径不变** |

## 2. 关键决策（详见 ADR-0064）

1. **线程本地所有权**：`threading.local()` 存空闲连接，**无锁**。provider 的同步传输本就在工作线程上跑
   （`asyncio.to_thread` / `run_in_executor`），同线程连续调用即复用 —— 覆盖真实负载形态（对话轮次、
   RAG 索引循环）而不引入并发风险。
2. **代理回落**：`proxy_for(url)` 非空 ⇒ `urlopen`。`http.client` 不读代理环境变量，`urlopen` 会；
   回落 = 代理环境下退化为原行为（**不产生回归**），无代理（多数部署）时走复用。
3. **3xx 回落**：`http.client` **不跟随重定向**；若自己实现跟随会改变既有语义（`urlopen` 会跟随），
   故交回 `urlopen`。
4. **失效重建恰一次**：捕获 `RemoteDisconnected` / `BadStatusLine` / `ConnectionResetError` / `BrokenPipeError`
   ——**只在复用的连接上**（新连接就失败 ⇒ 真故障，直接归一为领域异常，不重发）。
5. **错误口径**：非 2xx → `urllib.error.HTTPError`（带 code/reason/headers）⇒ `map_http_error` 的状态码映射
   **零改动**生效；`http.client` 连接层异常无 urllib 包装 ⇒ 在 `map_http_error` 补
   `(OSError, http.client.HTTPException) → LLMNetworkError`，与 `URLError` 同层级（可重试）。
   **顺序关键**：`HTTPError ⊂ URLError ⊂ OSError`，状态码分支必须在前。
6. **读尽才归还**：`resp.isclosed()` 为真才回池；SSE 提前停止（未读尽）⇒ 关闭丢弃，防半读流污染下次请求。

## 3. 测试设计：为什么必须用**真实 socket**

既有 `test_llm_provider.py` mock 掉 `urlopen` —— 连「有没有第二条连接」都**看不见**（mock 无 socket）。
本变更的断言对象是**连接本身**，故新用例起本地 `ThreadingHTTPServer`（`protocol_version = "HTTP/1.1"`，
在 `setup()` 里计 accept 数）：

| 用例 | 断言（规格场景的可证伪形式） |
|---|---|
| `test_two_calls_reuse_one_connection` | 两次 `acompletion` → 服务端 `requests == 2` 且 `connections == 1`（场景「连接复用」） |
| `test_embedding_shares_the_same_connection` | chat + embeddings 同一连接（RAG 索引循环的收益形态） |
| `test_pool_keys_connections_by_origin` | 两 host 各一条、回到首个 origin 仍复用（不串用） |
| `test_connection_rebuilt_after_server_side_close` | 服务端答完即静默关连接（模拟空闲超时）→ 第二次调用仍成功且 `connections == 2`（场景「连接失效时自动重建」） |
| `test_error_status_maps_to_domain_error` | 429 → `LLMRateLimitedError`（http.client 路径同口径） |
| `test_connection_failure_maps_to_network_error` | 连 127.0.0.1:1 → `LLMNetworkError`（不落裸 `OSError`、可重试） |
| `test_redirect_falls_back_to_urlopen` | 302 → 交回 `urlopen`（决策 3） |
| `test_proxy_configured_falls_back_to_urlopen` | 有代理 ⇒ 不入池（决策 2） |
| `test_stream_completes_over_transport` | SSE 走同一传输层且内容正确（流未读尽 ⇒ 不复用） |

**确定性**：断言「同一线程内的复用」⇒ 协程在**单工作线程**的事件循环里跑
（`loop.set_default_executor(ThreadPoolExecutor(max_workers=1))`），不依赖线程池调度时序；
本地桩端口随机（`("127.0.0.1", 0)`），不占用固定端口。

## 4. 已知边界（登记，不在本变更）

- 池化粒度 **线程 × origin**：多线程下各持一条连接（无锁的代价，决策 1）。
- 空闲连接由**服务端**超时关闭；客户端不做主动保活（保活定时器需要后台线程，属投机）。
- 代理环境退化为原行为（无复用）—— 决策 2 的作用域边界。
