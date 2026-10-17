# Tasks 0239

- [x] 取证：5 红于干净 HEAD 复现；组一 traceback 定位 `_await_post_turn` × `asyncio.run`
      新 loop；`git log` 锁定 7357a11（轮末收尾后台化）与 0236（空壳门）
- [x] 修 1：`default.py::_await_post_turn` 以 `task.cancelled()` 分野吞旧/传播新
- [x] 修 2：`test_benchmark_runner.py` 桩按「技能内容蒸馏器」分派 `_SKILL_CONTENT_JSON`
- [x] 五红全绿（63 passed）＋ 全量 **2655 passed，0 失败**（并行批次后仓库首次全绿）
- [x] 四门禁：`ruff check` ✓ / `ruff format --check` ✓ / `pyright`（无参，0-0-0）✓ / `pytest` ✓
- [x] 反证 A/B（摘 ⇒ 3 红 / 2 红；复原 md5 同 ⇒ 绿）
- [x] `openspec validate` → 归档
- [x] 台账：ADR-0223、E170、测试节 §146
- [x] 提交
