# Tasks

## 1. git 抽象接口（P0）

- [x] 1.1 在 git spec 追加「GitClient 抽象接口与依赖注入隔离」Requirement
- [x] 1.2 在 git spec「版本控制核心操作」操作列表补 stash
- [x] 1.3 新增 03-interfaces/git-interface.md（GitClient + 数据类型 + 错误码）

## 2. rag 去具体化与依赖注入（P0）

- [x] 2.1 在 rag spec「本地向量库存储」去具体化（sqlite-vec → 默认实现）
- [x] 2.2 在 rag spec「本地 Embedding」去具体化（sentence-transformers+BGE → 默认实现）
- [x] 2.3 在 rag spec 追加「存储与 Embedding 依赖注入隔离」Requirement
- [x] 2.4 在 rag-interface.md 补「依赖注入隔离（MAL）」节

## 3. mcp 传输层抽象（P0）

- [x] 3.1 在 mcp spec 追加「传输层抽象与依赖注入隔离」Requirement
- [x] 3.2 在 mcp-interface.md 补「Transport 抽象（传输层隔离）」节

## 4. MAL 约定留痕（P0）

- [x] 4.1 在 adr.md 追加 ADR-0040（MAL 四条约定）+ 变更追踪表

## 5. 验证（P0）

- [x] 5.1 openspec validate --all 全绿
