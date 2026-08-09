# WORK-PVAM-05 Elite SOURCE 原子性与外部发布证明施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-05`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-008、R-011` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-05-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-05` |
| 施工任务名称 | Elite SOURCE 原子性与外部发布证明 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-05@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-008、R-011` |
| 复核闭环追踪号 | `REM-008、REM-011 / W-008、W-011 / V-008、V-011` |
| 来源检查项 | `CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001` |
| 关联决策 | `DEC-007、DEC-008、DEC-011、DEC-017` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、02、03 DEV_VERIFIED |
| 功能开关 | `ELITE_ATOMIC_LEDGER_V2` |

### 1.1 一对一追溯摘要

```text
CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001
  └─ R-008、R-011
       └─ DEC-007、DEC-008、DEC-011、DEC-017
            └─ TASK-PVAM-05 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-05
                      ├─ STEP-PVAM-05-01 / STEP-PVAM-05-02 / STEP-PVAM-05-03 / STEP-PVAM-05-04 / STEP-PVAM-05-05 / STEP-PVAM-05-06
                      ├─ TC-PVAM-05-01 / TC-PVAM-05-02 / TC-PVAM-05-03 / TC-PVAM-05-04 / TC-PVAM-05-05 / TC-PVAM-05-06 / TC-PVAM-05-07 / TC-PVAM-05-08
                      └─ EV-PVAM-05-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-008、R-011 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-05` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001 | CONTROLLED |
| 正式决策 | DEC-007、DEC-008、DEC-011、DEC-017 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-05` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、02、03 DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 把 Elite stats、source assignment、revision/dirty、idempotency与outbox写入同一Redis权威提交；全量只在通过八项candidate gate后产生带checksum的ELITE_BONUS_BATCH_READY，等待外部receipt。 |
| 当前行为 | `EliteBonusService._track_bonus_source` 直接执行独立 `HSET` 与 `EXPIRE`。；`EliteBonusService.update_elite_bonus_incremental` 最后才通过 `_batch_save` 保存 stats；source 与 stats 不在同一权威提交。；`GlobalEliteBonusRecalculationService` 可在未提供 `db_executor` 时完成Redis重算并发 persisted=false 哨兵；正式candidate gate、PV_PSS、version、coverage及external receipt证明不完整。；DEC-008 已把关系库写入职责转给业务系统，本仓只能发布可验证的 batch/manifest，不能声称跨Redis/DB原子。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-05`；检查项 `CHK-BIZ-005、CHK-BIZ-006、CHK-EVT-005、CHK-PUB-001` |

### 3.2 已确认代码事实

- `EliteBonusService._track_bonus_source` 直接执行独立 `HSET` 与 `EXPIRE`。
- `EliteBonusService.update_elite_bonus_incremental` 最后才通过 `_batch_save` 保存 stats；source 与 stats 不在同一权威提交。
- `GlobalEliteBonusRecalculationService` 可在未提供 `db_executor` 时完成Redis重算并发 persisted=false 哨兵；正式candidate gate、PV_PSS、version、coverage及external receipt证明不完整。
- DEC-008 已把关系库写入职责转给业务系统，本仓只能发布可验证的 batch/manifest，不能声称跨Redis/DB原子。

### 3.3 本任务目标

把 Elite stats、source assignment、revision/dirty、idempotency与outbox写入同一Redis权威提交；全量只在通过八项candidate gate后产生带checksum的ELITE_BONUS_BATCH_READY，等待外部receipt。

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
| 1 | Elite增量 | `EliteBonusService.update_elite_bonus_incremental` | user_id/pv_delta | 调用_track_bonus_source后_batch_save | source可能先落 |
| 2 | SOURCE | `EliteBonusService._track_bonus_source` | source/bonus/layer | HSET+EXPIRE | 独立写 |
| 3 | stats | `EliteBonusService._batch_save` | models | Redis OM pipeline | 不含source/outbox |
| 4 | 全量 | `GlobalEliteBonusRecalculationService.settle_period` | period | 可选db_executor或persisted=false | gate/proof不足 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| Elite增量重放 | assignment ledger | 需幂等revision | 是 | STEP-05-02/TC-015/016 |
| Global Elite全量 | candidate/manifest | 需gate与空batch | 是 | STEP-05-03/04 |
| 外部业务writer | ELITE_BONUS_BATCH_READY | 本仓只发batch，不写DB | 接口 | TC-029 |
| SettlementCoordinator | receipt/state | WORK-06承接 | 后续 | TC-024/029 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Model/User/EliteSourceAssignment.py`，唯一键 `(period_num, source_user_id)`，记录chosen bonus user、minimal layer、accepted revision、event hash、status。
- 将 `_track_bonus_source` 改成纯 mutation intent，不执行Redis命令；统一由 Redis Function/Lua 或经证明的 WATCH/MULTI/EXEC 提交。
- 权威提交包含 stats JSON、assignment、revision/dirty、idempotency/stage marker、outbox；任一点失败全不成。
- 新增 `User/EliteBonusCandidateBuilder.py` 和 `User/EliteBonusPublishBatch.py`，验证 PV_PSS、version、资格/gpv_real、source-clean、run/revision/coverage/config/topology八项证明。
- 空candidate也产生显式batch，external receipt前状态只能READY_FOR_EXTERNAL_PUBLISH。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 继续独立HSET | R-008仍存在 | R-008 |
| Python直接写MariaDB | 违反DEC-008职责边界 | DEC-008 |
| estimated_bonus>0即视为资格proof | 缺PV_PSS/version/source-clean | R-011 |
| 空结果不发batch | 外部无法清旧期 | CHK-PUB-001 |
| 声称Redis+DB原子 | 跨存储虚假保证 | DEC-008 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + ELITE_ATOMIC_LEDGER_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | 新增三个模型/模块 |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Model/User/EliteSourceAssignment.py` | assignment模型/序列化 | 新增 | 不存在 | 定义唯一归属与revision状态 | 可重放审计 | 不得直接当正式DB行 |
| CHG-02 | `User/EliteBonusService.py` | `_track_bonus_source`、`update_elite_bonus_incremental`、`_batch_save` | 修改 | source独立HSET | 生成intent并统一权威提交 | 全成或全不成 | 不得吞WatchError |
| CHG-03 | `User/EliteRedisCommit.py` | `commit_incremental_stage` | 新增 | 不存在 | 封装Function/Lua或WATCH事务 | 单一提交API | 不得调用MariaDB |
| CHG-04 | `User/EliteBonusCandidateBuilder.py` | candidate gate | 新增 | 不存在 | 执行八项proof与reconciliation | 不合格阻断 | 不得用金额代替资格 |
| CHG-05 | `User/EliteBonusPublishBatch.py` | batch/manifest模型 | 新增 | 不存在 | 生成nonempty/empty batch、counts/checksum | external可校验 | 不得标persisted=true |
| CHG-06 | `User/GlobalEliteBonusRecalculationService.py` | `settle_period`、`_process_parent_batch`、`_emit_settlement_done` | 修改 | 重算后DONE/可选db_executor | 构建candidate/batch并发ready事件 | 等待WORK-06 receipt | 不得生产调用db_executor |
| CHG-07 | `User/EliteBonusService.py::snapshot_period_to_db` | 旧接口隔离 | 修改 | 本仓可调用DB executor | 标legacy/test-only并从生产调用图移除 | 职责边界清晰 | 不得删除历史测试入口 |
| CHG-08 | `User/Test/test_elite_atomic_commit.py` / `User/Test/test_elite_publish_batch.py` | pytest | 新增 | 不存在 | 命令点故障、revision、空batch、gate | 可重复验证 | 不得用mock证明跨存储原子 |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `EliteBonusService._track_bonus_source` | 独立`hget/hset/expire`，立即写Redis | 改为生成assignment命令，不在函数内提交 |
| `EliteBonusService._batch_save` | 单独pipeline保存stats | 扩展为唯一原子提交入口 |
| `GlobalEliteBonusRecalculationService._track_bonus_source` | 全量路径可在传入pipeline中写SOURCE | 与增量共享统一assignment/序列化合同 |
| `snapshot_period_to_db`/`db_executor` | 当前代码宣称本仓可写关系库 | 生产路径隔离；本仓输出batch/manifest，业务系统回receipt |

### 6.2 原子实现选择

本终稿固化使用`WATCH/MULTI/EXEC`，而不是直接用Lua重写redis-om JSON。理由是基线已使用`model.save(pipeline=pipe)`，该路径能保持redis-om序列化兼容；SOURCE最小layer读取、幂等marker和冲突检查放在WATCH阶段，stats JSON、SOURCE HSET/EXPIRE、revision、dirty、stage marker和outbox在同一MULTI内排队。发生`WatchError`必须整单重读并有限重试，禁止只补写SOURCE或只补写stats。

伪代码合同：

```python
for attempt in range(max_retries):
    with redis_conn.pipeline(transaction=True) as pipe:
        try:
            pipe.watch(*watched_keys)
            current = load_and_validate_under_watch(pipe)
            commands = build_complete_commit(current, event)
            pipe.multi()
            for model in commands.models:
                model.save(pipeline=pipe)
            queue_source_assignment(pipe, commands.assignment)
            queue_revision_dirty_stage(pipe, commands)
            queue_outbox(pipe, commands.outbox_event)
            pipe.execute()
            break
        except WatchError:
            if attempt + 1 == max_retries:
                raise
```

### 6.3 Candidate与receipt门禁

- Candidate必须独立证明PV_PSS、七条Elite gate、version=2、source-clean、revision/dirty、row/key/amount/checksum。
- 缺PV_PSS权威来源时状态为`BLOCKED_CANDIDATE_PROOF`；不得以`gpv_real>0`近似。
- 空candidate也生成batch，明确表达清空该period旧结果。
- 本仓只发`BATCH_READY`及manifest；业务系统返回签名/可校验receipt后，WORK-06才能转PUBLISHED。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-05-01：定义assignment与batch模型

- 目的：定义assignment与batch模型，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：WORK-01/02/03完成
- 修改文件：新增三个模型/模块
- 目标符号：数据合同
- 精确操作：
1. 字段含period/run/generation/source/revision/hash/layer/status/counts/checksum
2. 类型均严格。
- 必须保持：不设计业务DB表
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/User/EliteSourceAssignment.py User/EliteBonusPublishBatch.py User/EliteBonusCandidateBuilder.py`
- 本步单元验证：`TC-PVAM-05-01/02`
- 完成证据：`EV-PVAM-05-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：唯一键/字段与TASK不一致则BLOCK

### STEP-PVAM-05-02：实现Redis原子提交

- 目的：实现Redis原子提交，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-01
- 修改文件：`User/EliteRedisCommit.py`、`EliteBonusService.py`
- 目标符号：commit API/_track/_batch
- 精确操作：
1. 把source改为intent
2. 通过单一原子单元写stats/assignment/revision/dirty/idempotency/outbox。
- 必须保持：不允许先source后stats
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/EliteRedisCommit.py User/EliteBonusService.py`
- 本步单元验证：`TC-PVAM-05-03/04`
- 完成证据：`EV-PVAM-05-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一故障产生半状态立即停工

### STEP-PVAM-05-03：实现candidate八项gate

- 目的：实现candidate八项gate，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-01/WORK-01~04接口
- 修改文件：`User/EliteBonusCandidateBuilder.py`
- 目标符号：build/validate
- 精确操作：
1. 逐条校验PV_PSS、version、资格、gpv_real、source-clean、run/revision/coverage/config/topology
2. 生成reconciliation。
- 必须保持：不得只看bonus>0
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/EliteBonusCandidateBuilder.py`
- 本步单元验证：`TC-PVAM-05-05/06`
- 完成证据：`EV-PVAM-05-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：权威PV_PSS不可得则BLOCK

### STEP-PVAM-05-04：重构全量为batch-ready

- 目的：重构全量为batch-ready，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-02/03
- 修改文件：`GlobalEliteBonusRecalculationService.py`
- 目标符号：settle/emit
- 精确操作：
1. 移除生产db_executor路径
2. 构建非空/空batch，写manifest与outbox
3. 状态交WORK-06。
- 必须保持：不写PUBLISHED/DONE persisted true
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/GlobalEliteBonusRecalculationService.py`
- 本步单元验证：`TC-PVAM-05-06/07`
- 完成证据：`EV-PVAM-05-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无batch却标完成立即回滚

### STEP-PVAM-05-05：隔离旧writer并补扫描

- 目的：隔离旧writer并补扫描，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-04
- 修改文件：`EliteBonusService.py`与调用图测试
- 目标符号：snapshot接口
- 精确操作：
1. 保留测试兼容但加显式legacy/test-only标记
2. 生产入口扫描不得调用。
- 必须保持：不删除历史对账能力
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`grep -R "snapshot_period_to_db" -n --include="*.py" .`
- 本步单元验证：`TC-PVAM-05-08`
- 完成证据：`EV-PVAM-05-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：发现生产调用则BLOCK

### STEP-PVAM-05-06：故障/重放/空批测试

- 目的：故障/重放/空批测试，落实 `TASK-PVAM-05` 的已批准目标。
- 前置条件：STEP-05-02~05
- 修改文件：新增测试
- 目标符号：pytest
- 精确操作：
1. 在每个Redis命令点注错
2. 重复revision、hash冲突、退款、reassign、empty candidate。
- 必须保持：测试不得跳过
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_elite_atomic_commit.py User/Test/test_elite_publish_batch.py`
- 本步单元验证：`TC-PVAM-05-01~08`
- 完成证据：`EV-PVAM-05-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：mutation存活或半状态不得合并

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Elite source hash | 独立HSET | revisioned assignment ledger | Redis权威提交 | event/revision/hash | 冲突阻断 |
| Elite发布 | 可选DB writer/DONE | batch+manifest+external receipt | 全量收尾 | batch/run/generation | receipt前不PUBLISHED |

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
| TC-PVAM-05-01 | 契约 | assignment唯一键 | 同period/source两候选layer3/1 | 最终仅layer1，revision/hash可审计 | STEP-05-01 | DEV | NOT_RUN |
| TC-PVAM-05-02 | 契约 | batch checksum | 固定bonus/source行集 | 排序无关checksum稳定，counts精确 | STEP-05-01 | DEV | NOT_RUN |
| TC-PVAM-05-03 | 故障注入 | stats后source前失败 | 任一Redis命令异常 | stats/source/revision/outbox均无新状态 | STEP-05-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-04 | 幂等 | 同event/revision重放 | 相同hash重复/不同hash | 相同no-op；不同hash fail-loud | STEP-05-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-05 | gate | PV_PSS=0或version缺失 | 有estimated bonus脏值 | candidate阻断且产生明确proof failure | STEP-05-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-06 | SOURCE重归属 | 旧upline→新upline | 同source仅最新accepted归属；总SOURCE_PV不双计 | STEP-05-03/04 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-07 | 空快照 | 本期无候选，外部旧行存在fixture | 产生empty batch，外部模拟器清旧行 | STEP-05-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-05-08 | 静态 | DB writer边界 | 全仓调用图 | 生产无db_executor/snapshot_period_to_db调用；事件persisted=false | STEP-05-05 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-009, TC-010, TC-014, TC-015, TC-016, TC-023, TC-025, TC-026, TC-029, TC-030, TC-031`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-05}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-05"

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
  --work-id "WORK-PVAM-05" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-05.sh" \
  --out "evidence/WORK-PVAM-05/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from User.EliteRedisCommit import EliteRedisCommit


def test_elite_authority_commit_is_atomic(fake_redis, elite_commit_payload) -> None:
    commit = EliteRedisCommit(fake_redis)
    before = fake_redis.snapshot()
    fake_redis.inject_failure(command_index=3)
    with pytest.raises(RuntimeError):
        commit.commit_incremental_stage(elite_commit_payload)
    assert fake_redis.snapshot() == before
    fake_redis.clear_failure()
    commit.commit_incremental_stage(elite_commit_payload)
    once = fake_redis.snapshot()
    commit.commit_incremental_stage(elite_commit_payload)
    assert fake_redis.snapshot() == once
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-05-01：Elite原子/重放/candidate/空批

- 对应受控测试：`TC-014、TC-015、TC-016、TC-026、TC-029`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：Redis隔离；图与PV_PSS fixture；外部writer模拟器非生产
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work05-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-05 --run-id "$RUN_ID" --tc TC-014,TC-015,TC-016,TC-026,TC-029
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
test "${UAT_SCHEMA_ISOLATED:?must equal 1}" = "1"
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
CALL CALC_BE_E(${PERIOD_NUM:?}, ${CALC_MONTH:?});
SELECT PERIOD_NUM, CALC_MONTH, USER_ID, GPV_REAL, E_RATE, BONUS_E
  FROM AR_CALC_BONUS_E
 WHERE PERIOD_NUM = ${PERIOD_NUM}
 ORDER BY USER_ID;
SELECT PERIOD_NUM, CALC_MONTH, BONUS_USER_ID, SOURCE_USER_ID, SOURCE_PV, BONUS_LAYER
  FROM AR_CALC_BONUS_E_SOURCE
 WHERE PERIOD_NUM = ${PERIOD_NUM}
 ORDER BY SOURCE_USER_ID, BONUS_LAYER;
SQL
```

- 执行步骤：
1. 构造七条Elite gate正反例
2. 注入Redis提交点故障与重复revision
3. 执行重归属/退款/空candidate
4. 运行外部writer模拟器并回传receipt fixture
- 精确预期：
- 无半提交/双计
- candidate缺任一proof即阻断
- receipt前不PUBLISHED；empty batch可清旧
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| Elite候选 | PV_PSS=0, PV_PCS=1000 | CALC_BE_E不插入NET | candidate=0 | PV_PSS gate | 0 rows |
| Elite奖金 | GPV_REAL=1000.99, rate=15% | TRUNCATE=150.14 | 15014 cents | 向零两位 | 0 cents |
| SOURCE | 同source多个layer | ROW_NUMBER order BONUS_LAYER取最小 | assignment minimal layer | source唯一 | 0 rows |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | `_track_bonus_source` 不再直接执行 HSET/EXPIRE | STEP-PVAM-05-02/06 | TC-026、TC-031 | EV-PVAM-05-01 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 任一 Redis 命令点故障时 stats/SOURCE/revision/outbox 全成或全不成 | STEP-PVAM-05-02/06 | TC-026 | EV-PVAM-05-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 重复 normalized event/revision 幂等，冲突 hash fail-loud | STEP-PVAM-05-02/06 | TC-015、TC-016、TC-023、TC-026 | EV-PVAM-05-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 每个 source 最多一个正式 assignment，minimal layer 可复核 | STEP-PVAM-05-01/02/06 | TC-015、TC-016 | EV-PVAM-05-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | candidate 缺 PV_PSS/version/run/revision/coverage 任一字段时阻断 | STEP-PVAM-05-03/06 | TC-014、TC-029 | EV-PVAM-05-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 奖金和 SOURCE counts/checksum 与 manifest 一致 | STEP-PVAM-05-03/04/06 | TC-015、TC-016、TC-029 | EV-PVAM-05-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | 空快照生成显式 batch，模拟器可清空旧正式结果 | STEP-PVAM-05-04/06 | TC-029 | EV-PVAM-05-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 生产代码不调用 MariaDB db_executor；旧接口隔离并有扫描证明 | STEP-PVAM-05-05/06 | TC-029、TC-030 | EV-PVAM-05-08 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | receipt 不存在时只到 `READY_FOR_EXTERNAL_PUBLISH`，不标 PUBLISHED | STEP-PVAM-05-04/06 | TC-029 | EV-PVAM-05-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | DEC-011 数量变化/输出变化传播测试保持通过 | STEP-PVAM-05-03/06 | TC-009、TC-010 | EV-PVAM-05-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | 同一 run/generation 重跑幂等；新 generation 新 batch，不覆盖旧审计 | STEP-PVAM-05-01/02/03/04/06 | TC-015、TC-016、TC-025、TC-029 | EV-PVAM-05-11 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| Redis OM序列化与Lua不兼容 | 脚本直写格式偏差 | reader失败 | 先做序列化golden test；可选WATCH方案 | roundtrip证据 | BLOCK并选经批准方案 |
| PV_PSS来源缺失 | candidate gate无权威输入 | 错误发奖 | 硬阻断 | proof failure | BLOCK |
| external receipt伪造 | 事件被当已落库 | 假发布 | WORK-06验证签名/checksum | receipt审计 | IN_DOUBT |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-05/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：冻结Elite写入口；保留revisioned ledger、SOURCE与outbox；若发布批次已产生则进入IN_DOUBT并按receipt决定重放或废弃，不直接删除证据。

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
| EV-PVAM-05-01 | AC-01验收证据：`_track_bonus_source` 不再直接执行 HSET/EXPIRE | STEP-PVAM-05-02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-05-02 | AC-02验收证据：任一 Redis 命令点故障时 stats/SOURCE/revision/outbox 全成或全不成 | STEP-PVAM-05-02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-05-03 | AC-03验收证据：重复 normalized event/revision 幂等，冲突 hash fail-loud | STEP-PVAM-05-02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-05-04 | AC-04验收证据：每个 source 最多一个正式 assignment，minimal layer 可复核 | STEP-PVAM-05-01/02/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-05-05 | AC-05验收证据：candidate 缺 PV_PSS/version/run/revision/coverage 任一字段时阻断 | STEP-PVAM-05-03/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-05-06 | AC-06验收证据：奖金和 SOURCE counts/checksum 与 manifest 一致 | STEP-PVAM-05-03/04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-05-07 | AC-07验收证据：空快照生成显式 batch，模拟器可清空旧正式结果 | STEP-PVAM-05-04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-05-08 | AC-08验收证据：生产代码不调用 MariaDB db_executor；旧接口隔离并有扫描证明 | STEP-PVAM-05-05/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-05-09 | AC-09验收证据：receipt 不存在时只到 `READY_FOR_EXTERNAL_PUBLISH`，不标 PUBLISHED | STEP-PVAM-05-04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-05-10 | AC-10验收证据：DEC-011 数量变化/输出变化传播测试保持通过 | STEP-PVAM-05-03/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-05-11 | AC-11验收证据：同一 run/generation 重跑幂等；新 generation 新 batch，不覆盖旧审计 | STEP-PVAM-05-01/02/03/04/06 | evidence/WORK-PVAM-05/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-05-P01 | Elite assignment/commit/candidate/batch模块 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P02 | Elite增量/全量diff | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P03 | DB writer隔离调用图 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P04 | DEV故障/重放测试 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-05-P05 | UAT Elite SQL/source/empty batch证据 | 对应STEP/TC | evidence/WORK-PVAM-05/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-05" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-05/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-05` 批准 allowlist；
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
| STEP-PVAM-05-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-05-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-05-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |
| TC-PVAM-05-08 | DEV | 待执行 | NOT_RUN | EV-PVAM-05-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-05-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-05` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
