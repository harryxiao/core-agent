# tasks — `config get` 接入配置链 yaml 层（change 0078）

## 1. 测试先行（红）
- [x] 1.1 `test_config_get_default` 改 hermetic（显式 `--config <不存在>`）
- [x] 1.2 新增 `test_config_get_reads_yaml_layer`：`config.yaml` 的值被读到
- [x] 1.3 新增 `test_config_get_cli_overrides_yaml`：`--llm.model` 压过 yaml
- [x] 1.4 红证：实现前 1.2 得 `(未配置)`（yaml 层被漏），1.1 / 1.3 本就绿

## 2. 实现（绿）
- [x] 2.1 `src/core/entry.py`：`_config` 构造前移 + `get` 分支改 `mgr.config_value(args.key)`
- [x] 2.2 删除因此未使用的 `resolve` 导入
- [x] 2.3 绿证：全量 pytest **955 passed**（基线 953）+ 四门全绿

## 3. 规格
- [x] 3.1 判**规格中性**（`skip_specs`）：规格「配置源与分层」既有优先级链条款已覆盖，同 change `0070`
- [x] 3.2 `openspec validate 0078-config-get-yaml-layer` 通过

## 4. 文档
- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0075 + 变更追踪行 + ADR-0067 关联补指针
- [x] 4.2 `doc/00-product/user-guide.md`：单键读取处补「遵循同一优先级链」
- [x] 4.3 `doc/03-interfaces/configuration-interface.md` §2.5：消费方补 `config get`

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 表 E22 行、§4/§9 相应处
- [x] 5.2 `coding-plan/README.md`：状态行同步
- [x] 5.3 手动归档（移动目录）+ `openspec validate --all` 全绿
- [x] 5.4 记忆更新 + 提交
