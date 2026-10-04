# 任务：llm-reliability-tests（E11①）

## 1. 规格判断（先行）

- [x] 1.1 判定为**规格中性**（四场景行为已存在，只补验证）→ `.openspec.yaml: skip_specs: true`
- [x] 1.2 机制核实：临时 `0060-probe` 变更验证 `skip_specs` 被 `openspec validate` 接受后删除探针
- [x] 1.3 明写遗留：规格内「连接复用」条**未实现**，属 E11②，不在本变更内

## 2. 用例（`tests/test_llm_provider.py` 新增「模型调用可靠性」节）

- [x] 2.1 退避口径：指数 + 封顶（`_backoff`）
- [x] 2.2 重试：瞬时错误重试至成功（次数 = 1 + `max_retries`）
- [x] 2.3 重试：耗尽抛归一化异常
- [x] 2.4 重试：非可重试错误不重试
- [x] 2.5 超时：慢调用不挂起调用方（实测耗时断言）
- [x] 2.6 降级：切备用模型成功 + 审计记实际成功模型
- [x] 2.7 降级：非瞬时错误不降级
- [x] 2.8 断流：无 `[DONE]` 提前结束 → 部分返回
- [x] 2.9 断流：传输中途异常 → 先给已收内容再抛归一化错误（惰性生成器，非 `list()`）

## 3. 实现

- [x] 3.1 **无**（9 例一次全绿 = 实现正确的证据；`src/` 零改动）

## 4. 验证与收尾

- [x] 4.1 四门全绿（ruff check / ruff format --check / pyright / pytest）
- [x] 4.2 `openspec validate 0060-llm-reliability-tests` → 手动归档 → `openspec validate --all`
- [x] 4.3 账本 E11 行标 **🔶 部分关闭（① change 0060）** + §3 E11 段替换为已关闭块（含②遗留）
- [x] 4.4 `doc/04-testing/test-cases.md` 追踪行（规格中性变更：登记用例节 + 遗留说明）
- [x] 4.5 提交 `test(llm-provider): 补模型调用可靠性用例（重试/超时/降级/断流，change 0060）`
