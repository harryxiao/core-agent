# 0225 任务 — 镜像失真收口

- [x] 1. **实测取证**：脚本核对 §1 落点列 14 行 ⇒ **4 条失准**（①③⑥⑩）；grep 出 §4⑪／§2①／§3⑩
      三处旁注失真（其中 ①⑩ 由 `0222`/`0223` 引入，③⑥ 由提词收紧轮引入）。
- [x] 2. **纠错（M1）**：§4⑪ 旁注改写为「两道剥围栏 ＋ 不匹配即原样返回」。
- [x] 3. **行号（M2）**：§1 落点列 4 条改正（表 ＋ 标题共 8 处）。
- [x] 4. **旁注（M3）**：§2① 补形态 5 ＋ 流式未修；§3⑩ 补 `failure_steps` 节。
- [x] 5. **测试先行（红）**：`tests/test_prompt_mirror.py` 增落点行号核对 ＋ 加固点锚 ⇒ 先红
      （4 行失准 ＋ 旁注缺锚），改文档后转绿。
- [x] 6. **门禁加固（M4）**：两节转绿；`ruff check` / `ruff format --check` 通过。
- [x] 7. **指引（M5）**：§7 补第 4、5 步。
- [x] 8. **PA 簿（M6）**：§0 同步已闭 ＋ 出口约定第③条 ＋ §4 已转出索引 ＋ §2 行号口径 ＋ §3 行号。
- [x] 9. **反证（实测两组）**：① §1 落点行号改回 `:50` ⇒ `test_mirror_landing_line_points_at_symbol[①]`
      **`1 failed, 31 passed`**；② 镜像摘 `_FENCE_ANY` ⇒
      `test_mirror_notes_carry_known_hardening_anchors[0220 …]` **`1 failed, 31 passed`**。
      复原 ⇒ `prompts.md` `md5sum` **逐字节相同**（`24a38ee64628e8a46e10ebd413b61c92`）、复测 **32 passed**。
- [x] 10. **四门禁**：`ruff check` ✓ ／ `ruff format --check` ✓（403 文件）／ `pyright` **0-0-0** ／
      `.venv/bin/pytest -q` ⇒ **2534 passed**（基线 **2516**，**+18**；`test_prompt_mirror` 14 → 32）。
- [x] 11. **收口**：ADR-0215 ＋ `known-risk.md` §1 E162／§3；`test-cases.md` §138；归档 ＋ 单次提交。
      **注**：本环境**无 `openspec` CLI**（未安装）⇒ **未复跑** `validate`；本 change `skip_specs: true`
      且**零 spec delta** ⇒ canonical 计数不变（与 `0220` 同口径）。
