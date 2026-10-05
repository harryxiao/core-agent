# MCP 默认暴露面收窄（mcp-default-exposure-narrowing）

## Why

账本 **B7**（默认暴露面启发式过粗）。规格「工具暴露与白名单」场景「默认最小暴露」已逐字写
「仅暴露只读类工具，写/删除/**敏感**工具默认不暴露」—— 而实现 `server._is_readonly` 只把
「无 `write` 副作用」当作「只读」，**漏掉了「敏感」**。后果：一手实测（生产工具源）默认暴露面含

| 工具 | coeffects | 为什么算「敏感」 |
|---|---|---|
| `tools.delegate` | `[]`（**漏声明**） | 驱动**子 Agent loop**，是跨边界能力（未声明故启发式看不见） |
| `tools.web_fetch` | `network:outbound` | **网络出站**，可外发数据 / 拉取任意 URL |

即：外部客户端（Claude Code / Cursor）默认挂上本 server 即可驱动子 Agent 与出网 —— 与规格
「默认最小暴露」明文相悖。属「**规格要求 X 而实现没有**」（与 E12 / E11② / B3 / B4 / B6 同型）。

## What Changes

- `src/core/mcp/server.py`：默认暴露判据由「无 `write` 副作用」改为**声明的 coeffect 集合为纯本地只读**
  （`⊆ {"filesystem:read"}`，空集=未声明副作用亦视为只读）—— 写 / 进程派生 / 网络出站 / 委托驱动
  一律**默认不出**。函数更名 `_is_readonly` → `_is_default_exposed`。
- `src/core/runtime.py`：给 `tools.delegate` **补声明 coeffect** `agent:delegate`（它本来就在驱动子 loop，
  只是漏声明）并在 resolver 注册；使判据能**结构化**识别委托类工具，无需在 MCP 层硬编码工具名。
- 规格 delta：`mcp` spec **MODIFIED**「工具暴露与白名单」—— 把「默认最小暴露」的判据写实
  （只读**且**无跨边界 coeffect），并补场景「默认面排除跨边界工具」。

## Non-goals

- **不**改成「默认零暴露」（须显式白名单才出）：用户裁决为**收窄**而非全关 —— 纯本地只读工具
  （`tools.file_read` / `tools.list`）仍默认可见，保持「本地挂载即用」的可用性。
- **不**给 `ToolDef` 补风险分级字段（另一候选，未采纳）：现有 coeffect 已足以表达跨边界能力。
- **不**动 `call_tool` 的白名单/命名空间语义（仅默认面判据变化）。

## 风险

- **coeffect 新增可观测**：`tools.delegate` 从此需 `agent:delegate` 可达（组合根已注册 True ⇒ 行为不变）。
  单点：仅在 `runtime.build_runtime` 注册（唯一注册 `tools.delegate` 处）。
- **「空集=只读」的信任面**：留 `coeffects=[]` 的工具默认可见 —— 这是**契约**（未声明副作用即无副作用），
  delegate 的问题是**漏声明**而非契约缺陷；补声明后即被正确识别。假将来插件工具谎报空 coeffect，
  属插件契约问题（另论）。
