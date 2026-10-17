# Tasks 0238

- [x] 取证：复现 traceback 与安装 textual 8.2.8 逐行对齐；上游 issue #6643（OPEN）+
      最新 release = 8.2.8 ⇒ 升级不可修
- [x] 用户裁决修法：App 边界守卫（否决 compositor 过滤 / 关闭选择）
- [x] 测试先行：`tests/test_ui_event_guard.py` 3 用例（承重红 + 两守护锚绿）
- [x] `repl.py`：`ReplApp.on_event` 覆写，`contextlib.suppress(AttributeError)`
- [x] 转绿（3/3）；邻域回归（repl / ui / turn_cleanup 137 passed）
- [x] 四门禁：`ruff check` ✓ / `ruff format --check` ✓ / `pyright`（无参，0-0-0）✓ /
      `pytest -q` 2650 passed（5 红为并行批次遗留，`git stash` 于干净 HEAD 复现，非本 change）
- [x] 反证：摘守卫 ⇒ 1 红；复原 md5 同 ⇒ 绿
- [x] `openspec validate` → 归档
- [x] 台账：ADR-0222、E169、测试节 §145
- [x] 提交
