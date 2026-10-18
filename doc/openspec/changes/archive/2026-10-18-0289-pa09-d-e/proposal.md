# 0289 — PA-09 D/E 裁决收口：多跳检索基准 ＋ 语义检索可强制

## Why

PA-09 的两项待裁决项在 2026-10-18 由用户裁决为「先测后裁」（D：图存储/遍历）与
「基准 + 可选强制」（E：真语义检索）。本 change 把两条裁决落成**可复现的测量**与**最小的
运行时开关**，不预支未经验证的存储/模型改造。

- **D（图存储/遍历）**：关系三元组目前以扁平 L2 条目落库（`relation.*`，tags 含
  `entity:` / `predicate:`），**没有**邻接索引与遍历 API；`memory.relation_extract` 缺省
  `false`，真实记忆样本中关系条目为 0。没有数据能证明「建图」值得一次存储/协议变更。
- **E（真语义检索）**：change `0271` 已按端点表默认启用 embedding，但「语义是否真的优于
  词法」没有离线基准；且用户无法要求「没有 embedding 就拒绝启动」——当前静默回退词法。
  引入本地 embedding 模型的方案已明确否决。

## What Changes

- **D：只测不改产品**。新增 `tests/test_memory_graph_benchmark.py`：
  - 20 条合成多跳链（`Z --owns--> B`、`B --part_of--> C`），每条查询只命中首跳；
    度量**扁平检索**与**测试内模拟的 1 跳邻接扩展**对第二跳 gold 的 recall@5。
  - 用 `_plan_relations` 度量确定性流水线覆盖率（白名单谓词 / 未知谓词 / 空实体 / 同批
    重复 / 密钥形态 / 名额上限），输出可复现数字。
  - **裁决记录**：合成基准证明机制增益，但生产侧关系抽取缺省关闭、真实数据为 0 ⇒
    **本轮不建图**；轻图（tags 邻接 + 遍历 API）保留为重新开启时的既定形态。
- **E：基准 + 可选强制**。新增：
  - `llm.embedding_required`（ConfigSpec 三面，**缺省 `false`**；取值口径同
    `embedding_auto`）。开启时若 `LLMConfig.effective_embedding_model` 为空，配置校验期
    **阻断启动**；错误信息只含键名，不回显 endpoint / 密钥。只保证「模型已确定」，
    **不探测可达性**；调用期失败仍按既有路径降级词法。
  - `tests/test_semantic_benchmark.py`：确定性概念/同义词离线 embedder，使改写查询与
    gold 词面零重叠；对比词法 BM25 与语义余弦的 recall@1/@5、MRR@5。基准证明的是
    **通路与量纲**，不替代真实模型质量（登记为局限）。
  - 配置三面 + 校验测试并入 `tests/test_semantic_default.py`。

## Non-goals

- **不实现图存储 / 邻接索引 / 遍历 API**（D 的轻图是后续 change，须在关系抽取真实运行
  并积累数据后重新裁决）。
- **不引入本地 embedding 模型**；不改端点表；不改 `llm.embedding_auto` 语义。
- 不做网络可达性探测，不把 `embedding_required` 扩成「健康检查」。
- 不改既有词法降级路径、不新增第三方 LLM SDK 依赖。

## Impact

- 代码：`src/core/configuration/models.py`、`src/core/configuration/manager.py`。
- 测试：新增 2 个基准文件 + `tests/test_semantic_default.py` 追加。
- 规格：`configuration`（LLM 提供商配置）、`memory`（温度分层检索）两个 MODIFIED delta。
- 文档：configuration / memory 接口、ADR-0279、台账 E225、test-cases §201/§202、
  `Pending-Arbitration.md` 的 PA-09 D/E 裁决记录。
- 缺省行为：`embedding_required=false` ⇒ 与引入前逐字一致；无配置迁移。
