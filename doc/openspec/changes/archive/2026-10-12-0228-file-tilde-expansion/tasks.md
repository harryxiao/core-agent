## 1. Specification
- [ ] 1.1 **规格中性**（`skip_specs: true`）：`tool-use` spec 不约束文件工具路径语义 ⇒ 零 spec delta、
  canonical 计数不变。
- [ ] 1.2 `openspec validate --all` 全绿。

## 2. Tests（先红）
- [ ] 2.1 新 `tests/test_tilde_expansion.py`：`file_read` 读 `~/…` ⇒ 命中家目录文件；`file_write`
  写 `~/…` ⇒ 落到家目录、返回体仍回原文路径；`file_patch` 改 `~/…` ⇒ 命中家目录；撤销
  `file_write`/`file_patch` 的 `~/…` ⇒ 恢复家目录文件（**非**字面 `~`）；相对/绝对路径逐字不变；
  三个工具均不含 `~` 时 `expanduser` 恒等。

## 3. Implementation
- [ ] 3.1 `src/core/tools/builtin.py` 新增 `_expand(path)`；`file_read`/`file_write`/`file_patch`
  入口改用之；后两者把展开路径存入快照。

## 4. Interface Doc
- [ ] 4.1 `doc/03-interfaces/tool-use-interface.md` §3 落注 `~` 展开语义。

## 5. Gates & Archive
- [ ] 5.1 四门禁：`ruff check`／`ruff format --check`／`pyright`（**无参**）／`pytest`。
- [ ] 5.2 `openspec validate --all`；手工归档；台账回填（E165 / ADR-0218 / §141）；**单次提交**。
