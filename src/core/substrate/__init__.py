"""substrate = context 前身命名（命名对齐说明）。

本包是「上下文工程（Context Engineering）」模块（L2 记忆之上 / L3 输入侧）
在 src/core/ 下的前身命名，语义等同 doc/02-modules/context.md 所描述的
context 模块：按需加载、信息地图、自动压实，保证「每次只把当前任务最需要
的上下文装进窗口」。

命名对齐约定：对外文档 / 规格统一使用「context」；src/core/ 下本包沿用
历史命名「substrate」，二者指向同一模块。后续如需统一，可将本包重命名为
src/core/context/ 并同步更新引用，行为不变。

对应规格：doc/openspec/specs/context/spec.md
接口契约：doc/03-interfaces/context-interface.md
模块设计：doc/02-modules/context.md
"""
