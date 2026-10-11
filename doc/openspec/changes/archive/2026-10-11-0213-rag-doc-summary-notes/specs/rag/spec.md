# Rag Specification Delta — 文档→摘要：`rag ingest --summarize` 落 notes 结论笔记（change 0213）

## MODIFIED Requirements

### Requirement: 文档摄取与分块
系统 SHALL 提供文档摄取管线：导入知识文档 → 分块 → 生成 embedding → 建立向量索引，并支持增量更新与索引失效检测。

- **可选摘要**：摄取操作面 SHALL 提供**可选**的 `--summarize` 旗；显式给出时，摄取**成功后**
  系统 SHALL 把该文档**全文**交给一次模型调用产出摘要，并落为 **canonical 结论笔记**
  （见 `notes` 规格「文档摘要笔记」）。未给该旗 SHALL 保持既有摄取行为**逐字不变**（零配置键、
  零环境行为）。摘要产物 SHALL NOT 参与向量索引 / 检索语料（结论层与检索层分离）。
- **摘要失败不阻断**：摘要（模型调用 / 落盘）失败 SHALL **不**使已完成的摄取回退、SHALL NOT
  使命令以非零码退出（摄取已是既成事实）；失败 SHALL 告警留痕（只报 `doc_id`，不回显正文）。

#### Scenario: 文档导入建索引
- **GIVEN** 一份知识文档待导入
- **WHEN** 摄取管线处理该文档
- **THEN** 文档被分块、逐块生成 embedding 并建立向量索引，可被检索

#### Scenario: 源文档变更触发增量更新
- **GIVEN** 源文档内容变更
- **WHEN** 检测到 hash 不一致
- **THEN** 触发受影响块的增量重建，期间该文档检索降级为旧索引

#### Scenario: 摄取/重建失败降级
- **GIVEN** 摄取管线在 embedding 生成、索引写入或重建过程中失败（如 embedding 失败、索引损坏、重建失败）
- **WHEN** 摄取或重建出错
- **THEN** 该文档检索降级为旧索引（或纯 LLM 生成），记录失败并可重试，不阻断主流程

#### Scenario: 摄取可选摘要落结论笔记
- **GIVEN** 一份知识文档待导入，且摄取命令带 `--summarize`
- **WHEN** 摄取成功完成
- **THEN** 系统把文档全文交给一次模型调用产出摘要，并落成一篇 canonical 结论笔记
  （`source="notes.rag"`，`note_id` 由 `doc_id` 确定性派生）；该笔记**不进**向量索引语料；
  未带 `--summarize` 时 SHALL NOT 产生任何笔记（摄取行为与既有逐字一致）
