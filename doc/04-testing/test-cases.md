# 测试设计：测试用例（Test Cases）

> 用例编号与需求、规格 Scenarios 同号，实现"规格 → 需求 → 测试"全链路可追踪。

---

## 1. 插件注册与组合（TC-PLG）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PLG-01 | CORE-PLG-R1 | 注册一个新插件，不改核心代码 | 注册表可查到，可直接调用 |
| TC-PLG-02 | CORE-PLG-R2 | 执行写操作 → 记录 undo → 回滚 | 副作用完全撤销 |
| TC-PLG-03 | CORE-PLG-R3 | 声明 coeffect 但环境未注入 | 返回 `COEFFECT_MISSING`，拒绝执行 |
| TC-PLG-04 | CORE-PLG-R4 | 运行中 load/unload 插件 | 主循环不中断，切换生效 |
| TC-PLG-05 | CORE-PLG-R2 | 卸载前未确认的 undo | 自动回滚后再卸载 |

## 2. 智能体循环（TC-LOOP）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-LOOP-01 | CORE-LOOP-R1 | 发起一轮对话 | 四阶段全部执行，末了写记忆 |
| TC-LOOP-02 | CORE-LOOP-R2 | 替换 loop 插件为 Plan-Execute | 行为切换，无需改核心 |
| TC-LOOP-03 | CORE-LOOP-R3 | action 失败 | 该轮 undo 回滚，失败写记忆 |
| TC-LOOP-04 | CORE-LOOP-R4 | 触发不可逆操作 | ask_user 确认门触发 |
| TC-LOOP-05 | CORE-LOOP-R4 | 确认门拒绝 | 改写安全动作或终止 |

## 3. 分层记忆（TC-MEM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-MEM-01 | CORE-MEM-R1 | 写入 L2 事实 | 可检索到，归属正确层 |
| TC-MEM-02 | CORE-MEM-R2 | 超 budget 检索 | 按优先级截断，≤ budget |
| TC-MEM-03 | CORE-MEM-R3 | L3 技能结晶为插件 | 注册为代码，undo 可回滚 |
| TC-MEM-04 | CORE-MEM-R3 | 插件溶解回 L3 | 语义+教训回写，历史不丢 |
| TC-MEM-05 | CORE-MEM-R4 | 切换记忆后端 | 同一接口，行为一致 |

## 4. 工具使用（TC-TOOL）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-TOOL-01 | CORE-TOOL-R1 | 枚举 active tools | ≥ 9 个原子工具 |
| TC-TOOL-02 | CORE-TOOL-R2 | 传非法参数 | 返回结构化 `INVALID_ARGS` |
| TC-TOOL-03 | CORE-TOOL-R3 | file_write 后回滚 | 内容恢复原样 |
| TC-TOOL-04 | CORE-TOOL-R4 | 工具超时 | 中止返回 `TIMEOUT`，loop 不崩 |
| TC-TOOL-05 | CORE-TOOL-R3 | 不可逆工具未确认 | 阻断，`IRREVERSIBLE_BLOCKED` |

## 5. MCP 集成（TC-MCP）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-MCP-01 | CORE-MCP-R1 | 连接示例 MCP server | 发现并调用其 tools |
| TC-MCP-02 | CORE-MCP-R2 | 读取 resource/prompt | 纳入上下文 |
| TC-MCP-03 | CORE-MCP-R3 | 调用远程写工具 | 受确认门 + 可逆追踪约束 |
| TC-MCP-04 | CORE-MCP-R4 | stdio 与 http 传输 | 两种均可连通 |
| TC-MCP-05 | —— | server 掉线 | `DEGRADED`，不阻塞其他工具 |

## 6. 进化引擎（TC-EVO）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-EVO-01 | CORE-EVO-R1 | 喂轨迹跑一轮进化 | 四阶段闭环执行 |
| TC-EVO-02 | CORE-EVO-R2 | 注入单插件缺陷 | 诊断归因到该插件 |
| TC-EVO-03 | CORE-EVO-R3 | 候选过门 | 产出世代化不可变产物 |
| TC-EVO-04 | CORE-EVO-R4 | 候选在留出集退化 | 自动回滚，不发布 |
| TC-EVO-05 | CORE-EVO-R3 | 候选不过验证门 | 丢弃 + 教训写记忆 |

## 7. 权限与审批管控（TC-PERM）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-PERM-01 | CORE-PERM-R1 | 触发高危操作 | 默认拦截 `DENY_BY_DEFAULT` |
| TC-PERM-02 | CORE-PERM-R2 | 提交审批 → 超时未批 | 默认拒绝，审计归档 |
| TC-PERM-03 | CORE-PERM-R3 | 沙箱内执行异常 | fail-closed，沙箱自动销毁 |
| TC-PERM-04 | CORE-PERM-R4 | coeffect 越权调用 | 拒绝执行，记录越权 |

## 8. 任务编排（TC-ORCH）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-ORCH-01 | CORE-ORCH-R1 | 非法状态转移 | 拒绝并报 `ILLEGAL_TRANSITION` |
| TC-ORCH-02 | CORE-ORCH-R2 | 有依赖的子任务拆解 | 按拓扑序执行，无环 |
| TC-ORCH-03 | CORE-ORCH-R3 | 任务交接给子 Agent | 上下文完整传递（TaskHandoff） |
| TC-ORCH-04 | CORE-ORCH-R4 | 长任务中断后恢复 | 从断点续跑，不重头 |

## 9. 可观测性（TC-OBS）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-OBS-01 | CORE-OBS-R1 | 跑一轮 loop | 产出结构化 JSONL，无密钥明文 |
| TC-OBS-02 | CORE-OBS-R2 | 采样多轮 | 完成率/token/错误率指标可查 |
| TC-OBS-03 | CORE-OBS-R3 | 按 trace_id 重放 | 单轮可复现 |
| TC-OBS-04 | CORE-OBS-R4 | 进化经验采集 | 数据源来自统一遥测流 |

## 10. 约束与容错（TC-CONS）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-CONS-01 | CORE-CONS-R1 | 传非法输入 | 前置校验拦截，输出结构化错误 |
| TC-CONS-02 | CORE-CONS-R2 | 连续失败触发熔断 | 熔断/降级，恢复后自动重试 |
| TC-CONS-03 | CORE-CONS-R3 | 上下文超预算 | 压缩中间件裁剪至 ≤ budget |
| TC-CONS-04 | CORE-CONS-R4 | 调整中间件顺序 | 执行顺序随之变化且可观测 |

## 11. 技能封装（TC-SKILL）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-SKILL-01 | CORE-SKILL-R1 | 前置条件不满足调用技能 | 拒绝并提示缺失条件 |
| TC-SKILL-02 | CORE-SKILL-R2 | 灰度发布新版本技能 | 按比例路由，退化自动回退 |
| TC-SKILL-03 | CORE-SKILL-R3 | 相似任务路由 | Top-K 命中最佳技能 |
| TC-SKILL-04 | CORE-SKILL-R4 | evolution 结晶产物入库 | 唯一进入技能库，走评审 |

## 12. 上下文工程（TC-CTX）

| 用例 | 对应需求 | 步骤 | 期望 |
|---|---|---|---|
| TC-CTX-01 | CORE-CTX-R1 | 超预算上下文装配 | 裁剪后 ≤ token 预算 |
| TC-CTX-02 | CORE-CTX-R2 | 索引失效后 fetch | hash 校验触发重建，按需加载 |
| TC-CTX-03 | CORE-CTX-R3 | 多轮对话 | 关键信息自动压实并写回记忆 |
| TC-CTX-04 | CORE-CTX-R4 | 千页文档 | 仅呈现目录索引，细节按需跳转 |

## 13. 非功能（TC-NFR）

| 用例 | 对应 NFR | 期望 |
|---|---|---|
| TC-NFR-OBS1 | OBS1 | 100% 写操作有审计记录 |
| TC-NFR-OBS2 | OBS2 | 单轮 trace_id 可复现 |
| TC-NFR-PERF1~3 | PERF1~3 | 满足延迟/插拔目标 |
| TC-NFR-SEC1 | SEC1 | 日志/记忆无密钥明文 |
| TC-NFR-SEC2/3 | SEC2/3 | 不可逆操作必确认，爆炸半径可控 |

---

## 关联

- 测试计划：`doc/04-testing/test-plan.md`
- 需求：`doc/00-product/requirements.md`
- 规格：`doc/openspec/specs/*`
