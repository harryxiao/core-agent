# tasks — 出站白名单可配

## 1. 配置面（ConfigSpec 单一真源）

- [x] 1.1 `_CONFIG_SPECS` 增 `permission.sandbox.host_allowlist`
      （cli `--permission.sandbox.host-allowlist` / env `CORE_SANDBOX_HOST_ALLOWLIST` /
      default `""` / map_to `permission.sandbox.host_allowlist` / exposure `ADVANCED`）
- [x] 1.2 访问器 `sandbox_host_allowlist() -> list[str]`（缺省 `[]`，读嵌套 `extra`）
- [x] 1.3 `_split_hosts()`：逗号分隔 → 去空白 / 去空项 / 保序去重（兼容全角逗号）
- [x] 1.4 `_sandbox_errors()` + `validate_schema` 接线：非裸主机名 / 非字符串取值
      ⇒ `ConfigurationError` 阻断启动

## 2. 组合根

- [x] 2.1 `runtime.py`：`SandboxPolicy(host_allowlist=config.sandbox_host_allowlist())`
      （客户端与沙箱管理器仍共用同一实例）

## 3. 测试（先红后绿）

- [x] 3.1 `tests/test_permission_sandbox_config.py`：ConfigSpec 三面齐备
- [x] 3.2 缺省 `[]`（fail-closed）/ yaml CSV 归一（trim / dedupe / 全角逗号）
- [x] 3.3 env 覆盖 yaml / CLI 覆盖 env 与 yaml
- [x] 3.4 非法条目（scheme / 端口 / 路径 / 内部空白）与非字符串取值阻断启动
- [x] 3.5 组合根注入（策略单实例）+ 端到端（生产 http 守卫放行 / 拒绝）+ 缺省全拒回归
- [x] 3.6 红→绿证据：stash 源码 ⇒ 14 failed / 1 passed；恢复 ⇒ 15 passed

## 4. 文档

- [x] 4.1 `doc/03-interfaces/permission-interface.md` §4 补 `SandboxPolicy` 与配置路径
- [x] 4.2 `doc/03-interfaces/configuration-interface.md` 段与访问器
- [x] 4.3 `doc/02-modules/permission.md` 出站白名单来源
- [x] 4.4 `doc/01-architecture/adr.md` ADR-0068 + 映射表行
- [x] 4.5 `doc/04-testing/test-cases.md` 用例号

## 5. 归档与销账

- [x] 5.1 合并 spec delta 进 `doc/openspec/specs/permission/spec.md`（手动归档）
- [x] 5.2 变更目录移入 `doc/openspec/changes/archive/2026-10-05-0071-sandbox-host-allowlist-config/`
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 账本 `coding-plan/phase-19.md` §1 B5 行 ✅ + §4 B5 关闭块 + §0 + §9 第 5 步
- [x] 5.5 `coding-plan/README.md` 状态 / 依赖单元格
- [x] 5.6 四门（ruff check / format / pyright / pytest）
