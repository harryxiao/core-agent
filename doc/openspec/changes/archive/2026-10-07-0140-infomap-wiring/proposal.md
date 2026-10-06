# 0140 · 信息地图装配接线（skip_specs）

> 账本：`coding-plan/phase-34.md` **E77**（信息地图不可达：构造了却从不查）
> 规格面：**无 delta**（`context/spec.md`「信息地图」及三个 Scenario 早已是硬 SHALL）
> ADR：**0133** ｜ 用户裁决（§6.5 终裁）：**E73 / E77 死面 = 都补齐接线**

## Why

`context/spec.md`「信息地图」SHALL「把长文档转化为轻量化目录索引，**模型按需跳转获取细节**，
不把全文塞入窗口」，并以三个 Scenario 定格实现面：「地图定位与按需取详情」「地图失效重建」
「重建失败二阶兜底」。而实现是**纯背离**（E77）：

- `context/assembler.py` 的 `build()` **从不读** `_info_map`（`:32` 只在 ctor 存下）⇒ 装配出的
  `ContextPack` 里**没有任何目录层**，「先定位指针再取片段」的链路**不存在**。
- `assembler.fetch_detail()` **零生产调用点**（仅测试直调）⇒ 即使有指针，模型也**无通道**取详情。
- `context/info_map.py` 的 `_linear_scan()` 是**死码**：`index()` 恒同时写 `_docs` + `_maps`
  ⇒ `lookup()` 的「地图缺失」分支不可达 ⇒ 「重建失败二阶兜底」无法表达。

## What

**不改规格、不改动既有语义**，只把三级链路接通（全部为**增量**，缺省路径逐字不变）：

1. **地图可达（装配面）**：`DynamicAssembler.build()` 读信息地图，把各文档的**任务匹配指针**
   汇成目录层注入 `ContextPack.pointers`（新增字段，缺省空 ⇒ 未接地图时行为逐字不变）；
   `LLMPlanner._system_prompt` 渲染「文档目录（按需取详情，勿请求全文）」块 ⇒ 模型**先看目录**。
2. **取详情可达（消费面）**：新增只读原子工具 `tools.context_read`（按指针取片段、**不加载全文**），
   取数器**由组合根注入**（与 `gate_run` 执行器注入同理，工具层不依赖 context 层），
   `build_runtime` 注册到主工具面 ⇒ 模型**有通道**取详情。
3. **二阶兜底复活**：`InfoMap.register(doc_id, content)` = 仅登记**原文**（不建索引）⇒ 该文档的
   `lookup` 走 `_linear_scan` 受控分段线性扫描；扫描段数设硬上界（`_MAX_SCAN_SEGMENTS`）
   ——「受控」二字落为可断言的常量。
4. **生产非空转**：`build_runtime` 把 Core.md「## 项目信息」段建成目录索引（`core-profile`）
   注入装配器 ⇒ 地图在产线**非空**，`build()` 的读取与工具的取详情**都有真实对象**。

## 影响

- **零回归**：`ContextPack.pointers` 缺省空、`_gather_pointers` 对空地图返回空 ⇒ 既有装配/预算/
  提示词路径逐字不变；`token_used` 口径不变（指针目录**不计入**预算测量，规模由
  `_MAX_POINTERS_PER_DOC` / `_MAX_SCAN_SEGMENTS` 双重上界约束 —— 见 ADR-0133 已知局限①）。
- **工具面 +1**：`tools.context_read`（只读、`coeffects=[]`、`reversible=True`）；`test_phase13`
  的生产工具面清单同步 +1。权限分级按**完整词元**命中 `read` ⇒ 判只读放行（不落 deny-by-default）。
- **不改分档与封存**：`exclude_source_prefixes=("beast.", "pet")` 红线不动；本 change 只增目录层，
  不触碰记忆检索与预算裁剪判据。

## 验证

- `.venv/bin/ruff check src tests` / `ruff format --check` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ **1674 passed**（1665 → 1674，+9：`test_context` +5、新增
  `tests/test_infomap_wiring.py` +4）。
- `openspec validate --all` ⇒ 30 passed / 0 failed（无 delta ⇒ 计数不变）。

## 风险与已知局限

- **指针摘要语义**：`_build_pointers` 的 `summary` = 章节名（既有语义，本 change **不改**）⇒
  `context_read` 对**索引态**文档返回章节名、对**原文态**（线性扫描）返回该段原文；
  「用 LLM 提炼要点摘要」不在 E77 账内（另账）。
- **无 Rust/JS 面**：本 change 全 Python，四门禁即可覆盖。
