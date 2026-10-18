# 设计 — 0289 PA-09 D/E

## D1. D 只做测量：为什么不在本轮建图

**现状事实**（改动前取证）：

- 关系以扁平 L2 条目落库：`id=relation.<head>--<pred>--<tail>`，`content="H --p--> T"`，
  tags `relation` / `entity:<head>` / `entity:<tail>` / `predicate:<p>`（`store.py::_write_relation`）。
- 没有邻接索引；`MemoryBackend` Protocol 只有 `get/put/search/list_index/delete`，无遍历方法。
- `memory.relation_extract` 缺省 `false`；本机真实记忆样本 `relation.*` 为 **0** 条。

**基准设计**（`tests/test_memory_graph_benchmark.py`，纯离线）：

- 20 条链：`Z{i} --owns--> B{i}`、`B{i} --part_of--> C{i}`。
- 每链另有 2 条同头干扰（`Z{i} --uses--> D{i}`、`Z{i} --depends_on--> E{i}`）与 20 条共享
  `component` 词面的干扰。查询只含 `Z{i}` 与自然语言词，**第二跳 gold 与查询零词面重叠**。
- **扁平基线**：`MemoryStore.read()`（无 embedder，BM25）取 top-5。断言 gold recall@5 = 0。
- **模拟轻图**：从扁平 top-1（首跳）取 `entity:` 标签 → 用全部关系条目在**测试内**建
  entity→条目 邻接（不写产品代码）→ 把 1 跳邻居提升到候选前部 → 取 top-5。断言 gold
  recall@5 = 1.0。
- **覆盖度量**：`_plan_relations` 输入白名单谓词 / 未知谓词 / 空实体 / 同批重复 / 密钥形态 /
  超额条目，输出可落库数、丢弃原因与名额上限；断言确定性流水线 100% 保留合法项、
  100% 丢弃非法项并遵守 cap。

**裁决**：机制增益在**合成完美抽取**下成立；但生产侧关系抽取缺省关、真实数据为 0，
现在建图等于为零数据造索引。**本轮不建图**；轻图（tags 邻接 + 遍历 API）保留为关系抽取
真实运行并积累数据后的既定形态。基准与覆盖率数字是届时复评的基线。

**局限**（必须如实登记）：

- 合成链是完美抽取结果，**不测 LLM 抽取的召回/精度**；覆盖度量只测确定性后处理。
- 邻接在测试内模拟，不代表真实存储/协议成本。
- 因此基准只能证伪「图一定无用」，不能证明「图在生产中一定有用」。

## D2. E：`llm.embedding_required` 的语义边界

- **校验期 fail-closed**：`ConfigManager.validate_schema` 在 `embedding_required=true` 且
  `effective_embedding_model == ""` 时追加错误并阻断 `load()` / `apply_change()`。
- **只断言「模型已确定」**：显式 `llm.embedding_model` 或端点表推导命中都算满足。
  **不探测网络可达性**；调用期失败仍走既有降级（词法相似 + 一次启动提示）。
- **错误信息不含 endpoint / 密钥**：只含键名与可操作提示。
- **缺省 false**：不改变任何既有启动路径；无迁移。
- **取值归一**：与 `embedding_auto` 同集（原生布尔 + `true/false`·`yes/no`·`on/off`·`1/0`），
  非法值在校验期拒绝，不静默强转。
- **热更新一致**：`_merge_patch` 的基线字典包含 `embedding_required`，`apply_change` 会重新
  校验；把端点改成未知主机或关闭 `embedding_auto` 而 required 仍开 ⇒ patch 被拒。
- **不新增运行时探测 / 健康检查**：那是另一个产品面，且与「密钥只引用」红线纠缠。

## D3. E 基准设计

- 20 组互不重叠的同义词域；每组三词（查询表面 / gold 同义表面 / 干扰词）。
- 查询：`a b c`；gold：`a' b' c'`（零词面重叠）；干扰：`a d c`（与查询共享 2 个词面）。
- 两个独立 store：
  - 词法：无 embedder，BM25；预期干扰排前、gold 不进 top-1。
  - 语义：确定性 `ConceptEmbedder`（词 → 概念维；组内同义词映射同一维）；预期 gold 余弦
    1.0 排第一。
- 指标：recall@1 / recall@5 / MRR@5。断言语义 recall@1 ≥ 0.9、语义 MRR 显著高于词法；
  词法 recall@1 = 0。数字打印供人工查看。
- **局限**：假 embedder 证明「注入向量后排序按语义走」的通路与量纲，不证明真实模型质量；
  真实模型质量须在线测量（另立）。

## 兼容性与红线

- 无新第三方依赖；无网络；无密钥回显。
- `embedding_required=false`（缺省）⇒ 既有测试与运行时逐字不变。
- 不改 `exclude_source_prefixes=("beast.","pet")`、不改词法降级路径、不改端点表。

## 反证计划

1. 去掉 `validate_schema` 的 required 检查 ⇒ 空模型 + required 用例红。
2. 把 required 缺省改为 `true` ⇒ 既有「未知端点回退词法」用例红（证明缺省兼容）。
3. 图基准把邻接提升删除（退回扁平） ⇒ 图 recall 用例红。
