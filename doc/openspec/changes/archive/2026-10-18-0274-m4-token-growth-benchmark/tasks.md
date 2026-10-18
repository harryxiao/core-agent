# Tasks 0274 — M4 长任务 token 增长基准

## 1. 规格

- [x] 1.1 `loop` delta：ADDED「长任务 token 增长基准」（4 scenarios；不设绝对阈值）。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_m4_token_growth.py`：固定 24 轮序列 ＋ 桩 provider ＋ 有界摘要器；
      采集逐轮 `last_prompt_tokens()`，打印曲线与斜率。
- [x] 2.2 次线性判据：外置远期逐轮恒定；整体斜率 < 全量回灌基线；末轮占用 < 基线。
- [x] 2.3 确定性：两次运行曲线逐值一致。

## 3. 实现

- [x] 3.1 仅测试与文档；不改生产代码（若基准揭示膨胀缺陷，另立 change 修复）。

## 4. 验证

- [x] 4.1 反证：摘要不注入 / 维护节拍关闭 ⇒ 对应用例红；复原后全绿。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0264；`coding-plan/known-risk.md` 台账 E210 ＋ §3 局限行。
- [x] 5.2 `doc/04-testing/test-cases.md` §186；`doc/00-product/product-definition.md` M4 行补「衡量落地」。
- [x] 5.3 `coding-plan/Pending-Arbitration.md` 关闭 PA-10。
- [x] 5.4 单次提交 `feat(loop): ... change 0274 / ADR-0264 / 台账 E210`；更新记忆。
