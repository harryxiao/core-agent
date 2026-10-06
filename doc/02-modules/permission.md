# 模块设计：权限与审批管控（Permission & Approval Gate）

> 对应规格：`doc/openspec/specs/permission/spec.md` ｜ 接口：`doc/03-interfaces/permission-interface.md`
> 定位：**横切边界层**，是智能体安全落地的核心，解决裸模型无约束执行的失控风险。

---

## 1. 模块定位

权限与审批管控是 L0 确认门（Confirmation Gate）之上的**策略层**：它不决定"怎么做"，而决定"**能不能做、需不需要人点头**"。

它把上一层的可逆效应追踪（EffectTracker）与 coeffect 注入（CoeffectResolver）**升级为三级权限体系 + 人工审批流 + 沙箱隔离**，是所有写操作的强制前置检查点。

**设计原则**：默认拒绝（deny-by-default）。凡未显式授权的操作一律拦截，高危操作必须有人工审批。

---

## 2. 内部组成

```
PermissionGate（横切）
├── PolicyEngine       分级权限判定：read / data-edit / high-risk
├── ApprovalWorkflow   人工审批流：发起 → 待审 → 批准/拒绝 → 归档
├── SandboxManager     沙箱隔离：独立环境执行，执行完自动销毁
├── RiskClassifier     风险分级：操作属性 → 风险等级（默认 high-risk）
└── AuditTrail         审批与权限决策的审计日志
```

---

## 3. 关键设计

### 3.1 分级权限体系（三级）

| 等级 | 说明 | 默认行为 |
|---|---|---|
| `read` | 只读查询：读文件/查状态/只读 API | 放行（受 coeffect 约束） |
| `data-edit` | 数据编辑：写文件/改配置/DB 写 | 放行 + 可逆效应记录 |
| `high-risk` | 高危操作：删文件/杀进程/大额交易/系统级写入 | **默认拦截**，强制人工审批 |

- 分类依据：操作类型 × 作用对象 × 影响面（爆炸半径）。
- 分级结果进入每个 effect 的 `risk_level` 字段，供 EffectTracker 与审计复用。
- **判定按语义词元，非任意子串**（change `0095` 立规；change `0135` 补齐实现）：操作与目标先按
  `._:-/` 切成**词元集合**再命中，命名空间前缀偶然含只读词子串（`tools.` 含 `"ls"`）SHALL NOT 判为 `read`
  —— 同理 `tools.target`（含 `get`）、`tools.category_sync`（含 `cat`）亦 SHALL NOT 判只读（否则所有
  `tools.*` 误判只读、deny-by-default 失效）；显式声明的字面量 coeffect `agent:delegate` 判 `read`，
  且**不放宽为 `agent:` 前缀**。

**模式覆盖（`PermissionModeGate`）**：四档启动开关覆盖上述默认判定（映射 `config.permission.mode`
+ CLI `--permission-mode`）：

| 档 | 覆盖效果 |
|---|---|
| `read-only` | 拒 DATA_EDIT / HIGH_RISK（`PERMISSION_DENIED`） |
| `interactive` | 默认行为：高危走人工审批 |
| `auto-approve` | **无人值守全放行**：高危 / 不可逆写 / 出站网络 / 不可归类一律放行，不询问不阻断 |
| `high-risk-block` | 高危无条件阻断，不进入审批流 |

`auto-approve` 的两处落点**缺一不可**（confirm 门有两条独立来源）：`PermissionModeGate.authorize`
顶部短路（覆盖 HIGH_RISK 的 `approval_required`）+ `PermissionGuard.confirm` 的不可逆写分支感知模式
（该分支原本与权限档无关）。全放行**仅限权限层**，不越过正交的 guardrail 红线。

### 3.2 人工审批流

```
[拦截] high-risk 操作
   └─► ApprovalWorkflow.create(request)   # 生成审批单（含操作摘要、影响面、回滚预案）
         └─► ask_user（等待人工批准/拒绝）
               ├─ 批准 ─► 放行执行（仍记录可逆效应）
               └─ 拒绝/超时 ─► 阻断执行 + 写审计
```

- 审批单带 TTL，超时默认拒绝（fail-closed）。
- 审批结果与请求一起归档，可回溯"谁在何时批准了什么"。

### 3.3 沙箱隔离机制

- 所有代码执行、Shell 执行默认在**独立沙箱环境**运行（子进程 + 受限文件系统/网络 + 资源配额）。
- 执行完成后**自动销毁**沙箱，不留残留，避免污染宿主系统。
- 沙箱类型可插拔：`local-subprocess` / `container`（v0.5+），统一由 SandboxManager 调度。
- **出站网络白名单**（change `0071`，账本 B5）：`SandboxPolicy.check_outbound` 是唯一的网络守卫，
  生产调用点在 `core/mcp/transport.py` 的 http / streamable-http 传输（host 取自 `urlparse().hostname`）。
  白名单经 `permission.sandbox.host_allowlist` 声明（逗号分隔的裸主机名标量，`ConfigSpec` 单一真源
  三面齐备），组合根取值注入，与 `SandboxManager` **共用同一策略实例**；**缺省空 = fail-closed 全拒**，
  非法条目（带 scheme / 端口 / 路径）在校验期阻断启动（静默忽略的后果是「配了却连不上」）。

---

## 4. 与既有机制的衔接

| 既有机制 | 本模块的增强 |
|---|---|
| CoeffectResolver（L0） | 权限等级作为必需 coeffect 注入，缺失即拒绝 |
| EffectTracker（L0） | 不可逆/高危效应进入特殊审计区，审批单关联 trace_id |
| 确认门（loop） | loop 的 ask_user 门由本模块的 ApprovalWorkflow 接管 |

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 未授权操作 | 拦截，返回 `PERMISSION_DENIED`（含所需等级） |
| 高危操作未经审批 | 拦截，返回 `APPROVAL_REQUIRED`，创建审批单 |
| 审批超时 | fail-closed 拒绝，写审计 |
| 沙箱启动失败 | 阻断执行，返回 `SANDBOX_UNAVAILABLE`，不降级到宿主直跑 |

`APPROVAL_REQUIRED` 的**生产 raise 落点**（change `0135`）：高危 git 操作的审批门
（`GitClient._require_approval`，force-push / 删远程分支 / 历史改写）—— 「缺审批」与「无权限」
是两回事，此前误用 `PERMISSION_DENIED`（错误码表早有 `APPROVAL_REQUIRED` ⇒ 定义处零 raise 的死码）。
`PolicyEngine.authorize` 一侧仍以 `Decision(approval_required=True)` 表达「需审批」：它是 loop
confirm 门的契约（`guard._to_gate` 据此翻成 `confirm` 走审批通道），改成抛异常会打断审批流。

---

## 6. 关联

- 接口契约：`doc/03-interfaces/permission-interface.md`
- 规格：`doc/openspec/specs/permission/spec.md`
- 测试：`doc/04-testing/test-cases.md`（PERM 系列）
