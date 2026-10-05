# tasks — 0070 pet 前置判定接入 ConfigSpec 三层链（账本 E21）

## 1. 实现
- [x] 1.1 `ConfigManager.config_value(key)`：装配前只读单键解析（CLI > env > yaml > 缺省），缺文件容错
- [x] 1.2 `_flatten_by_specs`：按 `map_to` 取路径、以 `spec.key` 回填（键名不同名也对得上）
- [x] 1.3 `entry._pet`：门控与 `persons_dir` 改用 `config_value`；`ConfigManager` 提前构造并复用给 `build_runtime`

## 2. 测试（先红后绿）
- [x] 2.1 红：`tests/test_entry.py::test_pet_yaml_admits_and_honors_persons_dir` 在改 `entry.py` 前失败（已验）
- [x] 2.2 绿：`tests/test_entry.py` +yaml 采信 / +env 压过 yaml / +缺文件容错
- [x] 2.3 绿：`tests/test_configuration.py` +`config_value` 四例（yaml 层 / 三层链 / 缺省兜底 / 缺文件 / 键名不同名）

## 3. 文档
- [x] 3.1 `doc/03-interfaces/configuration-interface.md`：接口块 + §2.5 装配前单键解析
- [x] 3.2 `doc/04-testing/test-cases.md`：TC-CONF-04 / TC-CONF-05

## 4. 收口
- [x] 4.1 四门（ruff / pyright / pytest / openspec validate）
- [x] 4.2 账本 `coding-plan/phase-19.md`：§1 E21 行 + §3 E21 段 + §9 + 新增 E22 行；README 同步
- [x] 4.3 记忆与提交
