# TASK-PVAM-07B 事件路由、正式 Handler 与 Stream 保留护栏

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-07B` |
| 来源检查项 | `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003` |
| 来源问题 | `R-012B`（parent=`R-012`，最终路由/handler）、`R-013` |
| 处置项 | `REM-012B、REM-013` |
| 施工项 | `W-012B、W-013` |
| 验证项 | `V-012B、V-013` |
| 关联决策 | `DEC-007、DEC-010` |
| 严重级别 | `P0` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | `TASK-PVAM-06、TASK-PVAM-07A` |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。

### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

- 当前事件没有版本化 envelope/schema/handler registry；同名 `SETTLEMENT_PERIOD_DONE` 由 Global 与 Elite 产生不同 payload 和后置动作。
- 当前 pass/unknown 路由不能证明业务处理完成；T07A 只先使其 fail-closed，尚未完成最终 handler。
- Global、Elite、Placement producer 对同一 Stream 使用固定 `MAXLEN ~ 100000`，没有多 group ACK 水位、容量证明或 durable replay。
- ghost PEL 是 ACK 前裁剪/外部删除后的不可恢复信号，必须与 settlement manifest/event registry 联动。

## 3. 本任务修改目标

1. 建立版本化 envelope、schema registry、handler registry 与正式 disposition。
2. 为所有生产可达事件定义唯一 schema、幂等 handler、后置条件和 ACK 条件。
3. 迁移 producer，解决同名异构事件。
4. 取消固定 MAXLEN，实施 ACK-aware retention、容量/延迟告警和 durable replay/ghost recovery。
5. 保持 T07A 的 fail-closed 语义，最终关闭 R-012/R-013 需 DEV+UAT 双证据。

## 4. 处置决定与方案选择

### 4.1 Envelope

```text
schema_version
producer_service / producer_domain
event_type / event_subtype
period_num / run_id / epoch / generation
event_id / idempotency_key
payload_hash / created_at
payload
```

路由键必须唯一确定 schema 和 handler。新事件优先使用清晰专名；旧事件由 compatibility decoder 读取，无法消歧则 DLQ/重试。

### 4.2 Disposition

- `HANDLER_REQUIRED`
- `LEGAL_NOOP_AUDITED`（必须带批准编号）
- `RETRYABLE_FAILURE`
- `REJECT_TO_DLQ`

### 4.3 Retention

producer 不再指定固定 MAXLEN。独立 retention job 仅在以下全部满足时 `XTRIM MINID`：

- 所有注册 group 的 ACK 安全水位超过目标 ID；
- 无 unresolved PEL/claim/DLQ 事务；
- retention window、容量和延迟阈值满足；
- event registry/outbox/manifest 可重放；
- trim manifest 和 checksum 已写入审计存储。

### 4.4 被否决方案

- 只增加 consumer group；不能消除同名 schema 冲突。
- 把 MAXLEN 换成更大常数；仍会 ACK 前裁剪。
- 依赖 T07A 长期保留 unknown PEL 而不建设 handler；只解决不丢，不解决可完成性。
- deleted-ID 直接 ACK；掩盖不可恢复状态。

## 5. 修改范围与受影响模块

- `MessageConsumer/RecalcStreamConsumer.py`：接入 v2 registry/handlers，保留 T07A disposition。
- 新增 `RecalcEventSchema.py`、`RecalcHandlerRegistry.py`、`RecalcDisposition.py`。
- 新增/完善 handlers：Global done、Elite batch ready/published、Placement drift/materialized、highest rank、state drift。
- 修改 Global/Elite/Placement producers 使用统一 publisher。
- 新增 `Settlement/RecalcEventPublisher.py`、event registry/outbox 关联。
- 新增 `Ops/RecalcStreamRetention.py`、lag/PEL/DLQ metrics 和 ghost recovery runbook。

## 6. 明确排除项（防越界红线）

- 不把所有事件强制有副作用；audited no-op 必须有正式批准。
- 不以 DEC-010 测试 checkpoint 豁免豁免 ACK、trim、ghost recovery。
- 不修改奖金公式；handler 后置条件来自 T06 状态机和各业务 TASK。
- 不在有 unresolved ghost/IN_DOUBT 时执行 trim。

## 7. 前置条件与依赖关系

- T07A 已部署或其全部 DEV AC 已通过。
- T06 冻结状态事件、batch/receipt 和 ACK 后置条件。
- 使用 T01 的 strict type/hash 辅助。
- UAT 依赖 T08 的多 group Redis、故障注入和长积压能力。

## 8. 修改后行为与技术设计

### 8.1 最终事件名建议

- `GLOBAL_USERSTATS_RECALC_DONE`
- `PLACEMENT_RECALC_DONE`
- `ELITE_BONUS_BATCH_READY`
- `ELITE_BONUS_PUBLISHED`

### 8.2 处理顺序

继承 T07A 的统一 parse/disposition，再执行 v2 schema、registry、幂等 handler 和后置条件；只有 `HANDLER_REQUIRED` 成功或经批准的 `LEGAL_NOOP_AUDITED` 完成后 ACK。

### 8.3 Ghost 恢复

查询 durable event registry/settlement manifest；可恢复则重建关联事件，不可恢复则将 period/run 标为 IN_DOUBT 并阻断 trim/发布。只有恢复完成或正式人工裁决后清理 PEL。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | 所有生产事件变体在 registry 中唯一映射 schema、handler、disposition | DEV+UAT | TC-027 |
| AC-02 | Global/Elite/Placement 完成事件可无歧义区分并执行不同 handler | DEV+UAT | TC-027、TC-029 |
| AC-03 | handler 后置条件不满足时不 ACK；audited no-op 必须有批准编号与审计记录 | DEV+UAT | TC-027 |
| AC-04 | 所有 producer 不再使用固定 `maxlen=100000` | DEV+UAT | TC-028、TC-031 |
| AC-05 | 多 group 慢消费者场景，未 ACK 消息不被 trim | UAT | TC-028 |
| AC-06 | 超过100000消息、长 PEL、DLQ失败、consumer重启均不丢 payload | UAT | TC-027、TC-028 |
| AC-07 | ghost entry 通过 registry/manifest 恢复或进入 IN_DOUBT，不直接 ACK | UAT | TC-028 |
| AC-08 | trim job 生成 group 水位、PEL、范围、checksum 和恢复可用性证明 | UAT | TC-028、TC-032 |
| AC-09 | 旧 `SETTLEMENT_PERIOD_DONE` 兼容 decoder 无法消歧时进入 DLQ/重试，不猜测路由 | DEV+UAT | TC-027 |
| AC-10 | v2 producer/consumer 切换、dual-read/短期 dual-publish 和回滚保持 event_id 幂等 | DEV+UAT | TC-023、TC-025、TC-026、TC-032 |

## 10. 环境验证与回传证据

### DEV

- schema/registry/router/handler contract tests；
- producer scan 禁止固定 MAXLEN；
- compatibility decoder 和 event_id 幂等；
- retention dry-run 的 group/PEL/watermark 计算。

### UAT

关联 `UAT-009、UAT-010、TC-027、TC-028`：

- 至少两个 consumer group，其中一个故意慢/停；
- 发送超过100000条事件；
- handler/Redis/DLQ/consumer 故障；
- ghost PEL 恢复；
- 回传 XINFO/XPENDING、stream范围、ACK/DLQ、retention manifest、replay checksum。

## 11. 独立回滚与风险控制

1. envelope v2 与独立 group shadow consume；shadow 不 ACK v1 group。
2. dual-publish 只用于短期验证，按 event_id 去重；切换完成立即停止旧格式。
3. 回滚 v2 consumer 时同步停止 v2 producer或维持兼容 group，禁止旧 consumer 误读。
4. retention 默认 dry-run；全 group 水位验证后才启用实际 trim。
5. 任何 IN_DOUBT/ghost 未关闭时禁止回滚到固定 MAXLEN。


### 第四轮补充：Stream 回滚边界

默认回滚不得恢复固定 `maxlen=100000`；兼容回退必须保持 producer 无固定 MAXLEN。临时恢复固定上限仅允许在签署的紧急例外中执行，且必须限定窗口、写入速率、容量、告警、停止阈值、未 ACK 保护与再升级路径。
