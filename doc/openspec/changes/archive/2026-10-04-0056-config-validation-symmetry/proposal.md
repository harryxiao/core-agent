# Proposal — config-validation-symmetry（账本 E7 + E8）

## Why

账本 `phase-19.md` §2 的 E7/E8 是「契约层与实现对不上账」的两条。走查（2026-10-04）一手核对后，
两者的性质完全不同：

- **E7 是文档漂移，不是承诺缺失**。`coding-plan/cli-contract-baseline.md:260` 把内置工具列为
  「file_read/file_write/file_patch 已实现；code_run/web_scan/web_execute_js/ask_user/process/memory 未实现」。
  实测：`code_run` **已实现**（`tools/builtin.py:187`）；`web_scan`/`web_execute_js`/`ask_user`/`process`/`memory`
  在 `src/` 与 `doc/openspec/specs/` **零出现**（从未存在）；真实集合另有 `web_fetch` + `install`/`uninstall`/`list`。
  裁决依据：**规格是事实来源**——`tool-use/spec.md:109`「内置原子工具」只要求 `code_run` + `web_fetch`，
  与实测的 8 个工具 ID 逐一对得上。基线文件溯源到 `temp/plan_cli_ops/*` 的**设计态推演稿**（非规范文件）。
  → 无需改规格、无需补实现，**订正文档**即可。
- **E8 有三处「规格有、实现无」的校验缺口**（另 4 条只需订正，2 条已闭合）：

  | # | 条目 | 实测 |
  |---|---|---|
  | 3 | `secret_ref` 校验不对称 | `llm.api_key` 有「非空 + 可解析」双校验（`manager.py:238-246`），`im.secret` / `judgment.api_key` **只查明文**→ 空值 / 不可解析引用静默过校验 |
  | 7 | `permission-mode` 枚举 | permission 规格明列四档并写明「映射 `config.permission.mode`」，但 `permission_mode()`（`manager.py:269`）从 `extra` 取任意字符串、**不校验成员** |
  | 1/4/6 | flag 接线 / features 清单 / streamable-http | 1 已接线（`_CONFIG_SPECS` 声明全部 `--llm.*`/`--im.*`）；4 为设计如此；6 = 账本 B2，已跟踪 |
  | 2/5 | config set 写回；`extra` 无校验 | 2 基线自标已闭合；5 见 Non-Goals |

## What Changes

1. **规格（configuration delta，MODIFIED ×2）**
   - 「密钥分级与安全」：三个密钥引用**同口径**校验（非空 + 可解析），并写明可选段的参与条件。
   - 「配置校验与生效」：取值受所属能力规格约束的配置项（`permission.mode`）须校验枚举合法性。
2. **实现（`src/core/configuration/manager.py`，`validate_schema`）**
   - `im.secret` 非空 + 可解析（仅当 IM 段存在）；`judgment.api_key` 同（仅当 `provider` 非空）。
   - `permission.mode` ∈ 权限规格四档，否则报错并列出可选值。
3. **文档订正（E7）**：`coding-plan/cli-contract-baseline.md` §10 工具清单改为实测集合、§11 逐条标注结论，
   并在文件头标注其为**设计态快照、非规范文件**（事实来源是 `openspec/specs`）。
4. **账本**：E7 全闭（纯文档）；E8 关闭并转出 1 条后续行（`extra` 未知配置键校验）。

## Non-Goals

- **不动 `extra` 的宽松性**（E8 第 5 条）：`extra` 是既有兜底通道，收紧为白名单会**拒绝用户已有的自定义段**
  （改变既有接受行为、可能破坏既有部署）。按用户裁决选择「B 对称化」，该项**转出为独立后续账本行**。
- **不新增工具**：`web_scan` / `ask_user` 等 5 个名字**不是**承诺项，不补规格、不补实现。
- **不改 `permission.mode` 的语义与默认值**（仍缺省 `interactive`），只加取值校验。
- **不动 B2（streamable-http）**：仅交叉引用。

## Impact

- 能力：`configuration`（spec delta + 实现 + 接口文档）；`permission` / `tool-use` 规格**不变**（仅交叉引用）。
- 兼容性：**校验变严**——配置了 IM 段但 secret 为空 / 引用不可解析、或 `permission.mode` 取值非四档的配置，
  将从「静默接受」变为「启动报错」。这是刻意的：前者是安全缺口，后者是规格已承诺而未强制的契约。
- 测试：`tests/test_configuration.py` 新增 6 项；既有 750 项须全绿（已核对：无既有用例依赖宽松行为）。
- 文档：`cli-contract-baseline.md`、`configuration-interface.md`、ADR-0059。
