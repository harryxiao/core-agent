# AGENTS.md — core-agent 导航索引

> 项目目录导航与文档阅读索引，供编码 Agent（Cursor 等）快速定位。

## 目录导航

| 路径 | 内容 |
|---|---|
| `core_harness_architecture.md` | 架构总纲（三源融合 + 结晶经济） |
| `doc/` | SDD 开发文档集（00产品 → 05开发，入口 `doc/README.md`） |
| `openspec/specs/` | **行为规格（source of truth，勿直接改根目录）** |
| `openspec/changes/` | 变更提案（proposal/tasks/design + spec delta） |
| `src/core/` | 代码（substrate / tools / memory / loop / evolution / mcp） |
| `tests/` | pytest（单元 + 集成，BDD 用 pytest-bdd） |
| `openspec/config.yaml` | SDD 上下文与规则（AI 生成 artifact 时可见） |

## 文档阅读顺序

- 产品/PM：`doc/00-product` → `openspec/specs`
- 架构师：`doc/00-product` → `doc/01-architecture` → `doc/03-interfaces`
- 开发者：`doc/01-architecture` → `doc/02-modules` → `doc/03-interfaces` → `doc/05-development`
- 测试：`openspec/specs`（场景）→ `doc/04-testing`

> 完整方法论见 `doc/README.md`；架构取舍见 `doc/01-architecture/adr.md`。
