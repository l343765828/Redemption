# TASK-PVAM-02 订单/退款入口金额放大与边界转换

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-02` |
| 来源检查项 | `CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005` |
| 来源问题 | `R-003、R-007` |
| 处置项 | `REM-003、REM-007` |
| 施工项 | `W-003、W-007` |
| 验证项 | `V-003、V-007` |
| 关联决策 | `DEC-002、DEC-005、DEC-006、DEC-007、DEC-010` |
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

### 2.1 金额链事实

- `PEBonusService._apply_truncate` 使用 `cp.round`，并以 `/100.0` 输出奖金 float。
- `SuperEliteBonusService` 在金额/比例路径存在 Decimal 与后续 DataFrame 数值转换分叉。
- `LeadershipBonusGPUService._truncate_gpu` 显式转换 `float64`，再 `nextafter/trunc`。
- `EliteBonusStats.estimated_bonus` 与 Elite 服务写入 float。
- `PlacementRecalculationService` 从 Redis 读取金额时调用 `float(...)`，空表也构造 `float64` PV 列。

### 2.2 Period 事实

- `GlobalRecalculationService._get_previous_period` 硬编码首期为 1，并直接 `period-1`。
- `PlacementIncrementalService._get_prev_period` 同样硬编码首期 1。
- `PlacementRecalculationService._get_prev_period` 同时接受 `YYYYMM` 并做自然月减一，或接受正整数减一。
- 这些实现绕过“由 AR_PERIOD 唯一解析 current/first/previous/calc_month”的目标合同。

### 2.3 入口事实

- 当前 `Order/OrderService.py` 是 Dask/BFS 演示入口，不是受控 PV 订单消费边界。
- `MessageConsumer/UserConsumer.py` 消费用户变更并更新图，不是订单/退款金额 Normalizer。
- 因此实施不得把演示脚本或用户拓扑 consumer 直接宣称为生产金额入口；必须建立并证明真实接线。

## 3. 本任务修改目标

1. 建立外部订单/退款和 DB 批量装载的唯一金额转换边界。
2. 生成不可变 normalized delivery，提供唯一 `effective_pv_delta_units` 给 UserStats、Placement、Elite 三路。
3. 清除所有生产可达金额链中的 float/round 中转，使用 TASK-01 的 units/ppm/cents API。
4. 建立唯一 `PeriodResolver`，所有服务、Active、配置、writer 和退款归期共用同一 period snapshot。
5. 落实已确认的整单退款、一次冲销和批准时间归期原则，同时不越权决定人工 override/迟到边界。

## 4. 处置决定与方案选择

### 4.1 目标组件

建议新增：

- `Common/PeriodResolver.py`
- `MessageConsumer/PvEventSchema.py`
- `MessageConsumer/PvEventNormalizer.py`
- `MessageConsumer/PvEventConsumer.py`（或接入实际部署入口的等价模块）
- `Model/Order/NormalizedPvEvent.py`
- `Order/RefundReversalLedger.py`（Redis 权威接口/协议；事务落地与 epoch 在 TASK-06 联动）

### 4.2 两处放大边界

```text
A. Kafka/MQ raw event：canonical decimal string -> units
B. DB batch loader：Decimal/string -> units
```

内部服务只接收：

```text
period_num
source_system
source_event_id
normalized_event_id
business_revision / previous_business_revision
effective_pv_delta_units (strict int)
amount_encoding_version=2
approved_at / resolved_period_snapshot
```

### 4.3 PeriodResolver

解析动作必须：

1. 查询 `AR_PERIOD` 并验证 current period 唯一；
2. 读取 `CALC_YEAR/CALC_MONTH`；
3. 读取系统首期 `MIN(PERIOD_NUM)`；
4. 非首期验证 `current-1` 行真实存在；
5. 为退款把批准时间转换 GMT+8 后查询唯一 period；
6. 产出 immutable `PeriodSnapshot`，包含源查询 checksum/版本。

### 4.4 被否决方案

| 方案 | 否决理由 |
|---|---|
| 入口 `bv=int(bv)` | 会截断或误收非规范输入，且无法判断原单位 |
| 内部服务再次 `pv_to_units` | 导致双放大 |
| 根据 6 位字符串猜 YYYYMM | PERIOD_NUM 与 YYYYMM 语义不同 |
| 首期固定 1 | AR_PERIOD 首期可能不是 1 |
| 以 Kafka 到达时间决定退款期 | DEC-006 指定批准时间 |
| 把 `OrderService.py` demo 直接部署 | 没有 schema、幂等、period、guard 与三路分发合同 |
| 用 float64 提升 GPU 性能 | 违反财务定点合同 |

## 5. 修改范围与受影响模块

### 5.1 边界与 Normalizer

- 新订单/退款消息 schema 和 Normalizer。
- 实际 Kafka/MQ 部署入口及启动脚本。
- DB batch loader/全量重建入口。
- UserStats/Placement/Elite 增量调用签名。

### 5.2 float 清理

| 文件 | 目标修改 |
|---|---|
| `User/PEBonusService.py` | TOTAL_BASE_GPV/bonus 全整数；取消 `cp.round` 与 `/100.0` |
| `User/SuperEliteBonusService.py` | orders/pool/bonus 使用 units/cents；禁止 float dtype |
| `User/LeadershipBonusGPUService.py` | `_truncate_gpu` 改为整数比例/截断；gpv 列 int64 |
| `User/EliteBonusService.py` | estimated bonus 迁移到 integer cents；不写 float |
| `Model/User/EliteBonusStats.py` | v2 路径只写 integer-cents 字段 |
| `User/PlacementRecalculationService.py` | 去掉 Redis `float()`、float64 PV 列和 round |
| `User/PlacementIncrementalService.py` | 入口严格 units-int；period resolver |
| `User/GlobalRecalculationService.py` | period resolver；金额 version/dtype 守卫 |
| `User/EliteAchievementBonusService.py` | 保留其已批准最终 HALF_UP，但接入公共 units/cents 边界，避免多 scale 混用 |

### 5.3 测试

- raw schema/parser 测试；
- DB loader 测试；
- normalized single-delta 三路一致测试；
- period/退款边界测试；
- 各奖金和 Placement 金额 mutation/dtype 测试。

## 6. 明确排除项（防越界红线）

- 不改变 E/PE/SE/EAB/LB/TB 的资格、分母、比例和网络公式。
- 不把 corrected floor-zero 冒充 Legacy SQL；两种模式必须可追溯。
- 不决定退款金额不符后的人工 override、授权角色或专项池 reconciliation。
- 不自行定义“迟到事件 cutoff”；未签字场景自动路径拒绝并留证。
- 不在本任务完成 settlement epoch/发布状态机；由 TASK-06 实现。
- 不建设生产 TB 服务；只保证已有 oracle/验收输入单位不被混淆。

## 7. 前置条件与依赖关系

- 必须先完成 TASK-PVAM-01 的公共 API 与模型 version。
- 必须先完成 TASK-PVAM-03 的配置 API；配置相关比例必须通过该接口获取，本任务只负责金额运算迁移。
- 最终三路事件提交、epoch 和 coverage 依赖 TASK-PVAM-06。
- UAT 归期测试依赖 DEC-013 环境准入和 AR_PERIOD 只读权限。

## 8. 修改后行为与技术设计

### 8.1 外部金额 schema

只接受 JSON string：`"30"`、`"30.00"`、`"-100.25"`。拒绝 JSON number、bool、null、指数、NaN、Infinity、超过两位小数和空白修复式输入。

### 8.2 Normalized delivery

Normalizer 只计算一次：

```text
old_business_units
new_business_units
effective_pv_delta_units = new_business_units - old_business_units
```

`effective_pv_delta_units` 与 identity/hash 固化后，UserStats、Placement、Elite 只消费该字段，禁止重新聚合、钳制或放大。corrected floor-zero 仅在批准的业务状态计算点执行，并保留原始 signed event。

### 8.3 退款

- 任一商品退款触发原订单整单有效 BV 等额负向事件。
- 同一原订单从未冲销到已整单冲销只允许一次。
- 相同身份/hash 重投为幂等 no-op；第二个冲销请求按 DEC-005 识别 duplicate/no-op，不再次扣减。
- 金额与原订单不一致、身份冲突：自动路径拒绝，记录永久冲突；不做部分应用。
- 未发奖回原期，已发奖进入批准时间映射出的当前期；不重开已发历史期。

### 8.4 出计算域

- units -> cents 或 Decimal string 只在 writer/event adapter 做。
- 每个输出字段在编码矩阵中登记：字段名、内部单位、外部单位、舍入模式、调用点。
- DataFrame merge/groupby 前后调用 dtype assertion。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | 全仓只有两个批准的放大调用点；生产内部无第三处 `*1_000_000` | DEV+UAT | TC-001、TC-002、TC-023 |
| AC-02 | JSON number/float/bool/null/指数/NaN/Infinity 全部拒绝并进入明确错误处置 | DEV+UAT | TC-001 |
| AC-03 | 同一 normalized event 三路收到相同 int delta、version、revision 和 identity | DEV+UAT | TC-023、TC-026 |
| AC-04 | PE/SE/Elite/LB/Placement 生产金额列无 float dtype；EAB scale 不与公共 units 混用 | DEV+UAT | TC-002、TC-012、TC-017、TC-018、TC-021 |
| AC-05 | 最终奖金不以 float 输出，外部只输出两位 Decimal string 或 integer cents | DEV+UAT | TC-008、TC-017、TC-018、TC-019、TC-021 |
| AC-06 | PeriodResolver 不接受 YYYYMM 推导；首期来自 MIN(AR_PERIOD) | DEV+UAT | TC-006 |
| AC-07 | current/previous period 缺失、多行或不连续时 fail-loud | DEV+UAT | TC-006 |
| AC-08 | 退款批准时间经 GMT+8 在月界前后映射正确；到达时间不影响归期 | UAT | TC-006、TC-022 |
| AC-09 | 整单退款重复和第二次冲销不产生第二个负 delta | DEV+UAT | TC-010、TC-022 |
| AC-10 | SQL-Python 边界、极值、负值、跨分区差分符合 Legacy/Corrected 标签 | UAT | TC-008、TC-012、TC-017、TC-018、TC-019、TC-021 |
| AC-11 | demo/图 consumer 未被冒充金额入口；真实启动/部署接线有证据 | DEV+UAT | TC-024、TC-030、TC-032 |
| AC-12 | 本任务 feature flag 关闭后，不影响 TASK-01 模型/API | DEV | TC-031 |

> UAT 专属 AC 未取得 DEC-013 环境、真实 AR_PERIOD/消息数据或同数据 SQL oracle 时保持 `PENDING_TEST_ENV`。

## 10. 环境验证与回传证据

### DEV

- parser/normalizer/property-based 测试；
- 全仓 AST/dtype/forbidden-pattern 扫描；
- period resolver 使用固定 AR_PERIOD fixture；
- 三路 mock consumer identity/delta 一致性；
- E/PE/SE/EAB/LB/Placement 边界 fixture。

### UAT

关联 `UAT-001、UAT-004、UAT-005、UAT-007、UAT-011`：

- 真实 Kafka/MQ订单和退款；
- AR_PERIOD 跨月/跨年/非1首期/缺期；
- MySQL SQL 与 Python 同数据差分；
- GPU 大数和分区聚合 dtype；
- 重复、乱序、迟到、负值、整单冲销；
- 回传 topic/partition/offset、normalized payload、Redis前后、SQL/Python结果和 checksum。

## 11. 独立回滚与风险控制

1. Normalizer 以 `schema_version=2` 双轨发布；旧 consumer 不接收 v2 事件。
2. 先 shadow-compute 并比对，不写业务状态；通过后按 consumer 逐路切换。
3. 回滚时停止 v2 consumer，保留 normalized ledger 和 v2 Redis 状态；不得把 units 当 legacy BV 重放。
4. PeriodResolver 回滚时冻结结算，不允许恢复本地 period 算术继续生产写入。
5. 任一三路结果不一致时阻断该 normalized event，不能只回滚其中一路继续累计。
