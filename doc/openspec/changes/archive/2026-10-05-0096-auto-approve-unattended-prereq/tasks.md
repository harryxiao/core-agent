# tasks — auto-approve 无人值守前置条件补记（change 0096）

## 1. 事实核定（改前）
- [x] 1.1 核 `guardrail` 注入条件：仅当 `judgment.provider` 存在才注入 ⇒ 缺省 `guardrail=None`
- [x] 1.2 核 MCP 出站白名单缺省：`permission.sandbox.host_allowlist` 空 ⇒ `check_outbound` fail-closed
- [x] 1.3 核出站策略消费者：仅 MCP http/streamable 传输；`web_fetch`（urllib）/ `code_run`（非沙箱）不受限
- [x] 1.4 核进化结晶门：与权限档零耦合（`engine.py`「不引入低风险自动结晶」）

## 2. 文档
- [x] 2.1 `doc/03-interfaces/permission-interface.md` §6：新增「无人值守前置条件（change `0096`）」三行表 + 结论 + 熔断说明
- [x] 2.2 `doc/01-architecture/adr.md` ADR-0090：新增「已知边界（无人值守前置条件，change `0096` 补记）」条

## 3. 规格
- [x] 3.1 判**规格中性**（`skip_specs`）：规格已含 `auto-approve 与安全红线正交` 场景，本 change 补缺省装配**事实**
- [x] 3.2 `openspec validate 2026-10-05-0096-auto-approve-unattended-prereq` 通过

## 4. 收口
- [x] 4.1 `coding-plan/phase-19.md` §9 步 10：补 0096 后续行
- [x] 4.2 手动归档（`shutil.move` 进 `archive/2026-10-05-0096-...`）+ `openspec validate --all` 全绿
- [x] 4.3 记忆更新 + 提交（`docs(permission): 无人值守前置条件（change 0096）`）
