# 任务：crash-recovery-e2e（E12）

## 1. 规格（先行）
- [x] 1.1 `specs/durability/spec.md` MODIFIED「崩溃恢复」：原子提交正文 + 两新场景
- [x] 1.2 归档时合并进 `doc/openspec/specs/durability/spec.md`

## 2. 测试先行（`tests/test_durability_crash.py`，新）
- [x] 2.1 原子性（**红**）：写入中途失败（已截断目标）→ 既有检查点完好
- [x] 2.2 真实子进程 `SIGKILL` → 重载存储：检查点无丢失、`restore()` 取最近有效
- [x] 2.3 续跑幂等：按游标 `resume()` 不重复副作用；同句柄二次 `resume()` 无操作
- [x] 2.4 回归：`tests/test_durability.py` 既有用例全绿

## 3. 实现
- [x] 3.1 `src/core/durability/store.py`：`_persist` 改原子提交（tmp + `os.replace`）

## 4. 文档
- [x] 4.1 `doc/02-modules/durability.md`：持久化写入为原子提交（若该文件记写入语义）
- [x] 4.2 `doc/03-interfaces/durability-interface.md`：**无需改**（该文档不记存储实现语义，只记实体/管理器/恢复接口 —— 已核实）

## 5. 验证与收尾
- [x] 5.1 四门全绿（ruff / format / pyright / pytest）
- [x] 5.2 `openspec validate 0062-…` → 手动归档 → `openspec validate --all`
- [x] 5.3 账本 E12 关闭 + §9 步骤 9；`phase-2.md:122` 验收框注
- [x] 5.4 提交 `fix(durability): 检查点持久化原子提交 + 真实崩溃续跑用例（change 0062）`
