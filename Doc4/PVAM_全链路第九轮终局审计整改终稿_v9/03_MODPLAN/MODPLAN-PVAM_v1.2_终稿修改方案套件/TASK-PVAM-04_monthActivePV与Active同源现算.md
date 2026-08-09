# TASK-PVAM-04 monthActivePV 唯一取值函数与奖金 Active 同源现算

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-04` |
| 来源检查项 | `CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011` |
| 来源问题 | `R-005、R-006` |
| 处置项 | `REM-005、REM-006` |
| 施工项 | `W-005、W-006` |
| 验证项 | `V-005、V-006` |
| 派生缺口 | `GAP-DEC004-2B / DEFERRED` |
| 关联决策 | `DEC-004、DEC-016、DEC-018` |
| 严重级别 | `P0` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | `TASK-PVAM-01、TASK-PVAM-03` |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。


### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

- PE 当前以裸常量 30 派生活跃，绕过 `monthActivePV` 配置。
- PE/SE/EAB/Leadership 的输入合同仍要求或使用外部 `IS_ACTIVE`/活跃底表，形成多个权威源。
- Team Bonus oracle 接收 SQL `IS_ACTIVE` 是 Legacy correctness 输入，不能据此把该表变成新 Python 生产 Active 权威源。
- DEC-018 已明确不建设共享权威 snapshot；目标是各消费方使用同一 PV 源和唯一 getter 各自现算。

## 3. 本任务修改目标

1. 建立唯一 `monthActivePV` 取值函数和可审计读取链；本轮不实现 AR_CONFIG→Delta→Redis 写入/失效供给侧。
2. PE、SE、EAB、Leadership、TB（仅存在生产消费方时）都基于同一 `UserStats.pv` units 和同一 threshold 现算。
3. 移除外部 `IS_ACTIVE` 作为生产权威输入；如保留字段，只能作为审计比对，不参与发奖裁决。
4. 实现 INTEGER_BV_ONLY/scale=100 的门禁，并冻结 run manifest。

## 4. 处置决定与方案选择

### 4.1 唯一 getter

建议新增 `Common/MonthActivePvProvider.py`：

```text
1. 读 Redis 配置投影
2. 空 -> 等待 2 秒
3. 再读 Redis
4. 仍空 -> 读 Delta
5. 仍空 -> fail-loud，中止 run
```

重复同步行按 DEC-016 任取真实行一条，不要求排序；负值/超业务范围由上游校验，不在本系统二次业务阻断。

### 4.2 阈值规范

- 比较配置解析域为 scale=100；`30` 与 `30.00` 均规范为 30BV。
- `30.1` 含非零小数，按 INTEGER_BV_ONLY 阻断。
- 规范后的阈值再精确转换为 micro-units，用于与 `UserStats.pv` 比较。

### 4.3 DEC-004 2B 写入侧的本轮处置

本版明确选择 **缓建 / DEFERRED**：

- 本任务实现 Redis→等待2秒→Redis→Delta→fail-loud 的读取侧 getter、缓存冻结和消费方接线；
- 本任务不新增 AR_CONFIG CDC/批量同步、Delta 写入、Redis 装载/删除重载 producer；
- DEV 使用固定 fixture；UAT 由 TASK-08 协调 DBA/环境方受控注入 Redis/Delta fixture，并记录来源、注入人、版本、有效期和 checksum；
- fixture 只能验证读取侧，不能把 `GAP-DEC004-2B`、CHK-DATA-006 或 TC-007 的真实供给侧写成 PASS；
- 生产发布前必须另有受控施工任务完成写入/失效链，并通过 TC-007。

该处置不重新打开 DEC-004：目标合同已 CLOSED，未实现的是工程交付。

### 4.4 被否决方案

- 在每个服务写 `pv>=30`；会继续漂移。
- 读取 `AR_PERF_ACTIVE` 或共享 snapshot 作为权威；违反 DEC-004/018。
- 为方便审计物化共享 Active 表并要求所有服务消费；属于被否决的实现形态。
- 阈值缺失时默认30；违反 fail-loud 供给链。
- 用 float 比较 29.99/30.0；违反金额域。

## 5. 修改范围与受影响模块

- 新增 `Common/MonthActivePvProvider.py`、`Common/ActiveRule.py`。
- 修改 `User/PEBonusService.py`：输入改为 UserStats PV/version；删除 `IS_ACTIVE` 权威列和裸30。
- 修改 `User/SuperEliteBonusService.py`：不再要求 ddf_user_perf 的 is_active 作为裁决源。
- 修改 `User/EliteAchievementBonusService.py`：Active 由 pv+threshold 派生，理论/实际行保留现有业务语义。
- 修改 `User/LeadershipBonusGPUService.py`：从同 run 的 UserStats PV 派生最终发放闸门。
- 检查生产可达 TB 消费方；若不存在，仅维护 oracle 测试，不新增生产服务。
- 修改 orchestrator/run manifest：冻结 threshold raw/canonical/source/checksum。
- 明确不修改或新建 AR_CONFIG→Delta→Redis 写入侧 producer；该缺口由 TASK-08 登记并阻断生产关闭。
- 新增 cross-consumer consistency 测试。

## 6. 明确排除项（防越界红线）

- Elite Bonus 不受 Active 限制，不得新增闸门。
- 不建设共享 Active snapshot、表、唯一键或 builder。
- 不删除 SQL oracle 中的 `IS_ACTIVE` 字段；oracle 要保留 Legacy SQL 输入。
- 不改 SE 分母、EAB 理论行、LB理论金额、TB结余等既有业务规则。
- 不在 Python 读取 MySQL Active 表。
- 不把 UAT fixture、手工预置 Redis 或 Delta 行冒充生产 AR_CONFIG 同步链。
- 不对 DEC-016 已豁免的负值/上限/重复行做新的业务阻断。

## 7. 前置条件与依赖关系

- 依赖 TASK-01 的 units/version API。
- 依赖 TASK-03 的 ConfigSnapshot 和原始配置获取接口。
- 实际 UAT 依赖 TASK-08 的 Redis/Delta 受控 fixture 和固定环境；该 fixture 不关闭 `GAP-DEC004-2B`。

## 8. 修改后行为与技术设计

### 8.1 ActiveRule

```python
is_active = require_units_int(user_pv_units) >= threshold_units
```

输入必须属于同一 `period/run_id/config_snapshot_id`；version 不为2时阻断。

### 8.2 消费方接口

每个奖金服务接收：

```text
period_snapshot
config_snapshot / month_active_threshold_units
user_stats(user_id, pv_units, amount_encoding_version)
```

服务内部调用同一 `ActiveRule`。可选外部 `is_active` 只进入 `observed_active` 审计列；若不一致记录告警/差分，不覆盖派生值。

### 8.3 缓存与失效

getter 可按 config source version 缓存 canonical threshold；Delta/Redis 版本变化时只影响新 run。运行中不刷新，避免同一结算部分用户用旧阈值、部分用新阈值。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | 全仓生产路径不再出现裸 `>=30` Active 判定 | DEV+UAT | TC-007、TC-031 |
| AC-02 | 唯一 getter 的 Redis→2秒→Redis→Delta→fail 顺序有单测和故障测试 | DEV+UAT | TC-007 |
| AC-03 | 30、30.00 可规范；30.1 阻断；29.99PV不活跃，30PV活跃 | DEV+UAT | TC-007 |
| AC-04 | PE/SE/EAB/LB 在同一 user/period/run 下 Active 结果逐行一致 | UAT | TC-007、TC-017、TC-018、TC-019、TC-021 |
| AC-05 | 各服务不读取持久化 Active 表或共享 snapshot 作为权威 | DEV+UAT | TC-007、TC-030 |
| AC-06 | 外部 `IS_ACTIVE` 修改不改变奖金裁决，只产生审计差异 | DEV+UAT | TC-007 |
| AC-07 | Elite Bonus 结果不因 Active 变化而变化 | DEV+UAT | TC-007、TC-014 |
| AC-08 | SE 分母、EAB理论行、LB理论计算和TB结余语义不被改写 | UAT | TC-007、TC-013、TC-018、TC-019、TC-021 |
| AC-09 | run manifest 包含 threshold raw/canonical/source/version/checksum | DEV+UAT | TC-007、TC-032 |
| AC-10 | 配置在运行中变化不造成 run 内结果分裂 | DEV+UAT | TC-007 |
| AC-11 | UAT fixture 明确标记来源与 checksum；不得据 fixture 将 2B 生产供给链标为 PASS | UAT | TC-007、TC-032 |

> `GAP-DEC004-2B` 未关闭前，AC-02 在 DEV 可证明 getter 行为，但 CHK-DATA-006/TC-007 的真实供给侧验收仍保持 `BLOCKED` 或 `PENDING_TEST_ENV`。

## 10. 环境验证与回传证据

### DEV

- getter source chain、cache/invalidator、INTEGER_BV_ONLY 测试；
- 五消费方同一 fixture 的逐行结果；
- 全仓扫描 `IS_ACTIVE` 读取路径与裸30；
- mutation：让某消费方继续用外部 IS_ACTIVE，测试必须失败。

### UAT

关联 `UAT-003、UAT-005、UAT-007`：

- 29.99/30/30.00/30.1、配置切换、Redis缺失/Delta回退；
- PE/SE/EAB/LB同一用户全集；
- SQL Legacy active 与 corrected 派生结果并列差分；
- 回传 config snapshot、UserStats PV/version、各服务Active trace、奖金结果。

## 11. 独立回滚与风险控制

1. 以 `ACTIVE_RULE_V2` 按消费方切换；shadow 模式先比对，不发奖。
2. 回滚只能退回最后一个已验证的统一 getter 版本，不能恢复各服务硬编码。
3. 若某消费方切换失败，冻结该奖项发布；其他奖项可保持 shadow，不允许形成混合正式发奖。
4. threshold/config snapshot 永久保留用于复盘。
