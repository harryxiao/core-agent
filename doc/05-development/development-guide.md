# 开发指南（Development Guide）

> 版本 v0.1 ｜ 面向 CORE-Harness 的实现者：如何搭建、编码规范、SDD 工作流、验收。

---

## 1. 环境搭建

```bash
# Python 3.11+
python --version

# 建议使用虚拟环境
python -m venv .venv && source .venv/bin/activate

# 安装 OpenSpec CLI（规格工具）
npm install -g @fission-ai/openspec
openspec --version
```

仓库结构（规划）：

```
core-agent/
├── core_harness_architecture.md   # 架构原始构想
├── doc/                           # 本文档集（SDD 唯一事实来源）
├── openspec/                      # OpenSpec CLI 生成（可选，与 doc/ 同步）
├── frontend/                      # Svelte + Vite SPA（产物 frontend/dist/，不入库）
├── src-tauri/                     # Tauri v2 桌面壳（只做开窗口 / 挂 SPA / 启 sidecar）
├── src/core/
│   ├── plugin_registry/           # L0
│   ├── tools/                     # L1
│   ├── memory/                    # L2
│   ├── loop/                      # L3
│   ├── evolution/                 # L4
│   └── mcp/                       # 横切
└── tests/                         # 对齐 doc/04-testing
```

### 1.1 前端与桌面壳（change 0100）

前端**不在 Python 四门内**（本仓无 JS 测试基建）：`npm run build` 归验证节，不归门。

```bash
# 构建 SPA 产物（Node ≥ 20）——产物才挂到站点根，源码入库、产物本地构建
cd frontend && npm ci && npm run build      # ⇒ frontend/dist/index.html

# Web 模式：产物存在 ⇒ http://127.0.0.1:8000/ 直接是 SPA；不存在 ⇒ 纯 API 模式（不报错）
core-agent serve

# 桌面模式：起壳并由 DesktopBridge 拉起本地后端（sidecar）
core-agent app --port 8000
```

`frontend/dist/` 是**可选产物**：后端不硬依赖它，没跑过 `npm` 也能起服务与跑测试。

---

## 2. 编码规范

| 主题 | 约定 |
|---|---|
| 语言 | Python 3.11+，类型注解 + `dataclass`/`Protocol` |
| 插件契约 | 任何插件实现 `Plugin`（plugin_id/generation/schema/coeffects + load/unload/check） |
| 可逆性 | 写操作必须 `EffectTracker.record(effect, undo)` |
| coeffect | 不硬编码配置/密钥，通过 `CoeffectResolver` 注入 |
| 错误 | 结构化错误码，不向模型抛裸异常 |
| 密钥 | 只引用不读取，绝不进日志/记忆 |

---

## 3. SDD 工作流（Spec-Driven Development）

```
1. 写规格   doc/openspec/specs/<capability>/spec.md（Requirements + Scenarios）
2. 建变更   doc/openspec/changes/<id>/（proposal + tasks + design + spec delta）
3. 写测试   doc/04-testing/test-cases.md 对齐 Scenario（先写测试）
4. 实现     按 tasks.md 逐项实现，跑测试
5. 验证     openspec validate（若用 CLI）；测试全绿
6. 归档     openspec archive <id>；规格 delta 合并进 specs/
```

**黄金法则**：先规格，后实现；规格的每个 Scenario 都要有测试；实现若偏离规格，先改规格再改代码。

---

## 4. 实现顺序（MVP 里程碑）

| 里程碑 | 内容 | 验收 |
|---|---|---|
| M1 基底 | L0 插件注册 + 可逆效应 + coeffect + HMR | TC-PLG 全绿 |
| M2 工具 | L1 原子工具 + ToolProvider + 确认门 | TC-TOOL 全绿 |
| M3 记忆 | L2 五层记忆 + 检索上界 + 结晶/溶解钩子 | TC-MEM 全绿 |
| M4 循环 | L3 四阶段 loop（~100 行） | TC-LOOP 全绿 |
| M5 MCP | MCP client + 适配器 | TC-MCP 全绿 |
| M6 进化 | L4 四阶段 + 世代 + 验证门 + 留出评测 | TC-EVO 全绿 |

---

## 5. 提交规范

- 一个 commit 对应一个变更（change）或一个规格 delta，消息格式 `feat(<capability>): ...`。
- 涉及规格变更时，commit 必须同时包含 `openspec/specs` 与 `openspec/changes` 的更新。

---

## 6. 关联

- SDD 工作流详解：`doc/05-development/sdd-workflow.md`
- 规格：`doc/openspec/specs/*`
- 变更示例：`doc/openspec/changes/0001-bootstrap-core/*`
