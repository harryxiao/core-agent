# Tasks — 0302 记忆注入面分层、溯源与信任声明

## 1. 规格与测试先行

- [x] 1.1 `specs/memory/spec.md` ADDED ×1（记忆检索的层过滤）
- [x] 1.2 `specs/context/spec.md` MODIFIED ×1（动态上下文构建：层白名单 / 人格通道 / 溯源 / 信任声明）
- [x] 1.3 新增 `tests/test_memory_layer_filter.py`（4：只返指定层 / 先于预算 / 缺省兼容 /
      与来源排除 + 会话过滤叠加）
- [x] 1.4 新增 `tests/test_facts_provenance.py`（7：事实面只 L1/L2 / L4 不吃预算 /
      人格独立且不进 facts / 人格必保 / 溯源格式与 unknown / 声明与项目信息隔离）
- [x] 1.5 红/绿分布记录（实现前两文件红）；实现后逐项回退复验见 4.3（5 组反证）

## 2. 实现

- [x] 2.1 `MemoryStore.read(..., layers=())`：排名/预算前按层过滤；`protocol.py` 同步
- [x] 2.2 `ContextPack.personality` 字段；`BudgetManager` 计入测量与必保项
- [x] 2.3 `DynamicAssembler`：事实层白名单 `("L1","L2")`、`_gather_personality`、事实项带
      `layer/source/id/date`
- [x] 2.4 `planner.py`：人格独立块、事实 `[FACT|…]` 格式与块首声明、项目信息独立块
- [x] 2.5 既有装配器测试替身补 `**kwargs`（仅测试代码）

## 3. 文档账

- [x] 3.1 `doc/02-modules/memory.md`：§3.17 补层过滤；§5 修正「写入失败」行（P1-6）；
      §3.5 登记 importance 同步评分开销（P2-6）
- [x] 3.2 `doc/03-interfaces/memory-interface.md`（`read(layers=)`）、
      `doc/03-interfaces/context-interface.md`（`personality` / facts 溯源 / 渲染）
- [x] 3.3 ADR-0292 + known-risk E238 + test-cases §215

## 4. 门禁与反证

- [x] 4.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 4.2 `uv run pytest -q` 全量全绿
- [x] 4.3 反证（`cp` + `md5sum`）：去层过滤 / 事实白名单回全层 / 去人格通道 / 去溯源 /
      去声明 —— 各自对应用例红，复原后 `md5sum` 一致
- [x] 4.4 `cd doc/openspec && openspec validate --all`（归档前全绿）
- [ ] 4.5 归档 / 提交（用户确认后）
