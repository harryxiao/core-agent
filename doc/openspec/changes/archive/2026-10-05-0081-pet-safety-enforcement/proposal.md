# 0081 — pet 安全边界强制执行（受限探索工具集 + 越界阻断/通知）

## 为什么（账本 E25）

规格 `pet-mode` 三条款**明文要求强制**，实现**注入但不消费**：

| 规格 | 现行实现 |
|---|---|
| R11「Exploration Toolset」：**受限探索工具集（只读优先）**，清单可配置、需授权 | `Explorer` 在 `runtime.py:661` 构造并注入 `PetSession`（存 `_explorer`）—— **零读取点** |
| R12「Pet Safety Bounds」：越界/不可逆 ⇒ **阻断 + 暂停 + 通知主人** | `SafetyBounds` 同样只注入不消费（`_safety`） |
| 「Pet Session Runtime Wiring」：经组合根注入…受限探索工具集、安全边界 | 注入完成，但**从未生效** |

**更严重一层**（一手核实）：宠物**跑在主 loop 上** —— `runtime.py:660` `pet_loop = cast(LoopPlugin, loop)`
⇒ 宠物的一次唤醒可调用主 loop 的**全部**工具（`tools.file_write` / `tools.code_run` / `tools.web_fetch`…），
安全边界与受限清单在生产**无一处在路径上**。

**第三层事实**：两套词汇表**与真实工具对不上** —— `Explorer` 默认清单 = `file.read`/`web.search`/`memory.read`，
`SafetyBounds` 默认不可逆集 = `file.write`/`git.push`/`rm`；仓库真实 id 是 `tools.file_read` /
`tools.file_write` / `tools.code_run` / `tools.web_fetch`… ⇒ **即使今天接线也一条都匹配不上**。

## 用户裁决（三项）

1. **专属 loop 真强制**（而非最小前置校验、而非保持开放）；
2. **「越界即暂停」= 本轮阻断 + 通知主人，会话保持 `ACTIVE`**（不转 yielding/退避 ——
   生产无 `resume()` 调用方，转态即**永久楔死**）；
3. **订正为真实 id**（`Explorer`/`SafetyBounds` 与真实工具 id 对齐，同批订正其单测与文档）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/runtime.py` | pet 块：`_pet_tools()`（**受限 ToolProvider**：只注册白名单内真实工具）+ `_pet_loop()`（**专属 `DefaultLoop`**，middlewares = 安全中间件）⇒ 宠物唤醒**不再**走主 loop |
| `src/core/pet/safety/safety.py` | 词汇表订正为**真实工具 id**；「只读优先」由前缀启发式改为**只读白名单**；`target` 可为空（空则不做半径判定） |
| `src/core/pet/safety/middleware.py`（新） | `build_safety_middleware(bounds, notify)`：before 接缝判越界 ⇒ 终止 Action（本轮终止）+ 通知主人 |
| `src/core/pet/explore/explorer.py` | 默认清单 `file.read`/`web.search`/`memory.read` → **`tools.file_read`**；`available()` 成为受限 provider 的**白名单真源** |
| `src/core/pet/core/layers.py` | `SafetyLayer.check(op, target="")` 协议签名（`target` 可省） |
| `doc/openspec/specs/pet-mode/spec.md` | **MODIFIED**「Pet Safety Bounds」：钉死「暂停」实现口径（本轮终止、会话 `ACTIVE`）+ 新增场景「越界阻断不楔死会话」 |

**两个机制的职责划分**（避免两处真源打架）：

- **Explorer 白名单 = 授权（R11）** —— 决定宠物**能看见/能调用**哪些工具（未注册 ⇒ loop 结构化拒绝，fail-closed）；
- **SafetyBounds 边界（R12）** —— 决定即便工具已注册，该动作是否**越界**（只读优先 / 不可逆 / 爆炸半径）。

## 明确不做

- **不注入 constraints 熔断链**：宠物流量不应与主/神兽 loop **共享熔断态**（单实例 `ConstraintsChain` 会让宠物
  的坏调用影响主线）；宠物 loop 只挂安全中间件。
- **不新增配置键**：白名单/半径/不可逆集**构造面可注入**即满足「可配置/可控」（R11/R12 未要求配置面）；
  加 `ConfigSpec` 键属 YAGNI（且会牵出配置段设计，见 E20①/E24 的前车之鉴）。
- **不给宠物技能路由**（`skill_router=None`）/ 不接 JEV 语义路由：pet 任务是闲逛探索，与技能结晶链路无关。
- **不改 `Explorer.run()`**：它是抽象层占位（`真实工具执行由宿主注入`），真实执行走 pet loop 的工具调用。
