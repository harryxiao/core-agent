# Tasks 0269 — 钩子实现

## 1. 配置面

- [x] 1.1 `_CONFIG_SPECS` 增 `hooks.enabled` / `hooks.timeout_s` / `hooks.on_error` 三个标量
- [x] 1.2 `_parse_yaml_subset` / `_dump_yaml` 支持块序列与行内 flow 列表/映射（round-trip）
- [x] 1.3 `ConfigManager` 增 `hooks_enabled` / `hooks_timeout_s` / `hooks_on_error` / `hooks_entries`，超时截断告警

## 2. 钩子包

- [x] 2.1 `HookEvent` / `HookEntry` / 事件词表 / `match` 收窄
- [x] 2.2 载荷递归脱敏（正则 + 登记密钥）、单串上界、摘要（长度 + 哈希前缀）
- [x] 2.3 执行器：argv 子进程（不经 shell、白名单环境、超时、输出丢弃）+ 内置回调
- [x] 2.4 `HookManager`：before/after 分派、`on_error`、`kind="hook"` trace、会话幂等与 `close()`

## 3. Loop 接缝

- [x] 3.1 中间件 / 结果观察者可等待（同步实现逐字不变）
- [x] 3.2 `turn_before`（可否决）与 `turn_after`（只留痕）注入点；`current_trace_id` ContextVar
- [x] 3.3 `ActionResult.duration_ms` 供 `tool.after` 载荷

## 4. 记忆 / 组合根

- [x] 4.1 `MemoryStore(write_observer=...)`，公开 `write` 落库后通知，异常吞掉
- [x] 4.2 `build_runtime` 构造 `HookManager`、接四个 loop 与 `MemoryStore`、登记密钥明文
- [x] 4.3 `session.start` 首轮幂等 / `session.end` `atexit`

## 5. 测试与门禁

- [x] 5.1 新 `tests/test_hooks.py`：阻断 / 只留痕 / 超时 on_error / 环境白名单 / 脱敏 / 会话幂等 / 记忆不可否决 / 四个 loop 接缝
- [x] 5.2 `tests/test_configuration.py` 补 YAML 序列与 hooks 三层优先级、超时截断
- [x] 5.3 反证：摘关键分支对应用例红，复原 `md5sum` 同；四门禁 + `openspec validate --all`
- [x] 5.4 archive + ADR-0259 + 台账 E205 + 测试节 §181 + 模块文档 + 单次提交
