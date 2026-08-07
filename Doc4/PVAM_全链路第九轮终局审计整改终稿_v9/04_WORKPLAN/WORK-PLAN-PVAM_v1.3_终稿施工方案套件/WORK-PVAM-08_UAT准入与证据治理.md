# WORK-PVAM-08 风险、UAT 准入与机器可读证据包施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-08`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 本任务不修改业务计算代码；RISK/UV 仅生成验证、证据与阻断动作，OPT-001/002 仅生成已批准的测试/治理工具。
3. 基线必须精确等于 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；发现漂移立即登记 `BLOCK-PVAM-08-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-08` |
| 施工任务名称 | 风险、UAT 准入与机器可读证据包 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-08@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B` |
| 复核闭环追踪号 | RISK/UV/OPT 无预登记 REM/W/V；`UV-002 → UAT-011`；由 AC-11 生成机器可读追踪 manifest |
| 来源检查项 | `CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004` |
| 关联决策 | `DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018` |
| 代码基线 | `l343765828/Redemption@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| SQL基线 | `sql_uat/*@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | 阶段A可与所有DEV任务并行；阶段B依赖DEC-013及WORK-01～07B DEV_VERIFIED |
| 功能开关 | `N/A（治理/验证任务）` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004
  └─ RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B
       └─ DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018
            └─ TASK-PVAM-08 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-08
                      ├─ STEP-PVAM-08-01 / STEP-PVAM-08-02 / STEP-PVAM-08-03 / STEP-PVAM-08-04 / STEP-PVAM-08-05 / STEP-PVAM-08-06 / STEP-PVAM-08-07
                      ├─ TC-PVAM-08-01 / TC-PVAM-08-02 / TC-PVAM-08-03 / TC-PVAM-08-04 / TC-PVAM-08-05 / TC-PVAM-08-06 / TC-PVAM-08-07 / TC-PVAM-08-08 / TC-PVAM-08-09
                      └─ EV-PVAM-08-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B 的事实、状态与边界 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-08` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004 | CONTROLLED |
| 正式决策 | DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，工作树无未登记变更。
- [ ] `TASK-PVAM-08` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：阶段A可与所有DEV任务并行；阶段B依赖DEC-013及WORK-01～07B DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 不修改奖金业务代码，建立环境/数据/schema/config/callgraph/执行/证据manifest、可复制UAT脚本和机器追踪链；在 DEC-013 未关闭或外部材料缺失时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`；未生成工件使用 `artifact_status=PENDING`，不伪造 PASS。 |
| 当前行为 | 真实Kafka/Redis/Dask/RAPIDS/MySQL全链路、SQL-Python同数据差分、ACK/PEL/trim/崩溃恢复均未在当前开发环境完成。；DEC-009最小schema manifest、SQL_MODE、assignment对象与批准记录尚需外部提供。；TopologyMutationService生产可达性缺完整archive/部署证明。；候选测试缺原始stdout/stderr/exit/JUnit与固定镜像重跑包。；现有部分测试为脚本/demo，需要pytest可收集包装和机器可读追踪manifest。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 / P1 / 优化 |
| 证据位置 | 固定代码基线 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；来源 `TASK-PVAM-08`；检查项 `CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004` |

### 3.2 已确认代码事实

- 真实Kafka/Redis/Dask/RAPIDS/MySQL全链路、SQL-Python同数据差分、ACK/PEL/trim/崩溃恢复均未在当前开发环境完成。
- DEC-009最小schema manifest、SQL_MODE、assignment对象与批准记录尚需外部提供。
- TopologyMutationService生产可达性缺完整archive/部署证明。
- 候选测试缺原始stdout/stderr/exit/JUnit与固定镜像重跑包。
- 现有部分测试为脚本/demo，需要pytest可收集包装和机器可读追踪manifest。

### 3.3 本任务目标

不修改奖金业务代码，建立环境/数据/schema/config/callgraph/执行/证据manifest、可复制UAT脚本和机器追踪链；在 DEC-013 未关闭或外部材料缺失时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`；未生成工件使用 `artifact_status=PENDING`，不伪造 PASS。

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
| 1 | DEV测试 | 现有test与脚本 | 本地依赖 | 部分可运行 | 不能证明真实中间件 |
| 2 | UAT环境 | 外部测试环境 | 未获准入 | 不可执行 | UV-001等 |
| 3 | Schema | DBA最小manifest | 待提供 | 检查项BLOCKED | UV-002 |
| 4 | Topology | 源码/测试 | 只有代码与测试证据 | 生产可达未知 | RISK-001 |
| 5 | 证据 | 二手报告 | 缺原始包 | 不可复验 | RISK-002 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| 所有WORK任务 | DEV/UAT执行器与证据目录 | 提供统一脚本/manifest | 是 | STEP-08-01~05 |
| 技术复核 | traceability_manifest | 双向追踪 | 是 | TC-031/032 |
| DBA/架构 | schema manifest | 批准与哈希 | 外部 | TC-008/019/029 |
| WORK-06 | Topology callgraph | 触发TOPO-WIRE-01核验现有接线/实施缺失接线分支 | 是 | TC-011/024/030 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `evidence/manifest.schema.json` 和按 `WORK/attempt` 不可覆盖目录；每次执行记录commit/image/config/schema/data/command/exit/time/checksum。
- 新增 `uat/environment_manifest.yaml`、`schema_manifest.yaml`、`config_snapshot_manifest.yaml`、`test_run_manifest.yaml`、`callgraph_manifest.json`。
- 新增 `uat/scripts/check_baseline.sh`、`run_work_dev.sh`、`run_work_uat.sh`、`run_sql_python_diff.py`、`redis_stream_probe.py`、`build_callgraph.py`、`build_traceability_manifest.py`、`verify_evidence_pack.py`。
- 新增 `traceability_manifest.json`，覆盖 CHK→R/RISK/UV→DEC→TASK→WORK→STEP→controlled TC/local TC→EV。
- OPT-001：把脚本测试包成pytest/unittest可收集入口，保留CLI smoke但不计正式通过。
- GAP-DEC004-2B保持DEFERRED；fixture manifest必须明确其不能关闭生产供给链。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 无证据标PASS | 违反Loop闭环 | CHK-TEST-004 |
| 截图代替原始日志 | 不可重放 | 证据规范 |
| 缺schema时推定 | DEC-009要求BLOCK | DEC-009 |
| 基于RISK-001新建生产接线 | UAT_VERIFY不授权代码 | 施工铁律 |
| 把DEC-010测试豁免写成Gate C关闭 | 生产条件仍OPEN | DEC-010 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + N/A（治理/验证任务） | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `evidence/manifest.schema.json`、目录规范 |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `evidence/manifest.schema.json` | 证据schema | 新增 | 不存在 | 定义不可变attempt元数据 | 统一证据格式 | 不得覆盖旧attempt |
| CHG-02 | `uat/*.yaml/json` | 环境/schema/config/run/callgraph manifest | 新增 | 不存在 | 模板与校验规则 | 外部材料可审计 | 不得写密钥 |
| CHG-03 | `uat/scripts/check_baseline.sh` / `uat/scripts/run_work_dev.sh` / `uat/scripts/run_work_uat.sh` / `uat/scripts/stop_workload.sh` | 执行器 | 新增 | 不存在 | 固定commit、命令、日志、exit、checksum | 可复制运行 | 不得伪造结果 |
| CHG-04 | `uat/scripts/run_sql_python_diff.py` | 差分器 | 新增 | 不存在 | 保存输入/SQL中间/Python中间/字段diff | Legacy/Corrected分列 | 不得只输出总PASS |
| CHG-05 | `uat/scripts/redis_stream_probe.py` | Stream证据工具 | 新增 | 不存在 | XLEN/XINFO/XPENDING/XRANGE/trim/replay采集 | ACK证据完整 | 不得执行危险trim默认 |
| CHG-06 | `uat/scripts/build_callgraph.py` | 调用图工具 | 新增 | 不存在 | AST/import/entry/deploy引用清单 | Topology与所有P0可达性 | 不得把测试当生产 |
| CHG-07 | `traceability_manifest.json` / `uat/scripts/build_traceability_manifest.py` | 追踪 | 新增 | 不存在 | 机器双向链与完整性校验 | 无孤儿编号 | 不得把TC-000计完成 |
| CHG-08 | 现有脚本测试包装器 | pytest entry | 新增/修改测试 | print/CLI为主 | 可收集且有assert/exit/JUnit | OPT-001落地 | 不得改生产算法 |

### 6.1 本任务代码边界

本任务只能新增测试、证据、manifest、callgraph和执行包装器，不得修改奖金公式、金额转换、业务状态或生产handler。所有RISK/UV保持验证状态；材料缺失不自动升级成代码缺陷。

### 6.2 可复制命令参数规范

所有脚本必须使用强制环境变量，禁止尖括号占位：

```bash
: "${REPO_ROOT:?set REPO_ROOT}"
: "${RUN_ID:?set RUN_ID}"
: "${REDIS_HOST:?set REDIS_HOST}"
: "${REDIS_PORT:?set REDIS_PORT}"
: "${REDIS_DB:?set REDIS_DB}"
: "${UAT_PERIOD:?set UAT_PERIOD}"

git -C "$REPO_ROOT" rev-parse HEAD
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" INFO server
```

环境manifest必须分别记录Python redis客户端版本和Redis Server版本，不能互相推断。

### 6.3 Wave 0最小交付

在其他WORK引用`uat/scripts/*`前，08A先交付并DEV验证：

- `check_baseline.sh`：commit、工作树、有效文件过滤、SQL blob；
- `run_work_dev.sh`：原生命令包装，保留exit/stdout/stderr/JUnit；
- `build_callgraph.py`：输出入口、import、启动/部署证据及`CALLGRAPH_CONFIDENCE`；
- `build_traceability_manifest.py`：验证CHK→R→DEC→TASK→WORK→STEP→TC→EV无孤儿；
- `verify_evidence_pack.py`：schema、hash、时间戳、环境与命令完整性。

脚手架只能记录事实，不能生成PASS结论。所有实际执行状态初始为NOT_RUN。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-08-01：建立证据schema与目录

- 目的：建立证据schema与目录，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：无
- 修改文件：`evidence/manifest.schema.json`、目录规范
- 目标符号：schema
- 精确操作：
1. 定义attempt id、hash、环境、命令、exit、stdout/stderr、输入/输出、状态
2. 脚本创建只增不改目录。
- 必须保持：不记录密钥/完整敏感数据
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m json.tool evidence/manifest.schema.json`
- 本步单元验证：`TC-PVAM-08-01`
- 完成证据：`EV-PVAM-08-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：schema 无法区分 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV` 与 `artifact_status=PENDING` 时停工

### STEP-PVAM-08-02：建立环境与外部材料manifest

- 目的：建立环境与外部材料manifest，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01
- 修改文件：`uat/*.yaml/json`
- 目标符号：manifest
- 精确操作：
1. 列明DEC-009/013批准、版本、SQL_MODE、对象hash、fixture来源/有效期。
- 必须保持：缺失必须BLOCKED
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python uat/scripts/verify_evidence_pack.py --schema-only`
- 本步单元验证：`TC-PVAM-08-02`
- 完成证据：`EV-PVAM-08-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：不得填推测值

### STEP-PVAM-08-03：实现DEV/UAT执行器

- 目的：实现DEV/UAT执行器，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01/02
- 修改文件：`uat/scripts/check_baseline.sh`、`run_work_*.sh`、`stop_workload.sh`
- 目标符号：shell
- 精确操作：
1. 严格 `set -euo pipefail`，校验commit，tee stdout/stderr，保存exit与sha256
2. 支持dry-run。
- 必须保持：不得内置密码/地址
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`bash -n uat/scripts/*.sh`
- 本步单元验证：`TC-PVAM-08-03`
- 完成证据：`EV-PVAM-08-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：基线不符立即退出

### STEP-PVAM-08-04：实现SQL差分与Stream探针

- 目的：实现SQL差分与Stream探针，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01/02
- 修改文件：两个Python脚本
- 目标符号：CLI
- 精确操作：
1. 参数化输入/连接从环境读取
2. 默认只读/dry-run
3. 输出机器JSON和原始查询。
- 必须保持：不得默认清表/trim
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile uat/scripts/run_sql_python_diff.py uat/scripts/redis_stream_probe.py`
- 本步单元验证：`TC-PVAM-08-04/05`
- 完成证据：`EV-PVAM-08-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法隔离时BLOCK

### STEP-PVAM-08-05：实现调用图与追踪manifest

- 目的：实现调用图与追踪manifest，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01
- 修改文件：callgraph/trace builder
- 目标符号：CLI
- 精确操作：
1. 过滤_bak/_final/demo
2. 区分production/test/demo
3. 校验每个AC有STEP/TC/EV。
- 必须保持：不得把grep命中直接当生产可达
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile uat/scripts/build_callgraph.py uat/scripts/build_traceability_manifest.py`
- 本步单元验证：`TC-PVAM-08-06/07`
- 完成证据：`EV-PVAM-08-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：存在孤儿P0链不得签署

### STEP-PVAM-08-06：包装现有脚本测试

- 目的：包装现有脚本测试，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-03
- 修改文件：测试wrapper
- 目标符号：pytest
- 精确操作：
1. 为具名脚本建立可收集assert/exit
2. CLI smoke保留但标SMOKE。
- 必须保持：不复制生产公式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest --collect-only -q`
- 本步单元验证：`TC-PVAM-08-08`
- 完成证据：`EV-PVAM-08-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：收集0或只print不得验收

### STEP-PVAM-08-07：执行准入检查与生成UAT包

- 目的：执行准入检查与生成UAT包，落实 `TASK-PVAM-08` 的已批准目标。
- 前置条件：STEP-08-01~06
- 修改文件：所有manifest/scripts
- 目标符号：验证
- 精确操作：
1. 阶段 A 生成 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV` 与 `artifact_status=PENDING` 分域矩阵
2. DEC-013关闭后阶段B逐WORK运行并校验包。
- 必须保持：不把未运行标PASS
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python uat/scripts/verify_evidence_pack.py --root evidence`
- 本步单元验证：`TC-PVAM-08-01~09`
- 完成证据：`EV-PVAM-08-07`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一必需材料缺失保持BLOCKED

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| 证据与测试记录 | 散落/二手 | 不可变manifest包 | 执行脚本 | attempt_id/checksum | 缺失保持BLOCKED |

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
| TC-PVAM-08-01 | schema | 证据状态枚举 | validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED} | schema全部接受且要求reason/links | STEP-08-01 | DEV | NOT_RUN |
| TC-PVAM-08-02 | 治理 | 缺schema/DEC批准 | 空manifest | 受影响TC自动标BLOCKED，不推定 | STEP-08-02 | DEV | NOT_RUN |
| TC-PVAM-08-03 | CLI | 基线不匹配 | 工作树HEAD非2475c6c4 | 脚本退出非0且未执行测试 | STEP-08-03 | DEV | NOT_RUN |
| TC-PVAM-08-04 | 差分 | 固定PE样例 | SQL/Python同输入 | 输出字段级0差异和原始中间文件 | STEP-08-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-08-05 | 安全 | Stream probe默认 | 无`--apply-trim` | 只读，无XTRIM | STEP-08-04 | DEV | NOT_RUN |
| TC-PVAM-08-06 | 调用图 | Topology符号 | 源码测试引用+部署archive | 分类production/test/demo；不把测试升级为production | STEP-08-05 | DEV+UAT | NOT_RUN |
| TC-PVAM-08-07 | 追踪 | 全套编号 | 当前WORK套件 | 无孤儿R/AC/STEP/TC/EV；TC-000 retired | STEP-08-05 | DEV | NOT_RUN |
| TC-PVAM-08-08 | 测试收集 | pytest collect | 具名脚本包装 | 收集数>0且每用例有assert | STEP-08-06 | DEV | NOT_RUN |
| TC-PVAM-08-09 | 证据不可变 | 同attempt重复写 | 已有目录 | 拒绝覆盖，创建新attempt id | STEP-08-07 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-001～TC-032` 全量；`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-08}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
: "${WORK_STAGE:?set A or B for WORK-PVAM-08}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-08"

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
  --work-id "WORK-PVAM-08" \
  --stage "$WORK_STAGE" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-08.sh" \
  --out "evidence/WORK-PVAM-08/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import json
from pathlib import Path


def test_evidence_and_traceability_contract(tmp_path: Path, evidence_validator, trace_builder) -> None:
    manifest = {"validation_status": "BLOCKED", "reason": "DEC-013 not approved", "command": ["pytest", "-q"], "exit_code": None}
    evidence_validator.validate(manifest)
    out = tmp_path / "traceability.json"
    trace_builder.build(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["retired_tests"] == ["TC-000"]
    assert data["orphan_required_nodes"] == []
```

通过标准：工作树、index、untracked和rename四类生产目录门禁均为0且输出为空；所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-08-01：完整UAT准入与回传

- 对应受控测试：`TC-001～TC-032（TC-000 RETIRED）`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：DEC-013批准；固定镜像；DEC-009 manifest；专用数据/权限
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=full-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work ALL --run-id "$RUN_ID" --tc TC-001..TC-032
python uat/scripts/verify_evidence_pack.py --root "evidence/$RUN_ID"
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<'SQL'
SELECT VERSION() AS db_version, @@GLOBAL.sql_mode AS global_sql_mode, @@SESSION.sql_mode AS session_sql_mode;
SHOW CREATE TABLE AR_PERIOD;
SHOW CREATE TABLE AR_CONFIG;
SHOW CREATE TABLE AR_CALC_BONUS_E;
SHOW CREATE TABLE AR_CALC_BONUS_E_SOURCE;
SQL
```

- 执行步骤：
1. 校验commit/image/schema/config/data checksum
2. 按总方案Wave执行各ENV-TC
3. 保存stdout/stderr/exit/JUnit/DB/Redis/Kafka/Dask证据
4. 构建traceability manifest和P0/T0状态矩阵
- 精确预期：
- 每个TC有明确validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}
- 所有P0/P1证据可重放
- DEC-010豁免与Gate C OPEN分开登记
- 无截图/二手报告单独关闭问题
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| PE golden | 1500.99*15% | 225.14 | 22514 cents | 字段级diff | 0 |
| TB golden | A total 1000/600, rate10%, pool24 | TOUCH_BASE=60, TB_RATE=.4, BONUS=24.00 | 2400 cents | SQL中间+最终 | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | DEC-013 有正式环境/权限批准记录 | STEP-PVAM-08-02/07 | TC-032 | EV-PVAM-08-01 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | source archive、commit、image、schema、config、data 均有 checksum | STEP-PVAM-08-01/02/03/07 | TC-030、TC-031、TC-032 | EV-PVAM-08-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | DEC-009 最小 manifest 覆盖生产可达输入、Redis状态、事件/outbox和有效SQL对象 | STEP-PVAM-08-02/07 | TC-008、TC-019、TC-029、TC-032 | EV-PVAM-08-03 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 全局/会话 SQL_MODE 和数据库 assignment 有原始证据 | STEP-PVAM-08-02/04/07 | TC-008、TC-019、TC-029 | EV-PVAM-08-04 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | RISK-001 有可复核 call graph、部署入口和运行结果；证据触发 T06 `TOPO-WIRE-01` 分支 | STEP-PVAM-08-05/07 | TC-011、TC-024、TC-030、TC-032 | EV-PVAM-08-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 候选报告测试在固定镜像重跑，保留 stdout/stderr/exit/XML | STEP-PVAM-08-03/06/07 | TC-031、TC-032 | EV-PVAM-08-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | UAT-001～012 每项均有 manifest、输入、命令、前后状态、diff 和结论 | STEP-PVAM-08-03/04/05/07 | TC-001～TC-032 | EV-PVAM-08-07 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 失败能追踪到所属 TASK/AC/TC，不被总体统计吞掉 | STEP-PVAM-08-01/05/07 | TC-031、TC-032 | EV-PVAM-08-08 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | SQL-Python 差分明确标注 Legacy parity/corrected approved | STEP-PVAM-08-04/07 | TC-008～TC-021 | EV-PVAM-08-09 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | 故障注入在隔离环境执行，恢复 checksum 与干净重跑一致 | STEP-PVAM-08-03/04/07 | TC-022～TC-029 | EV-PVAM-08-10 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | P0/T0、CHK、TC、R/RISK/UV、REM/W/V、TASK、AC、证据形成机器可读双向追踪 | STEP-PVAM-08-05/07 | TC-031、TC-032 | EV-PVAM-08-11 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-12 | 没有仅凭截图、口头结论或二手报告关闭问题 | STEP-PVAM-08-01/07 | TC-032 | EV-PVAM-08-12 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-13 | OPT-001：脚本测试具有 pytest/unittest 可收集入口并保留 CLI smoke，exit code/报告统一 | STEP-PVAM-08-06/07 | TC-031 | EV-PVAM-08-13 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-14 | `GAP-DEC004-2B` 的 fixture 来源、注入人、checksum、有效期明确，且生产实现状态仍登记 DEFERRED/BLOCKED | STEP-PVAM-08-02/07 | TC-007、TC-032 | EV-PVAM-08-14 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 权限不足 | DEC-013未关闭 | UAT不可执行 | 阶段A/B分离 | 批准记录 | BLOCKED |
| 外部材料不完整 | schema/image/archive缺失 | 结果不可复验 | manifest强校验 | 缺失矩阵 | BLOCKED |
| 危险脚本误操作 | trim/清表默认开启 | 数据破坏 | 默认dry-run/专用prefix | command audit | 立即停工 |
| 证据覆盖 | 重跑覆盖旧日志 | 审计丢失 | immutable attempts | hash index | 拒绝覆盖 |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-08/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：本任务默认不改生产代码；回滚仅撤销证据脚本/CI配置。执行前后必须证明生产路径工作树、index、untracked及rename均为零。

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
| EV-PVAM-08-01 | AC-01验收证据：DEC-013 有正式环境/权限批准记录 | STEP-PVAM-08-02/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-08-02 | AC-02验收证据：source archive、commit、image、schema、config、data 均有 checksum | STEP-PVAM-08-01/02/03/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-08-03 | AC-03验收证据：DEC-009 最小 manifest 覆盖生产可达输入、Redis状态、事件/outbox和有效SQL对象 | STEP-PVAM-08-02/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-08-04 | AC-04验收证据：全局/会话 SQL_MODE 和数据库 assignment 有原始证据 | STEP-PVAM-08-02/04/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-08-05 | AC-05验收证据：RISK-001 有可复核 call graph、部署入口和运行结果；证据触发 T06 `TOPO-WIRE-01` 分支 | STEP-PVAM-08-05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-08-06 | AC-06验收证据：候选报告测试在固定镜像重跑，保留 stdout/stderr/exit/XML | STEP-PVAM-08-03/06/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-08-07 | AC-07验收证据：UAT-001～012 每项均有 manifest、输入、命令、前后状态、diff 和结论 | STEP-PVAM-08-03/04/05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-08-08 | AC-08验收证据：失败能追踪到所属 TASK/AC/TC，不被总体统计吞掉 | STEP-PVAM-08-01/05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-08-09 | AC-09验收证据：SQL-Python 差分明确标注 Legacy parity/corrected approved | STEP-PVAM-08-04/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-08-10 | AC-10验收证据：故障注入在隔离环境执行，恢复 checksum 与干净重跑一致 | STEP-PVAM-08-03/04/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-08-11 | AC-11验收证据：P0/T0、CHK、TC、R/RISK/UV、REM/W/V、TASK、AC、证据形成机器可读双向追踪 | STEP-PVAM-08-05/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-08-12 | AC-12验收证据：没有仅凭截图、口头结论或二手报告关闭问题 | STEP-PVAM-08-01/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-12/ | 待指派QA | PENDING |
| EV-PVAM-08-13 | AC-13验收证据：OPT-001：脚本测试具有 pytest/unittest 可收集入口并保留 CLI smoke，exit code/报告统一 | STEP-PVAM-08-06/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-13/ | 待指派QA | PENDING |
| EV-PVAM-08-14 | AC-14验收证据：`GAP-DEC004-2B` 的 fixture 来源、注入人、checksum、有效期明确，且生产实现状态仍登记 DEFERRED/BLOCKED | STEP-PVAM-08-02/07 | evidence/WORK-PVAM-08/attempt-*/ac/AC-14/ | 待指派QA | PENDING |
| EV-PVAM-08-P01 | 证据schema与manifest模板 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P02 | DEV/UAT执行器和安全探针 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P03 | SQL-Python差分器与callgraph工具 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P04 | pytest包装/collect报告 | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-08-P05 | 完整UAT回传包与traceability manifest | 对应STEP/TC | evidence/WORK-PVAM-08/attempt-*/package/ | 待指派QA | PENDING |

> 第 12 节交付物表中的 `PENDING` 属于 `artifact_status`，只表示工件尚未生成；环境验证状态必须使用 `validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}`。

### 12.A 标准补丁与实施 commit 门禁

文档中的 `diff` 均为 `DESIGN_FRAGMENT`，不是预生成补丁。真实代码完成后必须执行受控脚本；不得手工省略 scope、worktree、tree hash 或测试绑定：

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb"
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
  --work-id "WORK-PVAM-08" \
  --stage "$WORK_STAGE" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-08/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-08` 批准 allowlist；
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
| STEP-PVAM-08-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-08-07 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-08-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-03 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-05 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-07 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-08 | DEV | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |
| TC-PVAM-08-09 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-08-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-08-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-08` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
