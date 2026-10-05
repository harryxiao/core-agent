# design — pet 安全边界强制执行（change 0081 / 账本 E25）

## 决策 1：专属 loop 而非共享主 loop（用户裁决）

**问题**：`pet_loop = cast(LoopPlugin, loop)`（主 loop）⇒ 宠物可调用全部工具，边界不在路径上。

**三个选项**：

| 选项 | 评价 |
|---|---|
| ① **专属 loop**（受限 provider + 安全中间件）✅ | R11 由**注册面收窄**落地（未注册 = 结构化拒绝，fail-closed by construction，且模型**看不到**越界工具 ⇒ 不会白试）；R12 由 before 中间件落地。先例：`_agent_loop` / `_beast_loop` 都是专属 loop |
| ② 最小前置校验（`wake()` 里判 goal 文本） | 越界是**动作**属性而非 prompt 文本属性；工具调用仍不受约束 ⇒ R12 名存实亡 |
| ③ 保持开放 | 规格三条款持续与实现背离（本账本正在清的正是这类漂移） |

**取舍**：① 收窄了宠物可用工具面 —— 这**正是** R11 的本意（「受限探索工具集」），但属**行为变更**，
故在 proposal/接口/模块文档三处显式登记。

**共享 `pet_loop` 而非每宠一 loop**：现状即共享（多宠共享主 loop），本变更不动这一层；多宠隔离由
会话/任务队列/人格承担（规格 Multi-Pet Management），loop 无 per-session 态。

## 决策 2：「越界即暂停」= 本轮终止 + 会话 ACTIVE（用户裁决）

- 终止 Action（`Action(args={"reply": ...})`，`tool_id=""`）⇒ `act()` 直返、`observe()` 见 `data["reply"]` 即
  `ctx.finish()` —— 与既有 `decline()` 路径**同构**（loop 的既有机制，无需新增语义）；
- **不调 `suspend()`**（`_yielding=True`）：生产无任何 `resume()` 调用方 ⇒ 一次越界即**永久楔死**；
- **不转 `BACKOFF`**：把「用户授权外的动作」当故障，语义过重且需重建会话。

规格原文「宠物暂停」的读法由此**钉死进规格**（本 change 的 MODIFIED requirement），避免将来
「规格说暂停、代码没暂停」再记一条账。

## 决策 3：词汇表订正为真实工具 id（用户裁决）

| 旧（发明） | 新（真实） |
|---|---|
| `Explorer`：`file.read` / `web.search` / `memory.read` | **`tools.file_read`**（`memory` 非工具；`tools.list` 不在本组合根 provider 内，故不入默认清单） |
| `SafetyBounds` 不可逆集：`file.write` / `file.patch` / `git.push` / `rm` | **`tools.file_write` / `tools.file_patch` / `tools.code_run` / `tools.install` / `tools.uninstall`** |
| 只读判据：`op.startswith("read")` 前缀启发式 | **只读白名单**（`readonly_ops`，默认 `{"tools.file_read"}`）—— 真实 id 无 `read` 前缀，启发式必然失效 |

**半径**：`allowed_prefixes` 语义不变，但**仅当 `target` 非空**时判定（真实工具的参数名各异 ⇒
middleware 从 `args` 里取 `path`/`file`/`url`/`target` 首个命中键作为 target；取不到就不判半径，
避免「无目标的动作一律被半径拒绝」）。组合根缺省传 `[Path.cwd()]`（宠物只在**启动目录**内探索 ——
R12「爆炸半径可控」的最小可用默认），可构造面替换。

**保留的规则顺序**：不可逆 → 只读 → 半径（先判最不可逆的），与原实现一致。

## 已否决

- **共享 `ConstraintsChain`**（熔断）给 pet loop：单实例熔断态会被宠物流量污染，且本变更无此需求；
- **`SafetyBounds` 加 `ConfigSpec` 配置键**：构造面可注入即够（R11/R12 未要求配置面），新增键会牵出配置段语义；
- **注册 `tools.list`/`install_tools` 给宠物**：那是插件管理面，非「探索」；不进默认白名单；
- **在 middleware 里做 id→发明 op 映射**（用户裁决否）——两套词汇表长期并存，映射表即新真源；
- **给宠物 loop 接技能路由 / JEV 路由**：pet 任务与技能结晶链路无关（`skill_router=None`）；
- **每宠一 loop**：现状共享，多宠隔离已由会话维度承担，改动无收益。

## 转出

无新开账本行。余下 pet 侧零消费项已各自成行：**E26**（`surprise()`/`MicrotaskRunner` 零调用方，
用户裁决保持开放）、**E27**（`IMGateway` 零生产装配，需真实平台凭证）、**E28**（无宿主驱动 `wake()`）。
本变更后 E28 的语义更新：**一旦被宿主驱动，唤醒不仅投递通知（E16），且受安全边界约束（本变更）**。
