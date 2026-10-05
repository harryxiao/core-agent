# design — MCP 默认暴露面收窄（change 0076 / 账本 B7）

## 一手事实

生产工具源下，未配置白名单时 `MCPServer.list_tools` 的**默认暴露面**（旧判据 `_is_readonly` =
coeffects 不含 `write`）：

| 工具 | coeffects | 旧判据 | 应否默认出 |
|---|---|---|---|
| `tools.file_read` | `filesystem:read` | 出 | ✅ 出（纯本地只读） |
| `tools.list` | `[]` | 出 | ✅ 出（未声明副作用） |
| `tools.web_fetch` | `network:outbound` | **出** | ❌ 不出（网络出站） |
| `tools.delegate` | `[]` | **出** | ❌ 不出（驱动子 loop） |
| `tools.file_write` / `file_patch` | `filesystem:write` | 不出 | 不出 |
| `tools.code_run` | `process:spawn`,`filesystem:write` | 不出 | 不出 |
| `tools.install` / `uninstall` | `filesystem:write` | 不出 | 不出 |

两个**跨边界**工具穿过启发式：`web_fetch`（有 `network:outbound` 却没被判）与 `delegate`
（`coeffects=[]` **漏声明**）。

## 决策

### D1 判据改为「安全 coeffect 白名单」而非「无 write」黑名单
```
默认出 ⟺ set(tool_def.coeffects) ⊆ {"filesystem:read"}
```
- **空集通过**（`tools.list` 保留）：coeffect 是工具的**副作用契约** —— 未声明即承诺无副作用，
  信任声明一致（P1 无特权核心 / P3 声明式副作用面）。`delegate` 的问题是**漏声明**，非契约缺陷。
- 任何含 `filesystem:write` / `process:spawn` / `network:outbound` / `agent:delegate` 者**默认不出**。
- 函数更名 `_is_readonly` → `_is_default_exposed`（旧名已不达意）。

**已否决**：`_is_readonly` + 硬编码 `{"tools.delegate"}` 拒绝集 —— 会让 MCP 层**认识具体工具名**
（跨层耦合），且对下一个「漏声明的跨边界工具」再犯同样的错。

### D2 `tools.delegate` **补声明** coeffect `agent:delegate`
`delegate` 驱动子 Agent loop，本就是跨边界能力，只是 `coeffects=[]` 没写。补上后：
- 默认面判据**结构化**识别委托类工具（D1 的空集信任仍成立 —— 它不再「无声明」）；
- 组合根 `runtime.build_runtime` 注册 `agent:delegate=True`（唯一注册 `tools.delegate` 处），
  故**运行期行为不变**（coeffect 可解析），新增的是**可见性**。
- 命名沿 `domain:action` 惯例（`filesystem:read` / `network:outbound` / `process:spawn`）。

**已否决**：给 `ToolDef` 补风险分级字段（另一候选）—— 现有 coeffect 已能表达跨边界能力，
再引一层分级是重复真源。

### D3 不动白名单语义
显式 `--whitelist` 仍可开放任意工具（含跨边界者）—— 收窄只改**默认面**，用户显式声明即授权。

### D4 兼容性代价
- 破坏面：仅 `MCPServer.list_tools` 的默认判据 + `tools.delegate` 的 coeffect 声明。
- 白名单路径、`call_tool` 越权语义、命名空间、二级代理过滤**均不变**。
- 既有用例无默认面含这两个工具的断言（`test_mcp.py` / `test_mcp_server_stdio.py` 的工具源仅有
  file_read/file_write）⇒ 零改动即绿；`test_phase13.py` 的 id 集合断言不受 coeffect 影响。

## 转出

无。
