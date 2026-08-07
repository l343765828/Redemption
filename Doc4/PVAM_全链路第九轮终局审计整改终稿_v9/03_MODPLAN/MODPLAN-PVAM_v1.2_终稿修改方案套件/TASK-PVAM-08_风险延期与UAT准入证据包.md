# TASK-PVAM-08 风险、延期事项与 UAT 验证环境准入包

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-08` |
| 来源检查项 | `CHK-ARCH-001、CHK-DATA-006、CHK-DATA-007、CHK-BIZ-002、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011、CHK-EVT-003～007、CHK-PUB-001、CHK-PUB-002、CHK-TEST-001～004` |
| 来源问题 | `RISK-001、RISK-002、UV-001～UV-005、OPT-001、OPT-002、GAP-DEC004-2B` |
| 处置项 | `RISK/UV；OPT-001、OPT-002` |
| 施工项 | `UAT/证据施工项` |
| 验证项 | `UAT-001～UAT-012` |
| 派生缺口 | `GAP-DEC004-2B / DEFERRED` |
| 关联决策 | `DEC-004、DEC-009、DEC-010、DEC-012、DEC-013、DEC-017、DEC-018` |
| 严重级别 | `P0 / P1` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | 阶段A无；阶段B依赖 TASK-PVAM-01～06、07A、07B |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。


### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

### 2.1 风险

- RISK-001：当前没有固定 source archive、部署 manifest 和可复核 call graph，无法独立确认 `TopologyMutationService` 是否生产可达。二轮审查提到全仓引用可能仅在测试，但在未取得完整归档前不能升级为已确认缺陷。
- RISK-002：候选报告声明的命令、环境和测试没有随附原始 stdout/stderr、exit code、镜像和 XML，不能继承为 PASS。

### 2.2 无法验证

- UV-001：没有真实 MySQL/Redis/Kafka/Dask/RAPIDS/GPU 全链路环境。
- UV-002：DEC-009 最小 schema manifest、DDL、SQL_MODE、assignment 缺失。
- UV-003：无法用同一数据库/数据集做 SQL-Python 差分。
- UV-004：无法运行并发、ACK、PEL、trim、崩溃恢复和 checksum 故障注入。
- UV-005：缺精确整仓调用图、全套测试输出及完整 P0/T0 原始审计包。

## 3. 本任务修改目标

1. 对所有风险/UV 使用受控状态，不把材料缺口误写成代码缺陷或测试通过。
2. 建立 UAT 环境准入清单、证据目录、执行矩阵和回传格式。
3. 关闭 DEC-013 后，按 UAT-001～012 逐项验证 TASK-01～06、TASK-07A、TASK-07B。
4. 为 RISK-001 建立证据触发机制：固定证据决定 T06 `TOPO-WIRE-01` 执行分支，不再临时新增任务。
5. 形成可机器校验的 CHK/TC/R/REM/W/V/TASK/AC→命令→证据→结论链。
6. 承接 OPT-001/002，并管理 `GAP-DEC004-2B` 的受控延期和 fixture 边界。

## 4. 处置决定与方案选择

### 4.1 当前处置状态

| 编号 | 状态 | 子状态 |
|---|---|---|
| RISK-001 | `UAT_VERIFY` | `BLOCKED_EXTERNAL_EVIDENCE` |
| RISK-002 | `UAT_VERIFY` | `PENDING_RERUN_EVIDENCE` |
| UV-001 | `UAT_VERIFY` | `PENDING_TEST_ENV` |
| UV-002 | `UAT_VERIFY` | `BLOCKED_EXTERNAL_EVIDENCE` |
| UV-003 | `UAT_VERIFY` | `PENDING_TEST_ENV` |
| UV-004 | `UAT_VERIFY` | `PENDING_TEST_ENV` |
| UV-005 | `UAT_VERIFY` | `BLOCKED_EXTERNAL_EVIDENCE` |

当前没有针对 R/RISK/UV 的 `REJECTED`、`DEFERRED` 或 `NEEDS_DECISION`。DEC-013 仍 OPEN，作为环境执行门禁。

其他登记：

| 编号 | 状态 | 归属/说明 |
|---|---|---|
| OPT-001 | `ACCEPTED` | 本任务统一 pytest/unittest 收集、CLI smoke、exit/XML 证据 |
| OPT-002 | `ACCEPTED` | 本任务生成机器可读双向追踪 manifest |
| FIX-001 | `N/A — CONFIRMED_CLOSED` | DEC-017 文档 overlay 已核验，不计当前缺陷和施工 |
| GAP-DEC004-2B | `DEFERRED` | 本轮不建设 AR_CONFIG→Delta→Redis 写入/失效链；fixture 不得关闭生产 Gate |

### 4.2 被否决方案

- 根据候选报告文字直接继承测试通过；缺原始证据。
- 根据不完整搜索直接把 RISK-001 升为第14项缺陷；违反证据纪律。
- 因开发环境无法运行就永久延期；应通过 UAT 回传包闭环。
- 只上传截图；截图不能替代命令、exit code、原始输出和数据 checksum。
- 在共享生产环境直接故障注入；必须隔离 UAT。

## 5. 修改范围与受影响模块

本任务主要交付治理/测试资产，不直接修改业务算法：

- `evidence/manifest.schema.json`
- `uat/environment_manifest.yaml`
- `uat/schema_manifest.yaml`
- `uat/config_snapshot_manifest.yaml`
- `uat/test_run_manifest.yaml`
- `uat/callgraph_manifest.json`
- `uat/scripts/`：环境探测、静态扫描、测试编排、故障注入、checksum、SQL-Python diff。
- CI/流水线证据归档配置。
- `TopologyMutationService` 的固定归档、部署/调用图和运行验证，并触发 T06 `TOPO-WIRE-01`。
- pytest/unittest 收集 wrapper、CLI smoke 兼容层、JUnit/XML/coverage/mutation 归档。
- `traceability_manifest.json`：CHK/TC/R/REM/W/V/TASK/AC/命令/证据双向关系。
- DEC-004 2B fixture 注入登记与后续生产施工入口。
- TASK-01～06、TASK-07A、TASK-07B 的 UAT 执行与总验证报告输入。

## 6. 明确排除项（防越界红线）

- 不在未验证前把 RISK 升为确认错误。
- 不代拟 DEC-013 权限、主机和批准人；由环境/DBA/运维提供。
- 不更改业务代码来“让测试通过”；失败应回到所属 TASK 修复。
- 不对生产数据做破坏性清库/故障注入。
- 不把二轮审查 G2-01～G2-04重复登记为代码任务；v1.3 已修正报告。
- 不把 DEC-017 文档修复当作 CHK-BIZ-001 行为通过。

## 7. 前置条件与依赖关系

### 阶段 A：准入

可立即执行，不依赖其他 TASK。必须取得：

1. 固定 commit source archive 与 SHA-256；
2. 容器/conda/pip 镜像和依赖版本；
3. 隔离 MySQL、Redis、Kafka、Dask/RAPIDS/GPU；
4. DBA批准最小 schema manifest、SQL_MODE、DDL和assignment；
5. config、AR_PERIOD、测试数据和脱敏策略；
6. 故障注入及清理权限；
7. 业务系统发布 receiver/模拟器；
8. DEC-013 责任人批准；
9. monthActivePV Redis/Delta fixture 的来源、注入人、版本、有效期和 checksum；明确该 fixture 不等于生产 2B 链。

### 阶段 B：UAT

依赖 TASK-01～06、07A、07B 达到对应 DEV AC；按依赖顺序执行，不允许用后续任务掩盖前置失败。

## 8. 修改后行为与技术设计

### 8.1 环境 manifest

至少记录：

```text
repository / commit / archive_sha256
container_image_digest
python/requirements/conda
mysql/mariadb version + global/session SQL_MODE
redis version/topology/config
kafka broker/client/topics/groups
Dask/Distributed/RAPIDS/cuDF/CUDA/GPU
timezone/locale
schema/config/data snapshot ids + checksums
network/permissions/isolation
```

### 8.2 证据目录

```text
evidence/
  TASK-PVAM-xx/
    UAT-nnn/
      00_manifest.yaml
      01_command.txt
      02_stdout.log
      03_stderr.log
      04_exit_code.txt
      05_input_checksums.json
      06_before_state/
      07_after_state/
      08_diff/
      09_metrics/
      10_conclusion.md
```

原始文件不可覆盖；重跑使用新的 `attempt_id`。

### 8.3 UAT 执行矩阵与受控 TC 映射

| UAT | 主要 TASK/问题 | 对应 TC | 核心验证 |
|---|---|---|---|
| UAT-001 | 01/02；R-001～003 | TC-001、TC-002、TC-003、TC-008 | version、units、非法类型、无float、极值 |
| UAT-002 | 03；R-004 | TC-004、TC-005、TC-013、TC-018 | 配置矩阵、ppm、Country、SE exact raw、TB oracle |
| UAT-003 | 04；R-005/006 | TC-007、TC-017、TC-018、TC-019、TC-021 | Active同源现算及各奖金语义 |
| UAT-004 | 02；R-007/退款归期 | TC-006、TC-022 | AR_PERIOD、批准时间、整单冲销/冲突 |
| UAT-005 | 02/04/06；RISK-001 | TC-009、TC-010、TC-011、TC-012、TC-013、TC-024 | 传播、图、Placement、TB、Topology接线与guard |
| UAT-006 | 05；R-008/011 | TC-014、TC-015、TC-016、TC-026、TC-029 | Elite gate、SOURCE、原子批次、空快照/发布 proof |
| UAT-007 | 02/04；R-003/006 | TC-008、TC-017、TC-018、TC-019、TC-020、TC-021 | PE/SE/EAB/Honor/LB 精度、Active、截断 |
| UAT-008 | 06；R-009/010 | TC-023、TC-024、TC-026、TC-029 | revision、统一guard、epoch、提交边界、发布分层 |
| UAT-009 | 06/07B | TC-025、TC-026、TC-028 | coverage、旧epoch replay、恢复、retention |
| UAT-010 | 05/07A/07B；R-008/012/013 | TC-027、TC-028、TC-026 | outbox、schema、ACK、PEL、DLQ、trim、ghost恢复 |
| UAT-011 | 01/02/05/06；UV-002 | TC-008、TC-019、TC-029、TC-032 | DDL、SQL_MODE、assignment、writer proof、全链回传 |
| UAT-012 | 全部；RISK-002/UV-005 | TC-030、TC-031、TC-032 | 调用图、读取入口、pytest收集、mutation、完整审计包 |

`TC-000` 随 `CHK-GOV-001` 保留为 `RETIRED`，不执行、不计入完成率。上述矩阵覆盖 TC-001～TC-032；每个 TC 的最终状态仍按检查方案独立登记，不能因被某个 UAT 覆盖而合并省略。

### 8.4 RISK-001 证据触发与 T06 固定归属

T08 负责取得固定 archive、部署 manifest、consumer/cron/人工入口、call graph 和 UAT trace；T06 已预先拥有 `TOPO-WIRE-01`，因此不再临时立项。

- 证据证明无生产调用点：RISK-001 升级为确认实现缺口，由 T06 在本轮实施生产接线。
- 证据证明已有调用点：由 T06 核验该入口是否真正经过 TopologyMutationService 或等价事务编排，并补齐 period/version/guard/rollback。
- 证据仍不完整：RISK-001 保持 `BLOCKED_EXTERNAL_EVIDENCE`，T06 条件工作项不得宣称完成。

无论哪一分支，测试脚本、孤立 import 或直接 `graph_actor.run_update` 都不能作为 DEC-012 的生产接线通过证据。

### 8.5 `GAP-DEC004-2B` 延期与 fixture 纪律

- 当前版本明确不建设 AR_CONFIG→Delta→Redis 写入、变更删除/重载 producer。
- UAT fixture 由 DBA/环境方受控注入，必须有来源、注入脚本、操作者、时间、版本、有效期和 checksum。
- getter/Active 测试通过只能关闭消费侧 AC；真实同步链未实施时 CHK-DATA-006/TC-007 的供给侧保持 `BLOCKED`/`PENDING_TEST_ENV`。
- 后续生产施工必须建立独立受控工作项并继承 DEC-004/016，不得以本套件的 fixture 作为完成证据。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | DEC-013 有正式环境/权限批准记录 | UAT | TC-032 |
| AC-02 | source archive、commit、image、schema、config、data 均有 checksum | DEV+UAT | TC-030、TC-031、TC-032 |
| AC-03 | DEC-009 最小 manifest 覆盖生产可达输入、Redis状态、事件/outbox和有效SQL对象 | UAT | TC-008、TC-019、TC-029、TC-032 |
| AC-04 | 全局/会话 SQL_MODE 和数据库 assignment 有原始证据 | UAT | TC-008、TC-019、TC-029 |
| AC-05 | RISK-001 有可复核 call graph、部署入口和运行结果；证据触发 T06 `TOPO-WIRE-01` 分支 | DEV+UAT | TC-011、TC-024、TC-030、TC-032 |
| AC-06 | 候选报告测试在固定镜像重跑，保留 stdout/stderr/exit/XML | DEV+UAT | TC-031、TC-032 |
| AC-07 | UAT-001～012 每项均有 manifest、输入、命令、前后状态、diff 和结论 | UAT | TC-001～TC-032 |
| AC-08 | 失败能追踪到所属 TASK/AC/TC，不被总体统计吞掉 | DEV+UAT | TC-031、TC-032 |
| AC-09 | SQL-Python 差分明确标注 Legacy parity/corrected approved | UAT | TC-008～TC-021 |
| AC-10 | 故障注入在隔离环境执行，恢复 checksum 与干净重跑一致 | UAT | TC-022～TC-029 |
| AC-11 | P0/T0、CHK、TC、R/RISK/UV、REM/W/V、TASK、AC、证据形成机器可读双向追踪 | DEV | TC-031、TC-032 |
| AC-12 | 没有仅凭截图、口头结论或二手报告关闭问题 | DEV+UAT | TC-032 |
| AC-13 | OPT-001：脚本测试具有 pytest/unittest 可收集入口并保留 CLI smoke，exit code/报告统一 | DEV | TC-031 |
| AC-14 | `GAP-DEC004-2B` 的 fixture 来源、注入人、checksum、有效期明确，且生产实现状态仍登记 DEFERRED/BLOCKED | UAT | TC-007、TC-032 |

## 10. 环境验证与回传证据

本节即本任务核心交付。每次运行必须回传：

- 环境 manifest；
- 精确命令与工作目录；
- 开始/结束时间 GMT+8；
- exit code；
- 完整 stdout/stderr；
- 输入文件/表/Redis/消息 checksum；
- DB/Redis/Kafka/PEL/DLQ/日志前后快照；
- SQL/Python diff；
- 失败注入点与恢复时间线；
- 结论及审批人。

验证状态只能为：`PASS、FAIL、BLOCKED、PENDING_TEST_ENV`。不能用 `APPROVED` 代替测试结果。

## 11. 独立回滚与风险控制

1. 本任务不直接改生产业务数据，主要回滚 CI/脚本/manifest 配置。
2. 所有 UAT 使用隔离 namespace、topic、consumer group、Redis DB/key prefix 和数据库 schema。
3. 运行前自动备份/快照，运行后校验清理；任何污染立即停止后续 UAT。
4. 证据不可删除或覆盖；错误证据标记 superseded，但保留原件。
5. 外部材料缺失时，环境验证保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`；尚未生成的工件使用 `artifact_status=PENDING`，不得使用无域限定的裸 `PENDING`。
