# Design 0220 — 提词收紧轮低风险收口

## D1 PA-04：`strip_fence` 取**末**围栏块（而非新增语法判定）

**根因**：`_FENCE = ^```…\n(body)\n?```\s*$` 锚定**整串**，只剥「整体被围栏包裹」。模型若先写一句
说明再给围栏（`这是修补后的文件：\n\n```python\n…\n```），正则不匹配 ⇒ `strip_fence` 原样返回
⇒ 说明文字随代码写进 `.py`。

**取舍**：选项 B（取末块）对齐 `planner._trailing_json_object` 的「只认尾部」纪律 —— 模型最终给出的
内容总在末尾。**不选** C（落盘前 `ast.parse` 自检），那属验证门职责、不在解析侧。**注意**：整串若
**以围栏起首**则由既有 `_FENCE` 接管（锚定匹配会跨到末个围栏）；本兜底 `_FENCE_ANY` 只在串首不是围栏
时生效 —— 测试已显式区分二者。

## D2 PA-05：镜像核对落成**测试**（而非脚本/生成器）

**根因**：镜像（`prompts.md`）无自动校验，靠人肉；`test_prompt_pinning.py` 只钉常量 ↔ 副本。

**取舍**：选项 B（断言常量每一非空行出现在镜像）。**不选** C（由脚本反向生成镜像）—— 镜像里含
**解释性旁注**（现状、安全承重、动态内置内容），生成器须另存旁注、结构重排，改动面与裁决面更大。

**落点**：`tests/test_prompt_mirror.py`（零 `src/`）。⑤⑥ 的常量用 `.format()` 转义（`{{`→`{`），
镜像记录的是**渲染后**形态 ⇒ 仅当常量含 `{{` 时去转义；① 的 `{"args": {...}}` 是**字面**双 `}`，
一律去转义会误伤（已实测）。⑬ 人格面动态拼接、无常量 ⇒ 不逐字核对，另立断言其**在镜像登记**。

## D3 PA-06：⑧ 教训段写成「可复用的判据」

**根因**：⑧ 的「教训」段会被 loop「既往失败教训」块**直接注入规划器**；模型易写成「下次小心」
这类无信息空话 ⇒ 空话灌进推理面。

**取舍**：选项 B（只改 ⑧）。**不选** ⑦（重要度措辞）—— 它牵动 `W_IMPORTANCE` 乘性权重与写入闸门，
改措辞前应先有真实样本分布证据（登记为遗留）。改动 = 模块常量 ＋ pin 副本 ＋ 镜像**三处同改**。

- **规格（规格中性）**：无 spec delta；`skip_specs: true`。`openspec validate --all` 32 passed
  （31 canonical ＋ 1 change）→ 归档后 31 passed。
- **反证（三组，实测）**：① 摘掉 `strip_fence` 兜底分支（`if blocks:`→`if False:`）⇒
  `tests/test_evolution_author.py` **3 failed, 20 passed**；② 还原 ⑧ 教训措辞 ⇒ `test_prompt_pinning`
  ＋ `test_prompt_mirror` **2 failed, 29 passed**；③ 只改 ④ 常量（不动镜像）⇒ `test_prompt_mirror`
  **1 failed, 13 passed**。三次复原 ⇒ 三文件 `md5sum` **逐个相同**。
- **局限**：① PA-04 若模型输出**多个**围栏块，取末块理论上可能取错（倾向 false-positive 风险低，
  已由 `test_strip_fence_takes_last_block_among_several` 显式记录该语义）；② 镜像门禁只查「常量的行
  出现在镜像」，**不查镜像有无多余行**（镜像是超集即可）；③ ⑦ 未动。
- 来源另见 `doc/openspec/changes/archive/…-0219-prompt-catalog/design.md`、`coding-plan/Pending-Arbitration.md`。
