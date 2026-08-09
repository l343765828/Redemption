# TASK-PVAM-05 Elite SOURCE 写入原子性与正式 Writer Proof

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-05` |
| 来源检查项 | `CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001` |
| 来源问题 | `R-008、R-011` |
| 处置项 | `REM-008、REM-011` |
| 施工项 | `W-008、W-011` |
| 验证项 | `V-008、V-011` |
| 关联决策 | `DEC-007、DEC-008、DEC-011、DEC-017` |
| 严重级别 | `P0` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | `TASK-PVAM-01、TASK-PVAM-02、TASK-PVAM-03` |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。


### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

- `EliteBonusService._track_bonus_source` 直接 `HSET/EXPIRE` SOURCE；随后 `_batch_save` 再保存 stats，二者不是同一 Redis 事务。
- 异常发生在两次写之间时，SOURCE 与 EliteBonusStats、revision、dirty 状态可分裂。
- Elite candidate/writer 缺少完整 `PV_PSS` gate、amount version、run/revision/coverage 和正式提交证明。
- 当前服务包含 `snapshot_period_to_db/db_executor` 思路，但 DEC-008 已把关系库正式写职责移交业务系统；Python 只能提供完整、可校验的发布批次。

## 3. 本任务修改目标

1. 将 Elite stats、SOURCE assignment、revision/dirty、幂等标记和 outbox 纳入单一 Redis 权威原子提交。
2. 将 Elite 七条 gate 编译成可审计 candidate builder，缺任一 proof 时不产生正式批次。
3. 输出业务系统可消费的完整 batch + manifest + checksums + empty snapshot 语义，形成 Writer Proof。
4. 保持 DEC-011 的传播语义，不因为本任务重新修改已修订文档或扩散算法。

## 4. 处置决定与方案选择

### 4.1 原子边界

采用 Redis Function/Lua 或经证明的 `WATCH/MULTI/EXEC`，一次提交：

```text
EliteBonusStats mutations
SOURCE assignment ledger
source-to-bonus minimal-layer decision
business revision / dirty flags
idempotency marker
outbox event / batch-ready pointer
```

`_track_bonus_source` 改为生成 mutation intent，不再直接写 Redis。

### 4.2 正式 Writer Proof

Python 不直接写 MariaDB。新增发布批次：

```text
ELITE_BONUS_BATCH_READY
- batch_id / period / run_id / epoch / generation
- amount_encoding_version
- config_snapshot_id / period_snapshot_id
- candidate_gate_version
- bonus_rows_count / source_rows_count
- bonus_rows_checksum / source_rows_checksum
- empty_snapshot flag
- coverage / revision watermark
- payload_hash / created_at
```

业务系统写正式表后返回可验证 receipt；状态转换由 TASK-06 管理。

### 4.3 被否决方案

- 在 `_track_bonus_source` 外层加普通 Python 锁；进程崩溃仍可能半写。
- 先写 SOURCE 再写 stats，失败后补偿；补偿本身不可证明完整。
- 继续让 Python 直接写 MariaDB；违反 DEC-008，且跨 Redis/DB 不具备原子性。
- 只凭 `estimated_bonus>0` 作为 candidate gate；缺 PV_PSS/version/coverage proof。
- `persisted=False` 也视作正式完成；由 TASK-06 明确禁止。

## 5. 修改范围与受影响模块

- `User/EliteBonusService.py`：SOURCE intent、原子提交、integer cents、gate input。
- `User/GlobalEliteBonusRecalculationService.py`：candidate builder、完整批次、manifest，不再把 db_executor 作为生产正式路径。
- `Model/User/EliteBonusStats.py`：version、revision、integer cents、run/generation/dirty 字段（按 additive schema）。
- 新增 `Model/User/EliteSourceAssignment.py` 或 Redis ledger schema。
- 新增 `User/EliteBonusPublishBatch.py` / `User/EliteBonusCandidateBuilder.py`。
- 新增 Redis Function/Lua 与单元/故障测试。
- 业务系统接收协议由接口文档约束，实际关系库 writer 不在本仓库修改范围。

## 6. 明确排除项（防越界红线）

- 不修改 Elite/PE/SE 网络和 DEC-011 传播规则。
- 不恢复已经删除的 DEC-017 文档“差异段”。
- 不直接写 MariaDB，不声称 Redis+DB 跨存储原子。
- 不把无奖金顶端 SOURCE fallback 擅自恢复或删除；必须按现有批准 gate/SQL parity 标签处理。
- 不改变 EAB、PE、SE、LB 等其他奖金公式。
- 不在本任务实现全局 state machine；由 TASK-06 管理。

## 7. 前置条件与依赖关系

- TASK-01：amount version、units/cents API。
- TASK-02：normalized delta、period snapshot、无 float。
- TASK-03：冻结 Elite rate/config snapshot。
- TASK-06 依赖本任务的 batch-ready/receipt 合同。
- UAT 依赖 TASK-08 的 Redis/业务系统模拟 receiver 与故障注入权限。

## 8. 修改后行为与技术设计

### 8.1 SOURCE ledger

每个 source assignment 至少包含：

```text
period, source_user_id, bonus_user_id, layer
amount_encoding_version, business_revision
normalized_event_id, run_id, epoch, generation
assignment_hash, updated_at
```

条件更新“最小 layer”与 stats mutation 在同一 Redis 脚本内完成。

### 8.2 Candidate gate

正式候选必须同时证明：

1. period/run/epoch/generation 一致；
2. `amount_encoding_version=2`；
3. `PV_PSS > 0`（按有效 SQL/批准合同提供独立字段/证据）；
4. 初始化/传播输入与 `PV_PCS`、GPV、A/B path 一致；
5. `is_qualified=True` 且 `gpv_real_units>0`；
6. 配置 snapshot/费率/rounding 合法；
7. coverage/revision 无 gap；
8. SOURCE 每个 source 唯一归属，counts/checksum 对账。

缺任一项时 batch 状态为 `BLOCKED_CANDIDATE_PROOF`，不发 ready 事件。

### 8.3 空快照

无合格行也必须生成 `empty_snapshot=true` 的 batch manifest，明确表示“本期正式结果应为空”；不能因零行而不发批次，导致业务系统保留旧结果。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | `_track_bonus_source` 不再直接执行 HSET/EXPIRE | DEV | TC-026、TC-031 |
| AC-02 | 任一 Redis 命令点故障时 stats/SOURCE/revision/outbox 全成或全不成 | DEV+UAT | TC-026 |
| AC-03 | 重复 normalized event/revision 幂等，冲突 hash fail-loud | DEV+UAT | TC-015、TC-016、TC-023、TC-026 |
| AC-04 | 每个 source 最多一个正式 assignment，minimal layer 可复核 | DEV+UAT | TC-015、TC-016 |
| AC-05 | candidate 缺 PV_PSS/version/run/revision/coverage 任一字段时阻断 | DEV+UAT | TC-014、TC-029 |
| AC-06 | 奖金和 SOURCE counts/checksum 与 manifest 一致 | DEV+UAT | TC-015、TC-016、TC-029 |
| AC-07 | 空快照生成显式 batch，模拟器可清空旧正式结果 | DEV+UAT | TC-029 |
| AC-08 | 生产代码不调用 MariaDB db_executor；旧接口隔离并有扫描证明 | DEV | TC-029、TC-030 |
| AC-09 | receipt 不存在时只到 `READY_FOR_EXTERNAL_PUBLISH`，不标 PUBLISHED | DEV+UAT | TC-029 |
| AC-10 | DEC-011 数量变化/输出变化传播测试保持通过 | DEV+UAT | TC-009、TC-010 |
| AC-11 | 同一 run/generation 重跑幂等；新 generation 新 batch，不覆盖旧审计 | DEV+UAT | TC-015、TC-016、TC-025、TC-029 |

## 10. 环境验证与回传证据

### DEV

- Redis Lua/Function 原子性测试；
- SOURCE minimal layer、重复/冲突、revision gap；
- 七条 gate/candidate/empty batch；
- 模拟 receiver receipt/checksum；
- mutation：拆开 SOURCE/stats 两次写，测试必须失败。

### UAT

关联 `UAT-006、UAT-010、UAT-011`：

- 多订单、退款、并发 SOURCE；
- Redis中途断线/脚本超时/进程 kill；
- 完整和空批次；
- 业务系统写入模拟或隔离接口，receipt 与 checksum 回传；
- 回传 Redis dump、batch manifest、SOURCE、日志、receiver receipt、故障时间线。

## 11. 独立回滚与风险控制

1. 使用 `ELITE_ATOMIC_LEDGER_V2` 和 batch schema version 双开关。
2. shadow 阶段同时计算旧 SOURCE 与新 ledger，只比较，不双发正式批次。
3. 回滚时停止 v2 batch-ready，保留 ledger/manifest；不恢复非原子生产写入继续发奖。
4. 若 receiver 不兼容，新批次保持 READY/FAILED，不转 DONE；业务系统继续服务上一个 committed 版本。
5. 原子脚本和模型 schema 均 additive，回滚不删除字段/键。
