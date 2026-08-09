# WORK-PVAM-07B 事件路由、正式 Handler 与 Stream 保留护栏施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-07B`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-012B`（parent=`R-012`，最终路由）、`R-013` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-07B-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-07B` |
| 施工任务名称 | 事件路由、正式 Handler 与 Stream 保留护栏 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-07B@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-012B`（parent=`R-012`，最终路由）、`R-013` |
| 复核闭环追踪号 | `REM-012B、REM-013 / W-012B、W-013 / V-012B、V-013` |
| 来源检查项 | `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003` |
| 关联决策 | `DEC-007、DEC-010` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-06、WORK-PVAM-07A DEV_VERIFIED |
| 功能开关 | `RECALC_EVENT_SCHEMA_V2 / RECALC_ACK_AWARE_TRIM` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003
  └─ R-012B（parent=R-012，最终路由）、R-013
       └─ DEC-007、DEC-010
            └─ TASK-PVAM-07B (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-07B
                      ├─ STEP-PVAM-07B-01 / STEP-PVAM-07B-02 / STEP-PVAM-07B-03 / STEP-PVAM-07B-04 / STEP-PVAM-07B-05 / STEP-PVAM-07B-06
                      ├─ TC-PVAM-07B-01 / TC-PVAM-07B-02 / TC-PVAM-07B-03 / TC-PVAM-07B-04 / TC-PVAM-07B-05 / TC-PVAM-07B-06 / TC-PVAM-07B-07 / TC-PVAM-07B-08 / TC-PVAM-07B-09
                      └─ EV-PVAM-07B-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-012B（parent=R-012，最终路由）、R-013 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-07B` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003 | CONTROLLED |
| 正式决策 | DEC-007、DEC-010 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-07B` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-06、WORK-PVAM-07A DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 建立版本化envelope、schema/handler registry和明确disposition；移除producer固定MAXLEN，采用所有已登记group安全水位与durable replay证明驱动的retention。 |
| 当前行为 | 多个producer在同一stream写payload，但事件身份缺稳定schema_version/producer/domain/subtype。；Global与Elite均可使用 `SETTLEMENT_PERIOD_DONE`，payload/后置动作不同。；consumer没有正式handler registry；旧分支print/pass。；Global/Elite/Placement producer多处 `XADD ... maxlen=100000, approximate=True`。；fixed trim可能在所有consumer group ACK前删除payload；ghost恢复源/容量证明缺失。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-07B`；检查项 `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003` |

### 3.2 已确认代码事实

- 多个producer在同一stream写payload，但事件身份缺稳定schema_version/producer/domain/subtype。
- Global与Elite均可使用 `SETTLEMENT_PERIOD_DONE`，payload/后置动作不同。
- consumer没有正式handler registry；旧分支print/pass。
- Global/Elite/Placement producer多处 `XADD ... maxlen=100000, approximate=True`。
- fixed trim可能在所有consumer group ACK前删除payload；ghost恢复源/容量证明缺失。

### 3.3 本任务目标

建立版本化envelope、schema/handler registry和明确disposition；移除producer固定MAXLEN，采用所有已登记group安全水位与durable replay证明驱动的retention。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

retention阈值未签署时仅阻断实际trim，不阻断schema/registry/publisher/handler与dry-run实现；初始无批准no-op。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | Global producer | `GlobalRecalculationService` outbox xadd | payload JSON | 固定maxlen100000 | 可能提前trim |
| 2 | Elite producer | `GlobalEliteBonusRecalculationService._emit_settlement_done` | 同名done | 固定maxlen100000 | 同名异构 |
| 3 | Placement producer | Placement两服务 outbox | PLACEMENT_* | 固定maxlen100000 | 无统一envelope |
| 4 | consumer | `RecalcStreamConsumer._dispatch_business` | event_type | print/pass | 无handler/postcondition |
| 5 | reclaim | XAUTOCLAIM | PEL/ghost | 无durable replay合同 | 无法恢复 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| RecalcStreamConsumer | schema/registry/handler | 改为registry驱动 | 是 | STEP-07B-03/TC-027 |
| 所有outbox producer | 统一publisher/envelope | 修改 | 是 | STEP-07B-02 |
| consumer groups | ACK水位 | 纳入retention registry | 运维 | STEP-07B-04/TC-028 |
| durable event/settlement manifest | ghost replay | 读取恢复 | 接口 | STEP-07B-05 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `MessageConsumer/RecalcEventSchema.py` 定义v2 envelope和严格decoder；新增 `RecalcHandlerRegistry.py`/`RecalcDisposition.py`。
- 新增 `Settlement/RecalcEventPublisher.py`，所有producer通过该符号发布；event id/hash幂等。
- 建议唯一变体为 domain+event_type+subtype，例如 GLOBAL/RECALC_DONE、ELITE/BATCH_READY、PLACEMENT/RECALC_DONE；旧done由兼容decoder仅在字段足够时映射，否则DLQ/KEEP_PEL。
- 新增 `Ops/RecalcStreamRetention.py`，读取登记group的last-delivered/PEL/ACK safe watermark，只有durable replay可用且不存在未决消息时执行 `XTRIM MINID`。
- trim前后生成manifest：group水位、PEL、范围、checksum、replay availability、operator/time。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 固定MAXLEN调大 | 仍无ACK安全证明 | R-013 |
| 按event_type猜同名变体 | 可能执行错误handler | R-012 |
| unknown audited noop | 没有批准编号 | CHK-EVT-006 |
| ghost直接ACK | 永久丢事件 | CHK-EVT-007 |
| producer各自拼payload | 继续schema漂移 | TASK-07B |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + RECALC_EVENT_SCHEMA_V2 / RECALC_ACK_AWARE_TRIM | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | 新schema/registry/disposition文件 |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `MessageConsumer/RecalcEventSchema.py` | v2 envelope/decoder | 新增 | 不存在 | 严格schema/discriminator/hash | 唯一可识别 | 不得猜路由 |
| CHG-02 | `MessageConsumer/RecalcHandlerRegistry.py` / `MessageConsumer/RecalcDisposition.py` | registry/disposition | 新增 | 不存在 | schema→handler→postcondition→disposition | 无pass默认 | 不得自动noop |
| CHG-03 | `Settlement/RecalcEventPublisher.py` | publisher | 新增 | producer各自xadd | 统一envelope/event_id/hash；不设fixed maxlen | 可双写迁移 | 不得早trim |
| CHG-04 | Global/Elite/Placement producer文件 | xadd调用 | 修改 | 直接xadd fixed maxlen | 改用publisher | 统一事件 | 不得改变业务提交原子边界 |
| CHG-05 | `MessageConsumer/RecalcStreamConsumer.py` | decoder/dispatch | 修改 | event_type if/pass | registry驱动并校验postcondition | ACK条件明确 | 不得绕过07A结果 |
| CHG-06 | `Ops/RecalcStreamRetention.py` | 安全水位/trim/replay | 新增 | 不存在 | ACK-aware MINID与manifest | 慢group安全 | 不得使用MAXLEN |
| CHG-07 | `MessageConsumer/Test/test_recalc_event_v2.py` / `MessageConsumer/Test/test_stream_retention.py` | pytest | 新增 | 不存在 | 同名消歧、兼容、>100k、多group/ghost | 可验证 | 不得依赖单group假设 |

### 6.1 固定基线锚点复验

固定`maxlen=100000, approximate=True`至少存在于：

- `GlobalRecalculationService._save_recalc_pipeline`；
- `GlobalRecalculationService._emit_settlement_done`；
- `GlobalEliteBonusRecalculationService._emit_settlement_done`；
- `PlacementRecalculationService`的事件/完成写入；
- `PlacementIncrementalService._save_placement_pipeline`。

实际施工以全仓AST/grep结果为准，必须清零所有生产XADD固定裁剪点，不能只改列表示例。

### 6.2 v2路由键与兼容边界

路由主键固定为`(schema_version, producer_domain, event_type, event_subtype)`；同名`SETTLEMENT_PERIOD_DONE`不能只凭可选字段猜测。v1 decoder只接受能够唯一映射的旧事件；无法唯一判别的旧事件必须DLQ或保PEL。

初始registry不得登记任何`LEGAL_NOOP_AUDITED`；以后只有携带正式批准编号的事件才能添加。没有handler的事件维持07A的fail-closed结果。

### 6.3 Publisher与Retention

> **模式示意，非逐字可应用补丁。** 基线六处 XADD 的变量名、缩进与 payload 参数不同；实施时必须依据 §6.1 的固定提交逐处生成真实 diff，并以 AST/grep 证明所有生产固定 MAXLEN 已清零。

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
- pipe.xadd(name=OUTBOX_STREAM_KEY, fields=fields,
-           maxlen=100000, approximate=True)
+ pipe.xadd(name=OUTBOX_STREAM_KEY, fields=fields)
```

统一publisher附加event_id、idempotency_key、payload_hash和schema信息。独立retention job计算所有登记group的安全水位、PEL、最小保留窗和重放证明；默认`--dry-run`。容量模型/安全水位未签署时，只禁止实际XTRIM，不阻断schema、registry、publisher、handler和dry-run代码开发。

Ghost/deleted-ID不得ACK：先查权威event registry/outbox ledger恢复payload；无法恢复则写IN_DOUBT证据并阻断相关stage关闭。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-07B-01：定义v2 envelope/registry

- 目的：定义v2 envelope/registry，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：WORK-06/07A完成
- 修改文件：新schema/registry/disposition文件
- 目标符号：数据与handler合同
- 精确操作：
1. 定义必填字段、变体键、schema validator、handler postcondition与audited noop批准字段。
- 必须保持：不实现业务DBwriter
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcEventSchema.py MessageConsumer/RecalcHandlerRegistry.py MessageConsumer/RecalcDisposition.py`
- 本步单元验证：`TC-PVAM-07B-01/02`
- 完成证据：`EV-PVAM-07B-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一事件无唯一变体则BLOCK

### STEP-PVAM-07B-02：统一publisher并迁移producer

- 目的：统一publisher并迁移producer，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-01
- 修改文件：`Settlement/RecalcEventPublisher.py`及四类producer
- 目标符号：publish/xadd
- 精确操作：
1. 生成event_id/hash
2. 支持短期dual-publish/dual-read
3. 移除fixed maxlen。
- 必须保持：保持Redis权威事务边界
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`grep -R "maxlen=100000" -n --include="*.py" User MessageConsumer Settlement`
- 本步单元验证：`TC-PVAM-07B-03/04`
- 完成证据：`EV-PVAM-07B-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：仍有生产fixed trim不合并

### STEP-PVAM-07B-03：接正式handler与兼容decoder

- 目的：接正式handler与兼容decoder，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-01/WORK-07A
- 修改文件：`RecalcStreamConsumer.py`
- 目标符号：process/dispatch
- 精确操作：
1. decoder→registry→handler→postcondition→disposition→07A ACK
2. 旧同名无法消歧不猜。
- 必须保持：unknown保持PEL或DLQ
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcStreamConsumer.py`
- 本步单元验证：`TC-PVAM-07B-01/02/05`
- 完成证据：`EV-PVAM-07B-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：pass/默认成功残留不合并

### STEP-PVAM-07B-04：实现ACK-aware retention

- 目的：实现ACK-aware retention，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-02
- 修改文件：`Ops/RecalcStreamRetention.py`
- 目标符号：plan/execute trim
- 精确操作：
1. 枚举登记group，计算最小安全ID，检查PEL/DLQ/replay，dry-run后MINID trim并manifest。
- 必须保持：不得MAXLEN/删除未ACK
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Ops/RecalcStreamRetention.py`
- 本步单元验证：`TC-PVAM-07B-06/07`
- 完成证据：`EV-PVAM-07B-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何group状态不可读时不trim

### STEP-PVAM-07B-05：实现ghost恢复

- 目的：实现ghost恢复，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-03/04/WORK-06
- 修改文件：consumer/retention
- 目标符号：recover
- 精确操作：
1. 从event registry/settlement manifest重建entry或IN_DOUBT
2. 保持event_id幂等。
- 必须保持：不得直接ACK
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q MessageConsumer Settlement Ops`
- 本步单元验证：`TC-PVAM-07B-08`
- 完成证据：`EV-PVAM-07B-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无durable source则IN_DOUBT

### STEP-PVAM-07B-06：容量/兼容/故障测试

- 目的：容量/兼容/故障测试，落实 `TASK-PVAM-07B` 的已批准目标。
- 前置条件：STEP-07B-01~05
- 修改文件：新增测试与UAT脚本
- 目标符号：pytest/UAT
- 精确操作：
1. 发布100001+消息、多group、慢handler、重启、DLQ失败、dual-read/publish。
- 必须保持：不得只测单消费者
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q MessageConsumer/Test/test_recalc_event_v2.py MessageConsumer/Test/test_stream_retention.py`
- 本步单元验证：`TC-PVAM-07B-01~09`
- 完成证据：`EV-PVAM-07B-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何不可恢复丢失不得发布

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Stream payload | 无统一schema/同名异构 | v2 envelope | 统一publisher | schema/event_id/hash | v1兼容decoder |
| Stream保留 | MAXLEN~100000 | ACK-aware MINID | retention job | trim manifest | 无证明不trim |

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
| TC-PVAM-07B-01 | 契约 | v2变体唯一 | Global/Elite/Placement完成事件 | 各自映射唯一schema+handler | STEP-07B-01/03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-02 | 兼容 | 旧同名done | 字段充分/不足两类 | 充分时确定映射；不足时DLQ/KEEP_PEL，不猜 | STEP-07B-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-03 | 幂等 | dual publish/read | 同event_id v1/v2 | handler只执行一次 | STEP-07B-02/03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-04 | 静态 | 固定maxlen清除 | 全仓AST/grep | 生产xadd无maxlen=100000 | STEP-07B-02 | DEV | NOT_RUN |
| TC-PVAM-07B-05 | handler | postcondition失败 | handler返回但proof缺失 | KEEP_PEL/RETRY，不ACK | STEP-07B-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-06 | 容量 | 100001消息+慢group | fast已ACK、slow未ACK | trim点不越slow安全水位；所有payload存在 | STEP-07B-04/06 | UAT | NOT_RUN |
| TC-PVAM-07B-07 | 多group | 三group不同PEL | group状态fixture | 取最小安全水位；任一异常不trim | STEP-07B-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-07B-08 | 恢复 | ghost/deleted ID | durable源有/无 | 有则同event_id恢复；无则IN_DOUBT | STEP-07B-05 | UAT | NOT_RUN |
| TC-PVAM-07B-09 | 重启 | consumer kill/reclaim | handler中途kill | 重启后幂等完成，无丢/重 | STEP-07B-06 | UAT | NOT_RUN |

受控检查方案用例映射：`TC-023, TC-025, TC-026, TC-027, TC-028, TC-029, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-07B}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-07B"

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
  --work-id "WORK-PVAM-07B" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-07B.sh" \
  --out "evidence/WORK-PVAM-07B/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
from MessageConsumer.RecalcEventSchema import decode_recalc_event


def test_event_variant_and_retention_contract(retention_planner) -> None:
    global_event = decode_recalc_event({"schema_version": 2, "domain": "GLOBAL", "event_type": "RECALC_DONE", "subtype": "USER_STATS", "event_id": "e1", "payload": {}})
    elite_event = decode_recalc_event({"schema_version": 2, "domain": "ELITE", "event_type": "BATCH_READY", "subtype": "ELITE_BONUS", "event_id": "e2", "payload": {}})
    assert global_event.variant_key != elite_event.variant_key
    plan = retention_planner.plan(group_safe_ids={"fast": "200-0", "slow": "100-0"}, unresolved_pel_ids=["101-0"])
    assert plan.apply_allowed is False
    assert plan.safe_before_id <= "100-0"
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-07B-01：事件v2/handler/100001/trim/ghost

- 对应受控测试：`TC-023、TC-025、TC-026、TC-027、TC-028、TC-032`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：Redis容量隔离；至少2个consumer groups；durable registry/manifest fixture
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work07b-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-07B --run-id "$RUN_ID" --tc TC-023,TC-025,TC-026,TC-027,TC-028,TC-032
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
# N/A：本任务验证 Redis Stream schema/handler/retention，不执行 SQL。
```

- 执行步骤：
1. dual-publish v1/v2并执行handler
2. 制造100001条backlog和多group进度差
3. 执行retention dry-run/commit
4. 删除待处理entry并测试恢复
5. kill/restart consumer
- 精确预期：
- 未ACK不被trim
- 同event_id不重复执行
- ghost可恢复或IN_DOUBT
- manifest完整且无fixed MAXLEN
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| N/A | 事件/Stream治理 | N/A | N/A | Redis事件合同 | N/A |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 所有生产事件变体在 registry 中唯一映射 schema、handler、disposition | STEP-PVAM-07B-01/03/06 | TC-027 | EV-PVAM-07B-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | Global/Elite/Placement 完成事件可无歧义区分并执行不同 handler | STEP-PVAM-07B-01/03/06 | TC-027、TC-029 | EV-PVAM-07B-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | handler 后置条件不满足时不 ACK；audited no-op 必须有批准编号与审计记录 | STEP-PVAM-07B-01/03/06 | TC-027 | EV-PVAM-07B-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 所有 producer 不再使用固定 `maxlen=100000` | STEP-PVAM-07B-02/06 | TC-028、TC-031 | EV-PVAM-07B-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 多 group 慢消费者场景，未 ACK 消息不被 trim | STEP-PVAM-07B-04/06 | TC-028 | EV-PVAM-07B-05 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 超过100000消息、长 PEL、DLQ失败、consumer重启均不丢 payload | STEP-PVAM-07B-04/05/06 | TC-027、TC-028 | EV-PVAM-07B-06 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | ghost entry 通过 registry/manifest 恢复或进入 IN_DOUBT，不直接 ACK | STEP-PVAM-07B-05/06 | TC-028 | EV-PVAM-07B-07 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | trim job 生成 group 水位、PEL、范围、checksum 和恢复可用性证明 | STEP-PVAM-07B-04/06 | TC-028、TC-032 | EV-PVAM-07B-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 旧 `SETTLEMENT_PERIOD_DONE` 兼容 decoder 无法消歧时进入 DLQ/重试，不猜测路由 | STEP-PVAM-07B-03/06 | TC-027 | EV-PVAM-07B-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | v2 producer/consumer 切换、dual-read/短期 dual-publish 和回滚保持 event_id 幂等 | STEP-PVAM-07B-02/03/06 | TC-023、TC-025、TC-026、TC-032 | EV-PVAM-07B-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| backlog占内存 | 移除fixed trim | Redis压力 | 容量模型/背压/运维告警 | memory/XLEN/lag | 停producer或扩容，不假trim |
| dual-publish双处理 | compat窗口 | 重复副作用 | event_id幂等 | handler ledger | 关闭v2写回滚 |
| group漏登记 | trim越过未知消费者 | 事件丢失 | group registry+deny trim | XINFO GROUPS diff | BLOCK trim |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-07B/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止 producer/consumer；导出 XLEN/XPENDING/group 水位。默认回滚必须保持 producer 无固定 MAXLEN，仅关闭 v2 schema/handler 与 retention job。任何恢复 fixed MAXLEN 的动作都不得由 XLEN 或 ghost 当前值单独授权，只能进入 §11.3A 的运维/架构双签紧急例外门禁；未完整满足六类容量、速率、告警、停止阈值、未 ACK 保护和再升级条件时禁止执行。

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


#### 11.3A 固定 MAXLEN 紧急例外门禁

默认回滚**禁止**恢复已知不安全的 `maxlen=100000`。兼容回退应保持 producer 无固定 MAXLEN，只关闭 v2 schema/handler 与 retention job。

只有运维负责人和架构负责人共同签署紧急例外时，才可临时恢复固定 MAXLEN；签署的 rollback manifest 必须同时给出：

1. 最长临时窗口和强制再升级时间；
2. 期间最大写入速率、容量上界与计算依据；
3. `XLEN`、所有 group 的 `XPENDING`、consumer lag、ghost/`IN_DOUBT` 实时告警；
4. 自动停止写入/回滚的阈值和精确执行命令；
5. 未 ACK 消息保护与完整重放证明；
6. 当班责任人、批准人及监控证据 URI/SHA。

缺任一项，或运行期间任一阈值越界，必须保持无固定 MAXLEN 的 producer 版本，不得执行代码 revert。

## 12. 交付物与完成证据

| 编号 | 交付物/证据 | 生成步骤 | 位置/格式 | 验收人 | artifact_status |
|---|---|---|---|---|---|
| EV-PVAM-07B-01 | AC-01验收证据：所有生产事件变体在 registry 中唯一映射 schema、handler、disposition | STEP-PVAM-07B-01/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-07B-02 | AC-02验收证据：Global/Elite/Placement 完成事件可无歧义区分并执行不同 handler | STEP-PVAM-07B-01/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-07B-03 | AC-03验收证据：handler 后置条件不满足时不 ACK；audited no-op 必须有批准编号与审计记录 | STEP-PVAM-07B-01/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-07B-04 | AC-04验收证据：所有 producer 不再使用固定 `maxlen=100000` | STEP-PVAM-07B-02/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-07B-05 | AC-05验收证据：多 group 慢消费者场景，未 ACK 消息不被 trim | STEP-PVAM-07B-04/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-07B-06 | AC-06验收证据：超过100000消息、长 PEL、DLQ失败、consumer重启均不丢 payload | STEP-PVAM-07B-04/05/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-07B-07 | AC-07验收证据：ghost entry 通过 registry/manifest 恢复或进入 IN_DOUBT，不直接 ACK | STEP-PVAM-07B-05/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-07B-08 | AC-08验收证据：trim job 生成 group 水位、PEL、范围、checksum 和恢复可用性证明 | STEP-PVAM-07B-04/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-07B-09 | AC-09验收证据：旧 `SETTLEMENT_PERIOD_DONE` 兼容 decoder 无法消歧时进入 DLQ/重试，不猜测路由 | STEP-PVAM-07B-03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-07B-10 | AC-10验收证据：v2 producer/consumer 切换、dual-read/短期 dual-publish 和回滚保持 event_id 幂等 | STEP-PVAM-07B-02/03/06 | evidence/WORK-PVAM-07B/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-07B-P01 | v2 schema/registry/disposition源码 | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P02 | 统一publisher与producer diff | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P03 | ACK-aware retention/ghost recovery | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P04 | DEV兼容测试 | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07B-P05 | UAT多group/100001/restart证据 | 对应STEP/TC | evidence/WORK-PVAM-07B/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-07B" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-07B/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-07B` 批准 allowlist；
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
| STEP-PVAM-07B-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07B-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-07B-01 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-04 | DEV | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-06 | UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-08 | UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |
| TC-PVAM-07B-09 | UAT | 待执行 | NOT_RUN | EV-PVAM-07B-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-07B-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-07B` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
