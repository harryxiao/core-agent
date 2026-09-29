# Tasks

## 1. ui SSE 断线重连（P1）

- [x] 1.1 在 ui spec「Web 界面访问」追加「SSE 断线重连」Scenario

## 2. deployment 客户端断线与会话清理（P0）

- [x] 2.1 在 deployment spec 追加「客户端断线与会话清理」Requirement
- [x] 2.2 在 requirements.md 1.20 节追加 CORE-DEP-R6 行

## 3. observability 遥测缓冲与导出重试（P1）

- [x] 3.1 在 observability spec 追加「遥测缓冲与导出重试」Requirement
- [x] 3.2 在 requirements.md 1.9 节追加 CORE-OBS-R5 行

## 4. rag 摄取/重建失败降级（P1）

- [x] 4.1 在 rag spec「文档摄取与分块」追加「摄取/重建失败降级」Scenario

## 5. memory 检索降级与并发一致性（P1）

- [x] 5.1 在 memory spec「温度分层检索」追加「检索失败降级」Scenario
- [x] 5.2 在 memory spec「记忆压实」追加「并发压实一致性」Scenario

## 6. orchestration 断点续跑与 fan-out 幂等（P0）

- [x] 6.1 在 orchestration spec 追加「断点续跑」Requirement
- [x] 6.2 在 orchestration spec「并行扇出」追加「fan-out 幂等派发」Scenario

## 7. im 消息幂等与重连退避（P0）

- [x] 7.1 在 im spec「消息驱动会话」追加「重复消息幂等」Scenario
- [x] 7.2 在 im spec「会话隔离与容错」追加「重连退避」Scenario

## 8. skills 超时与资源上限（P0）—— superseded by 0031，不落地

- [ ] 8.1 ~~在 skills spec 追加「超时与资源上限」Requirement~~　【superseded by 0031：skills 超时已摘除，由 tool-use 承载】
- [ ] 8.2 ~~在 requirements.md 1.11 节追加 CORE-SKILL-R5 行~~　【superseded by 0031】
