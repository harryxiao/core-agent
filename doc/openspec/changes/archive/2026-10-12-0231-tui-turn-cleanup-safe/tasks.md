## 1. Specification
- [ ] 1.1 **规格中性**（`skip_specs: true`）：`ui` spec 不约束收尾顺序 / 忙态复位 ⇒ 零 spec delta、canonical 计数不变。
- [ ] 1.2 `openspec validate --all` 全绿。

## 2. Tests（先红）
- [ ] 2.1 新 `tests/test_ui_turn_cleanup.py`（复用 `test_repl.py` 的 `build_app` / `run_test` harness）：
  ①`_end_turn(flush_live=True)` 在 `_flush_live` 抛错后仍复位忙态（**承重**，单元）；
  ②`_end_turn` 在 `_spin_stop` 抛错后仍复位忙态（单元）；
  ③普通轮 `_spin_stop` 抛错 ⇒ 轮后忙态复位（集成）；
  ④任务轮 `/task` 同 ③（集成）；
  ⑤神兽轮 `/summon` 同 ③（集成）；
  ⑥`on_input_submitted` 中 `run_worker` 抛错 ⇒ 忙态复位（分发口守卫）。

## 3. Implementation
- [ ] 3.1 `repl.py`：新 `_end_turn`；三 runner `finally` 改调之、`_spin_start` 移入 `try`；分发口补复位守卫。

## 4. Gates & Archive
- [ ] 4.1 四门禁：`ruff check` / `ruff format --check` / `pyright`（**无参**）/ `pytest -q`。
- [ ] 4.2 反证：把 `_end_turn` 还原为裸序列（`_spin_stop()` 前先 `_turn_busy=False`）⇒ 承重用例红；复原 ⇒ md5 同。
- [ ] 4.3 `openspec validate --all`；手工归档；台账回填（E167 / ADR-0220 / §143）；**单次提交**。
