# TASK-PVAM-07A Recalc Consumer ACK 紧急修复

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-07A` |
| 来源检查项 | `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003` |
| 来源问题 | `R-012A`（parent=`R-012`，紧急 fail-closed 子集） |
| 处置项 | `REM-012A`（由 REM-012 拆分） |
| 施工项 | `W-012A`（由 W-012 拆分） |
| 验证项 | `V-012A`（由 V-012 拆分） |
| 关联决策 | `DEC-010` |
| 严重级别 | `P0` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | 无；可与 TASK-01、TASK-08A 并行 |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。

### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

- `RecalcStreamConsumer.process_event` 对空 payload 直接返回 True，主循环随后 ACK。
- JSON 解析成功后在保护区外执行 `e.get`，合法 JSON 非 object 会抛出未归类异常并持续卡 PEL/reclaim。
- `RECALC_STATE_DRIFT`、`RECALC_NODE_MATERIALIZED`、`HIGHEST_RANK_UPDATED`、`SETTLEMENT_PERIOD_DONE` 仅 print/pass，却被当作成功。
- 未知事件分支落空，`_dispatch_business` 正常返回，消息被 ACK。
- reclaim 对 deleted-ID/空 fields 直接加入 ACK。
- DLQ 写入若失败，当前异常路径没有统一证明“原消息未 ACK”。

## 3. 本任务修改目标

1. 在不改变 producer payload 的前提下立即消除“未处理即 ACK”。
2. 将空、非法 JSON、非 object、unknown、unhandled、handler failure、DLQ failure 和 ghost PEL 纳入统一 fail-closed 纪律。
3. 正常消费与 PEL reclaim 共用同一处理函数和 disposition 结果。
4. 形成可独立部署、独立回滚的 hotfix，为 TASK-07B 最终 schema/retention 改造建立安全底座。

## 4. 处置决定与方案选择

### 4.1 当前契约内的最小安全结果

处理函数不得仅返回布尔值，至少返回：

```text
HANDLED_ACK
DLQ_WRITTEN_ACK
RETRY_KEEP_PEL
UNHANDLED_KEEP_PEL
GHOST_IN_DOUBT
```

只有前两种允许 ACK；`DLQ_WRITTEN_ACK` 必须先证明 DLQ XADD 成功。

### 4.2 现有事件的临时处置

- 已有真实 handler：执行成功后 ACK；失败留 PEL。
- print/pass 或无 handler 事件：`UNHANDLED_KEEP_PEL`，同时告警和指标；不得编造业务副作用。
- 永久 schema 错误：尝试 DLQ，成功后 ACK，失败留 PEL。
- ghost/deleted-ID：记录 stream/group/message id，进入 `GHOST_IN_DOUBT`；不直接 ACK。

### 4.3 被否决方案

- 等待 TASK-06/07B 后一次性修改；会延长 P0 丢事件窗口。
- 把 unknown 全部当合法 no-op；无批准依据。
- DLQ 失败后仍 ACK；永久丢失原消息。
- 只改主消费循环，不改 xautoclaim；两条路径继续漂移。

## 5. 修改范围与受影响模块

- `MessageConsumer/RecalcStreamConsumer.py`：统一 parse/validate/dispatch/disposition/ack。
- 新增轻量 `MessageConsumer/RecalcProcessResult.py`（或等价 enum）。
- 新增当前 v1 事件允许表；没有 handler 的事件明确 fail-closed。
- 单元测试、隔离 Redis PEL/reclaim/DLQ 测试、mutation 测试。
- 不修改 producer、不引入 v2 envelope、不实施 trim job；这些归 TASK-07B。

## 6. 明确排除项（防越界红线）

- 不臆造 `SETTLEMENT_PERIOD_DONE`、drift、highest-rank 的业务 handler。
- 不把无 handler 事件改为 audited no-op；no-op 需要正式合同和批准编号。
- 不提高或删除 MAXLEN 来冒充 R-013 修复。
- 不修改奖金、状态机和发布规则。
- 不直接 ACK ghost PEL。

## 7. 前置条件与依赖关系

- 无代码前置，可立即开发。
- TASK-07B 必须继承本任务 disposition/ACK 测试，不得回退为布尔成功语义。
- UAT 依赖 TASK-08 的隔离 Redis、consumer group、DLQ 和故障注入权限。

## 8. 修改后行为与技术设计

```text
read entry
-> fields/payload presence validation
-> JSON parse inside common try boundary
-> top-level object validation
-> current-v1 event allowlist lookup
-> handler or UNHANDLED_KEEP_PEL
-> verify handler/DLQ postcondition
-> explicit process result
-> ACK only for HANDLED_ACK / DLQ_WRITTEN_ACK
```

normal read 与 xautoclaim 只调用一个 `process_entry()`；单条异常不得中断整个 reclaim 批次。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | 空 payload 不返回成功，不在无处置证据时 ACK | DEV+UAT | TC-027 |
| AC-02 | 非法 JSON 与合法非 object JSON 均进入统一异常边界，不中断 reclaim 批次 | DEV+UAT | TC-027 |
| AC-03 | 未知事件、缺 handler、现有 print/pass 分支不得落空成功 | DEV+UAT | TC-027 |
| AC-04 | handler 失败或后置条件未知时不 ACK，保留 PEL 等待重试/后续合同 | DEV+UAT | TC-027 |
| AC-05 | 永久非法消息只有在 DLQ 写成功后 ACK；DLQ 失败保留 PEL | DEV+UAT | TC-027、TC-028 |
| AC-06 | normal read 与 xautoclaim 使用同一处理函数，对同一 entry 行为一致 | DEV+UAT | TC-027、TC-028 |
| AC-07 | deleted-ID/empty fields 不直接 ACK；至少告警并阻断该批恢复链 | DEV+UAT | TC-028 |
| AC-08 | 本 hotfix 不要求 producer/envelope 变更，能够独立启停和回滚 | DEV | TC-031 |
| AC-09 | mutation 将 unknown 重新设为成功、ghost 直接 ACK、DLQ 失败仍 ACK 时，测试必失败 | DEV | TC-031 |

## 10. 环境验证与回传证据

### DEV

- 空/非法/非 object/unknown/pass/handler failure/DLQ failure 全矩阵；
- normal/reclaim 等价；
- fakeredis 或隔离 Redis 的 PEL、XPENDING、XACK 断言；
- mutation：恢复 unknown=True、ghost ACK、DLQ失败 ACK，测试必须失败。

### UAT

关联 `UAT-010、TC-027、TC-028`：

- 真实 Redis consumer group、PEL reclaim、DLQ 暂停；
- 现有 v1 producer 发送所有可达事件；
- 回传 XINFO/XPENDING、ACK ID、DLQ ID、日志与指标。

## 11. 独立回滚与风险控制

1. 使用 `RECALC_ACK_FAIL_CLOSED_V1` 开关；默认先 shadow 记录 disposition，再切 ACK 权威。
2. 回滚只能在停止消费且保存 PEL 快照后执行；不得回滚到 unknown/ghost 自动 ACK。
3. 新增 enum/指标为 additive；TASK-07B 复用。
4. hotfix 失败时停止 consumer，保留 PEL，由 runbook 人工恢复，不允许“为了清积压”批量 ACK。
