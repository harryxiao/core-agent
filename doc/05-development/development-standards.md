# 工程开发规范（Development Standards）

> **定位**：Phase -1「工程规范基线」的第一个交付物，先于任何业务编码落地。
> 本规范把 roadmap `1.5 工程规范基线` 的 12 主题固化为可执行约束；
> 工具链门禁配置见 `pyproject.toml`（ruff / pyright），架构约束见 `tests/test_architecture.py`。
> 开发流程 / 提交规范见同目录 `development-guide.md`。

---

## 0. 门禁三件套

| 层 | 工具 | 配置位置 | 覆盖主题 |
|---|---|---|---|
| Lint / 风格 | ruff（0.15.x） | `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.format]` | 1 / 2 / 4 / 7 / 10 / 12 |
| 类型 | pyright（strict） | `[tool.pyright]` → `typeCheckingMode = "strict"` | 1 |
| 架构 | pytest 架构测试（零依赖，`ast`/`importlib`） | `tests/test_architecture.py` | 2 / 4 / 5 / 7 / 9 |

门禁命令：

```bash
ruff check src tests            # lint（select 规则集）
ruff format --check src tests   # 格式（行宽 100、双引号）
pyright                         # 类型（strict，include=src）
pytest -q                       # 单元 + 架构测试
```

> **提交前四者必须全绿**；后续每个 Phase 的代码须 100% 通过门禁，否则视为未完成。

---

## 1. Python 编码规范

- PEP 8 为基线，格式统一交由 `ruff format`（行宽 **100**、双引号）与 `ruff check` 裁决，不手写空格争议。
- 公共 API 强制类型签名；核心模块类型覆盖率目标 **100%**，由 `pyright --strict` 兜底。
- 目标版本 Python 3.11（`requires-python = ">=3.11"`，`target-version = "py311"`），可用 `X | None`、`list[T]` 等现代语法，由 `UP` 规则自动升级。

**门禁**：`E/F/I/UP/B/SIM/N/TRY/PERF/PLC/PLR/C90/TID` + pyright strict。

### 1.1 导入语句

- 导入按「标准库 → 第三方库 → 项目本地模块」分组，组间空一行；顺序由 `ruff I`（isort）自动裁决，不手动调整。
- 禁止单条语句导入多个模块（`import a, b`）；禁止 `from x import *` 通配符导入。
- 项目内一律使用绝对导入，禁止相对导入（`.module` / `..module`）。

**门禁**：ruff `I` + `E401` + `F403` + `TID252`；禁相对导入另有 Code Review 兜底。

### 1.2 文档与注释

- 公共模块、类、对外 API 强制 Google 风格 docstring：标注 Args / Returns / Raises 语义。
- 注释只解释「为什么」，不翻译代码；修改代码时同步更新注释。
- 内部函数可省略 docstring，仅在关键逻辑处加行注释。

**门禁**：Code Review（强制校验公共 API 文档完整性；pyright / ruff 均不查 docstring）。

### 1.3 函数与参数

- 函数体 ≤ 25 行，超限拆分；参数 ≤ 5 个，超限以 dataclass 封装入参。
- 禁止可变类型（list / dict / set）作默认参数，用 `None` 初始化后函数内赋值。
- 实例方法首参固定 `self`，类方法首参固定 `cls`，不得改名。

**门禁**：ruff `PLR0913`（参数数）、`PLR0911`（返回数）、`B006`（可变默认参数）；25 行 / dataclass / self·cls 靠 Code Review。

### 1.4 作用域与变量

- 全局变量仅用于模块常量，禁止可变全局变量；跨函数共享状态用类成员。
- 避免单字母变量名（循环索引 i/j 可豁免），禁用 `l` / `O` / `I` 等易混淆单字符名。
- 内层函数修改外层变量必须显式 `nonlocal`，禁止隐式闭包改外层状态。

**门禁**：Code Review（`A` / `RUF` 规则集当前未启用，如要静态拦截需先在 pyproject 增补）。

---

## 2. 命名约定

| 对象 | 约定 | 示例 |
|---|---|---|
| 类 / Protocol / 类型别名 | PascalCase（大驼峰） | `LoopPlugin`、`MemoryEntry`、`Layer` |
| 函数 / 方法 / 变量 | snake_case（小驼峰） | `run`、`list_index`、`trace_id` |
| 常量 | UPPER_SNAKE | `DEFAULT_BUDGET` |
| 私有成员 | `_` 单下划线前缀 | `_cache`、`_merge` |
| name-mangling | `__` 仅限基类私有实现，不滥用 | `__state` |
| 缩写 | 禁止（`ctx/msg/id` 等通用词除外） | 用 `context` 而非 `ctx` |

> 「成员函数大驼峰/小驼峰」的澄清：**方法/函数一律 snake_case，只有类名用 PascalCase**，二者不可混用。

**门禁**：ruff `N`（pep8-naming）+ 架构测试 `test_public_function_names_snake_case`（dunder 豁免）。

---

## 3. 多线程安全

- 共享状态经 **锁 / 队列 / `asyncio` 单线程事件循环** 隔离，三种机制择一，禁止裸变量共享。
- 明确「**线程归属**」：谁创建谁访问；跨线程访问必须经过归属线程的同步原语。
- **禁止裸锁横跨 async 边界**：持有 `threading.Lock` 期间不得 `await`；异步上下文用 `asyncio.Lock`。
- **不把 GIL 当并发保障**：GIL 只保证字节码原子性，不保证复合操作 / 数据结构的线程安全。

**门禁**：暂无静态门禁，靠 Code Review（主题列为必须审查项）。

---

## 4. if/else 最大嵌套

- 最大嵌套 **≤ 3 层**；超限即重构：抽函数 / 卫语句早返回 / 字典（映射表）分发。
- 禁止深层 try 嵌套（同样计入 3 层上限）。
- 复杂条件先给「具名布尔变量」再判断，避免一行写多个 `and/or` 嵌套。

**门禁**：架构测试 `test_control_flow_nesting_max_three` + ruff `C90`（McCabe ≤10）、`PLR0912`（分支数）、`PLR0915`（语句数）。

---

## 5. 低耦合高内聚

- 模块**单一职责**：一个模块只做一件事，职责可一句话说清。
- **依赖倒置**：依赖 `Protocol`/抽象接口而非具体实现类；实现类经 plugin-registry 注册。
- 循环依赖由架构测试 / import-linter 拦截；**禁止跨层 import 实现类**（上层可依赖下层 Protocol，下层不得反向依赖上层实现）。
- 分层依赖方向（L0→L5 单向，横切 mcp 可被各层消费）：

```
plugin_registry(L0) → tools(L1) → memory(L2) → context(L2.5) → loop(L3) → evolution(L4) → composition(L5)
```

**门禁**：架构测试 `test_protocol_contracts_defined`（依赖倒置契约存在性）；import-linter 待引入。

---

## 6. 串行 / 并行处理规范

- **默认串行**（可读性优先）；仅当任务满足「**独立 I/O 或 CPU 密集** + **无共享状态**」时才引入并行。
- 并行统一走 `ThreadPoolExecutor` / `ProcessPoolExecutor` / `asyncio.gather`；**禁止裸 `os.fork`**。
- 批量任务加 **semaphore 限流** + **超时** + **取消传播**（取消异常沿调用链上抛）。
- 串行转并行必须给出可复现的基准对比，证明收益 > 开销。

**门禁**：Code Review（审查并行边界、资源上限、取消语义）。

---

## 7. 异常处理流程规范

- **异常分层**：业务异常 `DomainError` / 系统异常 `SystemError` 两类基类，禁止混用。
- **禁止裸 `except:`、禁止吞异常**（捕获后必须记录或重抛）。
- 跨边界（模块 / 服务 / 线程）统一包装并记录 **链路 ID**（trace_id）。
- `finally` 只释放资源，**不得在其中抛异常**（会覆盖原始异常）。

**门禁**：架构测试 `test_no_bare_except` + ruff `TRY`（tryceratops）。

---

## 8. 状态机设计

- 状态与迁移**显式建模**：`enum` 定义 state + 迁移表（`dict[(state, event)] → state`）。
- 非法迁移**抛错**（DomainError），不静默忽略。
- 状态**持久化**（配合 durability），恢复后可续跑；orchestration 子任务状态机复用同一模式。

**门禁**：Code Review（审查状态全集、迁移表完备性、持久化恢复路径）。

---

## 9. 模块设计

- 按 **L0-L5 分层**组织包结构，见主题 5 分层图。
- `__init__.py` 只做**白名单导出**（`__all__` 显式声明），禁止在 `__init__.py` 里写业务逻辑。
- **接口（Protocol/ABC）与实现分离**：接口定义在 `protocol.py`，实现类经 plugin-registry 注册。

**门禁**：架构测试 `test_layered_packages_present` / `test_every_package_has_init` / `test_packages_importable`。

---

## 10. 函数复用

- **DRY**：公共逻辑沉淀到 utils / 横切层；**≥3 处重复即抽取**。
- 复用优先于新写：动手前先检索现有 util / 技能 / 插件是否已覆盖。
- 抽取时保持单一职责（主题 5），不抽成「万能工具函数」。

**门禁**：ruff `SIM`（简化重复代码）、`PLC`（pylint 约定）。

---

## 11. 最小化实现

- **KISS + YAGNI**：只实现当前 Phase 需要的；**禁止臆测需求 / 过度设计**。
- 每个类 / 函数必须能回答「**为什么存在**」；删除无法回答的代码。
- **不做未使用的抽象**：没有第二个使用方的泛化，留到出现时再做。

**门禁**：Code Review（审查「为什么存在」可解释性）。

---

## 12. CPU 性能

- **先定位后优化**：用 `cProfile` / `py-spy` 找到热点再动手，禁止无依据预优化。
- 向量 / 批处理走 **numpy**；LLM 调用**合并批次**减少往返。
- 串行转并行须有基准对比证明收益（呼应主题 6）。

**门禁**：ruff `PERF`（性能反模式）+ Code Review。

---

## 附：工具链说明（离线环境）

| 工具 | 版本 | 可执行路径（离线缓存） |
|---|---|---|
| ruff | 0.15.6 | `~/.cache/uv/binaries-v0/ruff/0.15.6/x86_64-unknown-linux-gnu/ruff` |
| pyright | — | `~/.praisonai/venv/bin/pyright` |
| pytest | — | `~/.local/bin/pytest` |

> 注意：pyright 不支持命令行覆盖 `typeCheckingMode`，strict 级别只能在 `pyproject.toml` 里声明后验证；离线环境勿用 `uv run`（会触发环境解析超时），直接调上述缓存二进制。
