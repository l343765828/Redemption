# WORK-PVAM-02 订单/退款入口金额放大与边界转换施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-02`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-003、R-007` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-02-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-02` |
| 施工任务名称 | 订单/退款入口金额放大与边界转换 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-02@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-003、R-007` |
| 复核闭环追踪号 | `REM-003、REM-007 / W-003、W-007 / V-003、V-007` |
| 来源检查项 | `CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005` |
| 关联决策 | `DEC-002、DEC-005、DEC-006、DEC-007、DEC-010` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、WORK-PVAM-03 均达到 DEV_VERIFIED；WORK-PVAM-03 配置 API 在奖金切换前必须可用 |
| 功能开关 | `PV_NORMALIZER_V2 / PERIOD_RESOLVER_V2` |

### 1.1 一对一追溯摘要

```text
CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005
  └─ R-003、R-007
       └─ DEC-002、DEC-005、DEC-006、DEC-007、DEC-010
            └─ TASK-PVAM-02 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-02
                      ├─ STEP-PVAM-02-01 / STEP-PVAM-02-02 / STEP-PVAM-02-03 / STEP-PVAM-02-04 / STEP-PVAM-02-05 / STEP-PVAM-02-06 / STEP-PVAM-02-07
                      ├─ TC-PVAM-02-01 / TC-PVAM-02-02 / TC-PVAM-02-03 / TC-PVAM-02-04 / TC-PVAM-02-05 / TC-PVAM-02-06 / TC-PVAM-02-07 / TC-PVAM-02-08
                      └─ EV-PVAM-02-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-003、R-007 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-02` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005 | CONTROLLED |
| 正式决策 | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-02` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、WORK-PVAM-03 均达到 DEV_VERIFIED；WORK-PVAM-03 配置 API 在奖金切换前必须可用。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 实现唯一 raw→normalized PV 入口和唯一 PeriodResolver；三条增量链只消费同一 strict units-int delta；清除生产可达金额链中的 float/round 中转。 |
| 当前行为 | `User/PEBonusService.py::_apply_truncate` 使用 `cp.round` 并通过 `/100.0` 产生奖金 float。；`User/LeadershipBonusGPUService.py::_truncate_gpu` 将金额转为 `float64` 后使用 `nextafter/trunc`。；`User/PlacementRecalculationService.py::_process_extract_batch` 从 Redis 调用 `float(...)`，空表构造 `float64` PV 列，回写包含 `int(round(float(...)))`。；`GlobalRecalculationService._get_previous_period`、`PlacementIncrementalService._get_prev_period` 和 `PlacementRecalculationService._get_prev_period` 存在本地 period 算术/首期硬编码。；`Order/OrderService.py` 是 Dask/BFS 演示，`MessageConsumer/UserConsumer.py` 是拓扑变更 consumer；二者都不是受控金额入口。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-02`；检查项 `CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011、CHK-DATA-005` |

### 3.2 已确认代码事实

- `User/PEBonusService.py::_apply_truncate` 使用 `cp.round` 并通过 `/100.0` 产生奖金 float。
- `User/LeadershipBonusGPUService.py::_truncate_gpu` 将金额转为 `float64` 后使用 `nextafter/trunc`。
- `User/PlacementRecalculationService.py::_process_extract_batch` 从 Redis 调用 `float(...)`，空表构造 `float64` PV 列，回写包含 `int(round(float(...)))`。
- `User/SuperEliteBonusService.py:404`（基线稳定语句）以 `(orders['pv'] * 1000).round().astype('int64')` 生成 `pv_mills`，属于 R-003 登记的本地放大/round 链，必须改由公共金额边界与整数列合同承接。
- `Model/User/EliteBonusStats.py::estimated_bonus` 的 float 持久化字段由 WORK-PVAM-01 的 `estimated_bonus_cents` 兼容改造承接，本任务只负责入口和计算链不再继续制造 float。
- `GlobalRecalculationService._get_previous_period`、`PlacementIncrementalService._get_prev_period` 和 `PlacementRecalculationService._get_prev_period` 存在本地 period 算术/首期硬编码。
- `Order/OrderService.py` 是 Dask/BFS 演示，`MessageConsumer/UserConsumer.py` 是拓扑变更 consumer；二者都不是受控金额入口。

### 3.3 本任务目标

实现唯一 raw→normalized PV 入口和唯一 PeriodResolver；三条增量链只消费同一 strict units-int delta；清除生产可达金额链中的 float/round 中转。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | 用户变更消息 | `MessageConsumer/UserConsumer.py::consume_loop` | ChangeUserMsg | 直接 `actor.run_update` | 不是PV入口 |
| 2 | 订单演示 | `Order/OrderService.py::main` | OrderPayload示例 | 打印BFS结果 | 没有schema/幂等/period |
| 3 | 增量UserStats | `User/UserStatsService.py::update_elite_performance` | `bv` 后 `int(bv)` | 更新Redis | 原单位不可证明 |
| 4 | Placement全量 | `User/PlacementRecalculationService.py::_process_extract_batch` | Redis JSON | float转换/round回写 | 精度漂移 |
| 5 | Period | 三个本地 `_get_prev*` | 字符串/整数 | 本地减一或YYYYMM推导 | 绕过AR_PERIOD |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| UserStatsService | effective delta | 改为接收NormalizedPvEvent/strict units | 是 | STEP-02-04/TC-023 |
| PlacementIncrementalService | 同上 | 同一delta，不再转换 | 是 | STEP-02-04/TC-012/023 |
| EliteBonusService | 同上 | 同一delta，不再转换 | 是 | STEP-02-04/TC-015/023 |
| 批量全量服务 | DB金额/period snapshot | DB boundary转换一次 | 是 | STEP-02-03/05 |
| 奖金服务 | units/cents | 移除float中转 | 是 | STEP-02-06 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/PeriodResolver.py`，以可注入 repository 查询 AR_PERIOD；输出不可变 `PeriodSnapshot(period_num, calc_year, calc_month, first_period_num, previous_period_num, source_checksum)`。
- 新增 `Model/Order/NormalizedPvEvent.py`、`MessageConsumer/PvEventSchema.py`、`PvEventNormalizer.py`；raw 金额字段只接受 canonical JSON string。
- 事件身份不含 period；normalized event 固化 source identity、hash、business revision、previous revision、effective_pv_delta_units、version=2 和 resolved period snapshot。
- 退款用 `Order/RefundReversalLedger.py`（新增 Redis authority接口）保证同一原订单只产生一次整单负delta；批准时间按 GMT+8 映射。
- PE/SE/LB/Elite/Placement 的金额列改用 int64 units/cents；EAB 保留最终一次 HALF_UP，但入口统一使用公共units。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 入口 `int(bv)` | 会截断/误收原始单位 | R-003 |
| 内部再次乘1e6 | 双放大 | CHK-DATA-001 |
| YYYYMM猜period | PERIOD_NUM不是日历值 | DEC-006/CHK-DATA-005 |
| 到达时间定退款期 | 违反批准时间裁决 | DEC-006 |
| 部署OrderService demo | 没有生产合同 | CHK-ARCH-002 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + PV_NORMALIZER_V2 / PERIOD_RESOLVER_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/PeriodResolver.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/PeriodResolver.py` | `PeriodRepository`、`PeriodResolver`、`PeriodSnapshot` | 新增 | 不存在 | 从AR_PERIOD解析current/first/previous/approval-time period | 唯一period合同 | 不得本地减一猜测 |
| CHG-02 | `Model/Order/NormalizedPvEvent.py` | 不可变事件模型 | 新增 | 不存在 | 定义identity/revision/delta/version/period | 三stage同一payload | 不得含float |
| CHG-03 | `MessageConsumer/PvEventSchema.py` / `MessageConsumer/PvEventNormalizer.py` | schema与normalize | 新增 | 无受控金额入口 | canonical string→units一次，生成hash/delta | 非法输入fail-loud | 不得trim/指数/number洗白 |
| CHG-04 | `Order/RefundReversalLedger.py` | 原订单冲销CAS | 新增 | 不存在 | 一次整单冲销、重复no-op、冲突阻断 | 无二次负delta | 不得决定人工override |
| CHG-05 | `User/UserStatsService.py` | `update_elite_performance` | 修改 | 接收bv并int转换 | 改接收strict units/int + identity/revision；保留兼容adapter为非生产 | 不再缩放 | 不得绕过guard |
| CHG-06 | `User/PlacementIncrementalService.py` | `update_placement_performance`、`_get_prev_period` | 修改 | bv int、本地period | 接收同一delta；注入PeriodSnapshot | 与UserStats同输入 | 不得period算术 |
| CHG-07 | `User/EliteBonusService.py` | `update_elite_bonus_incremental`、bonus字段 | 修改 | pv_delta int但无version；bonus float | strict units/version；写cents | 无float | 不得改资格公式 |
| CHG-08 | `User/PlacementRecalculationService.py` | `_get_prev_period`、`_process_extract_batch`、`_calculate_placement_pv`、`_write_back_placement_matrix` | 修改 | float读取/float64/round | int64 units与PeriodSnapshot | 无精度漂移 | 不得改闭包腿逻辑 |
| CHG-09 | `User/PEBonusService.py` / `User/SuperEliteBonusService.py` / `User/LeadershipBonusGPUService.py` / `User/EliteAchievementBonusService.py` | 金额计算边界 | 修改 | 多处float/本地scale | 接公共units/ppm/cents；整数运算 | writer前明确cents/string | 不得改变SQL公式 |
| CHG-10 | `MessageConsumer/PvEventConsumer.py`或WORK-08A证明的现有部署入口 | 生产消费编排 | 条件新增/修改 | 当前仓库未证明订单PV入口 | normalize一次后分发三stage；先guard后权威提交 | 唯一可追踪入口 | 无callgraph不得创建第二consumer/topic/group |

### 6.1 固定基线锚点与生产入口门禁

| 文件与符号 | 基线事实 | 裁决 |
|---|---|---|
| `Order/OrderService.py::main` | 构造`OrderPayload`后调用Dask图演示并打印，非生产金额入口 | 不得直接改造成生产consumer |
| `MessageConsumer/UserConsumer.py::consume_loop` | 消费`change-user`并直接调用`graph_actor.run_update` | 这是拓扑入口候选，不得当作订单PV入口 |
| `User/PlacementRecalculationService.py::_extract_period_data/_process_extract_batch` | 使用`float64`、`float(...)`和`int(round(float(...)))`链 | 改为严格int64/version读取 |
| `User/GlobalRecalculationService.py::_get_previous_period` | 以1为首期并做period-1 | 改为注入的`PeriodResolver` |
| `User/PEBonusService.py::_apply_truncate` | `cp.round(...*100)`与`/100.0` | 改为units/ppm/cents整数公式 |

`MessageConsumer/PvEventConsumer.py`是上游TASK允许的候选新文件，不是当前基线事实。施工分支必须由WORK-08A部署证据选择：

1. 已存在唯一订单/退款consumer：修改该真实文件并保留原Topic/group；
2. 没有现存consumer且部署方案明确批准新入口：才新增`PvEventConsumer.py`；
3. 证据不完整：只完成schema、normalizer、repository和单测，生产接线步骤标记`BLOCKED_CALLGRAPH`。

### 6.2 Period与Normalized事件接口合同

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

@dataclass(frozen=True)
class PeriodSnapshot:
    period_num: int
    calc_year: int
    calc_month: int
    previous_period_num: int | None
    source_checksum: str

class PeriodRepository(Protocol):
    def resolve_current(self, period_num: int) -> PeriodSnapshot: ...
    def resolve_approved_at(self, approved_at: datetime) -> PeriodSnapshot: ...
```

Normalized delivery必须冻结：`source_system/source_event_id/payload_hash/business_revision/previous_business_revision/effective_pv_delta_units/amount_encoding_version=2/period_snapshot`。三个stage只能消费该delta，不得重新解析raw金额、再次乘scale或自行钳制。

### 6.3 金额改造公式纪律

- GPU/CPU中间列保持signed int64；join后立即断言dtype。
- 比例计算使用`trunc_div_zero(base_units * rate_ppm, 1_000_000)`；最终支付转换到cents时按对应SQL截断点执行。
- EAB保留批准的“中间不舍入、个人最终一次HALF_UP”；本任务只替换输入/输出单位适配，不改变模式。
- 任何需要猜测真实Topic、group、退款字段名或DB loader位置的施工都必须停止并登记`BLOCK-PVAM-02-CALLGRAPH`。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-02-01：实现PeriodResolver

- 目的：实现PeriodResolver，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：WORK-01 DEV_VERIFIED
- 修改文件：`Common/PeriodResolver.py`
- 目标符号：resolver/repository
- 精确操作：
1. 按AR_PERIOD唯一性、MIN首期、真实前期行和GMT+8批准时间实现
2. repository接口不绑定具体ORM。
- 必须保持：不猜YYYYMM；不固定首期1
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/PeriodResolver.py`
- 本步单元验证：`TC-PVAM-02-01/02`
- 完成证据：`EV-PVAM-02-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：缺少AR_PERIOD字段合同则BLOCK

### STEP-PVAM-02-02：定义normalized事件与raw schema

- 目的：定义normalized事件与raw schema，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-01
- 修改文件：`Model/Order/NormalizedPvEvent.py`、`MessageConsumer/PvEventSchema.py`
- 目标符号：数据类/校验
- 精确操作：
1. 严格字符串金额、identity/hash/revision
2. 模型冻结不可变。
- 必须保持：不接受JSON number/bool/null/指数
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/Order/NormalizedPvEvent.py MessageConsumer/PvEventSchema.py`
- 本步单元验证：`TC-PVAM-02-03`
- 完成证据：`EV-PVAM-02-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：外部真实schema未确认则只做adapter不接生产

### STEP-PVAM-02-03：实现Normalizer和退款ledger

- 目的：实现Normalizer和退款ledger，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-02
- 修改文件：`MessageConsumer/PvEventNormalizer.py`、`Order/RefundReversalLedger.py`
- 目标符号：normalize/CAS
- 精确操作：
1. 只在raw或DB边界转换
2. 计算effective delta
3. 退款whole-order CAS。
- 必须保持：不得部分退款；不得自行定义迟到cutoff
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/PvEventNormalizer.py Order/RefundReversalLedger.py`
- 本步单元验证：`TC-PVAM-02-03~05`
- 完成证据：`EV-PVAM-02-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：原订单权威状态不可取时BLOCK

### STEP-PVAM-02-04：改造三stage增量入口

- 目的：改造三stage增量入口，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-03
- 修改文件：UserStats/Placement/Elite服务
- 目标符号：三个入口函数
- 精确操作：
1. 接收同一normalized payload或严格字段
2. 校验version/revision/hash
3. 删除本地转换。
- 必须保持：保持业务传播/锁/幂等公式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/UserStatsService.py User/PlacementIncrementalService.py User/EliteBonusService.py`
- 本步单元验证：`TC-PVAM-02-06`
- 完成证据：`EV-PVAM-02-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：三路hash不一致立即停工

### STEP-PVAM-02-05：替换本地period算术

- 目的：替换本地period算术，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-01
- 修改文件：Global/Placement/奖金入口
- 目标符号：`_get_previous_period`/`_get_prev_period`调用点
- 精确操作：
1. 改为注入PeriodSnapshot
2. 旧方法只做deprecated adapter并禁止生产直连。
- 必须保持：保留Redis key格式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/GlobalRecalculationService.py User/PlacementIncrementalService.py User/PlacementRecalculationService.py`
- 本步单元验证：`TC-PVAM-02-01/02`
- 完成证据：`EV-PVAM-02-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一生产入口仍本地算period不合并

### STEP-PVAM-02-06：清除生产float金额链

- 目的：清除生产float金额链，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：WORK-PVAM-01与WORK-PVAM-03均达到DEV_VERIFIED，且WORK-PVAM-03配置接口可用
- 修改文件：PE/SE/LB/Elite/EAB/Placement文件
- 目标符号：金额符号
- 精确操作：
1. 逐字段换成units/ppm/cents
2. merge/groupby前后dtype断言。
- 必须保持：保持各奖项SQL舍入点
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Model Common MessageConsumer Order`
- 本步单元验证：`TC-PVAM-02-07/08`
- 完成证据：`EV-PVAM-02-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：SQL黄金样例差1分立即停止

### STEP-PVAM-02-07：建立生产入口与回归测试

- 目的：建立生产入口与回归测试，落实 `TASK-PVAM-02` 的已批准目标。
- 前置条件：STEP-02-02~06
- 修改文件：由WORK-08A选定的唯一真实部署入口；仅在“无现存入口且新consumer获批”分支新增`MessageConsumer/PvEventConsumer.py`，并同步测试/部署文件
- 目标符号：consumer/pytest
- 精确操作：
1. 接入实际配置通过依赖注入
2. 先guard、后normalize、后stage提交、最后ACK由事件任务处理。
- 必须保持：不得写真实地址/密钥
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_pv_event_normalizer.py User/Test/test_period_resolver.py User/Test/test_amount_dtype_migration.py`
- 本步单元验证：`TC-PVAM-02-01~08`
- 完成证据：`EV-PVAM-02-07`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：部署入口未获确认时保持BLOCKED

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Kafka/MQ raw amount | 字符串/number混杂风险 | canonical string→units的NormalizedPvEvent | Normalizer唯一边界 | schema_version=2 | 非法输入DLQ/拒绝 |
| Redis金额状态 | 旧单位/float路径 | version=2 int64 units | 三stage/全量入口 | amount_encoding_version | legacy阻断/重建 |

### 8.2 迁移步骤

| 顺序 | 操作 | 批次/范围 | 幂等键或判定 | 校验 | 失败处理 |
|---|---|---|---|---|---|
| 1 | 只读扫描/dry-run | 专用period/fixture或全量key清单 | run_id + 对象唯一键 | 数量、版本、金额/事件汇总 | 不写入并生成BLOCK |
| 2 | 启用shadow/read验证 | 单个隔离run | event/run/generation或feature flag | 新旧输出逐字段比较 | 关闭flag |
| 3 | 受控新写/切换 | 批准的UAT范围 | idempotency key/CAS | 重复执行结果不变 | 停止consumer/回滚代码 |
| 4 | 保留审计与兼容窗口 | 直到Gate关闭 | manifest checksum | 无新旧混读 | 不删除新字段/证据 |

### 8.3 兼容矩阵

| 读取方 | 旧数据 | 新数据 | 混合数据 | 预期行为 |
|---|---|---|---|---|
| 旧代码 | 原合同内支持 | 默认不保证 | 禁止 | 回滚前必须停止新写；不得让旧代码读取v2数据 |
| 新代码 | 仅隔离adapter/审计 | 支持 | 普通计算阻断 | 不能静默换算 |
| 证据/迁移工具 | 只读支持 | 只读支持 | 分类报告 | 不参与奖金计算 |

### 8.4 幂等与重跑断言

- 第一次执行：产生一个可追踪 run/attempt 及确定结果。
- 相同输入重复执行：以本任务定义的 event/run/generation/idempotency 键 no-op 或得到完全相同结果。
- 中断后续跑：从权威状态判断旧/新完整状态，不把半状态当成功。
- 部分旧/部分新：普通计算阻断，输出精确异常对象与证据；不得自动洗白。

## 9. 测试设计

### 9.1 测试用例总表

| 测试编号 | 层级 | 场景 | 固定输入 | 精确预期 | 对应步骤 | 环境 | 状态 |
|---|---|---|---|---|---|---|---|
| TC-PVAM-02-01 | 单元 | Period首期/前期 | fixture period 40(2025/12),41(2026/01) | first=40,current=41,previous=40 | STEP-02-01 | DEV | NOT_RUN |
| TC-PVAM-02-02 | 单元/集成 | 批准时间GMT+8 | `2026-01-31T16:00:00Z` | 转换为GMT+8的2026-02-01 00:00并匹配唯一二月period | STEP-02-01 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-03 | 契约 | raw金额类型 | `"30.00"`与JSON number 30.0 | 字符串→30,000,000；number受控失败 | STEP-02-02/03 | DEV | NOT_RUN |
| TC-PVAM-02-04 | 幂等 | 整单退款重复 | 原订单100.25，两次退款请求 | 首个delta=-100,250,000；第二个duplicate/no-op，累计仍-100,250,000 | STEP-02-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-05 | 冲突 | 同identity不同hash | 同source id两payload | 阻断并记录冲突；无stage写入 | STEP-02-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-06 | 集成 | 三stage同delta | 同normalized event | UserStats/Placement/Elite输入hash、revision、delta完全相同 | STEP-02-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-07 | 差分 | PE截断样例 | 1,500.99 BV、15% | 1,500,990,000 units；奖金22514 cents=225.14 | STEP-02-06 | DEV+UAT | NOT_RUN |
| TC-PVAM-02-08 | 静态/mutation | float清除 | AST与dtype mutation | 生产金额路径无float64/round洗白；mutation被捕获 | STEP-02-06/07 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-001, TC-002, TC-006, TC-008, TC-010, TC-012, TC-017, TC-018, TC-019, TC-021, TC-022, TC-023, TC-024, TC-026, TC-030, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-02}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-02"

# Phase B：在由 parent provenance 证明来源的干净 PARENT_COMMIT worktree 应用当前 WORK 的直接 patch，
# 校验 per-WORK scope、applied tree hash，随后只编译本 WORK 实际变更的 Python 文件并执行专属测试命令。
bash "$CONTROL_ROOT/validate_work_dev.sh" \
  --repo "$REPO_ROOT" \
  --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" \
  --work-id "WORK-PVAM-02" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-02.sh" \
  --out "evidence/WORK-PVAM-02/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from datetime import datetime, timezone
from Common.PeriodResolver import PeriodResolver
from MessageConsumer.PvEventNormalizer import PvEventNormalizer


def test_period_and_refund_contract(period_repository, event_registry, refund_ledger) -> None:
    resolver = PeriodResolver(period_repository)
    snap = resolver.resolve_approval_time(datetime(2026, 1, 31, 16, 0, tzinfo=timezone.utc))
    assert snap.calc_year == 2026
    assert snap.calc_month == 2
    normalizer = PvEventNormalizer(resolver, event_registry, refund_ledger)
    first = normalizer.normalize_refund({"source_event_id": "R-1", "original_order_id": "O-1", "amount": "100.25", "approved_at": "2026-01-31T16:00:00Z"})
    second = normalizer.normalize_refund({"source_event_id": "R-2", "original_order_id": "O-1", "amount": "100.25", "approved_at": "2026-01-31T16:00:00Z"})
    assert first.effective_pv_delta_units == -100_250_000
    assert second.disposition == "DUPLICATE_NOOP"
    assert second.effective_pv_delta_units == 0
    with pytest.raises((TypeError, ValueError)):
        normalizer.normalize_order({"source_event_id": "O-X", "amount": 30.0})
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-02-01：真实订单/退款/period与三stage

- 对应受控测试：`TC-001、TC-006、TC-008、TC-010、TC-022、TC-023`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：Kafka/Redis/Dask隔离环境；AR_PERIOD只读；专用topic/group/period
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work02-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-02 --run-id "$RUN_ID" --tc TC-001,TC-006,TC-008,TC-010,TC-022,TC-023
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
test "${UAT_SCHEMA_ISOLATED:?must equal 1}" = "1"
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
SELECT PERIOD_NUM, CALC_MONTH, IS_PERFING, IS_PERFED, IS_CALCING, IS_CALCULATED
  FROM AR_PERIOD
 ORDER BY PERIOD_NUM;
CALL CALC_BE_PE(${PERIOD_NUM:?}, ${CALC_MONTH:?});
SELECT PERIOD_NUM, CALC_MONTH, USER_ID, GPV_REAL, PE_RATE, BONUS_PE, IS_ACTIVE
  FROM AR_CALC_BONUS_PE
 WHERE PERIOD_NUM = ${PERIOD_NUM}
 ORDER BY USER_ID;
SQL
```

- 执行步骤：
1. 导入固定AR_PERIOD和原订单fixture
2. 发布正常订单、重复订单、首次/第二次退款和冲突事件
3. 导出normalized、三stage输入及Redis前后状态
4. 运行SQL-Python金额差分
- 精确预期：
- 同一事件三stage delta/hash一致
- 整单退款只冲销一次且归期由批准时间决定
- 所有金额列int64；差分为0或已批准标签
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| PE截断 | `GPV_REAL+GPV_UNREAL=1500.99`, `proEliteRate=15` | `TRUNCATE(1500.99*0.15,2)=225.14` | `22514 cents` | SQL两位向零截断 | 0 cents |
| 退款 | 原订单100.25 | SQL/approved contract整单反向 | `-100_250_000 units`一次 | signed units | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 全仓只有两个批准的放大调用点；生产内部无第三处 `*1_000_000` | STEP-PVAM-02-02/03/04/06/07 | TC-001、TC-002、TC-023 | EV-PVAM-02-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | JSON number/float/bool/null/指数/NaN/Infinity 全部拒绝并进入明确错误处置 | STEP-PVAM-02-02/03/07 | TC-001 | EV-PVAM-02-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 同一 normalized event 三路收到相同 int delta、version、revision 和 identity | STEP-PVAM-02-02/03/04/07 | TC-023、TC-026 | EV-PVAM-02-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | PE/SE/Elite/LB/Placement 生产金额列无 float dtype；EAB scale 不与公共 units 混用 | STEP-PVAM-02-04/06/07 | TC-002、TC-012、TC-017、TC-018、TC-021 | EV-PVAM-02-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 最终奖金不以 float 输出，外部只输出两位 Decimal string 或 integer cents | STEP-PVAM-02-06/07 | TC-008、TC-017、TC-018、TC-019、TC-021 | EV-PVAM-02-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | PeriodResolver 不接受 YYYYMM 推导；首期来自 MIN(AR_PERIOD) | STEP-PVAM-02-01/05 | TC-006 | EV-PVAM-02-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | current/previous period 缺失、多行或不连续时 fail-loud | STEP-PVAM-02-01/05 | TC-006 | EV-PVAM-02-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 退款批准时间经 GMT+8 在月界前后映射正确；到达时间不影响归期 | STEP-PVAM-02-01/03 | TC-006、TC-022 | EV-PVAM-02-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 整单退款重复和第二次冲销不产生第二个负 delta | STEP-PVAM-02-03/07 | TC-010、TC-022 | EV-PVAM-02-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | SQL-Python 边界、极值、负值、跨分区差分符合 Legacy/Corrected 标签 | STEP-PVAM-02-06/07 | TC-008、TC-012、TC-017、TC-018、TC-019、TC-021 | EV-PVAM-02-10 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | demo/图 consumer 未被冒充金额入口；真实启动/部署接线有证据 | STEP-PVAM-02-07 | TC-024、TC-030、TC-032 | EV-PVAM-02-11 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-12 | 本任务 feature flag 关闭后，不影响 TASK-01 模型/API | STEP-PVAM-02-07 | TC-031 | EV-PVAM-02-12 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 真实入口不明 | 只有demo/拓扑consumer | 新代码不可达 | WORK-08 call graph与部署manifest | 入口trace | BLOCK并回上游 |
| period字段合同缺失 | 无批准schema | 错误归期 | repository adapter+manifest | resolver查询证据 | BLOCK |
| 双写期间单位混用 | 旧/新consumer并行 | 金额放大 | event version+feature flag | 三stage hash | 停止v2写 |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-02/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止订单/退款consumer并完成in-flight drain；保存normalized event与reversal ledger；恢复旧镜像后按event_id/revision受控重放，禁止重复冲销。

统一执行顺序：

1. 停止新写并完成本任务定义的drain/freeze；
2. 导出任务相关Redis/Stream/ledger/run状态及checksum；
3. 由已签署manifest执行真实部署系统回滚，禁止仅修改当前shell环境变量；
4. 执行数据恢复/重放门禁；
5. 运行健康检查与幂等复验；
6. 保存命令、退出码、stdout/stderr和SHA-256。

缺少manifest、隔离演练或数据恢复证明时，只允许停止工作负载和保留证据，不得执行生产切换或声称“可独立回滚”。

### 11.4 不可逆部分

本任务计划不包含不可逆生产数据删除。若实施中出现清库、物理删除、无法恢复的trim或数据库DDL需求，立即停工并回上游方案审批。

## 12. 交付物与完成证据

| 编号 | 交付物/证据 | 生成步骤 | 位置/格式 | 验收人 | artifact_status |
|---|---|---|---|---|---|
| EV-PVAM-02-01 | AC-01验收证据：全仓只有两个批准的放大调用点；生产内部无第三处 `*1_000_000` | STEP-PVAM-02-02/03/04/06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-02-02 | AC-02验收证据：JSON number/float/bool/null/指数/NaN/Infinity 全部拒绝并进入明确错误处置 | STEP-PVAM-02-02/03/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-02-03 | AC-03验收证据：同一 normalized event 三路收到相同 int delta、version、revision 和 identity | STEP-PVAM-02-02/03/04/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-02-04 | AC-04验收证据：PE/SE/Elite/LB/Placement 生产金额列无 float dtype；EAB scale 不与公共 units 混用 | STEP-PVAM-02-04/06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-02-05 | AC-05验收证据：最终奖金不以 float 输出，外部只输出两位 Decimal string 或 integer cents | STEP-PVAM-02-06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-02-06 | AC-06验收证据：PeriodResolver 不接受 YYYYMM 推导；首期来自 MIN(AR_PERIOD) | STEP-PVAM-02-01/05 | evidence/WORK-PVAM-02/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-02-07 | AC-07验收证据：current/previous period 缺失、多行或不连续时 fail-loud | STEP-PVAM-02-01/05 | evidence/WORK-PVAM-02/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-02-08 | AC-08验收证据：退款批准时间经 GMT+8 在月界前后映射正确；到达时间不影响归期 | STEP-PVAM-02-01/03 | evidence/WORK-PVAM-02/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-02-09 | AC-09验收证据：整单退款重复和第二次冲销不产生第二个负 delta | STEP-PVAM-02-03/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-02-10 | AC-10验收证据：SQL-Python 边界、极值、负值、跨分区差分符合 Legacy/Corrected 标签 | STEP-PVAM-02-06/07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-02-11 | AC-11验收证据：demo/图 consumer 未被冒充金额入口；真实启动/部署接线有证据 | STEP-PVAM-02-07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-02-12 | AC-12验收证据：本任务 feature flag 关闭后，不影响 TASK-01 模型/API | STEP-PVAM-02-07 | evidence/WORK-PVAM-02/attempt-*/ac/AC-12/ | 待指派QA | PENDING |
| EV-PVAM-02-P01 | PeriodResolver与测试 | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P02 | normalized schema/normalizer/退款ledger | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P03 | 三stage入口与float清理diff | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P04 | DEV测试/mutation报告 | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-02-P05 | UAT订单退款/SQL差分证据 | 对应STEP/TC | evidence/WORK-PVAM-02/attempt-*/package/ | 待指派QA | PENDING |

> 第 12 节交付物表中的 `PENDING` 属于 `artifact_status`，只表示工件尚未生成；环境验证状态必须使用 `validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}`。

### 12.A 标准补丁与实施 commit 门禁

文档中的 `diff` 均为 `DESIGN_FRAGMENT`，不是预生成补丁。真实代码完成后必须执行受控脚本；不得手工省略 scope、worktree、tree hash 或测试绑定：

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set implementation commit}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to released 05_CONTROL}"

bash "$CONTROL_ROOT/validate_work_patch.sh" \
  --repo "$REPO_ROOT" \
  --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" \
  --work-id "WORK-PVAM-02" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-02/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-02` 批准 allowlist；
3. patch 非空，由 `git diff --full-index --binary BASE WORK_COMMIT` 生成；
4. 在干净 BASE worktree 上 `git apply --check --index` 与实际 apply 均成功；
5. apply 后 tree hash 与 `WORK_COMMIT_SHA^{tree}` 完全一致；
6. 证据记录 base、work commit、patch SHA-256、applied tree hash、changed paths、命令、退出码和日志；
7. DEV 结果必须在该 applied tree 上重跑，不能用 `HEAD==BASE_SHA` 的预检查冒充实施验证。

无代码变更的 WORK 必须提交受控 `NO_CODE_CHANGE` 裁决，不得生成空 patch 冒充通过。

## 13. 执行记录（实施后填写）

### 13.1 实际修改

| 步骤 | 实际修改文件/符号 | commit | 执行人 | 时间 | 结果 |
|---|---|---|---|---|---|
| STEP-PVAM-02-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-02-07 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-02-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-03 | DEV | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |
| TC-PVAM-02-08 | DEV | 待执行 | NOT_RUN | EV-PVAM-02-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-02-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

任何新增缺陷必须回复核报告登记新的 `R-*`；任何业务/架构歧义必须新增或重开 `DEC-*`。

## 15. 任务结论

本任务结论：`BLOCKED`

说明：本项是**执行/验证结论**，不是文档审批结论。本 v1.3 任务书治理状态为 `DRAFT`、执行状态为 `BLOCKED`；未取得组织授权和实施/DEV/UAT/rollback 证据前不得转为 `READY`。

### 15.1 签署

| 角色 | 姓名 | 结论 | 时间 | 备注 |
|---|---|---|---|---|
| 实施 | 待指派 | 待签署 | 待补充 |  |
| 代码复核 | 待指派 | 待签署 | 待补充 |  |
| 测试环境执行 | 待指派 | 待签署 | 待补充 |  |
| 最终验收 | 待指派 | 待签署 | 待补充 |  |

## 16. 版本记录

| 版本 | 日期 | 变更内容 | 变更原因/来源 | 编制人 | 批准状态 |
|---|---|---|---|---|---|
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-02` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
