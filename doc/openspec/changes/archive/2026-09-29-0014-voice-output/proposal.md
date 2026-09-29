# Change: 实时语音输出（语音播报与打断）

## Why

Core-Agent 已支持多模态输入（语音输入转写），但缺少文本回复的语音输出闭环。用户在不便看屏幕的场景（驾车、移动、听障辅助、全双工对话）需要系统将回复以流式 TTS 合成语音实时播报，并能在播报过程中打断（barge-in）直接以语音继续对话。全双工（边听边播）与打断是语音交互的自然范式，缺失会导致多模态能力只进不出。

## What Changes

- 新增 `ui` capability 下的「实时语音输出」Requirement：流式 TTS 播报（分片增量合成，不等待整段回复）
- 用户打断（barge-in）：播报中开口或按键立即停止，转入语音输入，被打断文本不丢失并保留在会话记录
- 会话语音上下文引用：语音与文本共享同一会话记录，可相互引用，必要时保留原始音频引用
- 三模一致：CLI / Web / Desktop 均支持语音输出与打断交互

## Impact

- **Affected specs**：`ui`（新增 Requirement：实时语音输出）
- **Affected docs**：`06-ui-frontend/ui-architecture.md`（语音输出交互设计：全双工/打断/三模）
- **Affected code**：无（本 change 声明语音输出行为，具体实现由后续步骤确定）
- **Dependencies**：复用 `ui` 多模态输入管道（音频采集/转写）、`llm-provider`（流式文本分片）；TTS 引擎选型留待实现阶段
