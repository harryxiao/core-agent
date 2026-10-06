# tasks — 神兽/宠物任务结果可见性（change 0113 / phase-28 E46）

## 1. 规格（先行）
- [x] 1.1 `specs/beast-mode/spec.md`：ADDED「Task Result Visibility」——结果经会话**只读查询面**取用 +
      `summon` CLI 呈现 + **不落 L2 / 封存语义逐字不动** + 无结果不谎报（3 场景）
- [x] 1.2 `specs/pet-mode/spec.md`：ADDED「Task Result Query」——`PetControl.result` + 寻址规则一致 +
      **`status` 返回面逐字不变** + 只本进程/只最近一次/不落盘 + 无结果不谎报（4 场景）
- [x] 1.3 `openspec validate 0113-beast-pet-result-visibility` 通过

## 2. 测试（先写，红）
- [x] 2.1 新 `tests/test_beast_result_visibility.py`：召唤后 `result_summary()` 返回 `{agent_id, has_result,
      reply, failed}` 且 `reply` 与 handoff 返回的 `LoopResult.reply` **同一来源**；未执行会话 ⇒ `has_result=False`、
      `reply is None`
- [x] 2.2 同文件：CLI `summon`（真 argv + `capsys`）⇒ stdout 含结果正文；**无结果**（注入 fake 无 handoff 的
      manager / 空 router）⇒ stdout **不含**伪造正文
- [x] 2.3 同文件：**封存语义守护** —— 断言主 loop 装配的 `exclude_source_prefixes` 仍含 `"beast."`
      （`runtime.build_runtime` 后读装配对象；结果可见性**未**引入第二写路径）
- [x] 2.4 新 `tests/test_pet_result_query.py`：`wake()` 后 `control.result()` 返回 `{session_id, has_result,
      reply, failed}`，`reply` 为 loop 返回正文；未唤醒 ⇒ `has_result=False`
- [x] 2.5 同文件：**`status` 面守护** —— 同一会话下 `control.status()` 的键集合**逐字等于**既有六键
      （`session_id/state/sleeping/pending/wake_count/fault`），且**不含** `reply`/`preferences`
- [x] 2.6 同文件：寻址三分支（单宠物默认 / 多宠物未指定 ⇒ `PET_TARGET_AMBIGUOUS` / 未注册 ⇒ `PET_NOT_FOUND`）
- [x] 2.7 同文件：CLI `pet result`（真 argv + `capsys`）走通 + 未知会话退出码 1
- [x] 2.8 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `beast/session.py`：`result_summary() -> dict`（取用既有 `last_result`，只读、不落库）
- [x] 3.2 `pet/core/session.py`：`__init__` 增 `last_result: LoopResult | None = None`；`wake()` 内自留一份
      （**不进 `snapshot`**）
- [x] 3.3 `pet/core/control.py`：`result(session_id=None) -> dict`（复用 `_resolve` 寻址）
- [x] 3.4 `entry.py`：`_summon` 呈现结果；`pet` verb 面加 `result`（help 串 + 分派 + `_print_pet_result`）
- [x] 3.5 `ui/api.py`：`pet_command` 加 `result` 分支（复用 `PetControl.result`）
- [x] 3.6 四门全绿（直连二进制，不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/pet-mode-interface.md`：控制面 verb 表加 `result`
- [x] 4.2 `doc/03-interfaces/beast-mode-interface.md`：`summon` CLI 呈现结果口径（如有 CLI 表）
- [x] 4.3 `doc/04-testing/test-cases.md`：TC-PET-xx / TC-BEAST-xx
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0106 —— 结果可见性走查询面（**否决落 L2**：封存条款自败；
      **否决改 `status`**：隐私条款）＋已知局限

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/{beast-mode,pet-mode}/spec.md` + tick tasks +
      `shutil.move` 进 `archive/2026-10-06-0113-beast-pet-result-visibility/`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填（`phase-28.md` §0/§1.3/§4 E46 → 已闭 + 判据订正；`README.md` 同步）
- [x] 5.4 记忆更新 + 提交（`feat(beast,pet): …`，一个 Phase 一个 commit）
