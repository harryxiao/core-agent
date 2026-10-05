# tasks — skillhub 供给侧接线（change 0105）

## 1. 规格（先行）
- [x] 1.1 `specs/skillhub/spec.md`：MODIFIED「技能市场与技能发现」（目录可落盘 + 跨进程可见场景）
- [x] 1.2 `specs/skillhub/spec.md`：MODIFIED「签名校验与可信下载」（本地市场制品库 fetcher + 篡改拒绝场景 +
      「市场未接入」GIVEN 改写）
- [x] 1.3 `specs/skillhub/spec.md`：MODIFIED「技能发布与审核流」（CLI 生产触达点 + 制品入库 + 审核跨进程 +
      版本提升落盘 + 3 新场景）
- [x] 1.4 `openspec validate 2026-10-05-0105-skillhub-supply-side-wiring` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_skillhub.py` 追加：`MarketIndex(path=…)` 跨实例保持目录；损坏文件降级（warn）且官方源仍在；
      `locate` 跨源定位
- [x] 2.2 `tests/test_skillhub.py` 追加：`SkillPublisher(artifacts=…)` 发布后制品可被拉取；**跨实例审核**
      （另一实例 publish → 本实例 review approved ⇒ published + v2 落盘）
- [x] 2.3 `tests/test_skillhub_cli.py` 追加：**供给侧闭环端到端**（publish → 重开目录断言 pending →
      search 命中 → review approved → 重开断言 published/v2 → install → 重开技能库断言 draft）
- [x] 2.4 `tests/test_skillhub_cli.py` 追加：publish 未注册技能 ⇒ 退出 1 + 不落盘；制品篡改后 install ⇒
      退出 1 + 不落盘；review 未发布技能 ⇒ 退出 1
- [x] 2.5 既有 `test_skill_install_without_market_reports_error` 语义对齐（缺省装配已含本地 fetcher ⇒
      「本地市场无该技能」）
- [x] 2.6 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `skillhub/index.py`：`MarketIndex(path=…)` 装载/落盘（`core.persistence` 原子写 + 损坏降级）+
      `locate()`
- [x] 3.2 `skillhub/publisher.py`：删 `_published`、`review` 经 `locate` 定位源并回写 `put`；
      `publish` 增 `artifacts` 入库
- [x] 3.3 `entry.py`：`_build_market_index` / `_build_market_artifacts` / `_build_publisher` +
      `_build_skillhub_client` 注入落盘目录与本地 fetcher
- [x] 3.4 `entry.py`：`skill publish` / `skill review` 子命令（parser + 分派 + 退出码）
- [x] 3.5 四门全绿（直连二进制不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/skillhub-interface.md` §2（fetcher 本地市场）/§3（落盘 + locate）/§4（发布触达点）
- [x] 4.2 `doc/02-modules/skillhub.md` §3.1/§3.3/§4（供给侧已接线；凭证半口径订正）
- [x] 4.3 `doc/01-architecture/adr.md`：**ADR-0098**（落盘目录 + `_published` 删除 + 制品入库 + 不做消费闸门）
      + 末尾映射表行
- [x] 4.4 `doc/04-testing/test-cases.md`：`TC-SKH-*` 用例组
- [x] 4.5 `coding-plan/contracts_summary.md` skillhub 行（供给侧契约**已兑现**，不写「未启用」）
- [x] 4.6 `coding-plan/phase-22.md` §4 落地状态；`coding-plan/README.md` §2 第 22 行

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/skillhub/spec.md` + tick tasks + `shutil.move`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填
- [x] 5.4 记忆更新 + 提交（`feat(skillhub): 供给侧接线（change 0105）`）
