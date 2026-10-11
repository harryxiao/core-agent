# Tasks 0220

- [x] **PA-04**：`src/core/evolution/author.py` 加 `_FENCE_ANY` ＋ `strip_fence` 兜底（整体匹配失败
      取末块）；`tests/test_evolution_author.py` ＋4 测试（无围栏原样、说明+围栏取块、多块取末、接缝级）。
- [x] **PA-05**：新 `tests/test_prompt_mirror.py`（13 常量逐行核对 ＋ ⑬⑭ 登记断言）。
- [x] **PA-06**：`src/core/memory/episodic.py` ⑧ 教训段加「可复用的判据」；同步 pin 副本
      （`tests/test_prompt_pinning.py::_EPISODIC_HEAD`）＋ `doc/03-interfaces/prompts.md` §3⑧。
- [x] 三组反证（PA-04 摘兜底 / PA-06 还原措辞 / PA-05 改 ④ 常量）＋ 复原 `md5sum` 逐个相同。
- [x] ADR-0210 ＋ 变更追踪表。
- [x] `doc/04-testing/test-cases.md` §133（TC-LOWRISK，4+14 用例）。
- [x] `coding-plan/known-risk.md` §1 E157 / §3 ADR-0210；`coding-plan/Pending-Arbitration.md` 标
      PA-04 / PA-05 / PA-06 **已闭**。
- [x] 四门禁 ＋ `openspec validate --all` ＋ 手工归档 ＋ 台账回填 ＋ 单次提交。
