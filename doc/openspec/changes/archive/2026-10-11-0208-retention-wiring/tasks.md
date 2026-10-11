# Tasks 0208 — 保留策略接线

## 1. 规格（spec-first）

- [x] `specs/durability/spec.md`：**MODIFIED**「生命周期与保留策略」（全量替换，narrative 补「两配置键 +
      缺省关 + 接线点 + 存储配额未接」句 + **ADD** Scenario ×3；既有两 Scenario 逐字保留）
- [x] ADR-0198 +「变更追踪」表行
- [x] 其余 3 条 `durability` Requirement **逐字保留**

## 2. 测试先行（红）

- [x] 新 `tests/test_retention_wiring.py`：超限清理最旧 / 时间窗口清理过期 / pinned 豁免 /
      缺省零清理（零回归锚）/ 三面解析（spec 声明 + yaml + env）/ 非法值阻断启动
- [x] **反证**：摘 `_write_checkpoint` 的 apply 调用 ⇒ 清理用例红

## 3. 实现（绿）

- [x] `configuration/manager.py`：两 `ConfigSpec`（`durability.retention.max_count` /
      `durability.retention.time_window_s`）+ 访问器 `retention_limits()` +
      `_retention_errors` 校验（挂 `validate_schema`）
- [x] `runtime.py` `_write_checkpoint`：落盘后按已配置通道 `RetentionManager.apply`

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] **反证**：见 §2 末
- [x] `openspec validate 2026-10-11-0208-retention-wiring`
- [x] 手工归档（MODIFIED 合并，Scenario 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失；
      `durability` 4→4 req / 14→17 scen）
- [x] `doc/04-testing/test-cases.md` §121 + 基线 bump；台账 E145（`known-risk.md` §1）+
      §3 ADR-0198 行；`doc/02-modules/durability.md` / `configuration.md` 增补
- [x] 单次提交 `feat(durability): 保留策略接线（change 0208 / ADR-0198 / 台账 E145）`
