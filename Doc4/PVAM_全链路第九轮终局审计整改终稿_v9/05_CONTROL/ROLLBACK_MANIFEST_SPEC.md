# ROLLBACK MANIFEST SPEC v2

每个准备部署的 WORK 必须提交真实、签名并在隔离环境演练通过的 rollback manifest。缺失时为 `BLOCKED_EXTERNAL_EVIDENCE`。

必填字段：deployment_system、environment、workload/release/config、image_before/after、精确 argv、健康检查、状态快照 URI/SHA、数据恢复/重放步骤、执行人/复核人/批准人/时间、演练日志与退出码。

## 数据面最小要求

- WORK-01～04：编码/version/config/Active 的双读边界、停止新写、旧/新数据隔离和受控重跑；
- WORK-05～06：run/epoch/coverage、SOURCE/outbox/receipt、候选批次与 PUBLISHED 状态恢复；
- WORK-07A：PEL/DLQ/XPENDING 快照、未处理消息不得 ACK、重放幂等；
- WORK-07B：XLEN/group/PEL/ghost/IN_DOUBT/replay proof 与 retention 状态；
- WORK-08：只回滚治理/测试资产，不得修改生产目录。

## WORK-07B 特别红线

默认回滚路径**不得恢复已知不安全的固定 `maxlen=100000`**。应回退到“兼容 reader/handler 关闭、producer 仍无固定 MAXLEN、retention job 停用”的安全版本。

只有紧急例外获得运维/架构签署时，才允许临时恢复固定 MAXLEN；manifest 必须同时规定：最长回滚窗口、最大写入速率、容量上界、实时 XLEN/PEL/lag 告警、停止阈值、未 ACK 消息保护、再升级时间和责任人。缺任一项即禁止执行。
