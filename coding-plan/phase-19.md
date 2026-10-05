# Phase 19 — 排期遗漏账本（Phase 18 收口后的未排期项）

> **定位**：Phase 0–18 已全部落地归档后，本文件是「**已记档、但从未排期**」项的单一账本，供后续按优先级重开。**本文件不含新能力设计**——每项只记「现象 / 根因 / 关闭动作 / 触发前提」，细则仍在各自的 spec / interface / ADR 原文。
> **基线**：`feat/phase0-base` @ `f898768`；669 tests 绿；`openspec validate --all` 29 specs 全绿、**无活跃变更**；最近四个 change `0044`–`0047` 均已归档。
> **走查来源（2026-10-04）**：对 `coding-plan/` 全部 31 份文档 + `doc/` 关键文档（requirements / retro / data-model / adr / 各 interface / specs）做了全量巡读，并对每条自陈「deferred / 未接 / 缺口」反向核对 `src/` 调用点与 `doc/openspec/changes/archive/` → 分三档落账：**明确未做**（E/B/C 类）、**疑似已做未勾**（G 类）、**无法判定**（F 类）。
> **与 `debug-gaps.md` 分工**：`debug-gaps.md` 是「开始真机调试前」的缺口快照（基线 `60d9724` @ 2026-10-01，其 §2.2 多数已修）；本文件收其后的**新增遗留** + 长期未排期项，C 类只引用不重列。
> **规则**：本 Phase 是**记账**不是**里程碑**；重开任一项须按其所属 capability 走常规 SDD 流程（spec delta → 测试 → 实现 → 四门 → 归档），并在此表标注「已关闭」。

---

## 0. 结论

- **无任何一项阻塞核心回路**：669 tests 覆盖的回路（记忆读写/压实/固化/遗忘、技能提炼/路由/迭代、进化四阶段 + HITL + 自动溶解）在生产路径上均已接通。
- **A3 全闭（skills 半边 change `0050`，evolution 半边 change `0051`）**；**A5 + 本次新增发现 A10 已于 change `0051` 关闭**（冷路径驱动面 = loop 节拍 + `evolve run`；观察窗口落盘 + 批次成功率采样；ADR-0054）。
- **A2+E2（会话维度）已于 change `0048` 关闭**（标识透传 + `compact` 接真 + 按会话读取）；**A1 已于 change `0049` 关闭**（收尾维护节拍 + `memory maintain`）。**A 类已全清**（**A6 已随 change `0063` 关闭**、**A9 已销账**——规格明文认可现状、**A8 已销账**——后端单锁已满足规格操作性保证、**A11 已销账**——规格明文「逐条打分」+ 成本触发条件未成立，均零变更）。
- **唯一需要 ADR 裁决的重开项是 B 类（Phase 12 MCP）** —— **B1 的 client 侧（stdio 传输 + 安装分流 + 消费侧安全接线）已于 change `0054` 关闭**（ADR-0057），余 http 会话 1 行后续（B2；**服务端 stdio B3 已于 change `0073` 关闭**、**白名单配置 B5 已于 change `0071` 关闭**、**CLI 接线 B4 已于 change `0074` 关闭**、**标准 envelope B6 已于 change `0075` 关闭**、**默认暴露面收窄 B7 已于 change `0076` 关闭**、**远端错误码映射 B8 已于 change `0077` 关闭**）；E 类中曾判定有真实行为影响的 **E1（constraints 熔断）** 与 **E2（per-session）** **均已关闭**（E2 → change `0048`；E1 → change `0052`），其余为「接线缺失」。
- **A4 已于 change `0055` 关闭**（候选 `candidate_id` 稳定身份 + 门禁/评测随候选落盘为一条记录 + `core-agent evolve pending|confirm|reject` 操作面；high 风险候选由操作面签发审批单；ADR-0058）。
- **E1 已于 change `0052` 关闭**（constraints 熔断按 `tool_id` 接入 loop：结果侧观察者 + 按工具熔断 + 只计执行失败；ADR-0055）；核销时一并**订正**了账本原「校验空转」的说法（校验实由工具层承担）。
- **E7（契约基线漂移）+ E8（配置校验三处缺口）已于 change `0056` 关闭**（密钥引用同口径 + `permission.mode` 枚举校验 + 基线文档订正；ADR-0059），E8 第 5 条转出为 **E18**。
- **A6（观察窗口覆盖语义）+ E13（`parse_output` 零调用方判定）+ E19（durability 过度承诺）已于 change `0063` 关闭**（纯文档、规格中性：已知语义登记 + 「有意不接线」判定 + 过度承诺订正）；E19 的裁决 = **订正文档承认现状**（该承诺规格里从来没有，静默降级会掩盖磁盘满）。
- **E17（pet 无后台 daemon）已于 change `0065` 关闭 —— 判定「规格未要求」**：一手核实三件事 ① 规格无 daemon / 调度线程条款（Lifecycle 只写「**每次唤醒**…同步薄壳逐次执行」，Yielding 明写让行模型是「**同步 + 锁（RLock）**」）；② 文档自述「逐次执行**不常驻**」——「后台自治调度」是文档层过度承诺（与 E19 同型）；③ `core-agent pet <verb>` 是**一次性进程**（激活 → 打印 → 退出），进程内线程**必随进程结束** ⇒ 在那里 daemon 化是**错误解法**，唯一可承载常驻驱动的宿主是 `ui serve` 长驻进程。用户裁决**规格中性收口**：接口 §5 / 模块 §4 登记「`wake()` 由**宿主**驱动、内核不自建调度线程」，零代码。
- **E18（`extra` 未知配置段）已于 change `0064` 关闭**（ADR-0063）：用户裁决**仅告警**（WARN 不阻断，兼容既有自定义段；硬拒会改变既有接受行为）——`ValidationResult.warnings` 产出 + `load()` 发出（stdlib `warnings`，零接线）；已知段白名单**由 `_CONFIG_SPECS` 派生**（单一真源，新增 Spec 自动进白名单）；口径**只到顶层段名**（子键未知不判，属各能力 schema 义务）。
- **E11（LLM 可靠性）已于 change `0060` + `0066` 全关闭**：① 用例侧 —— 重试/超时/降级/断流 9 例**一次全绿**，`src/` 零改动（实现本就正确，缺的是验证，change `0060`）；② **连接复用已实现**（change `0066` / ADR-0064）—— **关键判定：这是「规格要求 X 而实现没有」**（规格「模型调用可靠性」正文与场景「连接复用」逐字要求 keep-alive 复用 + 失效自动重建）⇒ **改代码向规格靠拢，不订正规格**（与 E12 同型，对比 E17/E19 的「文档过度承诺」型）。实现：`http_pool.HTTPConnectionPool` 线程本地按 origin 复用 keep-alive（无锁）+ 失效重建恰一次 + 代理/3xx 回落 `urlopen` + 非 2xx 转 `HTTPError`（既有状态码映射零改动）+ 读尽才归还；`map_http_error` 补连接层 `OSError`/`HTTPException` → `LLMNetworkError`。
- **E10（功能开关运行时门控）已于 change `0067` 关闭**（ADR-0065）：用户裁决**缺省装配**——门控名单内可选模块（`pet`/`beast`/`evolution`）**未声明即装配**（保持既有行为），仅显式 `features.<模块>: false` 才**完全不装配**（不构造实例、不注册神通、不读状态文件、`cold_path` 置 `None`、7 个 CLI 入口拒绝并退出 0）。名单由组合根 `runtime.GATABLE_MODULES` **单一真源**维护（配置层不认识模块名）；新增查询谓词 `is_disabled`（与 `is_enabled` 极性相反、用途不同，后者语义不变）。**口径订正**：phase-0「功能开关缺省关闭」的字面与裁决不符，规格已订正为「白名单内缺省开」。
- **E15（熔断阈值/冷却不可配）已于 change `0068` 关闭**（ADR-0066）：构造面本就可注入、唯一调用点不传参 ⇒
  硬编码类缺省 5 / 30s。**改代码**：两键写进 `_CONFIG_SPECS`（`map_to="constraints.*"`）⇒ CLI flag / env / yaml /
  §2.3 白名单**全部自动派生**（单一真源）；**不新增结构化段**（镜像 `permission.mode` 的 `extra` 驻留，不动规格「五个结构化段」字面）；
  访问器 `circuit_breaker()` + 校验期拒绝（阈值 ≥1 整数 / 冷却 ≥0 数值，**不静默兜底**）；组合根注入、主/子 loop 共享同链。
  **明确不做**：`features` 值强转（E20② 已随 change `0072` 关闭；**E20① 已由 change `0085` 关闭**）。
- **E20② + E23（feature flag 取值被强转 / CLI 面零消费）已于 change `0072` 关闭**（ADR-0069）：规格明文的三条输入通道实测**只有两条半生效** —— `--feature NAME[=BOOL]` **零消费**（静默无效）、`features.<模块>: off` 之类被 `bool()` 静默当作**开启**。**改代码向规格靠拢**（与 E12 / E11② 同型）：取值收敛到**单一归一/校验点**（`true/false`·`yes/no`·`on/off`·`1/0` + 原生布尔，其余**校验期拒绝并阻断启动**），CLI 面经覆盖层 `features.<模块>` 接入优先级链并支配装配。**E20①（段内未知模块名无告警）已由 change `0085` 关闭** —— 规格先行（顶层段名口径加 `features` 唯一例外）+ 组合根注入已知模块名集合、仅告警；**新增 E24**（env 前缀实现为复数 `CORE_FEATURES_`、规格/文档写单数 `CORE_FEATURE_<模块>`，改名属对外破坏性变更，**待裁决**；**已由 change `0080` 关闭** —— 裁决「改规格/文档向实现靠拢」，零代码变更）；顺带订正 `doc/00-product/user-guide.md` 中「feature flag 缺省关闭」的陈旧措辞（change `0067` 订正规格时漏改）与三面取值口径。
- **B3（MCP Server 模式 stdio 事件循环）已于 change `0073` 关闭**（ADR-0070）：规格「MCP Server 模式」场景「stdio 本地挂载」要求外部 agent 拉起本 server 并握手调工具，`MCPServer` 的方法级行为早已齐备却**没有事件循环**把它们接到 JSON-RPC 上（`serve()` 只绑连接即返回，CLI `mcp serve` 落「已识别，尚未接线」）⇒ 场景在生产**不可达**。**改代码向规格靠拢**（与 E12 / E11② 同型）：`serve_stdio(endpoint)` 以换行分帧 JSON-RPC 承载 stdio 事件循环（按 `id` 应答 / 无 `id` 通知不应答 / 非法行跳过 / EOF 退出），`mcp serve` 接线并在 `_HANDLERS` 注册；**单条请求异常隔离为错误应答、绝不终止循环**；同批补齐**文档已写而代码缺席**的暴露面契约 —— 对外名 `core.<tool_id>`、白名单接受裸名与带前缀两种写法、`mcp.*` 远程工具**禁止二级代理**；协议版本提为共享常量 `core.mcp.models.PROTOCOL_VERSION`。**新增 B6/B7 两行**：wire 形状沿用仓内既有约定（**非**标准 MCP envelope）⇒ 第三方客户端直接挂载尚不可用；默认暴露面沿用 `_is_readonly` 粗粒度启发式 ⇒ `tools.delegate` / `tools.web_fetch` 亦在默认暴露面。
- **B4（`mcp` CLI 接线 + 端点注册表持久化）已于 change `0074` 关闭**（ADR-0071）：规格「MCP Server 安装与移除」五条场景**全部以 CLI 为锚**（`WHEN 执行 mcp add`），而 `entry._mcp` 对非 `serve` 子命令落「已识别，尚未接线」兜底 ⇒ 场景在生产**不可达**；安装管线（change `0054`）本身齐备，缺三件：① CLI 接线；② **跨进程持久化**（CLI 是一次性进程，`PluginInstaller._assets` 随之蒸发）；③ **稳定工具命名**（`connect` 用 `uuid4().hex`，工具名 `mcp.<uuid>.<工具>` 每次装配都不同，与模块文档「`mcp.<server>.<tool>`」不符）。**改代码向规格靠拢**（与 E12 / E11② / B3 同型）：端点注册表落 `$CORE_STATE_DIR/mcp-endpoints.json`（**状态非配置**，原子写）；`mcp add` **先握手成功再落盘**；命名安装以**安装名**作 `handle_id`（`mcp.<名>.<工具>` 跨进程稳定）+ 重名拒绝（`ENDPOINT_NAME_CONFLICT`，不静默覆盖）；组合根**装配期**读回并经同一安装管线连接注册，**单端点不可达只告警跳过**（坏端点不得让整个系统不可用）；`mcp remove` 对称（先卸载释放连接/子进程、再删记录）。**排查记录**：`mcp add --command C` 的 argparse `dest` 曾与顶层 `add_subparsers(dest="command")` 冲突，把 `args.command` 覆盖成 `None` ⇒ `mcp add` **静默落进 Textual REPL 并阻塞**（已改 dest 为 `mcp_command`/`mcp_args`）。
- **B6（MCP wire envelope 未对齐标准）已于 change `0075` 关闭**（ADR-0072）：规格「MCP Server 模式」逐字点名 Claude Code / Cursor 可直接挂载本 server，而一手核实**双向都不通** —— server 应答是裸列表 / `CallResult` 直出（ADR-0070 ⑤ 沿用仓内三方约定），client 的 `initialize` params **为空**（对端 zod 校验回 `-32603`）且 `RemoteTool(**item)` 遇标准容器键会逐字符迭代、遇厂商扩展字段会 `TypeError`。**改代码向规格靠拢**（与 E12 / E11② / B3 / B4 同型，「规格要求 X 而实现没有」）：两侧最小对齐标准 envelope（协议版本 `2024-11-05`）—— 载荷**恒 JSON 编码**进 `content[].text`、`isError` 携错误、client 侧**容忍扩展字段 + 裸形状兜底**（既有 echo server 不破裂）；命名不放宽（仍 `core.<tool_id>`）。**真机双向验收**：`claude mcp add` 挂本 server 后 `claude mcp list` 报 `✔ Connected`；反向 `core-agent mcp add "claude mcp serve"` 成功并发现 20 工具。**转出**：远端 JSON-RPC 错误码未映射到本地码（账本新行）。
- **B7（默认暴露面启发式过粗）已于 change `0076` 关闭**（ADR-0073）：规格场景「默认最小暴露」明写
  「写/删除/**敏感**工具默认不暴露」，而实现只把「无 `write` 副作用」当只读，**漏掉「敏感」** ⇒
  驱动子 loop 的 `tools.delegate`（`coeffects=[]` 漏声明）与有网络出站的 `tools.web_fetch`
  （`network:outbound`）**默认即在暴露面内**。**改代码向规格靠拢**（与 E12 / E11② / B3 / B4 / B6 同型）：
  默认面判据改为**安全 coeffect 白名单**（`coeffects ⊆ {filesystem:read}`，空集=未声明副作用亦视为只读）；
  给 `tools.delegate` **补声明** `agent:delegate`（组合根注册，运行期行为不变、新增的是可见性）使判据
  结构化识别委托类工具（不硬编码工具名）；白名单语义不动（显式 `--whitelist` 仍可开放跨边界工具）。
  默认面收窄为 {`tools.file_read`, `tools.list`}。
- **B8（远端 JSON-RPC 错误码未映射）已于 change `0077` 关闭**（ADR-0074）：`StdioTransport._await` 把
  **一切**远端 JSON-RPC `error` 包成 `MCP_UNAVAILABLE` ⇒ 「方法未实现 / 参数非法 / 工具不存在 / 内部异常」
  塌缩为同一本地码，模型无法区分「工具名写错」（可自纠）与「远端挂了」（该熔断重试）。**改代码向语义靠拢**：
  `transport.map_remote_error(method, error)` 按「方法 + 标准码」归一 —— **`tools/call` 的 JSON-RPC 错误 →
  `MCP_TOOL_NOT_FOUND`**（MCP 约定工具**执行**失败走成功应答的 `isError` 结果信封，故该路径上的错误 =
  调用本身被拒）、其余方法 `-32700`/`-32600`/`-32601`/`-32602` → `MCP_PROTOCOL_MISMATCH`、`-32603`/未知码 →
  `MCP_UNAVAILABLE`；映射为**可测纯函数**，原始码与消息保留于文本。**已否决**按码判（对端对未知工具回 `-32603`）
  与消息文本启发式。client/server/命名空间/白名单/http 传输零改动。
- **E25（pet 安全越界路径未接）已于 change `0081` 关闭**（ADR-0077）：一手核实「**比记载严重** —— 注入但不消费 + 宠物跑在主 loop 上 + 两套词汇表与真实工具 id 全不匹配（`file.read` vs `tools.file_read`）」。用户裁决三项：① **专属 loop 真强制**（受限 `ToolProvider` 落地 R11 / before 安全中间件落地 R12）；② **「越界即暂停」= 本轮阻断 + 通知主人、会话保持 `ACTIVE`**（终止 Action 与 `decline()` 同构；`suspend()` 会因无 `resume()` 调用方**永久楔死**）；③ **订正为真实 id**（`tools.file_read` 等 + 「只读优先」由前缀启发式改白名单）。`pet-mode` spec MODIFIED（钉死「暂停」实现口径 + 新增场景「越界阻断不楔死会话」）；接口 §5.1 / 模块 §3.5 / ADR-0077 / TC-PET-03-04 同批。
- **E29（pet「Runtime Wiring」规格字面写「主 loop」）已于 change `0082` 关闭**（**零代码，改规格向实现靠拢**）：**由 change `0081` 自报** —— `0081` 按用户裁决把宠物改为**专属 loop**（受限工具集 + 安全中间件），规格原字面「唤醒用的**主 loop**」/场景「复用运行系统的**主 loop**」随之成陈迹（共享主 loop 会使 R11/R12 不在路径上）。订正为「组合根装配的真实 loop（可为宠物专属 loop，非 echo 兜底）」+ 追加口径段（真实 **≠** 主；对照 `beast-mode` 明文「独立 `LoopPlugin` 实例」）。`pet-mode` spec MODIFIED（**非** `skip_specs`）。
- **E5（主 Agent 自动迭代内部模块）已于 change `0084` 关闭**（ADR-0079）：一手核实进化闭环**四阶段与两个驱动面早已接线**，缺的是**目标选择层**（`Diagnoser` 单一信号 + 并列即弃权 + 跨轮无记忆）。用户裁决**落点 = 引擎侧**（`CurriculumPlanner`）、**信号 = 结构化信号排序建议 + 显式目标入口**（不用记忆自由文本 —— `MemoryEntry.importance` 恒 0、无结构化教训标记；不用 LLM —— 非确定 / 不可验证 / token 无界 / 静默编造）。议程作诊断**先验**（权重按位次几何递减，恒 < 1.0 ⇒ 证据恒优先、先验只破并列），`evolve run --goal X` 为**指令**（直接采用）；不放宽人工门、不给模型新工具、不新增驱动面。**规格改动**：ADDED「自动课程（目标生成与调度）」+ MODIFIED「对比诊断」「冷路径驱动」。
- **E28（无宿主驱动 `wake()`）已于 change `0083` 关闭**（ADR-0078）：**用户裁决**新增 CLI `core-agent pet run [--interval S]`（**禁** `ui serve` 隐式后台线程 —— 隐式副作用 + 线程生命周期 + 新配置键，且无 UI 部署仍不可驱动），把 `0065`「周期触发由宿主驱动」落到**宿主侧**：驱动薄壳 `PetWakeDriver` 逐会话唤醒 + **故障隔离**（`PetError` 预期态静默跳过 / 意外异常记 `failed` 且**继续其余宠物**，规格 R8）+ 跨进程注册表恢复；`--interval` 为宿主运行参数（不进 `ConfigSpec`），空注册表只提示不造宠物。**规格中性**（`skip_specs`）；接口 §5 那句「能承载常驻驱动的只有 `ui serve`」同批订正。
- **共同的形态问题**：A/E 两类绝大多数是同一个根因——**运行时零件「进程内、无状态、无驱动」**，即 Phase 13/16 起反复出现的「抽象已落地、缺生产触达点」。A3/A5、E2/E4/E5 全归此（A4 已随 change `0055` 关闭、E3 已随 change `0057` 关闭）。
- **一条值得单独记的形态问题**：`cli-contract-baseline.md` 的**内置工具契约与实现已对不上账**（见 E7）——契约列的 5 个工具在代码里从未存在。

| 类别 | 项数 | 最高优先级 | 是否阻塞调试 |
|---|---|---|---|
| A Phase 18 收口遗留 | 11 | 中 | 否 |
| E 早期 Phase 未闭合项 | 29 | 中 | 否 |
| B Phase 12 MCP（部分关闭） | 8 | 低（B1 client 侧 / B3 服务端 stdio / B4 CLI 接线 / B5 白名单 / B6 标准 envelope / B7 默认暴露面 / B8 远端错误码 已闭） | 否（可绕开） |
| C 真实外部后端未接 | ~20 处 | 低 | 否 |
| D 文档与仓库杂项 | 6（4 已关闭） | 无 | 否 |
| F 验收勾选状态 | ✅ 已清尾（6 组核实完毕） | 无 | 否 |
| G 已闭合但未销账 | 7 组 | 无（仅订正文档） | 否 |

---

## 1. 总览（可操作项）

| 编号 | 类别 | 项 | 现象（一句话） | 优先级 | 前置 |
|---|---|---|---|---|---|
| A1 | A | ~~`forget` 无调度器~~ | ✅ 已关闭（change `0049`）：loop 收尾维护节拍触发 `forget` + `core-agent memory maintain` 显式入口 | 中 | — |
| A2 | A | ~~生产 `session_id` 恒空串~~ | ✅ 已关闭（change `0048`）：标识透传至 `remember`，压实/固化/遗忘按会话归组 | 中 | — |
| A3 | A | ~~进程内无持久化~~ | ✅ 已关闭（change `0050` + `0051`）：技能库/反馈/SOP 样本/灰度态 + 观察窗口全落盘 | 中 | — |
| A4 | A | ~~`EvolutionEngine.confirm` 无生产调用方~~ | ✅ 已关闭（change `0055`）：候选稳定身份 + 门禁/评测随候选落盘 + `evolve pending\|confirm\|reject` 操作面签发审批单 | 中 | — |
| A5 | A | ~~`observe` 无采样调度器~~ | ✅ 已关闭（change `0051`）：冷路径批次成功率按 `plugin_id` 归因采样 | 中 | — |
| A6 | A | ~~观察窗口按 target 覆盖~~ | ✅ 已关闭（change `0063`）：覆盖是**有意语义**（窗口判「当前那次发布」是否回归，跨版本混池会使基线失义），已登记 `evolution-interface.md` §3.1；历史留痕待审计需求出现再开 | 低 | — |
| A7 | A | ~~语义分未接历史成功率加权~~ | ✅ 已关闭（change `0058`）：排序分 = 基础分 × 历史成功率因子（冷启动中性 + 下限 0.5，判定仍用基础分）；**候选预筛**转出为 **A11** | 低 | — |
| A8 | A | ~~memory「并发压实一致性」无实现~~ | ✅ 已销账（**零变更**）：规格的操作性保证**已由后端满足** —— `FileBackend` 单把 `RLock` 覆盖**全部**读写路径（`get`/`search`/`put`/`delete`/`list_index`，整文件 `_persist` 在锁内）⇒ 并发访问**串行等待**；压实只**归档不删除**（`migrate` L2→L4）⇒ 不丢条目；既有用例 `test_memory.py::test_concurrent_writes_no_loss`（16 线程 × 200 写，零丢失）直接验证。**账本原判「无并发调用方」订正为**：`ui serve` 同步路由（`/session/compact` 等）由 Starlette 线程池按请求并发、与事件循环上的 `/run`（写记忆）**真并发** ⇒ 规格场景**在生产已被触发且满足** | 低 | — |
| A9 | A | ~~`context.stage` 语义化残留~~ | ✅ 已关闭（**规格明文认可现状**）：`context/spec.md:9` 逐字写「stage 为装配阶段标注、**暂不参与事实选择**」（由 change `0038` 写入），接口文档同口径、实现一致 ⇒ 无差距可闭，**零变更**（Phase 18 的 A3/B6 已判「按架构如此」） | 低 | — |
| A10 | A | ~~进化冷路径无驱动面~~ | ✅ 已关闭（change `0051`）：loop 收尾节拍 + `core-agent evolve run` | 中高 | — |
| A11 | A | ~~语义兜底候选未预筛（成本随库规模线性）~~ | ✅ 已销账（**零变更**）：规格明文「逐条打分」（`skills/spec.md:65-66`）⇒ 未预筛是**规格行为非缺陷**；O(N) 成本需**三重条件同时成立**（JEV 真凭证注入 `runtime.py:301` + 技能库规模大 + 词法 miss）——当前均不成立；「改批量单调用」非局部改动（`score` 原语只返「条目集单一分数」，ADR-0047 决策 ③）。用户裁决：登记销账、零代码 | 低 | — |
| E1 | E | ~~constraints 中间件链从未注入 loop~~ | ✅ 已关闭（change `0052`）：按 `tool_id` 熔断接入 loop（动作前链 + 结果侧观察者）；**校验实由工具层承担**（原「校验空转」订正） | 中高 | — |
| E2 | E | ~~UI 无每会话 loop/memory~~ | ✅ 已关闭（change `0048`，会话维度部分）：标识透传 + 单店按会话归组 | 中（与 A2 同根） | — |
| E3 | E | ~~神通（beast）runtime 桥接缺失~~ | ✅ 已关闭（change `0057`）：20 神通注册进全局技能库 + 专属路由**作用域强制**（`SkillRouter.match(domain=)`）+ 按兽装配 loop/共享记忆注入 + CLI `summon/recall` 走组合根 | 中 | — |
| E4 | E | ~~pet 运行时注入整族缺失~~ | ✅ 已关闭（change `0053`）：pet 纳入组合根（真 loop/共享记忆注入）+ 注册表落盘 + WebUI NL 入口 | 中 | — |
| E5 | E | ~~主 Agent 自动迭代内部模块~~ | ✅ 已关闭（change `0084`／ADR-0079）：引擎侧**自动课程**（目标生成与调度 —— 失败强度定序 / 已处理目标降权 / 位次给先验权重**恒 < 1.0** ⇒ 先验只破并列、不压证据）+ **显式目标入口** `evolve run --goal X`（直接采用、不进竞争）；信号面封闭为**引擎内部结构化数据**（不读记忆自由文本、不调模型）；驱动面仍两个、模型工具面 9 个不变、人工门不放宽 | 中（新能力） | — |
| E6 | E | ~~规格 deferred 未解除（context 判定升级等）~~ | ✅ 已关闭：context 压实「留待后续」已由 change `0041` 规格订正（启发式为**有意降级路径**，LLM 提炼归 memory 通道）；余两项转 **A7 / A8** | 低 | — |
| E7 | E | ~~内置工具契约与实现漂移~~ | ✅ 已关闭（change `0056`）：裁决「规格为准」——契约列 5 个工具**从未存在**（非承诺项），订正 `cli-contract-baseline.md` §10 | 中（契约裁决） | — |
| E8 | E | ~~CLI 契约基线 §11 未决项~~ | ✅ 已关闭（change `0056`）：7 条逐条定性；`im.secret`/`judgment.api_key` 校验对称化 + `permission.mode` 枚举校验（余 `extra` 未知键 → **E18**） | 低 | — |
| E9 | E | ~~文档层其他未闭合项~~ | ✅ 已关闭（change `0061`）：`data-model.md` §4 四实体按**源码回填** + rag/mcp/git 三条替换性锚点登记为 `TC-RAG-10` / `TC-MCP-06` / `TC-GIT-11`（锚点测试本已存在，补的是追踪号）+ retrospective/ADR 日期补记；余两项（远程制品仓库、market-registry）归 **C 类**（§5 已具名） | 低 | — |
| E10 | E | ~~功能开关无运行时门控~~ | ✅ 已关闭（change `0067` / ADR-0065）：门控名单（`pet`/`beast`/`evolution`）归**组合根**单一真源（`runtime.GATABLE_MODULES`）；用户裁决**缺省装配**（兼容现状），仅显式 `features.<模块>: false` 才完全不装配（不构造 / 不注册技能 / 不读状态文件 / 冷路径置空 / 入口拒绝）；新增谓词 `is_disabled`（`is_enabled` 语义不变） | 低 | — |
| E11 | E | LLM 可靠性：连接复用缺失 + 无测试 | ✅ **已关闭**：① 用例已补（change `0060`，9 例，`src/` 零改动 —— 缺的是验证）；② **连接复用已实现**（change `0066` / ADR-0064：`http_pool.HTTPConnectionPool` 线程内按 origin 复用 keep-alive + 失效重建，真实 socket 用例 9 例） | 低 | 无 |
| E12 | E | ~~崩溃恢复无真实 `kill -9` 用例~~ | ✅ 已关闭（change `0062`）：真子进程 `SIGKILL` 端到端 + **修持久化非原子写入缺陷**（`write_text` 先截断 → 半写即整体丢失 → 改 tmp + `os.replace` 原子提交 / 规格 delta） | 低 | — |
| E18 | E | ~~`extra` 未知配置键无校验~~ | ✅ 已关闭（change `0064`，ADR-0063）：用户裁决**仅告警**（WARN 不阻断）——未知顶层段名告警、段仍在 `extra`、白名单由 `ConfigSpec` 派生 | 低 | — |
| E19 | E | ~~durability 文档承诺的「持久化故障降级」未实现~~ | ✅ 已关闭（change `0063`）：**用户裁决订正文档承认现状**——该承诺**规格里从来没有**（只在模块文档），静默降级会掩盖磁盘满；`durability.md` §5 改写为「不静默降级，上层断点续跑承接」 | 低 | — |
| E13 | E | ~~`Validator.parse_output` 零生产调用方~~ | ✅ 已关闭（change `0063`）：规格「输出解析失败不执行」的生产实现是**动作感知**的 `LLMPlanner._parse`（失败 → 终止 Action：工具不执行 + 原因回灌下一轮）；`parse_output` **无动作语义、有意不接线**（非遗漏），补追踪号 `TC-CONS-05` | 低 | — |
| E14 | E | ~~校验码重复~~ | ✅ 已关闭（change `0059`）：`_matches_type` 双拷贝删除，工具层调用前校验**委托** `Validator.validate_input`（单一真源，行为中性 / ADR-0062） | 低 | — |
| E15 | E | ~~熔断阈值/冷却不可配~~ | ✅ 已关闭（change `0068`，ADR-0066）：阈值/冷却成为配置项 `constraints.failure_threshold`（缺省 5）/ `constraints.cooldown_s`（缺省 30s），经 `ConfigSpec` **单一真源**派生四通道（CLI flag / env / yaml / 优先级链）；**不改结构化段**（镜像 `permission.mode` 的 `extra` 驻留）；非法取值**校验期拒绝并阻断启动**（不静默兜底）；组合根注入、主/子 loop 共享同链 | 低 | — |
| E16 | E | ~~`AsyncNotifier` 无 channel~~ | ✅ 已关闭（change `0079`／ADR-0076）：**一手核实后比记载严重 —— 通知链路三层全断**（生产者 `PetSession._notifier` 零调用、通道 `AsyncNotifier()` 无 `channel`、投递点 `flush()` 零调用方）⇒ 已接通三环：生产者落 `wake()` 收尾（反馈周期命中投递 `report()` 产出）+ 缺省通道 = stderr 一行（主人可见观测面，可宿主替换为 IM）+ 投递点由组合根收成单一可调用体（入队即 flush）；注入面签名不变。**账本自述前置「IM 通道为依赖」经核实不存在**（`IMGateway` 在 `src/` 零生产装配 ⇒ 转出为 **E27**） | 低 | — |
| E25 | E | ~~pet 安全越界路径未接~~ | ✅ 已关闭（change `0081`／ADR-0077）：**一手核实后比记载严重** —— ① `Explorer`/`SafetyBounds` 注入 `PetSession` 后**零读取点**（规格 R11/R12 明文要求强制，实现只注入不消费）；② 宠物**跑在主 loop 上**（`pet_loop = cast(LoopPlugin, loop)`）⇒ 一次唤醒可调用全部工具；③ 两套词汇表（`file.read`/`web.search`/`memory.read`；`file.write`/`git.push`/`rm`）**与真实工具 id 全不匹配** ⇒ 即使接线也一条都命中不了。已接通：组合根新增**受限 `ToolProvider`**（只注册 `Explorer.available()` 白名单内真实工具 —— R11，未注册即结构化拒绝 fail-closed）+ **专属 loop**（`middlewares=[build_safety_middleware(...)]` —— R12）；**「越界即暂停」= 本轮终止 + 通知主人、会话保持 `ACTIVE`**（终止 Action 与 `decline()` 同构；不 `suspend()` —— 生产无 `resume()` 调用方，转 yielding 即永久楔死）；词汇表**订正为真实 id** + 「只读优先」由前缀启发式改为**只读白名单**；半径仅当 `target` 非空判定（缺省 `[Path.cwd()]`） | 低 | — |
| E26 | E | `surprise()` / `MicrotaskRunner` 零调用方 | ✅ **已关闭**：**surprise 半边**（change `0086`／ADR-0081 —— `surprise() -> str \| None`：无偏好**不产出不谎报**、有偏好经**真实 loop** 代办并回报**真实产出**；唤醒收尾与反馈**同节拍**投递、失败 fail-soft）；**microtask 半边 + 空闲自治睡眠**（change `0087`／ADR-0082 —— `MicrotaskRunner` 接线且三条任务**真实化**（无真实产出 ⇒ `None` 不谎报）；`wake()` **消费队首任务**、队列清空 ⇒ **入睡**（让行态、不新增枚举、不编造任务）、新任务 `dispatch()` ⇒ 自动唤醒；宿主驱动零改动）。用户裁决「全量 ①②+③ / 跨进程仅同进程」—— **控制面** `/pet [cmd]`（change `0088`／ADR-0083 —— `PetControl` 单门面收口 `status`/`sleep`/`wake`/`assign`/`stop`（CLI 与 `UIAPILayer.pet_command` 复用同一实现）、寻址不猜（单宠物默认 / 多宠物 `PET_TARGET_AMBIGUOUS` / 未知 `PET_NOT_FOUND`）、`status` 不外泄偏好与任务正文、**作用域仅本进程**（跨进程有意不做）） | 低 | 已关闭 |
| E27 | E | `IMGateway` 零生产装配 | `IMGateway` 在 `src/` 内**零生产装配**（仅自身模块 + 单测 + 配置 spec 映射 + 接口文档），im 规格「分平台接入」要求真实平台 Provider（Telegram/飞书/企业微信…）⇒ 属 C 类真后端；亦为 pet 通知的将来真通道 | 低 | 真实平台凭证 + 联网 |
| E28 | E | ~~无宿主驱动 `wake()`~~ | ✅ 已关闭（change `0083`／ADR-0078）：**用户裁决**新增 CLI `core-agent pet run [--interval S]`（**禁** `ui serve` 内隐式后台线程 —— 隐式副作用 + 线程生命周期 + 需新配置键，且无 UI 部署仍不可驱动），把 `0065`「周期触发由宿主驱动」落到**宿主侧**。新增驱动薄壳 `PetWakeDriver(sessions, *, sleep=…)`：`tick()` 逐会话唤醒并返回结构化 `WakeOutcome`（`woken`/`skipped`/`failed`，库层不打印 ⇒ 呈现归 CLI），`sessions` 为**可调用体**（`PetManager.list`）每轮重取 ⇒ 驱动期间新注册的宠物自动纳入，`sleep` 可注入 ⇒ 节拍测试确定性（先例：`0052` 注入 `clock`）；**故障隔离**：让行/退避/未激活（`PetError`）= 预期态静默跳过，意外异常 ⇒ `failed` 记因并**继续其余宠物**（规格 R8「A 宠物异常不影响 B 宠物」）。CLI 面 `--interval` 从 `rest` 提取（`REMAINDER` 同 `--name` 先例）、缺省 60s、非法/非正 ⇒ 用法错误退出 1；跨进程注册表 `pets.json` 恢复会话继续驱动；空注册表 ⇒ 提示激活入口退出 0（**不自动造宠物**）。`--interval` 是**宿主运行参数、不进 `ConfigSpec`**。规格中性（`skip_specs`） | 低 | — |
| E17 | E | ~~pet 无后台 daemon~~ | ✅ 已关闭（change `0065`，**规格未要求**）：`wake()` 由**宿主**驱动、内核不常驻；接口 §5 / 模块 §4 登记为已知语义 | 低 | — |
| E20① | E | ~~`features` 未知模块名无告警~~ | ✅ 已关闭（change `0085`／ADR-0080）：**规格先行** —— MODIFIED「配置校验与生效」给顶层段名口径加**唯一例外**（`features` 子键按经注入的已知模块名集合校验、未知**仅告警**、未注入不校验）；实现 `ConfigManager(known_modules=…)`（缺省 `None`=不校验）+ `_unknown_feature_warnings`、`entry._config_manager` **单点注入** `GATABLE_MODULES`（组合根仍单一真源，配置层只消费注入 ⇒ 不逆转 ADR-0065） | 低 | — |
| E20② | E | ~~feature flag 取值被 `bool()` 强转~~ | ✅ 已关闭（change `0072`，ADR-0069）：取值收敛到单一归一/校验点（`true/false`·`yes/no`·`on/off`·`1/0` + 原生布尔），其余取值**校验期拒绝并阻断启动**；`features.pet: off` 不再被当作开启 | 低 | — |
| E21 | E | ~~`entry._pet` 的 `pet.enabled` 判据忽略 config.yaml~~ | ✅ 已关闭（change `0070`）：CLI 前置判定改走 `ConfigManager.config_value(key)`（CLI > env > **config.yaml** > 缺省，ConfigSpec 单一真源），`pet.persons_dir` 同源读取；缺文件按「无 yaml 层」容错 | 低 | — |
| E22 | E | ~~`config get` 同型缺陷~~ | ✅ 已关闭（change `0078`／ADR-0075）：`entry._config` 的 `get` 分支改用 `ConfigManager.config_value(key)`（与 `pet` 门控同一通路，ADR-0067）⇒ 遵循完整优先级链 CLI > env > **config.yaml** > 缺省；构造前移 + 孤儿 `resolve` 导入删除；`test_config_get_default` 改 hermetic | 低 | — |
| E23 | E | ~~`--feature NAME[=BOOL]` CLI 面零消费~~ | ✅ 已关闭（change `0072`，ADR-0069）：`entry._cli_overrides` 收进覆盖层 `features.<模块>`，CLI 面**真的**参与优先级链并支配装配（组合根端到端用例锁住）；裸名视为开、语法非法在解析点拒绝 | 低 | — |
| E24 | E | ~~env 前缀实现与规格不符~~ | ✅ 已关闭（change `0080`，**改规格/文档向实现靠拢**）：**零代码变更** —— 规格/接口/模块文档的单数 `CORE_FEATURE_<模块>` 订正为**复数** `CORE_FEATURES_<模块>`（与段名 `features` 同源，`manager.py` `_FEATURE_ENV_PREFIX`），`configuration` spec MODIFIED + 新增场景「env 面以复数前缀生效」；单数前缀**不生效**、**不做**兼容别名（同一开关两个真源）；顺带**补齐** `0072` 归档时丢失的该 Requirement 第二段正文（三通道全部生效 / 三面同口径 / 禁 `bool()` 静默强转） | 低 | — |
| E29 | E | ~~pet「Runtime Wiring」规格字面写「主 loop」~~ | ✅ 已关闭（change `0082`，**改规格向实现靠拢**）：**零代码变更** —— `0081` 起宠物跑在**专属 loop**（受限工具集 + 安全中间件，用户裁决「专属 loop 真强制」；共享主 loop 会使 R11/R12 都不在路径上）⇒ 规格「Pet Session Runtime Wiring」的「唤醒用的**主 loop**」与场景 「复用运行系统的**主 loop**」即成陈迹。订正为「组合根装配的**真实 loop**（可为宠物专属 loop，非 echo 兜底）」+ 追加口径段（真实 **≠** 主：对照 `beast-mode` 明文「独立 `LoopPlugin` 实例」）。**由 change `0081` 自报** | 低 | — |
| B1 | B | Phase 12 MCP 安装/传输/安全（client 侧） | 🔶 **部分关闭（change `0054`）**：stdio 传输 + `add` 分流 + 沙箱/白名单/确认门接线 + 组合根装配已落地（ADR-0057）；**余** http 会话 → B2（服务端 stdio B3 / CLI 接线 B4 / 白名单 B5 均已关闭） | 低 | 无 |
| B2 | B | 远端 http/streamable-http 会话 | `build_http_transport` 仅落地「白名单守卫 + SDK 缺失降级 + 会话待接入报错」；`Mcp-Session-Id`/SSE/headers 未实现 | 低 | mcp SDK（离线不可装） |
| B3 | B | ~~`MCPServer.serve` stdio 事件循环~~ | ✅ 已关闭（change `0073`，ADR-0070）：`serve_stdio` 换行分帧事件循环 + `mcp serve` 接线 + `core.` 命名空间 + 禁二级代理 + 共享协议常量；端到端用例用本仓 client 拉起真实子进程锁住 | 低 | — |
| B4 | B | ~~`mcp` CLI 接线 + 端点注册表落盘~~ | ✅ 已关闭（change `0074`，ADR-0071）：`mcp add/list/remove` 接线（先连通验证再落盘）+ 端点注册表 `$CORE_STATE_DIR/mcp-endpoints.json`（原子写）+ 装配期连接注册（稳定命名 `mcp.<端点名>.<工具>`）+ 不可达端点降级不阻断（注册表损坏同口径）+ 重名 `ENDPOINT_NAME_CONFLICT` | 低 | — |
| B5 | B | 出站白名单不可配 | ✅ **已关闭（change `0071`）**：`permission.sandbox.host_allowlist`（CSV 标量，ConfigSpec 单一真源三面）+ 校验期拒绝非法条目 + 组合根注入（缺省空 = fail-closed 不变），ADR-0068 | 低 | ~~E10 配置门控~~（已闭） |
| B6 | B | ~~MCP wire envelope 未对齐标准~~ | ✅ 已关闭（change `0075`，ADR-0072）：两侧最小对齐标准 envelope —— server `tools/list` 回 `{"tools":[...]}` / `tools/call` 回 `{"content":[{"type":"text","text":<JSON 载荷>}],"isError":<bool>}`（载荷恒 JSON 编码保往返保真）；client `initialize` 携标准三元组、解析容器键并**容忍厂商扩展字段**、归一 `isError` 信封，同时**兼容旧式裸形状**；**真机双向验收**：`claude mcp add` 挂本 server 后 `claude mcp list` 报 `✔ Connected`，反向 `core-agent mcp add "claude mcp serve"` 成功并发现 20 工具 | 低 | — |
| B7 | B | ~~默认暴露面启发式过粗~~ | ✅ 已关闭（change `0076`，ADR-0073）：默认面判据由「无 `write`」改为**安全 coeffect 白名单**（`⊆ {filesystem:read}`，空集视为只读）—— 出网 / 进程派生 / 委托驱动（`agent:delegate`）一律默认不出；`tools.delegate` 补声明 `agent:delegate`（原 `coeffects=[]` 漏声明）使判据结构化识别；白名单语义不动 | 低 | — |
| B8 | B | ~~远端 JSON-RPC 错误码未映射~~ | ✅ 已关闭（change `0077`／ADR-0074）：`transport.map_remote_error` 按「方法 + 标准码」归一 —— `tools/call` 的 JSON-RPC 错误 → `MCP_TOOL_NOT_FOUND`（= 调用被拒）、其余 `-32700/-32600/-32601/-32602` → `MCP_PROTOCOL_MISMATCH`、`-32603`/未知码 → `MCP_UNAVAILABLE`；原始码保留于文本 | 低 | — |
| C1 | C | 真实外部后端 ~20 处「未接」 | 抽象 + fake 已落地，真后端待接。**代码半 / 凭证半二分见 `phase-20.md`**（8 项有可离线验证的代码半）；**C4 `observability` 代码半已关闭（change `0089`／ADR-0084）**；**C2 `git` 代码半已关闭（change `0090`／ADR-0085；余装配待消费者 + 远程凭证/可靠性半）**；**C3 `ci_cd` 代码半已关闭（change `0091`／ADR-0086；余装配/CLI 待消费者 + 制品仓库凭证半）**；**C5 `skillhub` 已关闭（change `0092`／ADR-0087；余真实市场 fetcher 凭证半）**；**C6 `plugin_registry` 四源解析器已关闭（change `0093`／ADR-0088；余 git 远端/市场/端点凭据凭证半）** | 低 | 见 `debug-gaps.md` §2.3 |
| D1 | D | ~~README §2 状态行待核实~~ | ✅ 已关闭：Phase 18 行刷新为 ✅；`17.5` 行改为「🔶 部分完成（遗留见 E3/E4）」 | 无 | — |
| D2 | D | `coding-plan/phase-3-prompt.md` 未跟踪 | 一次性 prompt 残留 | 无 | 删除或 `git add` |
| D3 | D | ~~根目录 `config.yaml` 未跟踪~~ | ✅ 已关闭：`git check-ignore` 原为**零命中**（仅「没 add 过」）→ 已补 `.gitignore` 守卫 | 无 | — |
| D4 | D | `.claude/settings*.json`（部分关闭） | ✅ `settings_deepseek/glm.json` 已 ignore；⚠ `settings.json` **已跟踪且已修改**（非本项目改动）—— **用户裁决：保持不动、继续不提交**（既不改工作区、也不提交他人改动） | 无 | 保持不动（用户裁决） |
| D5 | D | ~~本文件未入 README 索引~~ | ✅ 已关闭：已登记 `README` §1（清单 22 份）+ §2（第 19 行） | 无 | — |
| D6 | D | ~~`doc/02-modules/llm-provider.md` 称「LiteLLM 默认实现」~~ | ✅ 已关闭（change `0069`，纯文档 / 规格中性）：默认实现实为 `StdlibLLMProvider`（ADR-0044 已删 litellm）⇒ 订正模块文档 + 全仓现行文档同类措辞（`requirements.md` CORE-LLM-R2/R3 / `doc/README.md` / `test-cases.md` TC-LLM-03 / `ui-interface.md`）；历史 ADR 与 archive 不改 | 无 | — |

---

## 2. A 类：Phase 18 收口遗留（本 Phase 新报）

### A1 `forget` 无调度器 — ✅ 已关闭（change `0049`）

- **现象**：遗忘（衰减归档）只在 loop 的压实收尾被顺带调用（`src/core/loop/default.py:285`，随 `compact()` @ :281 之后），**没有独立的定时/节拍驱动**；长闲置会话不会自动衰减。
- **根因**：`MemoryStore.forget(*, threshold=...)` 是纯函数式接口，无调度依赖；Phase 18 #5 明确把「定时衰减循环」排除在范围外（需调度器）。`adr.md:513` 同样记为「需调度依赖，另立变更」。
- **关闭动作**：✅ **已由 change `0049-memory-maintenance-cadence` 闭合**（采「节拍闸门 + CLI 显式入口」）：loop 收尾加**维护节拍**（`_MAINTENANCE_INTERVAL_S = 900s` 默认，距上次达间隔才触发一次 `MemoryStore.forget`，失败降级不中断本轮、走 `maintenance_failed` trace）；`forget` 补进 `MemoryStore` Protocol；CLI 新增 `core-agent memory maintain`（装配 runtime → `compact()` + `forget()`，打印归档条数）。**未**引入调度器/常驻后台任务（无真实常驻宿主：`HarnessHost` 在 `entry.py` 每条命令各起一份）。spec delta：`loop`/`memory`/`cli-ops` 三份（29 specs 全绿），测试 679 passed。
- **前置**：无（已完成）。

### A2 生产 `session_id` 恒空串（含 `UIAPILayer.compact` no-op）— ✅ 已关闭（change `0048`）

- **现象**：`MemoryEntry.session_id` 缺省空串（`src/core/memory/protocol.py:32`），而生产侧 `loop/runtime` **从不设置它**（grep 无引用）→ 压实/固化/遗忘全部按单一 `""` 组聚合，「按会话」维度的语义在实际运行中退化为「全局单组」。
- **次生**：`UIAPILayer.compact(session_id)` 仍是 no-op（`src/core/ui/api.py:119-121`，注释自陈「MemoryStore 无显式 compact」），ui spec 无该 Requirement，故未擅自接线。
- **关闭动作**：✅ **已由 change `0048-session-scoped-memory` 闭合**（与 E2 合并做）：loop 三入口收 `session_id` 并写入 L2 条目；`UIAPILayer.compact` 直调 `MemoryStore.compact`；`get_memory` 按会话归属过滤。spec delta：`loop`/`memory`/`ui` 三份（29 specs 全绿），测试 674 passed。
- **前置**：无（原「与 E2 同根，建议合并做」已按此执行）。

### A3 进程内无持久化 — ✅ 已关闭（change `0050` + `0051`）

- **现象**（五处同源）：
  - `SkillLibrary` 注册表 —— SOP 提炼入库的技能随进程消失；
  - `SkillFeedback` 统计（`src/core/skills/feedback.py`，模块注释「仅进程内统计（不落盘、不写记忆）」）；
  - 观察期窗口（`src/core/evolution/observation.py:39`「窗口仅进程内（不持久化）」）；
  - SOP 样本累积（`SopExtractor` 组内计数）；
  - `VersionManager` 灰度 / A/B 状态。
- **根因**：Phase 18 有意把持久化排除（先跑通闭环逻辑，再补落盘）；与 Phase 13/16 的「进程内态」同类（E4 的 `PetManager` 同族）。
- **关闭动作**：定存储选型（复用 `FileBackend` 或新 backend）→ 逐类补 spec 持久化 Requirement → 与「依赖与重开顺序」第 3 步的 serve 常驻进程一并落地。
- **关闭进度**：🔶 **skills 半边已由 change `0050-persist-skills-state` 闭合**（存储选型 = 沿用既有 `path: Path | None` + `_load`/`_persist` 惯例，共用 `skills/persist.py` 两个纯函数、单文件 JSON 快照、零第三方依赖，决策见 **ADR-0053**）：`SkillLibrary` / `SkillFeedback` / `SopExtractor` / `VersionManager` 四类各加可选 `path`（缺省纯内存，向后兼容），`build_runtime` 注入 `$CORE_STATE_DIR/{skills,skill-feedback,sop-samples,skill-versions}.json`；spec 补「技能态持久化」Requirement（29 specs 全绿），测试 685 passed。
- **evolution 半边闭合**：🔶 **已由 change `0051-evolution-cold-path` 闭合** —— `ObservationRegistry` 加可选
  `path`，落盘 `{target: {baseline, samples, frozen_until}}`（**冻结截止一并落盘**，否则重启即解冻、冷却期形同虚设），
  缺省纯内存；`build_runtime` 注入 `$CORE_STATE_DIR/observations.json`。两个纯函数 `read_state` / `write_state`
  同时从中立化提升到 `src/core/persistence.py`（技能态与进化态共用，决策见 **ADR-0054**）。
- **剩余**：候选 `pending` 队列曾仍进程内 —— 属 A4，已随 change `0055` 的「队列落盘 + 操作面」一并关闭（非本项缺口）。
- **前置**：无（存储选型已定，ADR-0053 / ADR-0054）。

### A4 `EvolutionEngine.confirm` 无生产调用方 — ✅ 已关闭（change `0055`）

- **现象**：`confirm(candidate, *, approval=...)` 的三重门（present + `is_approved` + target 匹配）已在 `0046` 实现并被测试覆盖，但**生产侧无调用者**（grep 仅命中 permission gate 的同名方法）→ 维度 2 的 HITL 闸门在生产路径上尚不触达。
- **根因**：候选 `pending` 队列需要「操作面」驱动（谁来发起 confirm、审批单从哪来），Phase 18 #9 有意只做闸门本身。
- **关闭动作（方案较原记扩围，缘由如下）**：原记「在操作面接 pending 队列 → 构造 `ApprovalTicket` → 调 `confirm`」在**每条命令各起一份装配**的 CLI 上不可行，且跨进程**根本不可能**——队列态与门禁/评测结论原以 `id(candidate)` 为键存于引擎私有字典，`Proposer._generation` 又是进程内自增（两次 `evolve run` 会产出同 `generation`/同 target 的两个候选）。故一并落地三件事：
  1. **稳定身份**：`GenerationCandidate.candidate_id`（UUID 前 12 位 hex，构造即固化），门禁/评测检索改按 `candidate_id`；
  2. **队列落盘**：`PendingQueue` 把「候选 + `GateReport` + `EvalReport`」作为**一条记录**整体落盘（`$CORE_STATE_DIR/evolution-pending.json`），缺省纯内存；`pending()` 只列 `status="pending"`，已确认/已拒绝的留痕不额外归档；
  3. **操作面**：`core-agent evolve pending|confirm <id>|reject <id> [--note]`；`confirm` = 确认 + 结晶发布一步；`risk_level="high"` 的候选由**操作面**（人）签发 `ApprovalTicket` 后交引擎判定（引擎语义一字不动）；未知 id → stderr + 退出码 1，不复活。
  **副产品**：`crystallize`（过门发布）由此获得**首个生产调用方**（此前为死路径）。决策见 **ADR-0058**。
- **前置**：审批单来源（`permission` 审批流的发起端）—— 已由 `core/im/gateway.py` 的同形先例 + 本变更在 CLI 侧签发满足。

### A5 `observe` 无采样调度器 — ✅ 已关闭（change `0051`）

- **现象**：`EvolutionEngine.observe(target, score, *, now=...)` 是采样接缝，但**无生产调用方**（grep 无命中）→ 观察期窗口开而不采，自动溶解在生产侧不会被触发。
- **根因**：Phase 18 #10 明确不把调度器放进引擎（保持引擎纯粹、`now` 可注入以便测试）。
- **关闭动作（已落地）**：采样来源取**已有数据的最近似口径** —— `EvolutionWorker._sample_observations` 在每轮
  `run_cycle` 后，对本批 trace 中**已开窗**目标按 `plugin_id` 归因算**批次成功率**并各上报一次（线上代理指标、
  零额外评测成本）；无归因 trace 的目标不采样。**已知口径张力（如实记录）**：批次成功率与留出评测分不是同一指标，
  绝对分差容差 `0.2` 只是近似可比 —— 宁漏报不误杀（溶解是不可逆方向的重动作）。**不采纳**「`Evaluator` 评测轮次
  回灌」（要再造一条无人驱动的评测）与「外部上报」（生产无上游）。
- **前置**：A3 进化半边（已随本次一并落盘）。

### A6 观察窗口按 target 覆盖 — ✅ 已关闭（change `0063`，维持现状 + 接口文档标注）

- **现象**：`ObservationRegistry.open` 对同一 target **覆盖旧窗口**（重发布即重开基线、丢旧样本，`observation.py:59-64`，注释即写「重新发布即重新起算基线」）。
- **关闭动作（已落地）**：**维持覆盖语义**并在 `doc/03-interfaces/evolution-interface.md` §3.1 登记为**已知语义**
  ——为什么要覆盖：该窗口的判据是**回归**（基线 = 该次发布的 `eval.held_out_score`），
  同一 target 二次发布若保留旧样本，样本池会混入两个版本的成绩 ⇒ 均分既不表示 v1 也不表示 v2，
  **回归判据失效**；覆盖即「重发布重新校准基线」。
- **不做**：窗口历史留痕（审计需求未出现，不预造存储）；需要时承载点已具名（`dissolve` 教训条目 L2 + 遥测流）。
- **前置**：无。

### A7 语义分未接历史成功率加权 — ✅ 已关闭（change `0058`，ADR-0061）

- **现象**：`SkillMatch.score` 注释自述「匹配度（语义 + 历史成功率 + 适用声明）」，实现只算词法命中率 / 语义分；`SkillFeedback`（`0045` 落地并已接生产）零消费方 → 迭代闭环算出的成功率**路由侧不用**。
- **关闭动作（已落地）**：`SkillRouter` 增可选 `feedback` 注入；`match` 返回前把每个候选的基础分乘**历史成功率因子**即得排序分。
  - 因子：**无样本 = 1.0**（冷启动中性——`success_rate` 无样本返回 0.0，直接相乘会把全部新技能归零）；有样本 = `0.5 + 0.5 × 成功率`（下限防「一次失败 → 不入选 → 无新样本 → 永久失败」的正反馈）；未注入 → 恒 1.0（零回归）。
  - **加权只改排序、不改命中**：词法命中筛选与语义阈值判定的都是**基础分**——否则「语义 0.9 + 历史全失败」会被加权到 0.45 < 阈值而丢弃，属语义漂移。
  - 组合根把 `skill_feedback` 构造**前移**并注入路由（与 `SkillIterator`/`VersionManager` 同一实例，单一真源）。
- **验证**：新增 `tests/test_skill_ranking.py`（8 例：冷启动 / 全成功 vs 全失败 / 50% 缩放 / 按版本取统计 / 语义命中不受阈值加权影响 / 冷启动保持原始语义分 / 共享实例注入 / 端到端排序随反馈变化）；四门全绿（776 passed）。
- **未纳入（转出）**：候选预筛 → **A11**（本次用户裁决 A：只做加权，见下）。

### A8 memory「并发压实一致性」无实现 — ✅ 已销账（零变更，一手核实「规格已满足」）

- **现象**：memory spec 有此场景（`doc/openspec/specs/memory/spec.md:112-115`：压实与写入/检索并发 ⇒ 「通过加锁/事务保证不产生数据竞争，并发读写**等待或**走一致性快照，不丢失条目」）。
- **销账理由（三件一手证据）**：① **加锁覆盖全部读写路径** —— `FileBackend` 单把 `RLock`（`backend.py:27`）保护 `get`/`search`/`put`/`delete`/`list_index`，且**整文件 `_persist` 在锁内**（`put`:38 / `delete`:65）⇒ 任一并发读写在锁上**串行等待**，无数据竞争；② **压实只归档不删除** —— 摘要写入与整批迁移均走 `migrate`（`store.py:129`）→ L2 迁 L4，非物理删除 ⇒ **不丢失条目**；③ **既有用例直接验证** —— `tests/test_memory.py::test_concurrent_writes_no_loss`（16 线程 × 200 并发写，断言零丢失）。
- **账本原判订正：「当前无并发调用方」不成立** —— `ui serve`（E4/change `0053`）的 FastAPI **同步路由由 Starlette 线程池按请求并发执行**（`fastapi_serve.py`：`/session/compact`、`/memory`、`/tools/invoke` 均为 `def`；仅 `/run` 为 `async def` 在事件循环），故**压实（工作线程）与记忆写入（事件循环上的 `/run`）真并发**——规格场景**在生产路径上已被触发**；其落点全部经上述单锁后端，故**保证成立**。
- **余项（不是缺口）**：「多步压实序列的**一致性快照**」未实现 —— 但规格以「等待**或**快照」给出二选一，**「等待」已由单锁满足**；仅当将来出现「同一会话并发压实 / 跨进程共享状态目录」这类**要求序列原子性**的需求时，才需补快照语义（届时先补规格）。
- **零变更**：无代码、无规格、无文档改动（本行 + §0 + §9 + README 为记账）。

### A9 `context.stage` 语义化残留 — ✅ 已关闭（规格明文认可现状，零变更）

- **现象**：`ContextPack.stage` 是装配阶段标注，不参与事实选择；唯一调用点恒传常量 `"reason"`（`loop/planner.py:135`）。
- **一手核实（三层已一致，无差距）**：① **规格逐字认可现状** —— `doc/openspec/specs/context/spec.md:9`：
  「系统 SHALL 以**任务目标**为检索信号按需加载上下文（L2 事实检索以 task 为 query；**stage 为装配阶段标注、
  暂不参与事实选择**）」；② **接口文档同口径** —— `context-interface.md:13` 字段注释、`:27` 签名；
  ③ **实现一致** —— `assembler.build(task, stage=...)` 只把 stage 存进包（`:39`），检索用 task（`:57` 注明「stage 不参与检索」）。
- **该措辞的来源**：change `0038-task-keyed-memory-recall`（commit `4cf2be7`）把检索 query 由 stage 改为 task，
  并**同时**在规格里写明 stage 的定位（stage 变常量后作 query 只会召回噪音）。该 commit 的遗留登记
  （「A3 stage 装饰性」）即本项来源；Phase 18 已把 B6 判为「**按架构如此**」（装配是 Reason 前的一次性步骤）
  并把 A3 记为「已如实标注 + 仍可选：赋予阶段化权重（留待按需）」。
- **关闭判定**：这是**「规格已明文认可、文档与实现三层一致」**型 —— 与 A6/E17 的「文档过度承诺」不同（那需订正文档），
  此处**无任何不一致**，故**零变更**、纯账本销账（同 E6 的关闭形态）。
- **将来若要**：阶段化权重 / 按阶段差异化选事实 = **新能力**（须先补规格 Requirement，非本项欠账）。

### A10 进化冷路径无驱动面 — ✅ 已关闭（change `0051`）

- **现象**（本次会话走查新增）：`EvolutionWorker.on_trace_complete` / `maybe_run` 全仓**仅 `runtime.py`（构造）与
  `tests/` 引用** —— CLI 无对应命令、loop 无节拍、无定时器 → L4 整条冷路径离线：`run_cycle`（诊断→提案）、
  `crystallize`（发布 + **开窗**）在生产都不会发生。**这是 A5 的上游**：`observe` 无调用方，但即便把采样接进
  worker，也仍然没人驱动 worker。
- **根因**：同一个形态问题 —— 零件「进程内、无状态、**无驱动**」。与 A1（`forget` 无调度器）同源，只是这一处漏在 L4。
- **关闭动作**：两个诚实答案（无真实常驻宿主：`HarnessHost` 每条 CLI 命令各起一份、serve 非长驻调度器）——
  ① **loop 收尾维护节拍**给出一次冷路径机会（组合根注入 `Callable[[], None]`，与记忆维护**共用节拍闸门**
    `maintenance_interval`；loop 不 import evolution，DI 红线不破）；② CLI **`core-agent evolve run`** 一次性入口
    （装配 runtime → `maybe_run(force=True)` → 打印结局）。**阈值门仍归 `EvolutionTrigger`**，驱动面只给「机会」。
- **前置**：无。

### A11 语义兜底候选未预筛（成本随库规模线性）— ✅ 已销账（零变更，一手核实「规格行为 + 触发条件未成立」）

- **现象**：`SkillRouter.match` 在**词法全无命中**时调语义打分器兜底；`SkillMatcher.score`（`judgment/skills.py:25`）
  **逐候选** `_score_one` → `router.decide()` ⇒ N 个候选 = N 次决策调用（miss 轮模型调用数 O(N)）。
- **销账理由（四件一手证据）**：① **规格明文要求现状** —— `skills/spec.md:65-66` 逐字写「以注入的语义打分器…对候选技能
  **逐条打分**，达阈值者按分排序返回」⇒「未预筛」是**规格行为、非缺陷**（同 A9 形态：规格已认可现状 ⇒ 零变更）；
  ② **成本面三重条件** —— 打分器**仅 `jev is not None` 时注入**（`runtime.py:301`）、且**仅词法 miss 时才调用**
  （`router.py:87` 的 `or self._semantic(...)`）、且成本随库规模线性 ⇒ 三者**同时成立**才构成事实约束，当前均不成立
  （技能靠 SOP 提炼逐步结晶，生产起始为空）；③ **「改批量单调用」非局部改动** —— `score` 原语只返回「条目集
  **单一分数**」（无 per-item 分数，ADR-0047 决策 ③，`adr.md:481-482`）⇒ 要动**原语契约 + judgment DSL + provider prompt**，
  非 `SkillMatcher` 局部；④ **预筛以召回换成本** —— 比词法更粗的排序信号（字符 n-gram）会**先丢掉真正的最优候选**，
  在库未成大事实约束前是**净损失**。
- **用户裁决（本次）**：**登记销账、零代码** —— 保留现状（规格行为），登记「触发条件」留待将来；不做投机预筛（CLAUDE.md §2）。
- **将来若要**：库规模/打分成本成**事实约束**时，二选一 —— ① **粗预筛**（字符 n-gram 粗排 + Top-N/阈值常量，纯 skills 层，
  **须先改规格**「逐条」→「预筛后逐条」）；② **批量单调用**（`score` 原语返回 per-item 分数，**须先改 ADR-0047 决策 ③**）。
  二者皆属**新能力/契约变更**，非本项欠账。
- **零变更**：无代码、无规格、无文档改动（本行 + §0 + §1 + §9 + README 为记账）。

---

## 3. E 类：早期 Phase 未闭合项（全量走查新增）

> 全部经「文档自陈 + `src/` 调用点 / 归档反向核对」判定为**明确未做**。已闭合但文档未销账的旧记见 §8（G 类）。

### E1 constraints 中间件链从未注入 loop（Phase 13 遗留）— ✅ 已关闭（change `0052`）

- **现象**：`DefaultLoop` 有完整中间件链（`loop/default.py` 的 `Middleware` / `_apply_middlewares`），但**生产零注入**——`grep -rn "middlewares=" src/` 空 → 熔断在生产无任何等价物。
- **根因**：`constraints.Middleware` 形状（`ExecRequest/ExecResponse`）与 loop 的 `(LoopContext, Action) → Action|None` 不同，需适配层；`phase-13.md:91` 标「随 Phase 14」但掉档。
- **订正（本次一手核实）**：账本原写的「**校验空转**」**不成立**——校验生产已由工具层 `ToolProvider._validate_args` 承担（与 `Validator.validate_input` 逐行等价）；上下文压缩亦已接线（`compactor=`）。真实残留 = **熔断**。
- **关闭动作**：✅ **已按 change `0052-constraints-middleware-wiring` 闭合**（ADR-0055）——① loop 增**加法式结果侧接缝** `action_observers`（`Middleware` before-only 契约不变）；② 新增 `core/loop/constraints_adapter.py` 的 `ConstraintsChain`（**按 `tool_id` 隔离**熔断、**只计执行类失败**、策略性拒绝不计入）；③ 组合根注入主/子 loop（共享同一实例，熔断态 per-runtime）。**有意未接**：`Validator`（被工具层吸收）、`RetryPolicy`/`Fallback`（幂等风险 / 无生产 `fallback_fn`）。
- **前置**：无。

### E2 UI 无「每会话独立 loop / memory / tools」（Phase 13 遗留）— ✅ 已关闭（会话维度部分，change `0048`）

- **现象**：`UIAPILayer` 只持**一个共享** `self._loop` / `self._memory`（`ui/api.py:52-53`），`self._sessions` 仅存 mode 字符串（`:61`）→ 多会话共用同一 loop 与同一记忆命名空间。
- **根因**：`phase-13.md:93` 把「serve/repl 运行时装配 + 每会话独立 loop+memory+tools」标为 deferred。
- **关闭动作**：✅ **已按 A2 合并方案闭合（change `0048`）**——采「会话标识透传 + 单店按会话归组」（**不做**每会话独立 `(loop, memory)` 实例：单实例并发服务多会话时标识随调用走、天然不串号，组合根与生命周期不动；见 change `0048` design 决策 1/2）。据此 `run_loop` 透传标识、`get_memory` 按会话过滤、`compact` 接真。
- **前置**：无。

### E3 神通（beast）runtime 桥接缺失 — ✅ 已关闭（change `0057`，ADR-0060）

- **现象**（四项同源，2026-10-04 复核全部属实）：
  - `register_innate_skills`（`beast/skills.py`）**零生产调用者**（仅 `tests/test_beast.py`）→ 20 个 `beast.*` 神通从未进过运行时 `SkillLibrary`。
  - `BeastManager` 的 handoff 段被**整段跳过**：`entry._summon` 构造裸 `BeastActivator()`（未传 router）→ `manager.py` `router is None` 短路。
  - `BeastSession` 未注入 loop/memory → 命名空间隔离失效，`remember` 直接抛 `BEAST_MEMORY_WRITE_FAILED`。
  - `SkillRouter.match` 无 domain 参数 → 专属路由只有语义、无 runtime scoping。
- **裁决（用户 2026-10-04）**：**A 全做・解除 deferred**。理由：**「只注册不路由」不是中性半成品**——`SkillRouter.match` 的候选池是全局 `SkillLibrary`，注册后专属神通会进主 Agent 候选并灌进主 prompt，即把系统推入「违反自己规格 R5」的状态。故四项必须一次闭合。
- **关闭动作（已落地）**：
  ① **规格**：beast-mode MODIFIED R4/R5，删去「runtime 调用 deferred」，写明组合根装配义务与**路由期作用域强制**口径；
  ② **注册**：`build_runtime` 构造 `BeastRegistry` → `register_innate_skills(skill_library, registry)`；
  ③ **作用域**：`SkillRouter.match(task, *, domain=None)` —— 三节 `beast.<域>.<技能>` 为专属技能，仅 `domain == "beast.<域>"` 进候选（形状即约定，不另建注册表）；主 Agent / 通用子 Agent 传缺省 → **看不到任何专属神通**；
  ④ **注入**：`BeastManager(registry, router=MultiAgentRouter([]), loop_factory=_beast_loop, memory=memory)`，按兽惰性装配独立 loop（`_loop_hooks(beast.agent_id)` 域内路由）+ 共享 `MemoryStore`；`Runtime` 增 `beast_manager`/`beast_activator`；`entry._summon/_recall` 改走 `build_runtime`（与 `_pet` 同口径）。
- **验证**：新增 `tests/test_beast_wiring.py`（7 例：注册面 / 主 Agent 不可见 / 域内可见 / 通用技能不被误伤 / 组合根暴露面 / 注入生效 / 端到端 summon 跑真 loop + 记忆隔离）；四门全绿（768 passed）。
- **已知接受项**：① CLI 每进程无状态装配 → `recall <beast>` 在该进程内必 `BEAST_NOT_MANIFEST`（**既有性质**，多兽跨命令状态另属后续行）；② 词法路由噪声项（如领域串里的 `/`）可能让他兽技能命中，属打分口径而非作用域（作用域只保证非本域**专属**神通不可达）。
- **未纳入本变更**：多兽并行调度与 `TaskScheduler` 的配合、神兽专用权限策略、`/summon` 斜杠与 WebUI 自然语言入口的真实 UI 接线。

### E4 pet 运行时注入整族缺失（Phase 17.5 §3.2）— ✅ 已关闭（change `0053`）

- **现象**（四项同根：`src/core/runtime.py` 零 pet 引用）：
  - **跨进程存活**：`entry.py:818` 每次调用**新建** `PetManager()`，进程退出即丢 → `pet gather` 后新进程 `pet list` 看不见、`pet stop` 失效。
  - **依赖注入**：`entry.py:819` `PetActivator(manager=manager)` **未注入** loop/memory/explorer/safety/notifier → `observe()/prefer()` 偏好落不到 L2。
  - **wake 无触发**：即便唤醒，`PetSession` 默认是 echo 的 `DefaultLoop`（非真实 loop）。
  - **三入口**：`ui/api.py` 零 pet 引用 → WebUI 自然语言激活（`activate_from_nl`）未接。
- **关闭动作（已落地）**：`build_runtime` 组装 `Explorer`/`SafetyBounds`/`AsyncNotifier` +
  `PetManager`（落盘 `$CORE_STATE_DIR/pets.json`）+ `PetActivator`（注入 runtime 的 loop/memory），
  `Runtime` 增 `pet_manager`/`pet_activator`；`entry._pet`（CLI）与 `UIAPILayer.activate_pet`（WebUI NL）共用之；
  `PetSession.snapshot()/restore()` 支撑注册表快照恢复（`factory` 使加载记录恢复为活会话）。ADR-0056。
- **前置**：A3（存储选型）已闭。
- **未纳入本变更（记后续）**：① `AsyncNotifier` 无 channel → `flush()` 投递未接（记 **E16**）；
  ② 无后台 daemon（pet 仍显式 `wake`，记 **E17**）—— **已由 change `0065` 关闭**（规格无 daemon 条款，登记为「唤醒由宿主驱动、不常驻」）。
- **已知接受项**：`DefaultLoop` ↔ `LoopPlugin` 协议签名错位（`astream`/`act` 的 async 方向相反）沿用全仓既有
  `cast` 桥接，**非本次引入**。

### E5 主 Agent 自动迭代内部模块 — ✅ 已关闭（change `0084`／ADR-0079）

- **现象**：`phase-17.md:76` 把「自动化迭代闭环本身（主 Agent 自动迭代内部其余模块）」单列为后续 Phase，**此后无任何 Phase 承接** → 从未排期；即 Phase 18 §1.3-D 点名的「Voyager 式自动课程（P2 可选，不实现）」。
- **一手核实（关闭动作的前提）**：闭环**不缺** —— 四阶段（诊断/提案/验证门/留出评测）与**两个驱动面**（loop 收尾节拍、CLI `evolve run`）都已在生产接线；缺的是**「这一轮该迭代谁」**：`Diagnoser` 只有单一信号（本批失败计数）且**并列即弃权**（转人工、无归因），跨轮**无记忆**（刚发布、仍在观察期的插件照样被再次选中）。
- **关闭动作**（落点与信号策略均经用户裁决）：
  ① **落点 = 引擎侧目标生成**（`src/core/evolution/curriculum.py`：`EvolutionGoal` + `CurriculumPlanner.plan`）—— 目标选择是进化引擎的**职责**；loop 侧会倒挂依赖方向（loop 不得依赖 evolution），CLI 侧则只有显式入口有课程（宿主节拍这条**生产默认**路径拿不到 ⇒「自动」落空）。两个驱动面保持「只给机会」的薄壳语义不变。
  ② **信号面封闭**为引擎内部**结构化数据**三层：失败计数（定序）/ 观察期目标（降权）/ 待确认候选（降权）。**不读记忆自由文本**（`MemoryEntry.importance` 缺省恒 0、无结构化教训标记 ⇒ 只能关键词启发式，排序不可解释）、**不调 LLM**（非确定 + 无凭据不可验证 + token 无界 + 失败模式是静默编造）。
  ③ **先验而非裁决**：议程作 `diagnose(prior=…)` 并入分数表，权重**按位次几何递减**（0.5/0.25/0.125…，恒 < 1.0），而每条失败证据计 1.0 ⇒ **任一插件多一条证据即压过先验**；先验**唯一**效果 = **解并列**（今天并列 = 弃权 = 转人工）。降权同理只改并列顺序、不压证据。
  ④ **显式目标是指令**：`core-agent evolve run --goal X` ⇒ `directive` **直接采用**（不被证据改写），仍走完整四阶段 + 验证门 + **人工 `confirm`**（低风险亦须显式确认，不放宽）。
  ⑤ **红线不变**：驱动面仍只有规格「冷路径驱动」的那两个；课程**不常驻**、**不给模型新工具**（模型可见工具仍是 9 个）。
- **接线**：`EvolutionWorker` **缺省自建** planner（只读 `engine.observations` / `engine.pending` 两个既有公开面 ⇒ `runtime.py` **零改动**、生产两驱动面自动开课），可注入替换（对齐既有 `trigger` 惯用法）。
- **规格**：`evolution/spec.md` ADDED「自动课程（目标生成与调度）」+ MODIFIED「对比诊断」「冷路径驱动」（**行为变更已登记**：并列在开课后由先验解；无课程注入时行为不变）。
- **前置**：无（技能迭代闭环 `0045`、冷路径驱动面 `0051`、候选稳定身份 `0055` 均已就位）。

### E6 规格层 deferred 未解除项 — ✅ 已关闭（规格订正 + 两项转出）

| 项 | 结论 |
|---|---|
| context「上下文自动压实」判定仍是启发式关键词，未升级为 LLM 判定 | ✅ **规格已订正**（change `0041`，commit `cb61ef3`）：`context/spec.md` 正文已写明本压实器为**启发式降级路径**（关键词识别结论/决策/未决事项），「LLM 提炼统一由记忆压实通道承担，此处不新增模型调用」——即「启发式」是**规格认定的有意行为**，非未兑现的承诺，deferred 不复存在（memory 侧 LLM 摘要通道已由 `cb61ef3` 实现并接线）。**无代码动作**。 |
| M3 遗留：技能 miss 只沉淀、不复用 | → **A7**（§2 A 类），此处仅备案。 |
| memory 并发压实一致性（规格有实现无） | → **A8**，此处仅备案。 |

### E7 内置工具契约与实现漂移 — ✅ 已关闭（change `0056`，纯文档订正）

- **现象**：`cli-contract-baseline.md:260` 的「内置工具 tools.* 9 个」把 `code_run / web_scan / web_execute_js / ask_user / process / memory` 全列为**未实现**。2026-10-04 实测：
  - `tools.code_run` **已实现**（`tools/builtin.py:187`）→ 文档过时；
  - `web_scan` / `web_execute_js` / `ask_user` / `tools.process` / `tools.memory` 在全仓**零出现** → 不是「未实现」，而是「**从未存在**」；
  - 实际实现集：`file_read` / `file_write` / `file_patch` / `code_run` / `web_fetch`（`builtin.py`）+ `install` / `uninstall` / `list`（`install_tools.py`）→ 与契约基线的**名字与集合都已对不上账**。
- **关闭动作（已落地）**：裁决依据是**层级**而非「谁更新」——`doc/openspec/specs/tool-use` 是规范文件、`cli-contract-baseline.md` 是 Phase 早期 `temp/plan_cli_ops/*` 推演稿（文件自附溯源），故**规格赢**。该 5 个名字在 `src/` 与 `specs/` **零出现**（从未存在），不是「未实现」；真实集合 8 个与规格对得上账。→ 订正 `cli-contract-baseline.md` §10 工具清单 + 头部标注「设计态快照、非规范文件」，**未**按过时清单补实现。
- **前置**：无（裁决已由 change `0056` 完成）。

### E8 CLI 契约基线 §11 未决项 — ✅ 已关闭（change `0056`；第 5 条转出 E13）

来源 `cli-contract-baseline.md` §11（其中「config set 写回 + revalidate」已闭环）：

- `--llm-*` / `--im-*` flag 是否接线（当时三模入口未实现，大概率仅设计态）→ 现状需复核（`--llm.embedding-model` 等已在 `0040` 落地，说明 flag 面已部分接通）。
- `permission-mode` 枚举成员未定（与 **E1** 的权限中间件相关）。
- **secret 校验不对称**：`secret_ref` 不强制非空/可解析 → 「空 secret 也能过校验」。
- `features` 无固定清单 → `--feature` 的补全/帮助无法静态枚举。
- `extra` 透传无校验 → 拼错的配置段名被静默吞进 `extra`，不报「未知配置键」。
- `streamable-http` transport 是否支持（= **B1** 子项）。
- **关闭动作（已落地，逐条定性）**：① flag 接线 —— 实测**已接线**（`_CONFIG_SPECS` 声明全部 `--llm.*`/`--im.*`）；② 已闭合；③ `secret_ref` 不对称 —— **已修**（`im.secret`/`judgment.api_key` 与 `llm.api_key` 同口径：非空 + 可解析）；④ features 无固定清单 —— 定性为**设计如此**；⑤ `extra` 未知键 —— **按用户裁决 B 未收紧**（收紧会拒绝既有自定义段），转出为 **E18**；⑥ streamable-http —— = **B2**；⑦ `permission.mode` 枚举 —— **已定并已强制**（四档 `read-only`/`interactive`/`auto-approve`/`high-risk-block`，校验期拒绝其他取值）。
- **前置**：无。

### E9 其他文档层的未闭合项

| 项 | 出处 | 处置 |
|---|---|---|
| `data-model.md` 待补实体 `Session` / `ExecContext` / `ExecRequest` / `ExecResponse`（「字段以编码阶段落地为准」） | `doc/01-architecture/data-model.md:130-138` | 反过来说明**从未回填** → 文档缺口，编码阶段已过，须补 |
| rag / mcp / git 的「替换 X→零改动」测试锚点待补 | `adr.md:329` | ADT 可替换性**无守护测试** |
| 远程制品仓库与凭证 / market-registry 远端服务 | `adr.md:293,302` | 真后端类 → 归 **C** |
| `doc/00-product/retrospective.md:86-90`「实现落地（src=0 是唯一短板）」 | retrospective | **已过时**（当时 `src/` 为空骨架）→ 属 D 类文档订正 |

#### ✅ 已关闭（change `0061-doc-layer-closeout`）

- **一手核实的关键订正**：四项里**只有两项是真缺口**，另两项本就已在账本他处具名 ——
  ① 四实体**均已落地为真实类型**（`core/im/models.py:27`、`core/constraints/models.py:16/24/34`），
  缺的只是 `data-model.md` 回填；② 三条替换性锚点**测试早已存在**
  （`Retriever(_FixedEmbedder(), store)` / `MCPClient(transport_factory=…)` / `GitClient(backend=FakeBackend())`），
  原判「ADT 可替换性**无守护测试**」**不成立** —— 缺的是 `test-cases.md` 的**追踪号**（规格→用例不可达）。
- **关闭动作**：`data-model.md` §4 按源码回填四实体（含权威位置 + 字段，可一步核对）；
  `test-cases.md` 补 `TC-RAG-10` / `TC-MCP-06` / `TC-GIT-11` 三条（挂靠三条「…依赖注入隔离」Requirement）；
  ADR-0040 后果行与 `retrospective.md` §六.1 各加**日期补记**（历史正文不改写 —— 那是伪造决策记录）。
- **改判归属**：远程制品仓库/凭证 与 market-registry 远端服务 → **C 类**（§5 已具名，非文档缺口）。
- **规格中性**：规格/接口/源码三者本就一致，本变更只补登记层 → `skip_specs: true`，`src/`+`tests/` **零改动**。
- **有意不造重复用例**：`_FixedEmbedder` / `FakeTransport` / `FakeBackend` 就是「替换 X」本身，
  再造同义测试是重复建设；rag「替换向量库」一侧仅单实现（生产 sqlite-vec → C 类），追踪行**如实标为半覆盖**。

### E10 功能开关无运行时门控（Phase 0 验收未达成）— ✅ 已关闭（change `0067`，ADR-0065）

- **现象**：`phase-0.md:32` 要求「未启用的模块**完全不初始化**」。实测 `ConfigManager.is_enabled` 的缺省 off 语义已实现并测试（`tests/test_configuration.py:85`），但 `runtime.py` 的 `build_runtime` **无条件构造全部模块**——无门控、无「未启用则不构造/不注册」证据。
- **根因**：Phase 0 只交付配置侧开关语义，运行时侧门控从未接线（Phase 13 组合根建立时也未补）。
- **裁决**：用户选「**可选模块缺省开**」（兼容现状）——门控名单内模块未声明即装配，仅显式 `features.<模块>: false` 才关闭。**口径订正**：phase-0「功能开关缺省关闭」的字面与裁决不符，规格订正为「白名单内缺省开」。
- **关闭动作**（change `0067`）：门控名单 `runtime.GATABLE_MODULES = ("pet", "beast", "evolution")` 归**组合根**单一真源（配置层不认识模块名）；新增 `ConfigManager.is_disabled`（极性相反、用途不同；`is_enabled` 语义不变）；三处装配点按名单裁剪——`beast` 关闭时**连 `register_innate_skills` 也不做**、`pet` 关闭时不读状态文件、`evolution` 关闭时 `cold_path=None`；7 个 CLI 入口（`evolve run/pending/confirm/reject`、`pet *`、`summon`/`recall`）统一拒绝并退出 0（说明含模块名与开关名）。18 例新测试（含「关闭时空面」与「缺省即装配」对照，证明否定断言非空转）。
- **分层**：`features.pet`（装配，缺省开）与 `pet.enabled`（启用，缺省关）**两层并存**、不重复；核心模块（`runtime`/`loop`/`memory`/`tools` 等）不在名单，不可关。
- **遗留**（本次走查新报，见 §1 表 E20/E21）：① `features` 未知模块名无告警（**E20① 已由 change `0085` 关闭** —— 规格先行 + 组合根注入已知模块名集合、仅告警）；**取值强转（E20②）与 CLI 面零消费（E23）已于 change `0072` 关闭**（ADR-0069：三面取值同口径 + `--feature` 接入优先级链；`--feature` 此前**零消费者**、`off`/`"false"` 等被 `bool()` 当作开启）；② `entry._pet` 的 `pet.enabled` 判据**忽略 config.yaml**（`resolve(cli=, env=)` 无 yaml 层），违反文档优先级链 —— **E21 已于 change `0070` 关闭**。

### E11 LLM 可靠性：连接复用缺失 + 重试/超时/降级/断流无测试（Phase 1 验收未达成）

- **现象**：`phase-1.md:30` 要求「失败自动重试、超时控制、服务降级、**连接复用**、流式断流处理」。实测：`stdlib_provider.py:81-122` 已有重试/退避/超时/降级/断流**代码**，但**无任何对应测试**；且「连接复用」**未实现**——`urllib` 每请求新建连接，无 keepalive / 连接池。
- **根因**：核心零三方依赖红线下的 stdlib 手写 provider，可靠性面只做到"能跑"，未做连接复用（需 `http.client` 长连接或自建池）。
- **关闭动作**：① 补可靠性用例（重试次数/退避、超时、降级、断流半包）；② 连接复用单独立项（涉及自建池，属实现变更，须 spec delta）。
- **前置**：无（① 可随时做；② 需定夺是否值得为 stdlib provider 自建连接池）。

#### ✅ ① 已关闭（change `0060-llm-reliability-tests`）

- **关闭动作**：`tests/test_llm_provider.py` 增「模型调用可靠性」节 **9 例**，按规格「模型调用可靠性」逐 Scenario 对应：退避口径（指数 + 8s 封顶）／重试（瞬时错误重试至成功、耗尽抛归一化异常、非可重试错误不重试）／超时（慢调用不挂起调用方，实测耗时断言）／降级（切备用模型 + 审计记**实际成功**的模型；非瞬时错误不降级）／断流（无 `[DONE]` 提前结束部分返回、传输中途异常**先给已收内容再抛**）。
- **关键事实**：**9 例一次全绿** —— 可靠性实现本就正确，Phase 1 未达成的直接原因是**缺验证**；故本变更 `src/` **零改动**（规格中性，`.openspec.yaml: schema: spec-driven + skip_specs: true`，本仓首个合法的无 delta 变更）。
- **接缝**：重试/超时/降级打桩 `_call_provider`（保留 `acompletion` 的重试循环/`wait_for`/`models` 遍历）；断流打桩 `urlopen`（让真实 `_iter_sse_payloads` 参与，且必须传**惰性生成器**——`list()` 会让异常在进 provider 前就抛，等于没测）。
- **衍生机制**：`skip_specs` 需与 `schema` 同现方被采信（仅 `skip_specs` 报 `expected string, received undefined`）——已由临时 `0060-probe` 探针核实，记入该 change design §4。

#### ✅ ② 已关闭（change `0066-llm-connection-reuse`／ADR-0064）

- **裁决与形态**：用户 2026-10-05 裁决**实现（stdlib 零依赖）**。**关键判定：这是「规格要求 X 而实现没有」**（与 E12 同型）—— 规格「模型调用可靠性」正文已声明「底层连接复用（connection reuse / keep-alive）」，场景「连接复用」逐字要求「复用底层 connection / keep-alive 连接，减少握手开销，**连接失效时自动重建**」⇒ **改代码向规格靠拢，不订正规格、不删条款**（对比 E17/E19 的「文档过度承诺」型）。
- **实现**：新增 `src/core/llm_provider/http_pool.py` —— `HTTPTransport` 协议 + `HTTPConnectionPool`（`http.client` + `ssl`，均 stdlib）。**线程本地按 origin 复用**（空闲连接存 `threading.local()`，无锁；provider 同步传输本就在工作线程上跑，同线程连续调用即复用）；**失效重建恰一次**（`RemoteDisconnected`/`BadStatusLine`/reset/broken pipe，且仅在「复用连接」上、且尚未收到任何响应字节 ⇒ 不重复计费副作用）；**代理与 3xx 回落 `urlopen`**（`http.client` 不读代理环境变量、不跟随重定向）；**非 2xx 转 `urllib.error.HTTPError`**（既有状态码映射零改动）；**读尽才归还**（SSE 中途停止 ⇒ 关闭丢弃）。`StdlibLLMProvider(transport=...)` 为注入接缝（ADR-0040 的 DI 边界），三条传输路径（chat/embedding/SSE）统一走 `transport.send(...)`。
- **错误口径**：`map_http_error` 补 `(OSError, http.client.HTTPException) → LLMNetworkError`（顺序在 `URLError` 之后；否则连接池路径会把「拒绝连接」落成**不可重试**的裸 `LLMError`）。
- **测试**：新 `tests/test_llm_provider_reuse.py`（9 例，**真实本地 `http.server` 桩**在 `setup()` 计 accept 数）：两次调用 1 条连接（规格场景的可证伪形式）/ embeddings 共用 / 按 origin 分键 / 服务端静默关连接后自动重建 / 429 与拒绝连接归一 / 3xx 与代理回落 / SSE 走同一传输层。确定性：协程跑在**单工作线程**事件循环（`set_default_executor(max_workers=1)`），不靠时序。既有 8 个 mock `urlopen` 用例平移为注入假传输（断言口径逐字不变）。四门全绿（805 passed）。
- **规格中性**：`skip_specs: true` —— 规格无需改（本变更实现其已声明条款），差距闭合记在账本即此处。

---

### E12 崩溃恢复无真实 `kill -9` 用例（Phase 2 验收部分未达成）

- **现象**：`phase-2.md:122` 要求「崩溃恢复测试：`kill -9` 后重启，`resume()` 恢复且无重复副作用」。现有覆盖是**内存 store 模拟**的 resume 幂等单测（`tests/test_durability.py:55,67`），**无真实进程 `kill -9` + 子进程重启**的端到端用例。
- **根因**：durability 用例跑在进程内（快而稳），真实崩溃语义（半写日志、store 未 flush、锁残留）从未被验证。
- **关闭动作**：补 subprocess 用例——子进程写一半被 `SIGKILL` → 重启 → `resume()` 恢复且副作用不重复。
- **前置**：无（低成本，可顺手在 E1 之前做）。

#### ✅ 已关闭（change `0062-crash-recovery-e2e`）

- **关键发现：不只是缺用例，是**实现偏离规格**。一手读 `store.py:77-91`：`_persist` 用
  `Path.write_text` —— **先截断、再整写全量** `checkpoints.jsonl`。进程在截断后、写满前被终止
  → 文件空/半写 → `_load` 跳过不可解行 → 既有检查点**整体丢失**，直接违反 durability 规格
  「崩溃恢复」正文「**已持久化结果不丢失**」。生产已接线（`runtime.py:563`），非死代码。
- **关闭动作**：① 规格「崩溃恢复」MODIFIED —— 明确写入 SHALL 为**原子提交**（半写不损坏既有集合）
  + 新增场景「持久化写入原子性」「真实进程崩溃后续跑」；② `_persist` 改原子提交
  （同目录 tmp + `os.replace`，stdlib；成功路径行为/格式/路径不变）；
  ③ 新增 `tests/test_durability_crash.py`：真子进程 `SIGKILL` 端到端（重载 → `restore()` 取最近有效
  → 按**调用方游标** `resume()` 不重复副作用）+ 半写不损坏（**旧实现必红**，已实测复现：
  `assert [] == ['8d29b2ce…']`）。
- **语义归属不变**：跨进程「不重复副作用」由**调用方游标**（检查点快照状态）保证 —— 本变更把这条
  分工**验证**出来，未改 `resume` 口径（同句柄一次，进程内）。
- **不做**：fsync/掉电语义（`os.replace` 保的是**进程崩溃**原子性，即 E12 场景）；其他持久化点
  （memory/skills/pending）不顺手扩面。
- **衍生新报**：**E19**（下方）—— durability 模块文档 §5 承诺的「持久化故障降级为内存环形缓冲 +
  异步重试落盘」在实现中不存在。

---

### E13 `Validator.parse_output` 零生产调用方 — ✅ 已关闭（change `0063`，判定「有意不接线」）

- **现象**：`Validator.parse_output`（`constraints/validator.py:66`）零生产调用方；
  `LLMPlanner._parse`（`loop/planner.py:201-246`）自解析（`json.loads` + `_PARSE_FAILED`）。
- **一手核实的关键订正**：**规格该 Requirement 已被别处满足**。`specs/constraints/spec.md`
  「输入输出校验」要求「调用后把自由文本解析为结构化指令，解析失败绝不带病执行」，其生产实现是
  **动作感知**的 `LLMPlanner._parse`：原生 `tool_calls` 优先；失败产出 `Action(args={"reply":
  "LLM_PLAN_PARSE_FAILED: …"})` —— reply 是**终止 Action**（`loop/default.py` 的 `act()` 对
  `is_terminal` 直接返回参数）⇒ **工具不执行**；失败 reply 作为观察回灌 ⇒ 下一轮模型看到原因
  ⇒ 即规格场景的「不执行，请求模型修正」。
- **为何 `parse_output` 不该接线**：它是**无动作语义**的通用 JSON 解析（只保证解析出对象，
  判不了 `tool_id` / `reply` 契约、也不认原生 tool_calls）；接进 planner 会让「参数 JSON 损坏」
  这类可归因错误退化成「解析出 dict 就当动作」——**降级**。故是「**不该用**」而非「没用上」。
- **关闭动作**：`constraints-interface.md` §2 把原一句无因断言扩为**判定**（含规格该 Requirement
  的实现归属）；`doc/02-modules/constraints.md` §3.1/§5 指向生产实现；`test-cases.md` 补
  `TC-CONS-05`（此前景规格→用例不可达）；保留 `parse_output` 为中间件契约输出侧 API（有单测）。
- **明确不做**：下沉 planner 解析到 `Validator`（降级，见上）；删 `parse_output`（契约 API，有测试背书）。
- **前置**：无。

### E14 校验码重复 — ✅ 已关闭（change `0059`，ADR-0062）

- **现象**：同一套「schema / 类型 / 必填」校验有两份实现——`tools/provider.py:_matches_type` 与
  `constraints/validator.py:_matches_type` **逐字节相同**；`ToolProvider._validate_args` 与
  `Validator.validate_input` **语义逐行等价**（同 `required` 早返回、同 `properties` 遍历、同消息模板）。
  这是 E1 走查的残留：E1 订正「校验空转」后确认校验实由**工具层**承担，而 `Validator` 是同一口径的
  **第二份实现**（其 `before` 从未接进 loop 链，ADR-0055「有意未接」）。
- **关闭动作（已落地）**：真源留 `constraints`（该义务在 constraints spec 中即其 Requirement）→
  `ToolProvider._validate_args` 改为委托 `Validator().validate_input(tool_id, args, schema)`，
  删除 provider 内 `_matches_type` 副本。**行为中性**：拒绝码 `INVALID_ARGS` 与两条错误消息逐字不变
  （`validate_input` 把缺参列首位、`properties` 序一致 ⇒ `errors[0]` 恒等于旧实现早返回那条）。
- **方向核验（一手）**：`tools → constraints` 合法——`tests/test_architecture.py` 的 `BASE_MODULES`
  不含 `tools`；phase1 禁集只有 `tools → {memory, llm_provider}`；phase2 禁集只有
  `constraints → {loop, skills, orchestration}`；`constraints` 全包不 import `tools`（无环）。
  与 change `0052` 的 `loop → constraints` 同型（横切能力被使用方 import）。
- **验证**：`tests/test_tool_use.py` 增结构守护（`core.tools.provider` 不再有 `_matches_type`）
  + 行为等价（缺参 / 错型两条路径拒绝口径一致）+ 合法参数两条路径皆通过；四门全绿（780 passed）。
- **明确不做**：`Validator.parse_output`（planner 自解析、零调用方 → **E13**）；不改 `tool-use` 规格
  （行为中性，口径只在 constraints 侧记一次）。

### E15 熔断阈值/冷却不可配 — ✅ 已关闭（change `0068`，ADR-0066）

- **现象**：`ConstraintsChain` 的构造面（`failure_threshold` / `cooldown_s`）本就是为注入而设计
  （`constraints-interface.md` 自述「可注入便于测试」），但生产唯一调用点 `runtime.py` 不传任何参数 ⇒
  硬编码类缺省 **5 次 / 30 秒**，运维无法按环境调整；`configuration/` 无 `constraints` 段（E1 走查记后续）。
- **关闭动作（已落地）**：① `manager.py` 增两条 `ConfigSpec`（`map_to="constraints.*"`，缺省 5 / 30.0）
  ⇒ CLI flag / env / yaml / §2.3 未知段白名单**全部自动派生**（单一真源）；② 新增访问器
  `ConfigManager.circuit_breaker() -> (int, float)`；③ `validate_schema` 增取值校验（阈值 **≥1 整数**、
  冷却 **≥0 数值**），非法即报错**阻断启动**（不静默兜底）；④ `runtime.py` 经访问器读出后传入
  `build_constraints_chain`，主 loop 与子 agent loop 仍**共享同一链实例**（熔断态 per-runtime 语义不破）。
- **不新增结构化段（决策）**：镜像 `permission.mode` 的 **`extra` 驻留**先例，而非加 `ConstraintsConfig` 段 ——
  避免改配置规格里「五个结构化段」的字面枚举，且 `map_to` 前缀已让白名单自动收纳 `constraints`。
- **验证**：`tests/test_constraints_config.py` 17 例（缺省 / yaml / env / CLI 优先级 / 非法 5+3 参数化 /
  不静默兜底 / 无未知段告警 / 组合根注入 identity / 端到端阈值驱动生产熔断）；四门全绿（840 passed）。
- **明确不做**：`features` 值强转（E20② 已随 change `0072` 关闭、**E20① 已由 change `0085` 关闭**）、
  RetryPolicy/Fallback 可配、半开试探参数（无生产需求）。

### E20① `features` 段未知模块名无告警 — ✅ 已关闭（change `0085`／ADR-0080）

- **现象**：`features` 段子键是**模块名**，模块名集合归组合根（`runtime.GATABLE_MODULES`，ADR-0065）。
  校验口径只到顶层段名 ⇒ `features.peet: false`（拼错）被照样归一，而 `is_disabled("pet")` 查的是
  `"pet"`（`features.get("pet") is False` ⇒ 假）⇒ **pet 照旧装配、静默 no-op**（用户以为关了）。
- **根因（一手核实）**：`validate_schema` 的 `_unknown_section_warnings` **只看顶层段名**（规格
  `configuration/spec.md` 逐字「告警口径 SHALL ONLY 作用于顶层段名，不递归校验已知段内部的未知子键」）；
  `features` 归一在 `_normalize_features`、**不校验键名**；模块名集合**不在配置层**（E10 归属）。
- **关闭动作**：**规格先行** —— MODIFIED「配置校验与生效」给顶层段名口径加**唯一例外**（`features`
  子键按**经注入的已知模块名集合**校验、未知**仅告警**、未注入不校验）+ 两新场景；实现
  `ConfigManager(known_modules=…)`（缺省 `None`=不校验，向后兼容）+ `_unknown_feature_warnings`
  （**仅告警不阻断**，同 E18 口径）；**单点注入** —— `entry._config_manager` 收口 10 处
  `ConfigManager(...)` 构造点，注入 `GATABLE_MODULES`。
- **归属守住**：集合仍归组合根单一真源，配置层**只消费注入**（不 import runtime、不硬编码模块名）⇒
  不逆转 ADR-0065。作用域**仅** `features`（其它段子键不校验，各能力 schema 义务）。
- **前置**：无。

### E17 pet 无后台 daemon（E4 收口时记后续） — ✅ 已关闭（change `0065`；判定「规格未要求」）

- **现象**：`PetSession.wake()` 生产**零调用方**（仅测试）；接口 §5 / 模块 §4 却写着「主循环之上叠加
  **后台自治调度**」——读者会以为内核里有常驻调度者，实际没有。
- **一手核实（三条，决定形态）**：① **规格无 daemon 条款** —— Lifecycle 只写「**每次唤醒**复用
  `Loop.run()` 同步薄壳逐次执行」，Yielding 明写让行模型是「**同步 + 锁（RLock）**，宠物让行不抢锁」；
  ② 文档**自述即「不常驻」**（`pet-mode-interface.md:138`、`pet.md:39`）——「后台自治调度」是**文档层
  过度承诺**（无组件承载），与 E19 同型；③ `core-agent pet <verb>` 是**一次性进程**（`entry._pet`：
  装配 → 激活 → 打印 → **退出**），进程内线程**必随进程结束**，唯一可承载常驻驱动的是 `ui serve` 长驻进程。
- **性质判定**：**「文档描述了 X，规格没要求、实现也没有」**（⇒ 订正文档承认现状），**不是**
  「规格要求 X 而实现没有」（⇒ 先改规格再改代码）。与 E12 的区别即在此。
- **用户裁决（2026-10-05）：规格中性收口**（不实现 daemon）。
- **关闭动作（已落地，纯文档）**：`pet-mode-interface.md` §5 表后新增「驱动归属」块、`pet.md` §3.2/§4
  同口径登记 —— `wake()` 是**同步薄壳、由宿主按周期调用**，内核**不自建调度线程**（三条理由：规格无条款 /
  一次性进程无法承载 / 仅长驻宿主可承载）；并写明**将来若要内核常驻须先补规格**（driver 需求 +
  `BACKOFF→ACTIVE` 复位语义 + 配置门控，E10 同族）。
- **前置**：无。

---

### E18 `extra` 未知配置键无校验（E8 第 5 条转出） — ✅ 已关闭（change `0064`；ADR-0063）

- **现象**：`AppConfig.extra` 收纳「五类结构化段之外的一切」，拼错的段名（如 `llmm:`）被**静默**吞入，
  不报「未知配置键」——用户看到的是「LLM 配置缺失」这类**误导性**报错，与真实根因相隔一层；
  `permission.mode` 亦寄居其中。
- **根因**：`extra` 是设计态的宽松兜底；收紧为白名单会**拒绝既有自定义段**（改变既有接受行为，change `0056` 已否）。
- **用户裁决（2026-10-05）：仅告警（WARN 不阻断）** —— 把「宽松接受」与「错误可见」解耦：
  接受行为不变（不破坏），但拼错段名不再隐形。
- **关闭动作（已落地）**：`configuration` spec「配置校验与生效」MODIFIED（增「未知配置段 SHALL 仅告警」
  正文 + 场景「未知配置段仅告警不阻断」）；实现 = `ValidationResult.warnings`（`errors` 阻断 /
  `warnings` 仅提示，两语义分开）+ `validate_schema` **产出**告警（纯谓词，无副作用）+ `load()`
  **发出**（stdlib `warnings.warn(..., stacklevel=2)`，一处发出、CLI 与库调用方都可见）；
  已知段白名单 `_known_sections()` = 五个结构化段 ∪ `ConfigSpec.map_to` 前缀 ∪ 寄居 `extra` 但有运行时
  语义的 `permission` —— **由单一真源派生**，不另立清单（免与 `_CONFIG_SPECS` 漂移）；
  **段不丢弃**（仍留 `extra`，无既有消费者受影响）。
- **口径边界**：**只到顶层段名** —— `llmm:` 告警、`llm.endpont:` 不告警（子键未知可能是前向兼容扩展，
  逐能力判定，属各能力的 schema 义务；判到子键 = 要求「配置全量 schema 化」）。
- **前置**：无（形态已由用户裁决）。

---

### E19 durability 文档承诺的「持久化故障降级」未实现 — ✅ 已关闭（change `0063`；走查来源 change `0062`）

- **现象**：`doc/02-modules/durability.md:74`（§5）称「持久化本身故障（磁盘满 / 后端不可用）不得阻塞
  主循环：**降级为内存环形缓冲，异步重试落盘**」；实现 `CheckpointStore._persist` 失败**直接抛出**。
- **一手核实的关键事实**：该承诺**规格里从来没有** —— 逐字核对 `specs/durability/spec.md`，只有
  「崩溃恢复（含 `0062` 的原子提交）」「检查点损坏降级」两条；过度承诺仅存在于**模块文档**。
  故本项**无规格可订正**，属纯文档订正（规格中性）。
- **关闭动作（用户裁决：订正文档承认现状）**：`durability.md` §5 改写为实际策略 ——
  持久化故障**不静默降级**（直接抛结构化错误，不把「写失败」伪装成「已落盘」）；
  「不得阻塞主循环」的关切由事实兜底：检查点在**波次边界**回调创建（`scheduler.py:226-227`），
  **不在主循环热路径**上，失败即该波中止 → 由 orchestration「断点续跑」承接。
- **明确不做**：实现环形缓冲 + 异步重试 —— 静默降级会**掩盖磁盘满**（与「已持久化结果不丢失」
  的规格精神相悖），且需为一条无生产需求的愿景引入后台线程 + 两套真源（内存 buffer vs 磁盘）。
- **前置**：策略裁决（已裁决）。

### E21 `entry._pet` 的 `pet.enabled` 判据忽略 config.yaml — ✅ 已关闭（change `0070`）

- **现象**：`entry.py:954` `resolve("pet.enabled", cli=cli, env=os.environ)` **漏 `yaml=` 参数**
  ⇒ CLI 前置判定只看两层（CLI/env），永远看不到 `config.yaml`；`pet.persons_dir`（:960）同病，
  被静默忽略、回落 cwd 下的 `./persons`。而**同一进程**稍后的 `build_runtime(ConfigManager(...))`
  走 `load()`（**含 yaml 层**）⇒ **同一次调用内两套判据**。
- **根因**：`resolve` 的 `yaml=` 层缺省为空映射，调用方须自行提供 yaml 层；`_pet` 未提供
  （`config get`（:372）同型 —— 见 §1 表新行 **E22**）。
- **裁决**：属「**规格要求 X、实现没有**」型（同 E11②/E12/E15）⇒ **改代码向规格靠拢，规格不动**。
  规格「宠物模式配置」明文要求经 `resolve()` 优先级链（CLI flag > env > config.yaml > 默认值）
  读取且「**禁止 pet 配置绕过 ConfigSpec 另起解析**」，场景「pet 配置经 ConfigSpec 声明」要求
  「CLI flag / env / yaml **三面一一对应**」。
- **关闭动作**（change `0070`，`skip_specs`）：
  ① 新增 `ConfigManager.config_value(key)` —— 装配前**只读单键**解析（CLI > env > yaml > 缺省），
  与 `load()` 共用 ConfigSpec 单一真源；**不校验 / 不阻断 / 不缓存**，`config.yaml` 缺失按
  「无 yaml 层」处理（**若在此处抛错，CI 无 config.yaml 时 `pet gather` 会由退出 0 变退出 1**）；
  ② 配套 `_flatten_by_specs` —— yaml 层以 `spec.key` 为键，而文件按 `map_to` 嵌套
  （`im.corp-id` vs `im.corp_id` 不同名），故经单一真源逐键取路径回填；
  ③ `entry._pet` 门控与 `persons_dir` 改用 `config_value`，`ConfigManager` 提前构造一次并**复用**给
  `build_runtime`（同实例，不重复读盘）；`_as_bool` 归一化保留（`config_value` 返回各层原文）。
- **验证**：先红后绿 —— `tests/test_entry.py::test_pet_yaml_admits_and_honors_persons_dir`
  在改 `entry.py` 前**实测失败**（yaml 的 `true` 被判为未启用）；`tests/test_entry.py` +3 例
  （yaml 采信 + persona 目录取自 yaml / env 压过 yaml / 缺文件容错）、`tests/test_configuration.py`
  +5 例（yaml 层 / 三层链 / 缺省兜底 / 缺文件 / 键名与 `map_to` 不同名）；四门全绿（848 passed）。
- **转出**：`config get` 同型缺陷登记为 **E22**（本变更**不改** —— 开发机存在本地 `config.yaml`，
  且 `test_config_get_default` 断言缺省值，改动会变更该命令在开发机的输出语义，须单独裁决）。

---

## 4. B 类：Phase 12 MCP（B1 client 侧 + B3 服务端 stdio + B4 CLI 接线 + B5 白名单配置 + B6 标准 envelope + B7 默认暴露面收窄 + B8 远端错误码映射 已关闭，余 B2 http 会话 1 行）

- **范围**：transport 生产实现（stdio/http）、client 安装分流、消费侧安全接线（本地 stdio 过 `SandboxManager`、远端 http 走出站白名单、不可逆工具走确认门）。

### B1 MCP client 侧：stdio 传输 + 安装分流 + 消费侧安全接线 — 🔶 部分关闭（change `0054`）

- **已关闭（change `0054-mcp-stdio-transport`，2026-10-04，**ADR-0057**）**：
  ① `StdioTransport` —— stdlib 手写换行分帧 JSON-RPC（`subprocess.Popen` + 读线程 + `queue` 超时按 `id` 配对），**零新依赖**；
  ② `SandboxManager.spawn(cmd, env, budget) -> Popen` —— 常驻子进程受 rlimit 约束，`permission` 仍是内核沙箱唯一 owner（复用 `_apply_resource_limits`，不重复实现）；
  ③ `build_transport` 按端点分派（stdio → `StdioTransport`；http/streamable-http → `build_http_transport`；未知 → 结构化 `MCP_CONNECT_FAILED`），**原占位抛错消除**；
  ④ `MCPClient.add` 按来源形状分流（`http(s)://` → http 端点，命令行 → stdio 端点；显式 `transport`/`command` 覆盖推断）+ ctor 注入 `sandbox`/`budget`/`policy`；
  ⑤ `MCPClient._call` 直通传输层结构化 `MCPError`（不再被兜底分支重包为 `MCP_UNAVAILABLE`）；`connect` 失败即 `close` 传输（不留半开连接）；
  ⑥ `plugins/install.py:_install_mcp` 传 `transport`/`command`/`args`（原硬编码 http 且丢参）；
  ⑦ 组合根装配 `SandboxPolicy → SandboxManager(policy=…) → MCPClient(sandbox=…, policy=…)` 并注入 `InstallDispatcher`；`Runtime` 增 `mcp_client` 字段；
  ⑧ `pyproject.toml` optional extra `mcp = ["mcp>=1"]`（ADR-0043 的 http 半边依赖声明）。
- **消费侧确认门经验证已成立**：`MCPToolAdapter` 适配的远端工具带 `coeffects=["network:outbound"]` + `reversible=False`，`PolicyEngine` 对 `network:` 前缀判 `HIGH_RISK` → `PermissionGuard.confirm` → `GateDecision("confirm")`。**无需新代码，仅补验证用例。**
- **ADR-0043 订正**：ADR-0043 字面写 stdio 用 `asyncio.create_subprocess_exec`，实际按同步 `Transport` 契约（`connect/call/ping/close`）落为**同步 stdlib**（`SandboxManager.spawn` + 读线程），已由 **ADR-0057** 记录理由（全 MCP/工具链同步，引 asyncio 会污染调用面）。
- **原阻塞原因（已解除）**：mcp SDK 离线不可装 + 「核心零第三方运行时依赖红线」→ 已由 ADR-0043 裁决（stdio stdlib 手写；http 懒 import 可选 extra）。
- **原现状（已消除）**：`build_transport` 占位抛 `MCP_CONNECT_FAILED` 与 `MCPClient.add` 硬编码 http 两条，均已在 `0054` 消除。

### B2 远端 http/streamable-http 会话 — ⏭ 待开工

- **残留**：`build_http_transport` 目前只完成**可离线验证的半边** —— 出站白名单守卫（非白名单 host → `PERMISSION_DENIED`）、SDK 缺失的清晰降级（`MCP_CONNECT_FAILED` 提示 `pip install core-agent[mcp]`）、已装 SDK 时明确报「会话待接入」。**真正的 http 会话未实现**（`Mcp-Session-Id` 复用、SSE 流解析、`headers` 透传）。
- **阻塞**：`mcp` SDK 为可选依赖，当前环境离线不可装 → 无法端到端验证，按 CLAUDE.md §2 不留投机实现。
- **附**：`pyproject.toml` 的 `[project.optional-dependencies].mcp = ["mcp>=1"]` 已随 change `0054` 声明，但 **`uv.lock` 未含该项**（本环境离线；`uv lock --offline` 会把既有 1600 行解析结果误删，已回滚）→ **联网后需执行 `uv lock`** 使锁文件与 `pyproject.toml` 一致。

### B3 `MCPServer.serve` stdio 事件循环 — ✅ 已关闭（change `0073`）

- **现象**：规格「MCP Server 模式」场景「stdio 本地挂载」要求外部 agent 以 stdio 拉起本 server → 握手 →
  取工具列表 → 调用；`MCPServer` 的方法级行为（`initialize`/`list_tools`/`call_tool`/白名单/会话分流）
  早已实现并有单测，但**没有事件循环**把 JSON-RPC 接到它们上 —— `serve()` 只构造连接即返回
  （docstring 自述「stdio/http 事件循环在 M2 接入」），CLI `mcp serve` 落 `_dispatch` 兜底分支
  ⇒ **规格场景在生产不可达**（能力只存在于单测的直接方法调用里）。
- **同类发现（文档已写、代码缺席）**：`07-mcp-server/mcp-server.md` §4 与接口 §6 均写「包装为 MCP tool
  （`core.<tool>`）」，而 `list_tools` 吐**裸** `tool_id`（无前缀隔离）；且**无二级代理防护** ——
  client 侧已发现的 `mcp.*` 远程工具会被原样再暴露（两个 core-agent 相互挂载即递归放大暴露面）。
- **裁决**：属「**规格要求 X、实现没有**」型（同 E12 / E11② / E15 / E21）⇒ **改代码向规格靠拢**；
  `mcp` spec「MCP Server 模式」「工具暴露与白名单」**MODIFIED** + 4 个新场景。
- **关闭动作**（change `0073-mcp-server-stdio-loop`，2026-10-05，**ADR-0070**）：
  ① `MCPServer.serve_stdio(endpoint, *, stdin, stdout)` —— 换行分帧 JSON-RPC 事件循环（stdin 逐行读 /
  stdout 逐行写、日志走 stderr），按 `id` 应答 / 无 `id` 通知不应答 / 非 JSON 行跳过 / **EOF 退出**；
  `stdin`/`stdout` 可注入 ⇒ 循环行为**纯内存**可验（无需子进程）；
  ② **错误分层**：协议层走 JSON-RPC `error`（`-32601` 未知方法 / `-32603` 内部异常），工具层走成功应答里的
  `CallResult`（`PERMISSION_DENIED` 等）；`_respond` **永不抛** —— 单条请求的任何异常（含提供者抛错、
  应答不可序列化）降级为该 `id` 的错误应答，**循环继续**；
  ③ **暴露面三件套**：对外名 `core.<tool_id>`；白名单接受裸名与带前缀两种写法（照 `tools/list` 抄名字可用）；
  `mcp.*` 过滤（禁二级代理）；`call_tool` 只接受已暴露名；
  ④ **协议常量同源**：`PROTOCOL_VERSION` 落 `core.mcp.models`（弃 client 侧私有 `_PROTOCOL_VERSION`），
  client 判定与 server 应答不再各写一份字面量；
  ⑤ `entry._mcp` / `_mcp_serve` / `_mcp_whitelist` + `mcp serve --whitelist`（逗号分隔）+ `_HANDLERS` 注册；
  非 stdio 传输**明确拒绝**（不静默起空 server）。
- **验证**：先红后绿 —— `tests/test_mcp_server_stdio.py`（新，14 例）实现前因 `PROTOCOL_VERSION` 缺席即
  `ImportError`（红），实现后全绿；含**端到端**（本仓 `MCPClient` / `StdioTransport` 拉起 `core-agent mcp serve`
  真实子进程：握手 → 发现 → 真读文件 → 越权拒绝）与 CLI 面（CSV 解析 / 传输拒绝）；既有
  `tests/test_mcp.py` 的 4 例 server 单测对齐 `core.` 命名空间契约。四门全绿（900 tests / 29 specs）。
- **转出**：**B6**（wire envelope 未对齐标准 ⇒ 第三方客户端挂载受限）、**B7**（默认暴露面启发式过粗）。
- **参考**：`archive/2026-10-05-0073-mcp-server-stdio-loop/`。

### B4 `mcp` CLI 接线 + 端点注册表持久化 — ✅ 已关闭（change `0074`）

- **现象**：规格「MCP Server 安装与移除」五条场景全部以 CLI 为锚（`WHEN 执行 mcp add`），而 `entry._mcp` 对非
  `serve` 子命令落「已识别，尚未接线」兜底 ⇒ **场景在生产不可达**（与 B3 同型的「CLI 面缺席」）。
- **根因**：安装管线本身齐备（`0054`：`MCPClient.add` → 适配 → `ToolProvider.register` / `remove` → 反注册 + `close`
  终止子进程），缺的是三件**外围**事：① **CLI → installer 接线**；② **跨进程持久化** —— CLI 是**一次性进程**，
  `PluginInstaller._assets` 随进程蒸发，`mcp add` 的成果无处可寻；③ **稳定工具命名** —— `connect` 以 `uuid4().hex`
  作 `handle_id`，工具名 `mcp.<uuid>.<工具>` **每次装配都不同**，与 `02-modules/mcp.md` §3.1「包装为
  `mcp.<server>.<tool>`」明文不符。
- **裁决**：属「**规格要求 X、实现没有**」型（同 E12/E11②/B3）⇒ **改代码向规格靠拢**，`mcp` spec 相应
  **MODIFIED**（补 CLI 形状 + 持久化 + 装配期注册 + 降级四组约束条款）。
- **关闭动作**（change `0074-mcp-endpoint-registry`，2026-10-05，**ADR-0071**）：
  ① `src/core/mcp/endpoints.py`（新）：`mcp_endpoints_path()` / `EndpointRecord`（+`manifest()` 单一解析点 /
  `asset()`）/ `default_endpoint_name()`（`--name` > URL 主机名 > 命令基名）/ `MCPEndpointRegistry`
  （`list`/`get`/`add` 重名拒 / `remove`，**原子写** tmp + `os.replace`；损坏与残缺条目**告警降级**）；
  ② `MCPClient.connect(endpoint, *, handle_id=None)`：命名安装以**安装名**作句柄（工具名跨进程稳定）；
  `add` 内先 `remove(name)` 释放旧连接（同名重装不得漏关子进程/socket）；
  ③ `errors.py` 增 `ENDPOINT_NAME_CONFLICT`；
  ④ `runtime.py`：装配期读注册表 → 逐端点经**同一安装管线**安装，**单端点异常只 `warnings.warn` 跳过**；
  ⑤ `entry.py`：`_mcp_add` / `_mcp_list` / `_mcp_remove` + `mcp add --name/--transport/--command/--args`
  （**先连通验证再落盘**；`remove` 先卸载再删记录；`list` **不连接**）。
- **验证**：先红后绿 —— `tests/test_mcp_endpoints.py`（新，21 例）覆盖注册表落盘/读回/删除/原子写/损坏降级、
  名称派生与重名拒绝、**稳定命名**（两个 client 实例同名安装工具名一致）、**装配期注册**（真 stdio echo server）
  与**降级**（不可达端点告警但不阻断）、**CLI 端到端真实子进程**（`add` → `list` → `remove` 往返 / 连不上不落盘 /
  重名拒绝 / 未知名失败）。四门全绿（921 tests / 29 specs）。
- **转出**：无（B6/B7 系 B3 收口时新报，与本项无关）。
- **参考**：`openspec/changes/archive/2026-10-05-0074-mcp-endpoint-registry/`。

### B5 出站白名单配置项 — ✅ 已关闭（change `0071`）

- **现象**：`SandboxPolicy(host_allowlist=…)` 的**构造面**早在 `0054` 可注入，但**唯一生产构造点**
  `runtime.py:363` 写死 `SandboxPolicy()`（不传参）⇒ 生产白名单**恒为空**、http 出站**永远被拒**。
  规格「沙箱执行颗粒度」场景「网络出站白名单」的**放行半边在生产不可达** —— 只有「拦截」可观测。
- **根因**：与 E15 同型 —— **可注入但唯一调用点不传参 ⇒ 生产不可达**；且 `configuration/` 无
  `permission.sandbox` 键 ⇒ `config show/set`、env、CLI flag 三条通道都够不着
  （ADR-0057 §⑤ 早已登记「白名单配置化记后续」）。
- **裁决**：属「**规格要求 X、实现没有**」型（同 E15/E21）⇒ **改代码向规格靠拢**，
  `permission` spec 相应 **MODIFIED**（补「白名单可经配置声明」的约束条款）。
  取值形态由用户裁定为 **CSV 标量**：本仓 `_parse_yaml_subset` 明文「不含列表」，
  三面（CLI / env / yaml）统一为标量最省，**yaml 解析与写回一行不动**。
- **关闭动作**（change `0071-sandbox-host-allowlist-config`，2026-10-05，**ADR-0068**）：
  ① `ConfigSpec` 增 `permission.sandbox.host_allowlist`（cli `--permission.sandbox.host-allowlist` /
  env `CORE_SANDBOX_HOST_ALLOWLIST` / default `""` / exposure `ADVANCED`）⇒ CLI flag、env、yaml、
  「未知配置段」白名单四者由单一真源自动派生；
  ② 访问器 `sandbox_host_allowlist()`（缺省 `[]`）+ `_split_hosts()`（逗号分隔 → 去空白 / 去空项 /
  保序去重 / 兼容全角逗号），镜像 `circuit_breaker()` 的「寄居 `extra` + 访问器」先例；
  ③ `_sandbox_errors()` 接入 `validate_schema`：**非裸主机名**（带 scheme / 端口 / 路径 / 内部空白）
  与**非字符串取值** ⇒ 校验期**阻断启动**，**不静默忽略**（`check_outbound` 的实参是
  `urlparse().hostname`，此类条目**永不匹配** —— 静默的后果是「配了却连不上」）；
  ④ `runtime.py`：`SandboxPolicy(host_allowlist=config.sandbox_host_allowlist())`，
  `MCPClient` 与 `SandboxManager` 仍**共用同一策略实例**；
  ⑤ **缺省空白名单 = fail-closed 不变**（本变更只把「恒空」变成「可声明」，安全姿态不动）。
- **验证**：先红后绿 —— `tests/test_permission_sandbox_config.py`（新，15 例）在 stash 源码后
  **14 failed / 1 passed**（唯一过的是 `test_default_is_empty_fail_closed` —— 缺省全拒本已成立），
  恢复后 15 passed；含**组合根注入**（策略单实例）与**端到端**（生产 http 守卫：白名单内越过守卫
  止于 `MCP_CONNECT_FAILED`、白名单外 `PERMISSION_DENIED`）与**缺省全拒回归**；四门全绿。
- **转出**：`fs_allowlist` 配置化（无生产调用点需要，YAGNI）；通配符 / 后缀匹配
  （规格只要求白名单，裸主机名精确匹配是 `check_outbound` 现状契约）。
- **参考**：`archive/2026-10-05-0071-sandbox-host-allowlist-config/`。

### B6 MCP wire envelope 未对齐标准 — ✅ 已关闭（change `0075`，ADR-0072）

- **现象**：规格「MCP Server 模式」字面点名 Claude Code / Cursor 可直接挂载本 server，而实测**双向都不通**。
- **根因**：本 server `tools/list` 应答为**裸列表**、`tools/call` 为序列化 `CallResult` 直出（ADR-0070 ⑤
  沿用 change `0054` 的仓内三方约定，**非**标准 MCP envelope）；本 client `initialize` params **为空**
  （对端 zod 校验回 `-32603`），且 `RemoteTool(**item)` 遇标准应答的**容器键**会逐字符迭代、遇
  **厂商扩展字段**（`claude mcp serve` 的 tool 对象带 12 个扩展键）会 `TypeError`。
- **关闭动作**（**改代码向规格靠拢**，与 E12 / E11② / B3 / B4 同型）：两侧最小对齐标准 envelope
  （协议版本 `2024-11-05`）—— ① server `tools/list` → `{"tools": [...]}`、`tools/call` →
  `{"content": [{"type":"text","text":<JSON 载荷>}], "isError": <bool>}`（载荷**恒** JSON 编码保往返保真，
  失败载荷 `{"code","error"}`）；② client `initialize` 携标准三元组、发现接口解析容器键并**只取已知键**
  （容忍厂商扩展字段）、`call_tool` 归一 `isError` 信封，**同时兼容旧式裸形状**（既有 echo server 子进程
  夹具不破裂）；③ `FakeTransport` 改为标准形状（它是「远端」的模型）。命名不放宽（仍 `core.<tool_id>`，
  规格「工具命名空间隔离」明文要求）。
- **真机双向验收（一手证据）**：反向 `core-agent mcp add "claude mcp serve"` 成功并列出对端 **20 个**工具
  （此前 `-32603`）；被挂载 `claude mcp add ... -- core-agent mcp serve` 后 `claude mcp list` 报 `✔ Connected`。
- **转出（新增账本行，不在本变更内）**：远端 JSON-RPC 错误码未映射到本地码 —— `StdioTransport._await`
  把一切远端 `error` 包成 `MCP_UNAVAILABLE` ⇒ 对端「工具不存在」（`-32603`）在本端表现为 `MCP_UNAVAILABLE`
  而非 `MCP_TOOL_NOT_FOUND`（粒度不足但不误导）。
- **参考**：`archive/2026-10-05-0075-mcp-standard-envelope/`。

### B7 默认暴露面启发式过粗 — ✅ 已关闭（change `0076`，ADR-0073）

- **现象**：规格场景「默认最小暴露」写「写/删除/**敏感**工具默认不暴露」，而实测默认暴露面含
  `core.tools.web_fetch`（`network:outbound`，可外发数据 / 拉 arbitrary URL）与 `core.tools.delegate`
  （驱动子 Agent loop）⇒ 第三方客户端默认挂上即可出网与驱动子 loop。
- **根因**：`server._is_readonly`（coeffects 不含 `write`）只实现了「写/删除」，**漏掉「敏感」**；
  且 `tools.delegate` 的 `coeffects=[]` 是**漏声明**（实为跨边界能力）。
- **关闭动作**（用户裁决**收窄**，非「默认零暴露」）：① 判据改为**安全 coeffect 白名单**
  （默认出 ⟺ `coeffects ⊆ {"filesystem:read"}`，**空集通过** —— coeffect 是副作用契约，未声明即无副作用），
  函数更名 `_is_readonly` → `_is_default_exposed`；② 给 `tools.delegate` **补声明** `agent:delegate`
  并在组合根注册（运行期行为不变，新增的是可见性），判据由此**结构化**识别委托类工具（不硬编码工具名）；
  ③ 白名单语义不动（显式 `--whitelist` 仍可开放跨边界工具）。默认面收窄为 {`tools.file_read`, `tools.list`}。
- **转出**：无。
- **参考**：`archive/2026-10-05-0076-mcp-default-exposure-narrowing/`。

### B8 远端 JSON-RPC 错误码未映射 — ✅ 已关闭（change `0077`，ADR-0074）

- **残留**：`StdioTransport._await` 把一切远端 JSON-RPC `error` 包成 `MCP_UNAVAILABLE` ⇒ 「方法未实现 /
  参数非法 / 工具不存在 / 内部异常」塌缩为同一本地码，模型无法区分「工具名写错」（当场可自纠）与
  「远端挂了」（该熔断重试）。change `0075` 实测 `claude mcp serve` 对未知工具回
  `{"error":{"code":-32603,"message":"Tool no_such_tool not found"}}` 时转出。
- **关闭动作**：`transport.map_remote_error(method, error)`（`_await` 唯一调用点）按「方法 + 标准码」归一 ——
  **`tools/call` 的 JSON-RPC 错误 → `MCP_TOOL_NOT_FOUND`**（MCP 约定工具**执行**失败走 `isError` 结果信封，
  故该路径上的错误 = **调用本身被拒**）；其余方法 `-32700`/`-32600`/`-32601`/`-32602` → `MCP_PROTOCOL_MISMATCH`、
  `-32603`/未知码 → `MCP_UNAVAILABLE`；原始远端码与消息保留于文本。**已否决**按码判（对端对未知工具回
  `-32603`，按码判会继续漏）与消息文本启发式（脆弱）。client/server/命名空间/白名单/http 传输零改动。
- **转出**：无。
- **参考**：`archive/2026-10-05-0077-mcp-remote-error-mapping/`。

---

## 5. C 类：真实外部后端未接（低，不挡核心回路调试）

> **代码半 / 凭证半二分**：本块原**整块**记「真后端未接」，未区分「凭证」与「接线」；`coding-plan/phase-20.md` 逐行二分 —— **代码半**（可离线用 fake 验证的接线工程）单独记账并在彼处关闭，**凭证半**（真实 SDK / 网络 / 密钥）仍留本节。

抽象 + 可注入 fake 已落地，真后端待接（约 20 处「未接」标记）。**明细见 `coding-plan/debug-gaps.md` §2.3**，涉及模块：`git` / `im` / `mcp transport` / `ui`（TTS、Tauri 桌面壳）/ `observability`（OTel）/ `ci_cd` / `plugin_registry` / `skillhub` / `pet`·`beast`。

本轮走查**新增的具名条目**（原先只记「约 20 处」，现落到行）：

| 模块 | 具名项 | 出处 |
|---|---|---|
| ui | 流式 TTS 播报后端（barge-in 语音输出仅有抽象） | `phase-7.md:34-35`、`ui-interface.md:19`、`ui/api.py:106` |
| ui | 桌面入口 Tauri 壳 + sidecar（`desktop_bridge.py:34` 直接 raise） | `phase-9.md:21` |
| ui | Web 前端独立托管（`web_bridge.py` 仅设计、无前端实现） | `phase-7.md:105` |
| im | 真实平台 SDK（Telegram / 钉钉 / 企微）+ 退避重连 | `phase-7.md:96,106`、`im/provider.py:4` |
| git | 真实 git 后端 + 断线重试/连接释放 | `phase-7.md:107`、`git/backend.py:51` |
| pet | 探索工具真实执行（R11） | `phase-8.md:84`、`pet/explore/explorer.py:30` |
| pet | 真实通知通道（R12/R13，越界暂停后通知主人） | `phase-8.md:85-86`、`pet/notify/notifier.py:4` |
| pet | 微任务 git 写回（R14） | `phase-8.md:87`、`pet/microtask/microtask.py:4` |
| cli | `skill search` 恒空（`SkillHubClient` 存在但未接线到 CLI） | `debug-gaps.md:51`、`entry.py:426-427,539-550` |
| ci_cd | 门禁执行器 + 真实制品仓库 | `adr.md:293`、`debug-gaps.md:49` |
| plugin_registry | market-registry 远端服务 + 多源 resolver + git 版本锁定 | `adr.md:302` |

> **立场不变**：抽象不锁选型，待有真实选型需求时逐项接线。注意其中 **pet·beast 三行**曾是运行时的**接线**缺口（E3/E4）——**两者均已关闭**（change `0053` / `0057`），现余的只是后端本身。

---

## 6. D 类：文档与仓库杂项（无阻塞）

- **D1** ✅ 已关闭：README §2 Phase 18 行刷新为 ✅ 完成；`17.5` 行改为「🔶 部分完成（遗留见 `phase-19.md` E3/E4）」（memory 召回注入已由 `0038` 闭，pet/beast 运行时注入未做）。
- **D2** `coding-plan/phase-3-prompt.md` 未跟踪（一次性 prompt 残留）→ 删除或明确 `git add`。
- **D3** ✅ 已关闭：核查发现 `git check-ignore` 对 `config.yaml` **零命中**（未被忽略，只是没 `git add`）→ 一次 `git add -A` 即会入库真实端点载体。已在 `.gitignore` 补 `/config.yaml` 守卫（密钥红线）。
- **D4** 🔶 部分关闭：`settings_deepseek.json` / `settings_glm.json` 已加入 `.gitignore`；**`settings.json` 例外**——它**已被跟踪**且有未提交改动（非本项目代码改动），gitignore 对已跟踪文件无效 → 归属仍需人工确认（保留此项）。
- **D5** ✅ 已关闭：本文件已登记进 README §1（文档清单 22 份）与 §2（Phase 总览第 19 行）。
- **D6** ✅ 已关闭（change `0069`，**纯文档 / 规格中性 `skip_specs`**）：
  现象 —— `doc/02-modules/llm-provider.md` §1/§2/§3.2/§3.3 称「**LiteLLM 作默认实现**」，而默认实现是 `StdlibLLMProvider`
  （`llm_provider/stdlib_provider.py`；`__init__.py` 自述；ADR-0044 已**删除 litellm**，核心运行时零三方依赖）。
  三类对齐：规格 `llm-provider/spec.md:5` + Requirement「默认实现与配置归一化」= stdlib；实现 = stdlib；**唯文档陈旧** ⇒
  「文档过度承诺/陈旧」型（同 E17/E19），订正文档承认现状。
  订正范围：主文件模块文档 + 全仓现行文档同类措辞（`requirements.md` CORE-LLM-R2/R3 陈旧镜像 / `doc/README.md` 清单行 /
  `test-cases.md` TC-LLM-03 / `ui-interface.md` §关联）。**不改**：`archive/` 历史变更、`adr.md` ADR-0021/0032（历史决策，
  由 ADR-0044 supersede）、ADR-0044 正文（故意叙述替换前现状）、`design-completeness-eval.md`（横向对比分析稿）。

---

## 7. F 类：验收勾选核实结果（✅ 已清尾）

> **本类已关闭**：6 组陈旧清单逐框对照 `tests/`（行号级）与 `doc/openspec/changes/archive/` 核实，**有证据才勾**；确未做的框**不勾**，转 A/E/B 类并在原文档就地标注去向。

| 文件 | 规模 | 核实结果（原文档已按此改） | 未做项去向 |
|---|---|---|---|
| `phase-0.md` | 14 框 | **13 已勾**：`:28-31`、`:33-36` 验收项与 `:127-131` 架构/压测/脱敏/降级均有 `tests/` 覆盖（`test_architecture.py:233`、`test_observability`/`test_configuration`/`test_permission` 等） | `:32` 功能开关门控 → **E10** |
| `phase-1.md` | 14 框 | **12 已勾**（`test_llm_provider` / `test_memory` / `test_tool_use` / `test_plugin_registry.py:69,83` 等） | `:30` LLM 可靠性 → **E11 全关闭**（① 用例 change `0060`；② 连接复用 change `0066`/ADR-0064）；`:35` 并发压实一致 → **A8 ✅ 已销账**（后端单锁已满足） |
| `phase-2.md` | 10 框 | **7 已勾**：durability `test_durability.py:37,105`、permission `test_permission.py:50,195,232`、架构 `test_architecture.py:268`、熔断 `test_constraints.py:75`、MCP 隔离 `test_mcp.py:117,160`、时间旅行与沙箱同族用例 | `:28` constraints 中间件 → **E1 ✅ 已关闭（change `0052`）**；`:31` mcp → **B1**；`:122` 真机崩溃恢复 → **E12** |
| `phase-2.5.md` | 6 框 | **6 全勾**（`test_installable.py:49`、`test_cli_ops.py:67`、`test_mcp.py:220`、`test_permission.py:252`；归档 `2026-09-27-0028/0029`） | — |
| `phase-17.5.md` | 8 框 | **3 已勾**（memory 召回注入等，由 change `0038` 闭合） | 其余 5 框 → **E3/E4** |
| `cli-contract-baseline.md` §11 | 6 条（非复选框） | 逐条定性（1 条已在代码中闭环） | → **E8** |

**合计**：52 个复选框 → **41 已勾销**、11 项转出（归入 E1/E3/E4/E8/E10/E11/E12/A8/B1 各一节）。**F 类无剩余待办。**

---

## 8. G 类：已闭合但文档未销账（仅需订正，无实现工作）

> 走查中确认「后来已被后续 Phase/change 闭合，但原文档仍是 deferred 措辞」——**无需实现工作**，只需订正原文档（勾选 / 删注 / 改状态）。

| 原记 | 已由何闭合 | 证据 |
|---|---|---|
| judgment 三决策点 DI（loop choice / memory score / permission noul） | Phase 13 | `runtime.py:182-241` 构造并注入 `DecisionRouter`/`Compactor`/`Guardrail`/`SkillMatcher`；`phase-13.md:21` 自陈「拆掉 Phase 11 的 deferred 标记」 |
| `VersionManager` 已存在但未接 runtime | change `0045` | `skills/iteration.py` 的 `SkillIterator` 现即其生产调用方（灰度 + A/B） |
| FastAPI HTTP/SSE 真实传输未接 | Phase 9 | `phase-9.md:103` + `src/core/ui/fastapi_serve.py` |
| serve / REPL 落地「实现 deferred」 | Phase 9 内 | `phase-9.md:74` 注记 vs `:103-104` 实际落地 |
| 端到端「真实模型调用待联调」 | Phase 13 | runtime 组合根 `loop.reason` 接 LLM provider |
| 架构审计三层缺口 M1（InstallableAsset）/M3（install 工具）/M4（cli-ops）/M5（CLI 覆盖层）/M6（permission-mode） | 后续 Phases | `plugin_registry/installable.py`、`tools/install_tools.py`、`entry.py` 子命令、`runtime.py` config.permission_mode；**除 mcp 传输外均已补齐** |
| phase-17.5 memory 召回注入（:69/:70/:123）+ 兽间并行/串行/拒绝（:93） | change `0038` / 既有实现 | 归档 `2026-10-04-0038-task-keyed-memory-recall`；`beast/manager.py` + `tests/test_beast.py` |

**销账（2026-10-04）**：上表 7 组**均已订正原文档**——`phase-11.md:84/95`（勾选 + 注明由 Phase 13 闭合，证据 `runtime.py:182-241`、`tests/test_phase13.py:83,500,508,515`）、`adr.md:554`（`VersionManager` → 0045 闭合）、`phase-7.md:95`（FastAPI/SSE → Phase 9）、`phase-9.md:74`（serve/REPL → 已落地）、`phase-3.md:35`（真实模型调用 → Phase 13）、`phase-17.5.md:69/70/93/123/126`（0038 闭合 + 已测）、`architecture-adjustment-plan.md` 与 `architecture-audit.md`（头部加销账注记，M1/M3/M4/M5/M6 已补齐、仅 M2 的 mcp 随 B1）。

**另有一条属于「真机动作」而非缺口**：`debug-gaps.md` §3 记「活 LLM 端点冒烟从未做过」。走查结论：真端点**实际被打到过**（`9db8b3a` 2026-10-01 修嵌套事件循环冒烟失败、`4c8b869` 2026-10-02 修端点 400 拒绝），但**仍无一次成功走完活 LLM 全回路的书面记录**（`5cd3552` 是记忆 embedding 检索冒烟，非 loop）。→ 建议作为**待执行动作**而非缺口对待。

---

## 9. 依赖与建议重开顺序

1. **D + F + G 清尾**（无依赖、低成本）：G 类订正 deferred 措辞 + F 类逐项勾销/定性 + README 同步 —— 使账本自身可达且不误导。 ✅ **已完成**（G 类 7 组订正；D1/D3/D5 关闭、D4 部分；F 类 6 组核实：41 框勾销 / 11 项转出 E·A·B；README 已同步）。
2. **A2 + E2 合并做**（同一根因）：会话标识透传 + 每会话独立 loop/memory + `UIAPILayer.compact` 接真。 ✅ **已完成**（change `0048-session-scoped-memory`：标识透传 + `compact` 接真 + `get_memory` 按会话过滤；**未采**每会话独立实例，理由见该 change design 决策 1/2）。
3. **A1**（记忆驱动侧）：遗忘节拍。宜在 A2 之后（会话维度不生效时，衰减分组也是错的）。 ✅ **已完成**（change `0049-memory-maintenance-cadence`：loop 收尾维护节拍 + `memory maintain` CLI）。
4. **A3 → A5 → A4 / E4**（进程内态 → 持久化 → 驱动面）：持久化先行，观察窗口 / pending 队列 / `PetManager` 才有意义。 ✅ **A3 全闭 + A5 + A10 + E4 已完成**（change `0050` 技能态落盘 / ADR-0053；change `0051` 进化冷路径驱动面 + 观察窗口落盘 + 批次成功率采样 / **ADR-0054**；A10 为本次走查新增的「冷路径无驱动面」发现；**E4** 见 change `0053` —— pet 纳入组合根 + 注册表落盘 + WebUI NL 入口 / **ADR-0056**）。✅ **A4 已完成**（change `0055-evolution-confirm-surface`：候选稳定身份 + 队列落盘 + `evolve` 操作面签发审批单 / **ADR-0058**）→ 本步**全闭**。
5. **B1**（独立轨）：🔶 **client 侧已关闭**（change `0054-mcp-stdio-transport`，ADR-0057 —— stdio 传输 / `add` 分流 / 消费侧安全接线 / 组合根装配；ADR-0043 的 ADR + spec delta 早已就绪）。**余 1 行后续**：B2 http 会话（需 SDK）。✅ **B4 已关闭**（change `0074`／ADR-0071：`mcp add/list/remove` 接线 + 端点注册表落盘（原子写）+ 装配期连接注册（稳定命名 `mcp.<端点名>.<工具>`）+ 不可达端点降级不阻断；排查记录见 §0/§4 —— `--command` 的 argparse `dest` 曾与顶层 `dest="command"` 冲突，把 `mcp add` 静默送进 REPL）。✅ **B3 已关闭**（change `0073`／ADR-0070：`serve_stdio` 事件循环 + `mcp serve` 接线 + `core.` 命名空间 + 禁二级代理；**新报 B6/B7** —— wire envelope 未对齐标准 / 默认暴露面启发式过粗，均待裁决）。✅ **B5 已关闭**（change `0071`，ADR-0068）。✅ **B6 已关闭**（change `0075`／ADR-0072：两侧最小对齐标准 MCP envelope + **真机双向验收** —— `claude mcp add` 挂本 server 报 `✔ Connected`、本 client 挂 `claude mcp serve` 发现 20 工具；另转出「远端 JSON-RPC 错误码未映射」新行 B8）。✅ **B7 已关闭**（change `0076`／ADR-0073：默认暴露面判据改为**安全 coeffect 白名单**（只读且无跨边界 coeffect）+ `tools.delegate` 补声明 `agent:delegate` ⇒ `web_fetch`/`delegate` 默认不出；白名单语义不动）。✅ **B8 已关闭**（change `0077`／ADR-0074：`transport.map_remote_error` 按「方法 + 标准码」归一 —— `tools/call` 的 JSON-RPC 错误 → `MCP_TOOL_NOT_FOUND`，其余方法按标准码映射；原始码保留于文本）。
6. **E1 + E7 + E8**（契约与中间件）：✅ **全闭** —— E1 见 change `0052`（ADR-0055；账本原「校验空转」说法已订正——校验实由工具层承担，真实残留是熔断）；**E7/E8 见 change `0056`（ADR-0059）**：E7 裁决「规格为准」→ 纯文档订正；E8 三处缺口修复，第 5 条转出为 E18。
7. **E3 / E6**（规格裁决）：✅ **全闭** —— 裁决「A 全做・解除 deferred」；**E3** 见 change `0057`（ADR-0060：神通注册 + 专属路由作用域 + 按兽 loop/共享记忆注入 + CLI 走组合根）；**E6** 无需代码（context 压实启发式已由 change `0041` 规格订正为有意行为，余两项转 A7/A8）。
8. **A7 + E6（miss 复用）**（低优先，同族）：✅ **全闭** —— **A7** 见 change `0058`（ADR-0061：排序分 = 基础分 × 历史成功率因子；预筛转出 A11）；**E6** 无需代码（见上，规格已由 change `0041` 订正）。
9. **A8 / A11 / E5 / E9 / E13 / E15–E16 / C 类**：随需（**A11 语义兜底候选预筛**（需先有比词法更粗的排序信号，**候选预筛**）/ E15 熔断阈值不可配 / E16 `AsyncNotifier` 无 channel）。✅ **E16 已关闭**（change `0079`／ADR-0076：pet 通知三环接线 —— 生产者落 `wake()` 收尾 + 缺省 stderr sink + 组合根收口 flush；转出 pet 安全越界路径 **E25**、`surprise()`/`MicrotaskRunner` 零调用方 **E26**、`IMGateway` 零生产装配 **E27**、无宿主驱动 `wake()` **E28**）。✅ **E25 已关闭**（change `0081`／ADR-0077：专属 loop 真强制 —— 受限 `ToolProvider`（R11）+ 安全中间件（R12）；越界 ⇒ 本轮终止 + 通知主人，会话保持 `ACTIVE`；词汇表订正为真实 id）。✅ **E29 已关闭**（change `0082`：pet「Runtime Wiring」的「主 loop」字面订正为「组合根装配的真实 loop（专属 loop，非 echo 兜底）」+ 口径段；零代码，**由 `0081` 自报**）。 ✅ **E28 已关闭**（change `0083`／ADR-0078：CLI `pet run --interval` 宿主驱动 + 驱动薄壳（`PetError` 预期态静默跳过 / 意外失败隔离不中断其余宠物，R8）+ 跨进程注册表恢复；规格中性）。✅ **E5 已关闭**（change `0084`／ADR-0079：引擎侧自动课程 —— 结构化信号定序议程（失败强度 / 观察期降权 / 待确认降权）+ 先验权重恒 < 1.0（只破并列、不压证据）+ 显式目标入口 `evolve run --goal`（直接采用）；驱动面仍两个、模型工具面不变、人工门不放宽）。✅ **E26 全关闭**（change `0086`／ADR-0081：pet 惊喜去谎报与上报 —— `surprise() -> str | None`，无偏好不产出不谎报、有偏好经真实 loop 代办回报真实产出，唤醒收尾同反馈节拍投递、失败 fail-soft；change `0087`／ADR-0082：`MicrotaskRunner` 接线且三条任务真实化（无真实产出 ⇒ `None`）、`wake()` 消费队首任务、队列清空 ⇒ 入睡（让行态、不编造任务）、新任务自动唤醒、宿主驱动零改动）；change `0088`／ADR-0083：pet 控制面 `/pet [cmd]` —— `PetControl` 单门面（CLI 与 UI 复用）+ 寻址不猜 + `status` 不外泄 + 仅同进程）。✅ **E14 已关闭**（change `0059`，ADR-0062）。✅ **E11 全关闭**（① change `0060`：可靠性用例 9 例，`src/` 零改动；② change `0066`/ADR-0064：**连接复用已实现** —— 线程本地按 origin 复用 keep-alive + 失效重建，真实 socket 用例 9 例）。✅ **A6 / E13 / E19 已关闭**（change `0063`，纯文档：已知语义登记 + 有意不接线判定 + 过度承诺订正）。✅ **E18 已关闭**（change `0064`，ADR-0063：未知配置段仅告警）。✅ **E17 已关闭**（change `0065`：规格未要求 daemon，登记「唤醒由宿主驱动」）。✅ **A9 已关闭**（**规格明文认可现状**：`context/spec.md:9` 逐字写 stage 不参与事实选择（change `0038` 写入），文档与实现三层一致 ⇒ 零变更销账）。✅ **A8 已销账**（**零变更**：`FileBackend` 单把 `RLock` 覆盖全部读写路径 + 压实只归档不删除 ⇒ 规格「加锁/等待」已满足；订正「无并发调用方」——`ui serve` 同步路由线程池与事件循环 `/run` 真并发）。✅ **A11 已销账**（**零变更**：规格明文「逐条打分」（`skills/spec.md:65-66`）⇒ 未预筛是规格行为；O(N) 成本需 JEV 真凭证 + 库规模大 + 词法 miss **三重条件同时成立**，当前均不成立；用户裁决登记销账、不做投机预筛）。✅ **E10 已关闭**（change `0067`／ADR-0065：门控名单（`pet`/`beast`/`evolution`）归组合根单一真源 + **缺省装配**（未声明即开，仅显式 `false` 才不装配）+ 7 入口拒绝）。 ✅ **E15 已关闭**（change `0068`／ADR-0066：`constraints.failure_threshold` / `constraints.cooldown_s` 经 `ConfigSpec` 单一真源四通道可配 + 非法取值校验期拒绝不兜底 + 组合根注入、主/子 loop 共享同链）。
   ✅ **E9 已关闭**（change `0061`：`data-model.md` 四实体回填 + rag/mcp/git 锚点登记 TC-RAG-10/TC-MCP-06/TC-GIT-11 + 两处日期补记；纯文档、规格中性）。
   ✅ **E12 已关闭**（change `0062`：真子进程 `SIGKILL` 端到端 + **修持久化非原子写入**（tmp + `os.replace`）/ 规格 delta）；另新报 **E19**（durability 文档承诺的持久化故障降级未实现）→ **已由 change `0063` 关闭**（订正模块文档承认现状）。
   ✅ **E21 已关闭**（change `0070`：`entry._pet` 前置判定接入 `ConfigManager.config_value` —— CLI > env > **config.yaml** > 缺省，ConfigSpec 单一真源；缺文件容错；persona 目录同源读取。同型缺陷 `config get` 转出为 **E22**）。✅ **E22 已关闭**（change `0078`／ADR-0075：`entry._config` 的 `get` 分支改用 `ConfigManager.config_value(key)`（与 `pet` 门控同一通路）⇒ 遵循完整优先级链 CLI > env > config.yaml > 缺省；`config get` 输出语义随之修正；`skip_specs`）。
   ✅ **E20② + E23 已关闭**（change `0072`／ADR-0069：feature flag 三面取值同口径 —— 合法集合 `true/false`·`yes/no`·`on/off`·`1/0` + 原生布尔、其余**校验期拒绝不静默强转**；`--feature` 经覆盖层接入优先级链并**真的**支配装配（此前零消费）；**E20① 已由 change `0085` 关闭**（规格先行：顶层段名口径加 `features` 唯一例外 + 组合根注入已知模块名集合、仅告警／ADR-0080）；**新报 E24** —— env 前缀实现/规格复数·单数不一致，改名属对外破坏性变更，待裁决；**已由 change `0080` 关闭**（裁决改规格/文档向实现靠拢：规格/接口/模块文档单数 → 复数，零代码；spec MODIFIED + 补齐 `0072` 丢失正文段）。**E26 全关闭**（change `0086`（surprise 去谎报与上报）+ change `0087`（微任务真实化 + 空闲自治睡眠）+ change `0088`（控制面 `/pet [cmd]`，用户诉求① 收口））、**D4 保持不动不提交**（用户裁决）。
10. **真机动作**：活 LLM 全回路冒烟（§8 末）。

---

## 10. 关闭判据

任一项标「已关闭」须同时满足：

1. 按所属 capability 走完 SDD：spec delta（或明确「规格中性」的判据）→ 测试先行 → 实现 → 四门全绿（ruff check / ruff format / pyright / pytest）；
2. `openspec validate --all` 全绿，change 已归档（本仓库 `openspec archive` 失败，须手动合并 delta + `mv`，见归档惯例）；
3. 本文件对应行更新为「✅ 已关闭（change id / commit）」；
4. 若改变了对外语义，同步 `doc/03-interfaces/*-interface.md` 及相应 ADR。
