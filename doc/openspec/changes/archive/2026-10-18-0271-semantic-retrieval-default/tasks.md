# Tasks 0271 — 语义检索默认化

## 1. 配置层

- [x] 1.1 新增 `configuration/embedding_models.py`：已知端点表 + `default_embedding_model`
- [x] 1.2 `LLMConfig` 增 `embedding_auto`（缺省 true）与 `effective_embedding_model`
- [x] 1.3 `llm.embedding_auto` 进 ConfigSpec 三面；解析 / 校验（非法取值阻断启动）
- [x] 1.4 `_merge_patch` 保留显式值语义（推导不固化）

## 2. 组合根与入口

- [x] 2.1 runtime 的 embed provider 与 RAG embedder 改用有效模型
- [x] 2.2 CLI 启动提示：有效为空 ⇒ 词法提示；推导 ⇒ 自动选用提示；显式 ⇒ 无提示
- [x] 2.3 `_rag` 的降级提示改用有效模型判断

## 3. 测试与门禁

- [x] 3.1 `tests/test_semantic_default.py`：表匹配 / 显式优先 / 开关关闭 / 未知端点 /
      配置解析与非法取值 / runtime 注入 / 提示文案
- [x] 3.2 反证：移除推导 / 忽略开关 / 入口仍看显式字段 ⇒ 对应用例红；复原 `md5sum` 同
- [x] 3.3 四门禁 + `openspec validate --all`；archive + ADR-0261 + 台账 E207 + 测试节 §183
      + 模块/接口文档 + 单次提交
