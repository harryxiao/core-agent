# Design — persist-skills-state

## 决策 1：逐类自持落盘，共用两个纯函数（不新建存储服务）

仓库既有的落盘惯例是三处各自实现「`path: Path | None` + `_load()`/`_persist()`」
（`memory/backend.py`、`durability/store.py`、`deployment/host.py`）。A3 涉及四个类，
若各自复制「读 JSON + 容错 + 原子写」会产生四份易漂移的实现；若新建一个通用存储服务，
又与「核心零第三方向依赖 + 不为单点建抽象」冲突。

取**中间解**：`src/core/skills/persist.py` 只放两个无状态纯函数——

- `read_state(path: Path | None) -> Any`：`None` / 文件缺失 / 非法 JSON → `None`（不抛）；
- `write_state(path: Path | None, data: Any) -> None`：`None` → 直接返回（不写盘）；否则
  `json.dump` 到同目录临时文件后 `os.replace` 原子替换。

四个类各自持有自己的 `path` 与序列化形状（各状态结构不同，序列化不该被抽象吃掉），
只把「字节进字节出」交给纯函数。**放在 skills 包内**（不提到 `core/` 顶层）：它只服务技能态，
不构成横切能力，也不引入新的分层箭头。

## 决策 2：JSON 快照（非 JSONL）

既有 `memory.jsonl` / `checkpoints.jsonl` 是**追加式日志**（条目只增不改、天然可截断），
而技能态是**可变快照**（技能字段会被迭代改写、灰度状态会被覆盖、样本组提炼后清空）。
用单文件 JSON 整体重写更贴合语义（读到的就是最新态，无需重放去重），也与
`entry.py` 的 `serve.json` / `releases.json` 同类。

## 决策 3：`path=None` 为缺省 = 纯内存（向后兼容）

四个组件的路径参数一律可选、缺省 `None`，保持「不注入就不落盘」——既有测试与
`SkillLibrary()` 这类纯内存构造**零改动**，落盘只是组合根的选择。生产侧由
`build_runtime` 显式注入 `$CORE_STATE_DIR`（同 `_memory_path()` 约定，env 可覆盖，
测试经 conftest 已隔离）。

## 决策 4：`VersionManager` 落盘须由 runtime 显式构造并注入

`SkillIterator` 在未注入 `versions=` 时**内部自建**一个 `VersionManager`
（`iteration.py:85-91`），runtime 拿不到它。因此 `build_runtime` 改为显式构造
`VersionManager(skill_library, metrics=feedback.success_rate, path=…)` 再传给
`SkillIterator`——顺带让「灰度/A-B 指标 = 各版本成功率」这条口径在生产侧显式化
（此前藏在 `SkillIterator` 的缺省分支里）。

## 决策 5：损坏降级为空态，不阻断启动

`read_state` 对非法 JSON / 非预期结构一律返回 `None` → 组件以空态启动，后续写入覆盖。
理由：技能态是**可重建的派生数据**（技能库能从记忆/提炼重建、样本能从后续轨迹重攒），
为它阻断启动（像 `ConfigManager.load()` 那样结构化拒绝）不成比例。与
`CheckpointStore` 的「损坏标记 + 跳过」同属一类防御。

## 备选与否决

- **新建通用 `StateStore` 服务**：否决——四个类状态形状各异，抽象层会迫使它们共享序列化协议，
  收益为负（见决策 1）。
- **复用 `memory.FileBackend`**：否决——它绑死 `MemoryEntry` + `Layer`，与技能态无关。
- **JSONL 追加**：否决——见决策 2。
