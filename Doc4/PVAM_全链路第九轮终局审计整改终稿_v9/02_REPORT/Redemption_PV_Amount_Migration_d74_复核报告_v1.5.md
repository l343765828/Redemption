# Redemption PV Amount Migration 复核报告 v1.5

> 本报告严格执行 `PLAN-PVAM-v1.15`，并依据 `PV_Amount_Migration_Checklist_Final_v2.25_d74.md` 的 P0/T0 权威登记册修正验收追踪矩阵。  
> 代码、SQL、治理、Skill与文档证据统一锚定 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`。历史 `097cae32` 到当前基线仅变更 `Doc/Elite_Bonus_发奖规则说明.docx`，Python/SQL无差异；R-001～R-013的代码事实经当前ref重新确认。  
> 报告没有把缺少原始日志的测试结果继承为事实，也没有把业务决议关闭写成实现通过。

## 1. 文档控制

| 项目 | 内容 |
|---|---|
| 报告名称 | `Redemption PV Amount Migration 复核报告 v1.5` |
| 报告编号 | `REPORT-PVAM-v1.5` |
| 报告版本 | `v1.5` |
| 当前状态 | `FINAL` |
| 对应检查方案 | `Redemption_PV_Amount_Migration_d74_检查方案_v1.15.md` / `PLAN-PVAM-v1.15` |
| 待审对象 | `l343765828/Redemption master@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| 基线分支 | `master` |
| 基线提交 | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`（代码、SQL、治理、Skill及当前文档证据的唯一活动基线） |
| 检查开始时间 | `2026-08-04 10:25 GMT+8` |
| 检查结束时间 | `2026-08-04 10:27 GMT+8` |
| 复核人 | `AI Agent（QA 架构与事实核验角色）` |
| 报告日期 | `2026-08-04` |

### 1.1 版本记录

| 版本 | 日期 | 修改人 | 修改内容 | 对应待审版本 |
|---|---|---|---|---|
| v1.0 | `2026-08-03` | 两份候选报告执行者 | 候选复核报告 A/B | `097cae32e0ff7708eb6ee69a7f2ce188e80c060c`（HISTORICAL_ONLY） |
| v1.1 | `2026-08-04` | AI Agent（合并复核角色） | 交叉诊断、证据降级、状态重算与终稿合并 | `097cae32e0ff7708eb6ee69a7f2ce188e80c060c`（HISTORICAL_ONLY） |
| v1.2 | `2026-08-04` | AI Agent（QA 架构与事实核验角色） | 历史版本 | 代码/SQL `097cae32`；文档overlay `2475c6c4`（HISTORICAL_ONLY） |
| v1.3 | `2026-08-04` | AI Agent（QA 架构与事实核验角色） | 历史版本 | 代码/SQL `097cae32`；文档overlay `2475c6c4`（HISTORICAL_ONLY） |
| v1.4 | `2026-08-05` | `用户会话指令 / AI Agent（全链路审计修订角色）` | 历史版本：统一基线、更正函数锚点并补齐专项追踪边 | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| v1.5 | `2026-08-05` | `AI Agent（第四轮事实与治理修订）` | 修正 compare 证据叙述；绑定 PLAN v1.15、Traceability v3；登记 F3-01～F3-10 的文档闭环边界 | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |

---

### 1.2A 基线迁移与证据继承裁决

- 活动证据ref统一为`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`。
- `097cae32e0ff7708eb6ee69a7f2ce188e80c060c`仅保留为`HISTORICAL_ONLY`版本说明。
- Git树比较确认两基线间Python/SQL无差异；唯一变化为Elite规则DOCX，因此静态缺陷事实可继承，但链接、commit元数据和DOCX证据均已改用当前ref。
- 报告治理状态为`FINAL`；报告业务结论仍为`REJECTED`，不得因文档定版而弱化13项缺陷。

### 1.2B 第四轮文档闭环边界

- 本报告是代码事实复核报告，状态 `FINAL`；代码总体结论继续为 `REJECTED`，因为 R-001～R-013 尚无实施 commit、真实 patch、DEV/UAT 证据关闭。
- 文档治理包当前状态为 `DRAFT / GATED`，没有可独立验证的组织施工授权；不得引用历史的 `APPROVED_BY_USER_INSTRUCTION` 作为施工批准。
- 八级追溯的机器事实源为 `TRACEABILITY_MANIFEST.json`；R-012 为父缺陷，R-012A/R-012B 为施工子项，不得重复计入 13 个核心缺陷。
- patch 与 DEV 证据必须绑定 `BASE_SHA + WORK_COMMIT_SHA + patch_sha256 + applied_tree_hash`，设计片段不作为实施证据。

## 2. 总结论

### 2.1 最终结论

> **`REJECTED`**

### 2.2 一句话结论

固定提交存在 13 项可静态确认的未关闭错误（P0 十二项、P1 一项），覆盖金额版本/精度、配置、Active、期间、Elite SOURCE/发布、统一守卫、事件 ACK 与 Stream 保留。依据方案“存在未关闭 P0/P1 已确认错误即 REJECTED”，当前版本不可批准；此外14项仍需UAT、7项因 schema、精确执行证据或审计包缺失而阻塞。

### 2.3 结论依据

- `UserStats`/`EliteBonusStats` 无金额编码版本，公共 `Common/PvAmount.py` 不存在，多条生产金额链仍使用 float/round。
- PE/SE 配置与 Active 路径违反已批准合同；期间仍以本地算术推导。
- Elite SOURCE、正式发布和守卫状态没有形成统一原子/状态边界；Recalc consumer 和 Stream 保留策略存在静态可确认缺口。
- 真实 MySQL/Redis/Kafka/Dask/GPU、同数据 SQL-Python 差分、DDL manifest 和完整测试证据均未提供，不得将相应检查写成 PASS。

### 2.4 结果统计

| 分类 | P0 | P1 | P2 | P3 | 合计 |
|---|---:|---:|---:|---:|---:|
| 已确认错误 | 12 | 1 | 0 | 0 | 13 |
| 潜在风险 | 0 | 2 | 0 | 0 | 2 |
| 建议优化 | — | — | 1 | 1 | 2 |
| 无法验证 | 4 | 1 | 0 | 0 | 5 |
| 已确认修复 | 0 | 1 | 0 | 0 | 1 |

### 2.5 检查项状态

| PASS | FAIL | PENDING_TEST_ENV | BLOCKED | NEEDS_DECISION | NOT_APPLICABLE | NOT_RUN |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 13 | 14 | 7 | 0 | 0 | 0 |

另有 `CHK-GOV-001=RETIRED`，不计入34个有效检查项。上表与第6节逐项一致。

---

## 3. 复核对象与版本完整性

### 3.1 待审对象

| 项目 | 实际值 | 核验方式 | 结果 |
|---|---|---|---|
| 仓库/交付包 | `l343765828/Redemption` | GitHub repository/commit metadata | PASS |
| 分支 | `master` | repository metadata | PASS |
| Git commit | 代码/SQL `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；DEC-017 文档 overlay `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` | commit lookup、compare 与固定 ref 读取 | PASS |
| 文件摘要/manifest | 核心代码文件有 blob SHA；`097cae32e0ff7708eb6ee69a7f2ce188e80c060c..2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 仅一份 DOCX 变化；完整 source/archive manifest 未随附件提供 | 固定 ref、commit compare 与附件核对 | PARTIAL |
| 数据库 Schema | DEC-009 批准的最小 schema manifest | 附件核对 | UNVERIFIED |
| 配置版本 | 仓库代码/SQL可静态读取；UAT运行快照未提供 | 固定ref读取 | UNVERIFIED |
| DEC-017 文档 overlay | `Doc/Elite_Bonus_发奖规则说明.docx` @ `2475c6c4`，blob `892640e6…`，SHA-256 `f80ea693…` | 两提交差异核验 + 文档内容核对 | PASS |

### 3.2 可访问材料

#### 已成功读取

| 证据编号 | 文件/对象 | 版本 | 用途 |
|---|---|---|---|
| EV-MRG-001 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.0.md` | v1.0 | 报告A事实声称与结构 |
| EV-MRG-002 | `PV_Amount_Migration_d74_复核报告_v1.0_other.md` | v1.0 | 报告B事实声称与结构 |
| EV-MRG-003 | `Redemption_复核报告模板(1).md` | 用户附件 | 18节+附录 schema |
| EV-MRG-004 | `Redemption_PV_Amount_Migration_d74_检查方案_v1.15.md` | PLAN-PVAM-v1.15 | 检查项、状态、判定规则 |
| EV-MRG-005 | `PLAN-PVAM_v1.13_执行任务书_复核报告.md` | 固定任务书 | DEV/UAT边界及证据纪律 |
| EV-REV-001 | `PV_Amount_Migration_复核报告v1.1_审查意见_v1.0.md` | v1.0 / 2026-08-04 | F-01～F-07 审查意见及其证据声明 |
| EV-REV-002 | `PV_Amount_Migration_复核报告v1.2_二轮审查意见_v1.0.md` | v1.0 / 2026-08-04 | G2-01～G2-04 二轮定点审查意见及独立复验声明 |
| EV-REG-001 | `PV_Amount_Migration_Checklist_Final_v2.25_d74.md` §十一/§十二 | Final v2.25-d74 | P0/T0 权威编号、主题及分层状态 |
| EV-GIT-001 | `097cae32..2475c6c4` commit compare | 2 commits | 区间唯一变化为 `Doc/Elite_Bonus_发奖规则说明.docx` |
| EV-DOC-001 | `Doc/Elite_Bonus_发奖规则说明.docx` | `2475c6c4` / 当前blob重新取证 / SHA-256 `f80ea693…` | DEC-017 三条件停止、数量变化保守传播、示例与删除段核验 |
| EV-CODE-001 | `Model/User/UserStats.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `224b9e82…` | 金额模型字段 |
| EV-CODE-002 | `Model/User/EliteBonusStats.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `ccaa18d9…` | Elite金额/版本/float |
| EV-CODE-003 | `User/EliteBonusService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `00b95fa0…` | SOURCE、writer、float |
| EV-CODE-004 | `User/PEBonusService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `0504b88b…` | 费率、Active、round/float |
| EV-CODE-005 | `User/SuperEliteBonusService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `fe22615d…` | rate/TYPE/scale |
| EV-CODE-006 | `User/LeadershipBonusGPUService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `022a1e0a…` | float64截断 |
| EV-CODE-007 | `User/GlobalEliteBonusRecalculationService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `0830fd87…` | persisted/DONE/Elite guard/maxlen |
| EV-CODE-008 | `User/UserStatsService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `ac6369dc…` | Global/Placement guard、corrected floor 静态形态 |
| EV-CODE-009 | `MessageConsumer/RecalcStreamConsumer.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `d72abe4…` | ACK/路由 |
| EV-CODE-010 | `User/GlobalRecalculationService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `6974cd1c…` | period推导/maxlen |
| EV-CODE-011 | `User/PlacementIncrementalService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `1fbc87da…` | XADD maxlen |
| EV-CODE-012 | `User/PlacementRecalculationService.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `616c93f…` | XADD maxlen |
| EV-CODE-013 | `Common/PvAmount.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` | 固定ref读取为不存在 |
| EV-SQL-001 | `sql_uat/CALC_BE_E.sql` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `84490b5a…` | Elite oracle |
| EV-SQL-002 | `sql_uat/CALC_BE_PE.sql` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `d648b309…` | PE oracle |
| EV-SQL-003 | `sql_uat/CALC_BE_SE_COUNTRY.sql` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` / blob `540afa62…` | SE oracle |

#### 未读取或读取失败

| 文件/对象 | 原因 | 对结论的影响 | 处置 |
|---|---|---|---|
| DEC-009 最小 schema manifest、SQL_MODE、DDL assignment | 未随附件提供 | DATA-007/BIZ-009/PUB-001 必须 BLOCKED | DBA/架构提供批准清单与SHA |
| 两份候选报告声称的原始命令日志、Team Bonus 93/93输出、环境探测文件 | 未随附件提供 | 不得继承为实际测试结果；TEST-001/PUB-002受阻 | 提供原始文件、命令、exit code |
| 精确 commit 的完整 source archive/文件 manifest | connector可读取具名文件，但未形成可校验整仓归档 | 不能独立证明全仓“零引用/无调用点” | 提供 archive/CI artifact |
| 真实 MySQL/Redis/Kafka/Dask/RAPIDS/GPU | 无主机、凭据、镜像和数据 | 14项维持 PENDING_TEST_ENV | 落实 DEC-013 |
| P0/T0 用户原始确认审计包 | v2.25/v34 登记册已读取，但部分 overlay 的用户原始确认文本仍未随本轮附件完整提供 | CHK-TEST-004 继续 BLOCKED；P0/T0 标题已可按权威登记册修正 | 补充全部原始确认文本与 SHA |

### 3.3 排除材料

| 文件/对象 | 排除依据 | 是否曾被第三方引用 | 影响 |
|---|---|---|---|
| 文件名含 `_bak`/`_bakN`/`_final` | redemption-file-filter | YES | 不用于当前缺陷证据 |
| Skill列出的9个旧/副本SQL | redemption-file-filter | YES | 只使用有效SQL |
| `GraphService.run_bfs` | 方案/Skill排除 | NO | 不评价演示逻辑 |
| PB/SFB/GPB/CRB Python算法 | 方案 EX-004 | YES | 不因缺生产实现登记当前缺陷 |
| 两份报告中未附原始输出的运行声称 | 模板“不得伪造/必须可追踪” | YES | 仅作差异诊断，不作为PASS证据 |

---

## 4. 权威基线与冲突处理

### 4.1 实际采用的基线

| 优先级 | 基线 | 权威范围 | 实际状态 |
|---:|---|---|---|
| 1 | 用户本轮“核验二轮审查意见并定点修订为 v1.3”要求 | 修改纪律、证据裁决与输出 | APPLIED |
| 2 | `AGENTS.md` | 项目审查规则 | LOADED（经固定提交读取） |
| 3 | `redemption-file-filter` / `redemption-sql-doc-map` | 排除与SQL路由 | LOADED |
| 4 | `PLAN-PVAM-v1.15` + `v2.25` P0/T0 登记册 | 检查标准、状态机、环境边界和编号主题 | READ |
| 5 | 有效 `sql_uat` | Legacy oracle | READ（本报告涉及的E/PE/SE） |
| 6 | 固定提交 Python | 当前实现事实 | READ（具名核心文件） |
| 7 | 报告A/B | 候选结论 | COMPARED，不自动继承 |

### 4.2 基线冲突

| 冲突编号 | 材料 A | 材料 B | 冲突内容 | 裁决依据 | 结果 |
|---|---|---|---|---|---|
| CONFLICT-001 | 报告A | 报告B | 缺陷数10 vs 13 | 模板单问题原则+代码证据 | 拆为13项 |
| CONFLICT-002 | 报告A | 报告B | PASS=0 vs PASS=2 | PASS须有原始证据；附件无日志/完整审计包 | PASS=0 |
| CONFLICT-003 | 报告A | 报告B | UAT-only检查项是否可静态判FAIL | 执行任务书环境表 | EVT-003/005/006/007保持PENDING_TEST_ENV |
| CONFLICT-004 | 报告A | 报告B | Topology无生产调用点是否已确认 | 缺完整call graph原始输出 | 降为风险 |
| CONFLICT-005 | 复核报告 v1.1 | v2.25 §十一权威登记册 | P0-1/2A/5A/5B/7 主题错位且缺 P0-2B-OPS、P0-3-TIME | EV-REG-001 + CHK-TEST-004 的逐项追踪要求 | 按权威登记册纠正并采用“决议/合同状态 + 实现验收状态”双层表达；TEST-004 仍因原始确认包不完整而 BLOCKED |
| CONFLICT-006 | 方案/代码基线 `2475c6c4` | DEC-017 后继文档提交 `2475c6c4` | 文档修订发生于方案基线之后 | EV-GIT-001 证明区间仅 DOCX 变化；EV-DOC-001 证明修订内容 | 代码/SQL结论继续锚定 `2475c6c4`；仅 DEC-017 采用受控文档 overlay，不外推为代码通过 |

---

## 5. 执行范围与验证边界

### 5.1 覆盖情况

| 范围编号 | 模块/对象 | 计划深度 | 实际完成 | 结果摘要 |
|---|---|---|---|---|
| S-001 | 治理、方案、模板、两份报告 | FULL | 完成 | 结构/枚举/统计交叉校验 |
| S-002 | 公共金额域 | FULL | 核心静态完成 | 版本与适配器缺失 |
| S-003 | 消息/事件治理 | TARGETED | consumer与producer静态完成 | ACK与trim问题；运行时待UAT |
| S-004 | 金额模型 | FULL | 核心模型完成 | version/float缺口 |
| S-005 | 推荐网/全量 | TARGETED | period/guard/Elite路径静态完成 | 传播差分未执行 |
| S-006 | Placement | TARGETED | period和Stream路径完成 | 业务差分未执行 |
| S-007 | Elite | FULL | 静态完成 | gate/SOURCE/publish问题 |
| S-008 | PE | FULL | 静态完成 | rate/Active/float问题 |
| S-009 | SE | FULL | 静态完成 | config/TYPE/scale问题 |
| S-010 | EAB | REFERENCE | 接口/金额文档对照 | schema与发布BLOCKED |
| S-011 | Honor/LB | TARGETED | LB float静态完成 | GPU/SQL diff待UAT |
| S-012 | Team Bonus | REFERENCE | 两报告执行声称已比较 | 原始日志未附，不登记通过 |
| S-013 | 有效SQL | TARGETED | E/PE/SE读取 | 真实DB执行未完成 |
| S-014 | Schema/发布 | REFERENCE | 未完成 | manifest缺失 |
| S-015 | 测试/Loop闭环 | FULL（报告层） | 状态与矩阵重算 | 执行证据包不完整 |

### 5.2 已执行命令或测试

| 执行编号 | 环境 | 命令/测试 | 输入或数据集 | 退出码 | 结果 | 证据 |
|---|---|---|---|---:|---|---|
| RUN-MRG-001 | DEV | 读取并解析报告A/B、模板 | 三份用户附件 | 0 | PASS | EV-MRG-001~003 |
| RUN-MRG-002 | DEV | 固定ref读取具名代码/SQL | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` | 0 | PASS（静态读取） | EV-CODE/EV-SQL |
| RUN-MRG-003 | DEV | 逐项重算34个检查项状态 | PLAN+任务书+证据 | 0 | PASS（报告一致性） | 本报告§6 |
| RUN-MRG-004 | DEV | 统计自检 | 13 FAIL+14 PENDING+7 BLOCKED | 0 | PASS | 本报告§2/§6 |
| RUN-MRG-005 | DEV | 对比 `097cae32e0ff7708eb6ee69a7f2ce188e80c060c..2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 并核验 DEC-017 文档 overlay | Git commit compare + 修订版 DOCX | 0 | PASS（文档侧） | EV-GIT-001、EV-DOC-001 |

### 5.3 未执行命令或测试

| 项目 | 原因 | 是否影响结论 | 后续执行环境 | 状态 |
|---|---|---|---|---|
| 两报告声称的DEV测试重放 | 无精确archive/依赖/原始命令输出 | YES（阻止PASS，不影响静态FAIL） | 固定DEV镜像 | BLOCKED |
| MySQL/MariaDB存储过程与assignment | 无schema/主机/权限 | YES | UAT | PENDING_TEST_ENV |
| Redis/Kafka锁、PEL、DLQ、trim恢复 | 无服务/数据 | YES | UAT | PENDING_TEST_ENV |
| Dask/RAPIDS/GPU测试 | 无镜像/GPU | YES | UAT | PENDING_TEST_ENV |
| SQL-Python同数据差分 | 无同一真实数据环境 | YES | UAT | PENDING_TEST_ENV |
| 全链路月结/发布/checksum | 无manifest/UAT | YES | UAT | BLOCKED |

### 5.4 验证声明

- 静态阅读完成：`YES，限本报告列明的具名核心文件和SQL`
- 实际运行测试：`NO；仅执行文档解析、固定ref静态读取和报告一致性检查`
- 使用真实 MySQL：`NO`
- 使用真实 Redis/Kafka：`NO`
- 使用真实 Dask/RAPIDS/GPU：`NO`
- 完成 SQL 与 Python 同数据差分：`NO`
- 完成测试环境全链路验证：`NO`

---

## 6. 检查项结果总表

| 检查项编号 | 检查内容 | 实际状态 | 严重级别 | 关联发现 | 关键证据 | 备注 |
|---|---|---|---|---|---|---|
| CHK-GOV-001 | 候选方案编制复核 | RETIRED | — | 无 | — | 方案规定保留编号，不进入统计 |
| CHK-ARCH-001 | 版本/材料/manifest 固定 | BLOCKED | P1 | 无 | EV-MRG-001~005 | schema manifest、精确证据包未提供 |
| CHK-ARCH-002 | 入口/调用链与生产可达性 | FAIL | P0 | R-010、R-012 | EV-CODE-007~009 | 统一守卫覆盖与消费者生产处置缺口成立；R-009 保持在发布/状态项 |
| CHK-ARCH-003 | 模块依赖与公共金额适配器 | FAIL | P1 | R-002、R-003 | EV-CODE-001~006 | 公共适配器缺失且金额链分叉 |
| CHK-DATA-001 | 双缩放边界与内部整数域 | FAIL | P0 | R-001、R-003 | EV-CODE-001~006 | 边界/版本/单位合同未闭合 |
| CHK-DATA-002 | 出计算域编码矩阵/禁 float | FAIL | P0 | R-003 | EV-CODE-004~006 | 生产 float/round 路径直接命中失败标准 |
| CHK-DATA-003 | 金额模型版本策略 | FAIL | P0 | R-001 | EV-CODE-001~002 | 金额模型无版本字段 |
| CHK-DATA-004 | 费率矩阵解析（六奖） | FAIL | P0 | R-004 | EV-CODE-004~005、EV-SQL-002~003 | 配置与 SQL/DEC 不一致 |
| CHK-DATA-005 | AR_PERIOD 期间合同 | FAIL | P0 | R-007 | EV-CODE-010 | 本地 period 算术 |
| CHK-DATA-006 | monthActivePV 取值函数与活跃网关 | FAIL | P0 | R-005、R-006 | EV-CODE-004~006 | 硬编码30及外部 Active 输入 |
| CHK-DATA-007 | int64 技术上界 | BLOCKED | P0 | 无 | EV-MRG-004 | 缺 DEC-009 schema manifest |
| CHK-BIZ-001 | 推荐网传播与 DEC-011 契约 | PENDING_TEST_ENV | P0 | 无 | — | 传播最终状态需同数据三路差分 |
| CHK-BIZ-002 | 图完整性与拓扑变更 | PENDING_TEST_ENV | P0 | RISK-001 | — | Topology 生产可达性与图 mutation 待完整工作树/UAT |
| CHK-BIZ-003 | 安置网 1L/2L/结余 | PENDING_TEST_ENV | P0 | 无 | — | Placement 全量/增量一致性待 UAT |
| CHK-BIZ-004 | Team Bonus oracle/费率/capping | PENDING_TEST_ENV | P1 | 无 | — | TB oracle、配置和生产 units 路径待 UAT |
| CHK-BIZ-005 | Global 七条与 writer 资格 | FAIL | P0 | R-011 | EV-CODE-002~003、EV-SQL-001 | Elite 候选/writer gate 不完整 |
| CHK-BIZ-006 | Elite 增量账本与原子边界 | FAIL | P0 | R-008、R-009、R-011 | EV-CODE-003、007 | SOURCE/发布合同不闭合 |
| CHK-BIZ-007 | PE 奖金 | FAIL | P1 | R-004、R-005、R-006 | EV-CODE-004、EV-SQL-002 | PE 配置与 Active 失败 |
| CHK-BIZ-008 | SE 奖金 | FAIL | P0 | R-004、R-006 | EV-CODE-005、EV-SQL-003 | SE rate/Active 失败 |
| CHK-BIZ-009 | EAB 奖金 | BLOCKED | P0 | R-006 | EV-MRG-004 | manifest 缺失使最终验收 BLOCKED；外部 IS_ACTIVE 权威输入的静态缺口另由 R-006 记录 |
| CHK-BIZ-010 | Honor 当期/历史最高 | PENDING_TEST_ENV | P1 | 无 | — | Honor 窗口/历史最高需 GPU+SQL 差分 |
| CHK-BIZ-011 | Leadership 九代/双闸门 | PENDING_TEST_ENV | P1 | R-003、R-006 | EV-CODE-006 | 静态金额/Active缺口已记录，业务差分待 UAT |
| CHK-EVT-001 | 退款权威账本/归期/二次冲销 | PENDING_TEST_ENV | P0 | 无 | — | 退款身份/归期纯 UAT |
| CHK-EVT-002 | 三阶段完成账本/coverage | FAIL | P0 | R-001 | EV-CODE-001~003 | 金额版本与单一 normalized delta 的入口合同未闭合；R-003 不再泛挂本项 |
| CHK-EVT-003 | 统一守卫与 Epoch 状态机 | PENDING_TEST_ENV | P0 | R-009、R-010 | EV-CODE-007~008 | 静态状态缺口；按任务书最终状态须 UAT |
| CHK-EVT-004 | run manifest 与重放 | PENDING_TEST_ENV | P0 | 无 | — | coverage/replay 纯 UAT |
| CHK-EVT-005 | Redis 权威提交边界 | PENDING_TEST_ENV | P0 | R-008 | EV-CODE-003 | 静态非原子形态；故障结果待 UAT |
| CHK-EVT-006 | 消费者 ACK/DLQ 纪律 | PENDING_TEST_ENV | P0 | R-012 | EV-CODE-009 | 静态 ACK 路径；PEL/DLQ待 UAT |
| CHK-EVT-007 | Stream 保留与 deleted-ID 恢复 | PENDING_TEST_ENV | P0 | R-013 | EV-CODE-007/010/011/012 | 四个 producer 固定 trim 已确认；运行时恢复待 UAT |
| CHK-PUB-001 | 正式发布/资格/对账 | BLOCKED | P0 | R-009、R-011 | EV-MRG-004、EV-CODE-007 | manifest 缺失，必须 BLOCKED |
| CHK-PUB-002 | 迁移保真度（读取入口/时序） | BLOCKED | P1 | 无 | UV-005 | 未提供精确全仓扫描/时序命令证据 |
| CHK-TEST-001 | 测试真实性与夹具处置 | BLOCKED | P1 | 无 | UV-005 | 两报告声称的测试日志未附 |
| CHK-TEST-002 | SQL-Python 全量差分 | PENDING_TEST_ENV | P0 | 无 | — | 同一数据库 SQL-Python diff 待 UAT |
| CHK-TEST-003 | 幂等/恢复/checksum | PENDING_TEST_ENV | P0 | 无 | — | 并发/故障/checksum 待 UAT |
| CHK-TEST-004 | Loop 闭环与审计包纪律 | BLOCKED | P1 | 无 | UV-005 | P0/T0 原始审计包及用户确认文本未附 |

统计校验：有效检查项34个=`FAIL 13 + PENDING_TEST_ENV 14 + BLOCKED 7`；另有 `RETIRED 1`。

### 6.1 P0-0～P0-12 状态矩阵

> 本矩阵以 `PV_Amount_Migration_Checklist_Final_v2.25_d74.md` §十一及其有来源 overlay 为编号与主题基准。  
> “决议/合同状态”只说明规则是否已确认；“实现验收状态”才表示当前实现证据。二者不得互相替代，尤其不得用 `PASS` 表示仅完成业务决议。

| 编号 | 权威主题 | 决议/合同状态 | 实现验收状态 | 证据/理由 |
|---|---|---|---|---|
| P0-0 | 全调用链 DDL/schema manifest | OPEN | BLOCKED | DEC-009 批准 manifest 未提供；CHK-DATA-007/BIZ-009/PUB-001 阻塞 |
| P0-1 | EAB 中间不舍入、最终个人奖金一次 `ROUND_HALF_UP` 两位 | CONFIRMED/CLOSED | BLOCKED | 本地算法方向可见，但 DDL/SQL_MODE/assignment oracle 未提供；CHK-BIZ-009 BLOCKED |
| P0-2A | corrected PV 非负下限（floor zero） | CONFIRMED/CLOSED | PENDING_TEST_ENV | 派生态有下限（`UserStatsService.py:173-175`），原始累计器无钳制；完整非负下限等价性待 TC-009/010 三路差分测试验证 |
| P0-2B | 整单一次性冲销及二次冲销不得再次扣减 | CONFIRMED — BUSINESS SCOPE | PENDING_TEST_ENV | 实现状态机、幂等/冲突证据待 CHK-EVT-001、T0-18、TC-022；不使用 PASS |
| P0-2B-OPS | 退款异常、人工 override、权限与专项 reconciliation | OPEN | NEEDS_DECISION | `REFUND_EXCEPTION_POLICY_OPEN` 尚需业务/架构签字；自动路径不得自行补造 |
| P0-3 | 未发回原期、已发进当前期 | CONFIRMED — BUSINESS PRINCIPLE | PENDING_TEST_ENV | 归期实现与发奖状态证据待 CHK-EVT-001、TC-022 |
| P0-3-TIME | 退款权威时间字段、GMT+8 cutoff 与迟到事件边界 | CLOSED CORE（DEC-006：批准时间/GMT+8/AR_PERIOD 唯一映射）/ 迟到事件边界残余 | NEEDS_DECISION | 核心时间字段及映射规则已关闭；字段绑定实现、缺失/冲突处置和迟到事件边界仍须冻结并在 TC-006/TC-022 验收 |
| P0-4 | Kafka/MQ 权威输入、Redis 投影与测试重建范围 | CONFIRMED — TEST SCOPE | PENDING_TEST_ENV | `P0-4-CODE-ACCEPTANCE`、在途排空、offset 与恢复证据待真实事件链 |
| P0-5A | required 配置必须且只能存在一条合法记录 | CONFIRMED/CLOSED | FAIL | PE 硬编码、SE 配置解析与 approved matrix 不一致；R-004 |
| P0-5B | rate/cap/limit/Country/TYPE 路径的剩余 requiredness | CONFIRMED CORE / 子政策 OPEN | FAIL | 已确认部分被 R-004 违反；未确认子政策继续在决议列保持 OPEN，不影响实现列仅记录已确认失败 |
| P0-6 | EAB 生产模式 `CORRECTED_EAB_V8` | CONFIRMED/CLOSED | BLOCKED | 模式/发布/assignment proof 未闭合；CHK-BIZ-009 BLOCKED |
| P0-7 | rate encoding/scale、ppm 与缺失/0处理 | CONFIRMED CORE / 部分政策 OPEN | FAIL | 生产 float/round、PE 固定率、SE 0/负值阻断；R-003、R-004 |
| P0-8 | Elite corrected 七条 gate | CONFIRMED/CLOSED | FAIL | PV_PSS、版本、run/revision 与 writer proof 不完整；R-011 |
| P0-9 | SE exact canonical + Legacy amount parity | CONFIRMED/CLOSED | FAIL | trim/lower、rate 阻断与多 scale；R-004，完整 parity 待 TC-018 |
| P0-10 | `monthActivePV` INTEGER_BV_ONLY / scale=100 | CONFIRMED CORE / 子政策 OPEN | FAIL | PE 裸 30 与外部 IS_ACTIVE 权威输入；R-005、R-006 |
| P0-11 | Event identity、退款因果与 Global Event Registry | OPEN | PENDING_TEST_ENV | 身份、registry、因果和跨期重试需真实事件链验证 |
| P0-12 | Global Elite full rebuild 正式 SOURCE | CONFIRMED/CLOSED | FAIL | SOURCE 非原子且正式 writer proof 不足；R-008、R-011 |

### 6.2 T0-1～T0-30 状态矩阵

| 编号 | 条目 | 状态 | 证据/理由 |
|---|---|---|---|
| T0-1 | CUTOVER_DB_SEED 双轨结余 | PENDING_TEST_ENV | 待 TC-012 |
| T0-2 | Epoch Guard + stage CAS + outbox | PENDING_TEST_ENV | R-009/R-010 静态预检；待 TC-024/026 |
| T0-3 | source-to-units loader | PENDING_TEST_ENV | 待精确入口验证 |
| T0-4 | 出域逐列编码矩阵 | FAIL | R-003 |
| T0-5 | int64 溢出证明 | BLOCKED | 缺 schema/assignment |
| T0-6 | SETTLEMENT_RUN_MANIFEST | PENDING_TEST_ENV | 待 TC-025/029 |
| T0-7 | Elite 费率链无 float | FAIL | R-003 |
| T0-8 | E/PE 无15%默认；缺失/0一致 | FAIL | R-004 |
| T0-9 | corrected EAB 原子发布 | BLOCKED | 缺 manifest |
| T0-10 | 传播契约（DEC-011） | PENDING_TEST_ENV | 待 TC-009/010 |
| T0-11 | SE exact-canonical 与 parity | FAIL | R-004；完整 parity 待 TC-018 |
| T0-12 | Raw/Normalized 双 checkpoint | PENDING_TEST_ENV | Gate C 保持 OPEN |
| T0-13 | PE 用户全集与 INT oracle | PENDING_TEST_ENV | 静态 Active 缺陷归 T0-19 |
| T0-14 | EAB audit/legacy 投影 | BLOCKED | 缺 manifest |
| T0-15 | Elite ledger/SOURCE reconciliation | FAIL | R-008、R-011 |
| T0-16 | registry/raw/outbox/checkpoint 同事务 | PENDING_TEST_ENV | R-008 静态预检；待故障注入 |
| T0-17 | 不读取 MySQL 活跃表（DEC-004） | BLOCKED | 缺精确全仓扫描证据 |
| T0-18 | 整单退款状态机/双revision | PENDING_TEST_ENV | 待 TC-022 |
| T0-19 | 活跃结果各消费方同规则现算 | FAIL | R-005、R-006 |
| T0-20 | PE period/month 校验 | PENDING_TEST_ENV | 待 TC-017 |
| T0-21 | Settlement Epoch Manager 与 coverage | PENDING_TEST_ENV | R-009/R-010 静态预检；待 TC-024/025 |
| T0-22 | TB assignment oracle/rate gate/结余 | PENDING_TEST_ENV | 待 TC-013 |
| T0-23 | 外部金额十进制字符串 schema | PENDING_TEST_ENV | 待消息样本 |
| T0-24 | source mode adapter | PENDING_TEST_ENV | 待 UAT |
| T0-25 | Global Event Registry | PENDING_TEST_ENV | 待 UAT |
| T0-26 | Normalized identity/generation/supersede | PENDING_TEST_ENV | 待 TC-025 |
| T0-27 | 退款/幂等/归期 | PENDING_TEST_ENV | 待 TC-022 |
| T0-28 | 全状态转换与崩溃恢复 | PENDING_TEST_ENV | 待 TC-026/028；Gate C OPEN |
| T0-29 | ConfigRequirementMatrix 与 P0-10 子政策 | FAIL | R-004、R-005、R-006 |
| T0-30 | 术语/旧合同残留清理 | BLOCKED | 原始合同审计包未附，不能据二手报告判PASS |

---

## 7. 已确认错误

### 7.1 汇总

| 问题编号 | 标题 | 级别 | 关联检查项 | 影响模块 | 当前状态 | 是否阻断 |
|---|---|---|---|---|---|---|
| R-001 | 金额模型缺少 amount_encoding_version，新旧编码无法隔离 | P0 | CHK-DATA-001、CHK-DATA-003、CHK-EVT-002 | UserStats、EliteBonusStats 及全部依赖其金额字段的增量/全量链 | OPEN | YES |
| R-002 | 批准的公共金额适配器 Common/PvAmount.py 不存在 | P1 | CHK-ARCH-003 | 全部金额边界转换和公共单位断言 | OPEN | YES |
| R-003 | 生产金额链仍存在 float/round 中转，违反精确定点合同 | P0 | CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011 | PE、SE、Elite、Leadership 金额与奖金输出 | OPEN | YES |
| R-004 | PE/SE 配置合同被硬编码、原始值归一化和过严阻断绕过 | P0 | CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008 | PE/SE 费率、Country/TYPE 解析和奖金结果 | OPEN | YES |
| R-005 | PE 使用裸值 30 派生 IS_ACTIVE | P0 | CHK-DATA-006、CHK-BIZ-007 | PE 发放资格 | OPEN | YES |
| R-006 | 奖金服务仍把外部 IS_ACTIVE 快照作为权威输入 | P0 | CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011 | PE、SE、EAB、Leadership、Team Bonus 发放资格一致性 | OPEN | YES |
| R-007 | 期间解析使用本地算术和首期硬编码，绕过 AR_PERIOD 合同 | P0 | CHK-DATA-005 | 跨期结余、历史最高、退款归期、writer period | OPEN | YES |
| R-008 | Elite SOURCE 写入与 stats 保存不在同一 Redis 权威提交 | P0 | CHK-BIZ-006、CHK-EVT-005 | Elite assignment/SOURCE、重放、dirty 与全量输入 | OPEN | YES |
| R-009 | Elite 未持久化正式结果时仍写 DONE 并发布完成事件 | P0 | CHK-BIZ-006、CHK-EVT-003、CHK-PUB-001 | Elite 奖金/SOURCE 发布和下游月结 | OPEN | YES |
| R-010 | 结算守卫被拆成两套，UserStats 守卫未覆盖 Elite 状态 | P0 | CHK-ARCH-002、CHK-EVT-003 | 结算期间订单、拓扑和奖金写入隔离 | OPEN | YES |
| R-011 | Elite 候选与正式 writer 缺少 PV_PSS、版本和提交证明 | P0 | CHK-BIZ-005、CHK-BIZ-006、CHK-PUB-001 | Elite 资格、奖金和正式 SOURCE | OPEN | YES |
| R-012 | Recalc consumer 对空、未知或未处理事件可返回成功并 ACK | P0 | CHK-ARCH-002、CHK-EVT-006 | 重算漂移、晋衔、完成哨兵及恢复链 | OPEN | YES |
| R-013 | 多个 Redis Stream producer 固定 maxlen=100000，在 ACK 水位前裁剪 | P0 | CHK-EVT-007 | 重算事件保留、PEL 与 deleted-ID 恢复 | OPEN | YES |

### 7.2 详细问题

#### `R-001` — `金额模型缺少 amount_encoding_version，新旧编码无法隔离`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-DATA-001、CHK-DATA-003、CHK-EVT-002` |
| 当前状态 | `OPEN` |
| 发现类型 | `DATA` |
| 影响范围 | UserStats、EliteBonusStats 及全部依赖其金额字段的增量/全量链 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

金额模型缺少 amount_encoding_version，新旧编码无法隔离。

**预期行为**

目标合同要求新编码记录明确标记 `amount_encoding_version=2`，缺失/未知版本不得静默进入 micro-units 计算域。

**当前行为**

固定提交中的 `UserStats` 与 `EliteBonusStats` 均包含 PV/GPV/奖金字段，但没有 `amount_encoding_version` 或等价版本判定字段。

**定位**

- 文件/类/函数/字段：`Model/User/UserStats.py::UserStats`；`Model/User/EliteBonusStats.py::EliteBonusStats`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
UserStats: pv/gpv/gpv_real/gpv_unreal/pv_1l/... 为整数金额字段；EliteBonusStats: pv_pcs/gpv/gpv_real/estimated_bonus。两模型字段列表均无 amount_encoding_version。
```

**判定理由**

持久化整数无法区分 legacy 原值与 ×1e6 新编码；同一数值在两种编码下可相差六个数量级，违反 DATA-003 的版本隔离硬门禁。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

迁移模型 schema 尚未落地。

**影响分析**

- 直接影响：新旧金额记录可能在同一 Redis/计算链混算。
- 间接影响：重放、跨期继承、对账无法判断金额单位。
- 数据影响：存在数量级污染风险；是否已影响历史数据仍为 UNVERIFIED。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：需补版本字段、迁移旧数据并按期重建。

**修正建议**

为所有持久化金额模型增加明确版本字段；入口拒绝未知版本；历史数据迁移必须带审计清单。

**建议验证**

- TC-001、TC-003；历史 Redis 混合版本读写与拒绝用例。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-001` | GENERATED |
| 施工方案 | `W-001` | GENERATED |
| 验证报告 | `V-001` | PENDING |


#### `R-002` — `批准的公共金额适配器 Common/PvAmount.py 不存在`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P1` |
| 关联检查项 | `CHK-ARCH-003` |
| 当前状态 | `OPEN` |
| 发现类型 | `DELIVERY` |
| 影响范围 | 全部金额边界转换和公共单位断言 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

批准的公共金额适配器 Common/PvAmount.py 不存在。

**预期行为**

金额转换、ppm、cents、micro-units 与边界断言应由 Common 最底层公共实现承载，业务服务不得各自复制。

**当前行为**

对固定提交读取 `Common/PvAmount.py` 返回不存在，仓库可访问文件中也未发现等价已批准适配器。

**定位**

- 文件/类/函数/字段：目标路径 `Common/PvAmount.py`（缺失）
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
固定提交 GitHub Contents 查询结果为 404；PE、SE、EAB、Leadership 各自保留本地转换逻辑。
```

**判定理由**

方案 CHK-ARCH-003 以公共适配器可达为通过前提；目标模块不存在属于实现缺口。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

公共金额域尚未建设。

**影响分析**

- 直接影响：服务无法复用同一边界转换。
- 间接影响：本地 scale/round/float 规则持续分叉。
- 数据影响：结构性风险，是否已造成历史金额错误需差分验证。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：新增模块并逐服务迁移。

**修正建议**

建立 `Common/PvAmount.py`，只允许外部事件边界与批量装载边界进行放大；内部统一 units-int。

**建议验证**

- 公共适配器单元矩阵；TC-001/TC-002 回归。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-002` | GENERATED |
| 施工方案 | `W-002` | GENERATED |
| 验证报告 | `V-002` | PENDING |


#### `R-003` — `生产金额链仍存在 float/round 中转，违反精确定点合同`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011` |
| 当前状态 | `OPEN` |
| 发现类型 | `DATA` |
| 影响范围 | PE、SE、Elite、Leadership 金额与奖金输出 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

生产金额链仍存在 float/round 中转，违反精确定点合同。

**预期行为**

PV/BV/GPV/结余/奖金基数在计算域内保持受控整数；最终金额用 integer cents；禁止生产 `float64`、`round(float)` 或 `/100.0` 输出。

**当前行为**

Leadership `_truncate_gpu` 将值转为 `float64` 并用 `nextafter/trunc`；PE `_apply_truncate` 使用 `cp.round(base*100)` 且 `BONUS_PE=bonus_cents/100.0`；SE 使用 `pv*1000` 后 `.round()`；Elite 的 `estimated_bonus` 模型字段为 float。

**定位**

- 文件/类/函数/字段：`User/LeadershipBonusGPUService.py::_truncate_gpu`；`User/PEBonusService.py::_apply_truncate`；`User/SuperEliteBonusService.py::calculate_se_bonus`；`Model/User/EliteBonusStats.py::estimated_bonus`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
`scaled = ...astype("float64") * factor`；`base_cents = cp.round(...*100)`；`BONUS_PE = bonus_cents / 100.0`。
```

**判定理由**

上述路径直接命中 CHK-DATA-002 的失败标准“金额列出现 float、round 洗白”；即使尚未运行出差异，也已违反编码合同。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

各奖金模块独立实现财务精度逻辑。

**影响分析**

- 直接影响：边界值与大数截断可能偏离 SQL。
- 间接影响：CPU/GPU、增量/全量结果难以严格对账。
- 数据影响：具体差异量待 UAT；代码形态已确认。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：修复后按周期重算并差分。

**修正建议**

改为 units-int/ppm/integer-cents 运算；所有 join/groupby 前后断言 dtype；禁止最终 writer 接收 float。

**建议验证**

- TC-002、TC-008、TC-017～TC-021；大数、负值、临界小数和跨分区聚合。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-003` | GENERATED |
| 施工方案 | `W-003` | GENERATED |
| 验证报告 | `V-003` | PENDING |


#### `R-004` — `PE/SE 配置合同被硬编码、原始值归一化和过严阻断绕过`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008` |
| 当前状态 | `OPEN` |
| 发现类型 | `BUSINESS` |
| 影响范围 | PE/SE 费率、Country/TYPE 解析和奖金结果 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

PE/SE 配置合同被硬编码、原始值归一化和过严阻断绕过。

**预期行为**

费率从冻结配置快照解析为有符号 ppm；缺失/显式0按批准规则为0；负值不得仅因负号阻断；SE exact-canonical 路径不得用 trim/lower 自动修复原始 TYPE。

**当前行为**

PE 构造函数固定 `_pro_elite_rate_ppm=150000`；SE 对 config/type 做 strip/lower，并在费率缺失、value 缺失或 `rate_val<=0` 时直接抛错。

**定位**

- 文件/类/函数/字段：`User/PEBonusService.py::PEBonusService.__init__`；`User/SuperEliteBonusService.py::_parse_se_rate/_parse_country_mapping`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
`self._pro_elite_rate_ppm = 150000`；`type_norm=...str.strip().str.lower()`；`if rate_val <= 0: raise ValueError(...)`。
```

**判定理由**

有效 PE/SE SQL从 AR_CONFIG 读取费率；当前实现绕过配置或与缺失/0/负值合同相反。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

ConfigRequirementMatrix 与统一 ppm parser 未落地。

**影响分析**

- 直接影响：配置变更不能被 PE 重放；SE 合法0/负配置被拒绝。
- 间接影响：SQL/Python parity 与配置审计失真。
- 数据影响：可能导致阻断或使用错误固定率；历史影响 UNVERIFIED。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：按期重算。

**修正建议**

建设统一配置解析器；PE 删除固定15%；SE 保留 raw 值并按 exact contract 校验，区分缺失、0、负、重复。

**建议验证**

- TC-004、TC-005、TC-017、TC-018。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-004` | GENERATED |
| 施工方案 | `W-004` | GENERATED |
| 验证报告 | `V-004` | PENDING |


#### `R-005` — `PE 使用裸值 30 派生 IS_ACTIVE`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-DATA-006、CHK-BIZ-007` |
| 当前状态 | `OPEN` |
| 发现类型 | `BUSINESS` |
| 影响范围 | PE 发放资格 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

PE 使用裸值 30 派生 IS_ACTIVE。

**预期行为**

Active 阈值只能经批准的 monthActivePV 取值函数取得，并在同一 run 冻结。

**当前行为**

`PEBonusService` 在未提供外部活跃表时直接执行 `UserStats.pv >= 30`。

**定位**

- 文件/类/函数/字段：`User/PEBonusService.py::execute_batch` 的活跃派生分支
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
日志声明“基于 UserStats.pv >= 30”；代码 `ddf_perf['IS_ACTIVE']=(... >= 30).astype('int32')`。
```

**判定理由**

直接命中 CHK-DATA-006 的“硬编码裸30”失败标准；当前配置即使恰为30，也不能证明可配置和可重放。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

统一 Active 阈值供给未接入 PE。

**影响分析**

- 直接影响：monthActivePV 变更时 PE 静默偏离。
- 间接影响：不同奖项 Active 结果分叉。
- 数据影响：当前配置为30时可能偶合；其他周期风险明确。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：修复后重算相关周期。

**修正建议**

改为调用唯一 getter，并把阈值版本/checksum 写入 run manifest。

**建议验证**

- TC-007、TC-017；阈值29.99/30/30.1及配置切换。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-005` | GENERATED |
| 施工方案 | `W-005` | GENERATED |
| 验证报告 | `V-005` | PENDING |


#### `R-006` — `奖金服务仍把外部 IS_ACTIVE 快照作为权威输入`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011` |
| 当前状态 | `OPEN` |
| 发现类型 | `BUSINESS` |
| 影响范围 | PE、SE、EAB、Leadership、Team Bonus 发放资格一致性 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

奖金服务仍把外部 IS_ACTIVE 快照作为权威输入。

**预期行为**

DEC-018 要求各消费方基于同一 UserStats.pv 与同一 monthActivePV 派生规则各自现算，不把共享/持久化 Active snapshot 当权威源。

**当前行为**

PE 的 REQUIRED_PERF_COLS 明确要求 `IS_ACTIVE`；SE/EAB 接收 `ddf_user_perf` 后 merge/fillna；可访问实现未提供这些输入与同一 PV/阈值 run 的可追溯绑定。

**定位**

- 文件/类/函数/字段：`User/PEBonusService.py::REQUIRED_PERF_COLS`；`User/SuperEliteBonusService.py` Step 5；`User/EliteAchievementBonusService.py` 入参合同
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
`REQUIRED_PERF_COLS=['PERIOD_NUM','USER_ID','IS_ACTIVE']`；SE/EAB 结果与外部 `is_active` 关联。
```

**判定理由**

接口本身允许不同调用者注入不同 Active 结果，无法满足“同源、同规则、同 run”证明。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

DEC-018 后的 Active 派生架构尚未迁入奖金接口。

**影响分析**

- 直接影响：同一会员可在不同奖金模块得到不同 Active。
- 间接影响：分母、理论奖金和实际发放不可对账。
- 数据影响：实际差异待 UAT。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：重建 Active 结果后按期重算。

**修正建议**

各奖金内部由同源 PV + 唯一阈值现算；外部输入只可作为审计对照，不能作为权威。

**建议验证**

- TC-007、TC-017～TC-021；同一 run trace 对比。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-006` | GENERATED |
| 施工方案 | `W-006` | GENERATED |
| 验证报告 | `V-006` | PENDING |


#### `R-007` — `期间解析使用本地算术和首期硬编码，绕过 AR_PERIOD 合同`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-DATA-005` |
| 当前状态 | `OPEN` |
| 发现类型 | `STATE` |
| 影响范围 | 跨期结余、历史最高、退款归期、writer period |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

期间解析使用本地算术和首期硬编码，绕过 AR_PERIOD 合同。

**预期行为**

当前期与上一期必须由权威 AR_PERIOD 唯一解析；系统首期取权威最小期；退款按批准时间映射 GMT+8 期间；缺期 fail-loud。

**当前行为**

Global `_get_previous_period` 把 period 转 int，`period==1` 视为首期，其余直接减1；Placement 路径还支持 YYYYMM 算术推导。

**定位**

- 文件/类/函数/字段：`User/GlobalRecalculationService.py::_get_previous_period`；`User/PlacementRecalculationService.py::_get_prev_period`；`User/PlacementIncrementalService.py::_get_prev_period`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
`if period_int == 1: return ""`；`return str(period_int-1)`；Placement 包含跨年 YYYYMM 计算。
```

**判定理由**

期号连续性和首期值属于数据合同，不能由整数格式假设代替；直接命中 DATA-005 的硬编码失败标准。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

缺少统一 PeriodResolver。

**影响分析**

- 直接影响：上一期结余或历史最高可能读取错误期。
- 间接影响：退款归期、完成状态和发布表错位。
- 数据影响：历史影响 UNVERIFIED。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：需按权威期间表重算和核账。

**修正建议**

建设唯一 PeriodResolver；所有入口和 writer 绑定 period snapshot；删除 `==1` 与 YYYYMM 推导。

**建议验证**

- TC-006、TC-022；跨年、缺期、非1首期、GMT+8 月界。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-007` | GENERATED |
| 施工方案 | `W-007` | GENERATED |
| 验证报告 | `V-007` | PENDING |


#### `R-008` — `Elite SOURCE 写入与 stats 保存不在同一 Redis 权威提交`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-BIZ-006、CHK-EVT-005` |
| 当前状态 | `OPEN` |
| 发现类型 | `CONCURRENCY` |
| 影响范围 | Elite assignment/SOURCE、重放、dirty 与全量输入 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

Elite SOURCE 写入与 stats 保存不在同一 Redis 权威提交。

**预期行为**

stats mutation、assignment ledger、revision、dirty、outbox 必须在同一 Redis 原子单元提交。

**当前行为**

`_track_bonus_source` 立即执行 HSET/EXPIRE；业务节点随后才由 `_batch_save` 通过另一个 pipeline 保存。

**定位**

- 文件/类/函数/字段：`User/EliteBonusService.py::_track_bonus_source/update_elite_bonus_incremental/_batch_save`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
SOURCE hash 写入发生在 `_batch_save(models_to_save)` 之前，二者没有共享 transaction pipeline。
```

**判定理由**

两次提交间崩溃可产生 SOURCE 已更新而 stats 未更新，或反之，命中 BIZ-006 的原子边界失败标准。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

SOURCE 作为旁路 hash 后加到既有保存流程。

**影响分析**

- 直接影响：SOURCE 与资格/业绩状态分裂。
- 间接影响：全量重建和 reconciliation 输入不可信。
- 数据影响：故障窗口内可能漏计/错归属；历史影响 UNVERIFIED。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：需从权威事件重建。

**修正建议**

改为不可变 assignment ledger，并与 stats/revision/dirty/outbox 在同一 Redis Function/Lua/CAS 单元提交。

**建议验证**

- TC-015、TC-016、TC-026；提交前后 kill/timeout。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-008` | GENERATED |
| 施工方案 | `W-008` | GENERATED |
| 验证报告 | `V-008` | PENDING |


#### `R-009` — `Elite 未持久化正式结果时仍写 DONE 并发布完成事件`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-BIZ-006、CHK-EVT-003、CHK-PUB-001` |
| 当前状态 | `OPEN` |
| 发现类型 | `STATE` |
| 影响范围 | Elite 奖金/SOURCE 发布和下游月结 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

Elite 未持久化正式结果时仍写 DONE 并发布完成事件。

**预期行为**

`persisted=false` 只能表示 Redis 重算完成待发布，不得进入最终 DONE/OPENED；正式 bonus/SOURCE 与 proof 完成后才能发布最终完成。

**当前行为**

没有 `db_executor` 时 `persisted=False`，流程仍调用 `_emit_settlement_done`；该函数把状态写为 DONE 并 XADD `SETTLEMENT_PERIOD_DONE`。

**定位**

- 文件/类/函数/字段：`User/GlobalEliteBonusRecalculationService.py::settle_period/_emit_settlement_done`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
代码明确记录“仅完成 Redis 重算、尚未落库”，随后仍执行 `_emit_settlement_done(... persisted=False)`；done payload 的 status 为 DONE。
```

**判定理由**

局部计算完成和正式发布完成共用终态，下游无法据状态判断结果是否可用。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

重算状态与发布状态未分层。

**影响分析**

- 直接影响：下游可能在正式表未更新时继续月结。
- 间接影响：增量入口可能提前放行。
- 数据影响：可产生旧表/新Redis混合视图。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：需冻结并重新发布/对账。

**修正建议**

拆分 RECALC_DONE_PENDING_PUBLISH、PUBLISHING、PUBLISHED；persisted=false 不发送最终完成事件。

**建议验证**

- TC-024、TC-029；无 db_executor、空 candidate、发布崩溃。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-009` | GENERATED |
| 施工方案 | `W-009` | GENERATED |
| 验证报告 | `V-009` | PENDING |


#### `R-010` — `结算守卫被拆成两套，UserStats 守卫未覆盖 Elite 状态`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-ARCH-002、CHK-EVT-003` |
| 当前状态 | `OPEN` |
| 发现类型 | `CONCURRENCY` |
| 影响范围 | 结算期间订单、拓扑和奖金写入隔离 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

结算守卫被拆成两套，UserStats 守卫未覆盖 Elite 状态。

**预期行为**

消息入口和核心写入口使用同一 guard，一次性检查 Global、Placement、Elite、Epoch 与 in-flight 水位。

**当前行为**

`UserStatsService.assert_period_settlement_available` 只检查 global lock/status 与 placement status；Global Elite 另有独立 guard，只检查 Elite lock/status，并仅阻断 RUNNING/FAILED。

**定位**

- 文件/类/函数/字段：`User/UserStatsService.py::assert_period_settlement_available`；`User/GlobalEliteBonusRecalculationService.py::assert_period_settlement_available`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
UserStats guard 的状态键集合中没有 Elite；Elite guard 不读取 Global/Placement。
```

**判定理由**

不同入口调用不同 guard 时无法证明三类全量状态的统一快照安全。注意：本终稿不声称“全仓零调用点”，该否定性结论未独立复现。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

各服务独立增加状态键，未形成 Settlement Coordinator。

**影响分析**

- 直接影响：Elite 重算期间其他入口存在放行窗口。
- 间接影响：与 R-009 叠加产生假完成后的竞态。
- 数据影响：运行时影响待 UAT。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：需状态审计和按期重建。

**修正建议**

建立统一 guard/coordinator，入口与核心方法双层防绕过；记录 offset 与 in-flight 排空证据。

**建议验证**

- TC-024；三状态组合、direct-call、补数和并发切换。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-010` | GENERATED |
| 施工方案 | `W-010` | GENERATED |
| 验证报告 | `V-010` | PENDING |


#### `R-011` — `Elite 候选与正式 writer 缺少 PV_PSS、版本和提交证明`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-BIZ-005、CHK-BIZ-006、CHK-PUB-001` |
| 当前状态 | `OPEN` |
| 发现类型 | `BUSINESS` |
| 影响范围 | Elite 资格、奖金和正式 SOURCE |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

Elite 候选与正式 writer 缺少 PV_PSS、版本和提交证明。

**预期行为**

有效 SQL/批准合同要求 PV_PSS>0 候选、初始 GPV=PV_PCS、A/B 路径及 qualified+GPV_REAL>0；writer 还须校验 version、run/revision、SOURCE_CLEAN 和 committed proof。

**当前行为**

EliteBonusStats 不含 PV_PSS；增量入口直接创建/更新节点；snapshot writer 只按 `gpv_real>0` 与 `estimated_bonus>0` 选行，并把 rate/bonus 转为 float。

**定位**

- 文件/类/函数/字段：`Model/User/EliteBonusStats.py::EliteBonusStats`；`User/EliteBonusService.py::update_elite_bonus_incremental/snapshot_period_to_db`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
`CALC_BE_E.sql` 初始化行要求 `PV_PSS>0` 且 `GPV=PV_PCS`；Python model/writer 没有对应候选字段和 proof 校验。
```

**判定理由**

金额大于0不能替代完整候选资格和发布证明，无法证明 Python 正式行集等价于 oracle。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

增量状态与 P0-8/P0-12 正式发布合同未闭合。

**影响分析**

- 直接影响：不合格来源可能进入或合格来源可能漏出。
- 间接影响：正式 SOURCE 与奖金无法 reconciliation。
- 数据影响：行集/金额影响待差分。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：按权威候选重建。

**修正建议**

补权威 PV_PSS 输入与七条 gate；正式 writer 只消费带 manifest/proof 的全量 candidate。

**建议验证**

- TC-014～TC-016、TC-029；Elite 全期 SQL-Python diff。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-011` | GENERATED |
| 施工方案 | `W-011` | GENERATED |
| 验证报告 | `V-011` | PENDING |


#### `R-012` — `Recalc consumer 对空、未知或未处理事件可返回成功并 ACK`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-ARCH-002、CHK-EVT-006` |
| 当前状态 | `OPEN` |
| 发现类型 | `STATE` |
| 影响范围 | 重算漂移、晋衔、完成哨兵及恢复链 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

Recalc consumer 对空、未知或未处理事件可返回成功并 ACK。

**预期行为**

每个事件变体必须通过 schema 校验并绑定 handler、审计 noop 或 DLQ；未知、空、缺 handler 不得成功 ACK。

**当前行为**

空 payload 直接返回 True；多个已知事件在 `_dispatch_business` 中仅 print/pass；未知 event_type 没有显式拒绝，调用返回后仍视为成功。

**定位**

- 文件/类/函数/字段：`MessageConsumer/RecalcStreamConsumer.py::process_event/_dispatch_business/_reclaim_stale`
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
`if not payload_str: return True`；`RECALC_STATE_DRIFT/HIGHEST_RANK_UPDATED/SETTLEMENT_PERIOD_DONE` 分支仅 print/pass。
```

**判定理由**

ACK 表示消息已完成，但代码没有产生业务副作用或受控 disposition，直接命中 EVT-006 的失败形态。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

consumer 骨架已建，正式路由和 schema registry 未实现。

**影响分析**

- 直接影响：事件可能被静默吞掉。
- 间接影响：状态投影、晋衔和完成链不可恢复。
- 数据影响：实际丢失数量待 PEL/UAT。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：若 Stream 未被裁剪可重放；否则需权威源重建。

**修正建议**

引入版本化 envelope/schema；所有 event_type 显式路由；未知/空进入 DLQ；仅处理成功或审计 noop 后 ACK。

**建议验证**

- TC-027；空、非法JSON、array/null、unknown、两类 done。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-012A` / `REM-012B` | GENERATED |
| 施工方案 | `W-012A` / `W-012B` | GENERATED |
| 验证报告 | `V-012A` / `V-012B` | PENDING |


#### `R-013` — `多个 Redis Stream producer 固定 maxlen=100000，在 ACK 水位前裁剪`

| 属性 | 内容 |
|---|---|
| 严重级别 | `P0` |
| 关联检查项 | `CHK-EVT-007` |
| 当前状态 | `OPEN` |
| 发现类型 | `STATE` |
| 影响范围 | 重算事件保留、PEL 与 deleted-ID 恢复 |
| 是否阻断上线 | `YES` |
| 证据可信度 | `CONFIRMED_STATIC` |

**问题陈述**

多个 Redis Stream producer 固定 maxlen=100000，在 ACK 水位前裁剪。

**预期行为**

保留策略须有容量证明并与 consumer-group ACK/PEL 水位协调；被裁剪 ID 必须能从权威源恢复。

**当前行为**

Global、Global Elite、Placement Incremental、Placement Recalculation 的 XADD 均使用固定 `maxlen=100000`，多处还启用 `approximate=True`，与 ACK 水位无耦合。

**定位**

- 文件/类/函数/字段：`User/GlobalRecalculationService.py`、`User/GlobalEliteBonusRecalculationService.py`、`User/PlacementIncrementalService.py`、`User/PlacementRecalculationService.py` 的 outbox XADD
- Git commit：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 行号：不使用行号；以固定提交中的类、函数、字段和 blob 定位

**原始证据**

```text
固定提交中可直接读取 `maxlen=100000, approximate=True`；至少四类 producer 使用同一硬上限。
```

**判定理由**

消费者停机或多 group 积压超过阈值时，未 ACK 条目可先被 trim；方案明确该项不受测试阶段 checkpoint 豁免。

**复现步骤**

1. 固定读取 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 的上述文件；
2. 对照 `PLAN-PVAM-v1.15`、有效 SQL 和已关闭 DEC；
3. 检查稳定函数/字段及最小代码片段；
4. 本轮未执行真实 MySQL/Redis/Kafka/Dask/GPU 运行时复现；运行时结果仍进入第13节。

**根因分析**

经验容量常量替代了 ACK-aware retention。

**影响分析**

- 直接影响：PEL 对应原始 entry 可能成为 deleted ID。
- 间接影响：重放与审计链断裂。
- 数据影响：实际峰值和丢失需 UAT；代码风险形态已确认。
- 历史数据是否受影响：`UNVERIFIED`
- 可恢复性：当前恢复能力未证明。

**修正建议**

改为 ACK-aware/时间窗口+容量证明策略；记录 deleted IDs 并提供权威重建。

**建议验证**

- TC-028；多 group、停机、积压>100000、trim与恢复。
- 相关模块回归及干净重跑 checksum

**追踪关系**

| 后续文档 | 编号 | artifact_status |
|---|---|---|
| 本轮修改方案 | `REM-013` | GENERATED |
| 施工方案 | `W-013` | GENERATED |
| 验证报告 | `V-013` | PENDING |



---

## 8. 潜在风险

| 风险编号 | 级别 | 风险描述 | 支持证据 | 尚缺证据 | 可能影响 | 建议动作 |
|---|---|---|---|---|---|---|
| RISK-001 | P1 | `TopologyMutationService` 是否存在生产可达调用点未能由本轮完整归档独立证明 | 报告B及审查意见声称全仓仅测试引用 | 精确 source archive、部署 manifest、可复核 call graph 输出 | DEC-012 接线可能未完成 | 获取完整归档后重跑引用/部署扫描；未确认前保持风险，不升级为第14项缺陷 |
| RISK-002 | P1 | 两份报告的环境、命令和测试声称缺少原始证据包 | 报告A/B均列出具体命令或时间，但附件只有报告文本 | stdout/stderr、exit、镜像、文件SHA、测试结果XML | 可能存在误报PASS、漏报失败或基线错位 | 按第13节UAT-012重新执行并回传 |

---

## 9. 建议优化

| 建议编号 | 建议 | 收益 | 成本/风险 | 优先级 |
|---|---|---|---|---|
| OPT-001 | 将脚本式测试统一包装为可收集的 pytest/unittest，同时保留CLI smoke | 统一exit code、CI报告和证据格式 | 中 | P2 |
| OPT-002 | 自动生成检查项→证据→R/REM/W/V的机器可读manifest | 防止统计漂移与状态错配 | 低 | P3 |

---

## 10. 无法验证

| 编号 | 级别 | 待验证事项 | 无法验证原因 | 已完成部分 | 所需补充 | 对总体结论的影响 |
|---|---|---|---|---|---|---|
| UV-001 | P0 | 真实MySQL/Redis/Kafka/Dask/RAPIDS/GPU全链路 | 无环境/权限/镜像 | 核心静态证据 | DEC-013准入、固定版本、数据 | P0功能不能转PASS；不改变既有REJECTED |
| UV-002 | P0 | DEC-009 schema manifest、DDL、SQL_MODE、assignment | 未提供 | SQL/模型静态预检 | DBA批准清单和SHA | DATA-007/BIZ-009/PUB-001 BLOCKED |
| UV-003 | P0 | SQL-Python同数据差分 | 无同一数据库和数据集 | 读取E/PE/SE SQL与Python | 隔离UAT库、过程权限、固定数据 | BIZ/TEST多项维持PENDING |
| UV-004 | P0 | 事件并发、ACK、PEL、trim、崩溃恢复checksum | 无真实中间件与故障注入 | 静态发现R-008/R-012/R-013 | Redis/Kafka、故障脚本、权威重建源 | EVT项维持PENDING |
| UV-005 | P1 | 精确整仓调用图、全套测试和原始P0/T0用户确认审计包 | 未附source archive/日志/全部原始确认文本 | 具名文件、v2.25/v34登记册与两报告交叉比对 | archive、manifest、测试输出、用户决议原文 | ARCH/PUB/TEST部分项BLOCKED |

---

## 11. 已确认修复

| 历史问题编号 | 历史问题 | 当前修复证据 | 验证方式 | 结果 |
|---|---|---|---|---|
| FIX-001 | DEC-017：Elite 说明文档仍使用两项停止条件、称数量变化不触发传导、示例在 B 层停止，并保留“与送审草稿的差异”段 | `097cae32e0ff7708eb6ee69a7f2ce188e80c060c..2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` 唯一变化为该 DOCX；后继版本 blob `892640e6…` / SHA-256 `f80ea693…` 已改为三项停止条件、数量变化触发保守传导、B 层继续到 A 层，并删除差异段 | STATIC / DOCUMENT DIFF（受控后继 overlay） | CONFIRMED（P1 文档修复；不表示 CHK-BIZ-001 已执行或通过） |

---

## 12. 第三方评审意见复核

| 意见编号 | 第三方原始意见 | 独立核验证据 | 裁决 | 是否形成当前问题 | 说明 |
|---|---|---|---|---|---|
| EXT-001 | 金额版本/公共适配器缺失 | EV-CODE-001/002/013 | CONFIRMED | R-001/R-002 | 拆分为模型版本与公共实现 |
| EXT-002 | 生产金额链存在float/多scale | EV-CODE-003~006 | CONFIRMED | R-003 | 只确认代码形态；具体金额差异待UAT |
| EXT-003 | 费率/SE exact合同不一致 | EV-CODE-004/005、EV-SQL-002/003 | CONFIRMED | R-004 | PE硬编码、SE阻断均可直接读取 |
| EXT-004 | 期间硬编码 | EV-CODE-010 | CONFIRMED | R-007 | `period==1`/`period-1`成立 |
| EXT-005 | Recalc consumer假ACK | EV-CODE-009 | CONFIRMED | R-012 | 运行时PEL仍待UAT |
| EXT-006 | Elite persisted=false仍DONE | EV-CODE-007 | CONFIRMED | R-009 | 状态与发布未分层 |
| EXT-007 | Elite SOURCE非原子 | EV-CODE-003 | CONFIRMED | R-008 | 两次提交 |
| EXT-008 | Active同源现算未实现 | EV-CODE-004/005及接口 | CONFIRMED | R-005/R-006 | 避免使用“全仓getter不存在”的绝对表述 |
| EXT-009 | Unified guard零调用点 | 两报告转述；无完整call graph | RISK_ONLY | 否 | 状态覆盖分裂形成R-010；零调用点不确认 |
| EXT-010 | TopologyMutationService无生产调用点 | 报告B转述 | UNVERIFIABLE | 否 | 降为RISK-001 |
| EXT-011 | Stream trim-before-ACK | EV-CODE-007/010~012 | CONFIRMED | R-013 | 固定maxlen代码成立 |
| EXT-012 | Elite候选/writer proof缺失 | EV-CODE-002/003、EV-SQL-001 | CONFIRMED | R-011 | PV_PSS与proof不完整 |
| EXT-013 | Elite文档传播冲突已修复 | EV-GIT-001、EV-DOC-001；blob `892640e6…` / SHA-256 `f80ea693…` | FIXED | 否 | 在 `2475c6c4` 文档 overlay 已核验；仅关闭文档侧 DEC-017，不改变 CHK-BIZ-001=PENDING_TEST_ENV |

---

## 13. 测试环境待验证清单

### 13.1 验证项

| 验证编号 | 关联检查项/问题 | 测试目标 | 前置数据 | 执行步骤 | 预期结果 | 回传证据 |
|---|---|---|---|---|---|---|
| UAT-001 | CHK-DATA-001/002/003；R-001~R-003 | 金额边界、version、float/scale mutation | legacy/new Redis记录、字符串订单、极值 | 执行 TC-001~003/008，记录每阶段 dtype/units | 非法类型和未知版本 fail-loud；全链整数；SQL差分满足批准规则 | 命令、dtype快照、Redis前后、diff |
| UAT-002 | CHK-DATA-004/BIZ-007/008；R-004 | 配置矩阵 | 缺失/0/负/重复/非法 TYPE/Country | 执行 TC-004/005/017/018 | PE/SE 使用冻结配置；exact raw 与 SQL/DEC 一致 | 配置快照、parser trace、SQL/Python输出 |
| UAT-003 | CHK-DATA-006；R-005/R-006 | Active 同源现算 | 29.99/30/30.1、配置切换、五消费方 | 执行 TC-007 与各奖金差分 | 同一PV/阈值/run下各模块结果一致 | 阈值版本、trace、逐用户结果 |
| UAT-004 | CHK-DATA-005/EVT-001；R-007 | 期间与退款归期 | 非1首期、缺期、跨年、GMT+8月界 | 执行 TC-006/022 | 只由 AR_PERIOD 解析；批准时间唯一归期 | AR_PERIOD查询、事件与writer period |
| UAT-005 | CHK-BIZ-001/002/003/004 | 传播、图、Placement、TB | 合法/非法图、阈值/退款/结余、TB配置 | 执行 TC-009~013 | 三路最终状态等价；非法图先阻断；TB结果与oracle一致 | 节点快照、Redis、SQL/Python diff |
| UAT-006 | CHK-BIZ-005/006；R-008/R-011 | Elite gate、SOURCE、原子提交 | 七条gate、多订单、revision/refund | 执行 TC-014~016/026 | 候选行集一致；stats/source/outbox同成败 | Redis dump、candidate、SOURCE、故障日志 |
| UAT-007 | CHK-BIZ-010/011；R-003/R-006 | Honor/LB窗口、九代、Active和截断 | Honor窗口、大区、9代、边界金额 | 执行 TC-020/021 | SQL/Python逐层一致，金额无float | 逐层分母/率/金额 diff |
| UAT-008 | CHK-EVT-003；R-009/R-010 | 统一 guard/Epoch/发布状态 | Global/Placement/Elite组合状态、并发消息 | 执行 TC-024/029 | 冻结、排空、阻断；persisted=false不进入最终完成 | 状态时间线、offset、锁、writer proof |
| UAT-009 | CHK-EVT-004 | coverage与旧epoch replay | 多partition、各stage覆盖差异 | 执行 TC-025 | 逐stage coverage正确，新generation映射完整 | manifest、ledger、checksum |
| UAT-010 | CHK-EVT-005/006/007；R-008/R-012/R-013 | 原子提交、ACK、trim恢复 | 故障点、空/非法/unknown、多group积压>100000 | 执行 TC-026~028 | 无半提交/假ACK/永久丢失；deleted-ID可恢复 | PEL、ACK、DLQ、stream、replay日志 |
| UAT-011 | CHK-PUB-001/BIZ-009/DATA-007 | DDL、assignment、原子发布 | DEC-009批准manifest、SQL_MODE、空/非空candidate | 执行 TC-008/019/029 | DDL单位/上界正确；空结果清旧行；发布原子可见 | manifest、DDL、事务查询、checksum |
| UAT-012 | CHK-TEST-001~004 | 固定镜像全套件与回传包 | 精确source archive、依赖、原始P0/T0材料 | 执行 TC-030~032并生成证据包 | 所有测试可收集；结果与指定commit绑定；审计链完整 | archive SHA、命令/exit、报告、证据索引 |

### 13.2 环境信息要求

测试执行者必须记录：

- 分支、完整 commit、source archive/镜像 SHA；
- Python、MySQL/MariaDB、Redis、Kafka、Dask/RAPIDS/GPU版本；
- DEC-009 schema manifest、SQL_MODE、DDL导出时间与SHA；
- 配置快照和checksum，敏感值脱敏；
- 测试数据生成方式、period、event identity；
- 执行时间、执行人、任务编号、命令、退出码和完整输出；
- 数据库、Redis、Kafka、PEL/DLQ、日志的前后证据。

### 13.3 回传后的裁决规则

| 测试环境结果 | 后续动作 |
|---|---|
| 与预期一致 | 对应项更新为 PASS，记录证据并重算总体结论 |
| 与预期不一致 | 新建或更新 R-xxx，并按严重级别重新裁决 |
| 环境失败 | 标记 BLOCKED，不得判为产品缺陷或通过 |
| 数据构造错误 | 修正后重测，保留无效记录 |
| 版本不一致 | 证据作废，必须基于报告指定commit重测 |

---

## 14. SQL、文档与 Python 差异

| 差异编号 | 业务点 | 有效SQL | 文档/决议 | Python当前实现 | 裁决 | 关联问题 |
|---|---|---|---|---|---|---|
| DIFF-001 | Elite候选 | `CALC_BE_E`: `PV_PSS>0`，初始`GPV=PV_PCS` | P0-8七条gate | model无PV_PSS；writer按金额筛选 | MISMATCH | R-011 |
| DIFF-002 | PE费率 | `CALC_BE_PE`: 从AR_CONFIG取`proEliteRate` | 配置冻结/ppm合同 | 固定150000ppm | MISMATCH | R-004 |
| DIFF-003 | SE费率 | `IFNULL(MIN(VALUE),0)/100` | 缺失/0→0；负值不得仅因负阻断 | 缺失/0/负均raise | MISMATCH | R-004 |
| DIFF-004 | Active | Legacy可作对照；corrected要求同源PV+monthActivePV现算 | DEC-018 | PE裸30；服务可消费外部IS_ACTIVE | MISMATCH | R-005/R-006 |
| DIFF-005 | Period | 权威AR_PERIOD/期间状态 | DEC-006批准时间 | `period==1`、`period-1`/YYYYMM算术 | MISMATCH | R-007 |
| DIFF-006 | 财务精度 | SQL TRUNCATE/DECIMAL | micro-units/ppm/cents、禁float | float64/round//100.0 | MISMATCH | R-003 |
| DIFF-007 | Elite完成语义 | 正式结果完成后才能进入后续编排 | Epoch/publish分层 | persisted=false仍DONE/事件 | MISMATCH | R-009 |
| DIFF-008 | SOURCE | SQL正式SOURCE由期末行集产生 | P0-12原子/reconciliation | 增量hash与stats分开提交 | MISMATCH | R-008/R-011 |
| DIFF-009 | Recalc事件 | 技术协议要求受控处理/重放 | EVT-006/007 | print/pass后成功；固定maxlen | MISMATCH | R-012/R-013 |

---

## 15. 测试结果

### 15.1 自动化测试

| 测试组 | 收集数 | 通过 | 失败 | 跳过 | Characterization | 环境 | 证据 |
|---|---:|---:|---:|---:|---:|---|---|
| 两份候选报告声称的DEV测试 | 0（本轮未收集） | 0 | 0 | 0 | 0 | NOT RUN | 原始日志/精确环境未附 |
| 固定提交全套测试 | 0 | 0 | 0 | 0 | 0 | BLOCKED | UV-005 |
| UAT全链路 | 0 | 0 | 0 | 0 | 0 | PENDING_TEST_ENV | UV-001~004 |

### 15.2 差分/边界/故障注入

| 测试编号 | 类型 | 场景 | 结果 | 发现 |
|---|---|---|---|---|
| TC-000 | — | RETIRED（随 CHK-GOV-001） | NOT_RUN | RETIRED |
| TC-001 | BOUNDARY | 双缩放边界三路一致 | NOT_RUN | R-001/R-003（静态） |
| TC-002 | MUTATION | 编码矩阵突变 | NOT_RUN | R-003（静态） |
| TC-003 | BOUNDARY | 版本策略 | NOT_RUN | R-001（静态） |
| TC-004 | DIFF | 费率矩阵（含负值） | NOT_RUN | R-004（静态） |
| TC-005 | MUTATION | Country/TYPE 变体 | NOT_RUN | R-004（静态） |
| TC-006 | DIFF | 期间/归期 | NOT_RUN | R-007（静态） |
| TC-007 | DIFF | 活跃门槛/供给链 | NOT_RUN | R-005/R-006（静态） |
| TC-008 | BOUNDARY | int64 上界 | BLOCKED | 缺 schema、精确源码/测试证据包或 UAT 回传包 |
| TC-009 | DIFF | 传播场景 A/B | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-010 | DIFF | 子用例⑤等 | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-011 | MUTATION | 图完整性/拓扑变更 | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-012 | DIFF | 安置网 | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-013 | DIFF | Team Bonus oracle | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-014 | DIFF | Global 七条 | NOT_RUN | R-011（静态） |
| TC-015 | FAILURE | Elite 原子边界 | NOT_RUN | R-008（静态） |
| TC-016 | DIFF | Elite 汇总 | NOT_RUN | R-008/R-011（静态） |
| TC-017 | DIFF | PE | NOT_RUN | R-004/R-005/R-006（静态） |
| TC-018 | DIFF | SE | NOT_RUN | R-004（静态） |
| TC-019 | DIFF | EAB | BLOCKED | 缺 schema、精确源码/测试证据包或 UAT 回传包 |
| TC-020 | DIFF | Honor | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-021 | DIFF | Leadership | NOT_RUN | R-003/R-006（静态） |
| TC-022 | FAILURE | 退款账本/归期/duplicate | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-023 | FAILURE | coverage 账本 | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-024 | FAILURE | 守卫/状态机负向 | NOT_RUN | R-009/R-010（静态） |
| TC-025 | FAILURE | manifest/replay | NOT_RUN | 无；待 UAT/固定 DEV 镜像 |
| TC-026 | FAILURE | Redis 权威提交注入 | NOT_RUN | R-008（静态） |
| TC-027 | FAILURE | 消费者 ACK/DLQ | NOT_RUN | R-012（静态） |
| TC-028 | FAILURE | 保留/deleted-ID 恢复 | NOT_RUN | R-013（静态） |
| TC-029 | FAILURE | 正式发布/空 candidate | BLOCKED | 缺 schema、精确源码/测试证据包或 UAT 回传包 |
| TC-030 | STATIC | 读取入口/时序保真 | BLOCKED | 缺 schema、精确源码/测试证据包或 UAT 回传包 |
| TC-031 | MUTATION | 套件真实性 | BLOCKED | 缺 schema、精确源码/测试证据包或 UAT 回传包 |
| TC-032 | DIFF | Loop 回传核对 | BLOCKED | 缺 schema、精确源码/测试证据包或 UAT 回传包 |

### 15.3 测试可信度说明

- 测试是否直接导入生产类/函数：`本轮未执行，无法确认`
- 是否过度 mock 核心计算：`本轮未执行，无法确认`
- 是否验证失败路径：`NO`
- 是否验证持久化结果：`NO`
- 是否验证幂等/重复执行：`NO`
- 是否包含 Characterization 测试：`两报告有相关描述，但原始输出未附，终稿不将其登记为已执行`

---

## 16. 剩余风险与上线条件

### 16.1 剩余风险

| 风险 | 发生可能性 | 影响 | 接受人 | 缓解措施 | 截止时间 |
|---|---|---|---|---|---|
| legacy与micro-units混入同一计算域 | HIGH | 数量级污染 | 技术/数据负责人 | 关闭R-001~R-003并重建对账 | 上线前 |
| 配置/Active/Period不可重放 | HIGH | 奖金资格和周期错位 | 业务/技术负责人 | 关闭R-004~R-007 | 上线前 |
| Elite假完成或SOURCE半提交 | HIGH | 正式结果不一致 | 结算负责人 | 关闭R-008~R-011，执行故障注入 | 上线前 |
| 消息假ACK/Stream裁剪 | HIGH | 事件永久丢失 | 平台负责人 | 关闭R-012/R-013，完成TC-027/028 | 上线前 |
| 测试与审计包不完整 | HIGH | 无法证明生产就绪 | 项目负责人 | 落实DEC-013和UAT-012 | 上线前 |

### 16.2 上线前置条件

- [ ] 关闭 R-001～R-013，或由有权限责任人书面接受非P0风险；
- [ ] 提供并批准 DEC-009 schema manifest、SQL_MODE 与DDL证据；
- [ ] 完成 UAT-001～UAT-012及对应回传包；
- [ ] SQL-Python同数据差分满足 Legacy/approved-corrected 双模式要求；
- [ ] 完成数据备份、干净重跑、回滚与恢复演练；
- [ ] Gate C 从 OPEN 转为有证据的通过状态；
- [ ] 技术负责人、业务负责人正式签署。

### 16.3 回滚触发条件

- 任一金额字段出现未知version、float或单位不明；
- SQL-Python金额/行集差异超出已批准差异；
- persisted=false却出现最终完成/下游读取；
- stats/SOURCE/outbox/checkpoint不一致；
- 未处理事件被ACK、PEL出现不可恢复deleted ID；
- 重跑checksum不一致或出现重复发放。

---

## 17. 后续处置建议

复核报告只提出处置建议，不直接授权修改。

| 问题/风险 | 建议处置 | 建议进入本轮 | 理由 | 责任角色 |
|---|---|---|---|---|
| R-001～R-003 | FIX | YES | 金额域基础阻断 | 架构/数据/开发 |
| R-004～R-007 | FIX | YES | 配置、Active、Period影响全奖项 | 业务架构/开发 |
| R-008～R-011 | FIX | YES | Elite原子、发布、guard与writer阻断 | 结算架构/开发 |
| R-012～R-013 | FIX + UAT_VERIFY | YES | 消息丢失与恢复风险 | 平台/消息开发 |
| RISK-001 | UAT_VERIFY | YES | 生产可达性证据不足 | 代码/部署负责人 |
| RISK-002 | PROVIDE_EVIDENCE | YES | 防止继承虚假测试结果 | QA/执行人 |
| UV-002 | PROVIDE_SCHEMA_MANIFEST | YES | 解除3项核心BLOCKED | DBA/架构 |
| UV-005 | PROVIDE_EXACT_ARCHIVE_AND_AUDIT_PACK | YES | 解除PUB/TEST/Loop阻塞 | 代码/QA/业务 |
| DEC-013 | ENABLE_UAT | YES | 14项等待真实环境 | 平台/项目负责人 |

后续《本轮修改方案》应对每项作出 `ACCEPTED / REJECTED / DEFERRED / NEEDS_DECISION / UAT_VERIFY` 的正式决定。

---

## 18. 最终签署

### 18.1 复核人声明

本人确认：

- 结论仅依据本报告列明并实际读取的材料；
- 已区分静态代码形态、文档交叉比对与实际运行测试；
- 未继承两份报告中缺少原始输出的测试通过声称；
- 未把纯UAT检查项仅凭静态证据标为PASS或最终FAIL；
- 已确认错误均有固定提交、真实文件和稳定定位；
- 统计数字与第6节逐项一致。

| 角色 | 姓名 | 结论 | 日期 | 备注 |
|---|---|---|---|---|
| 复核人 | AI Agent（QA 架构与事实核验角色） | REJECTED | 2026-08-04 | F-01～F-07、G2-01～G2-04 已完成核验与定点修订；等待人工签署 |
| 技术负责人 | 待签署 | — | — | 需审核证据与修正方案 |
| 业务负责人 | 待签署 | — | — | 已关闭DEC不在本报告回改 |

---

## 附录 A：证据索引

| 证据编号 | 类型 | 来源 | 版本/时间 | 内容摘要 | 完整性 |
|---|---|---|---|---|---|
| EV-MRG-001 | DOC | 报告A | v1.0 / 2026-08-03 | 10项P0、0 PASS、受限执行声称 | COMPLETE |
| EV-MRG-002 | DOC | 报告B | v1.0 / 2026-08-03 | 13项缺陷、2 PASS、完整克隆声称 | COMPLETE |
| EV-MRG-003 | DOC | 复核报告模板 | 用户附件 | 18节与证据纪律 | COMPLETE |
| EV-MRG-004 | DOC | PLAN-PVAM-v1.15 | 2026-08-02 | 35检查项、33用例、DEC与判定 | COMPLETE |
| EV-MRG-005 | DOC | 执行任务书 | 2026-08-03 | DEV/UAT分类、schema门禁 | COMPLETE |
| EV-REV-001 | DOC | 复核报告 v1.1 审查意见 | 2026-08-04 | F-01～F-07 与独立复验声明 | COMPLETE |
| EV-REV-002 | DOC | 复核报告 v1.2 二轮审查意见 | 2026-08-04 | G2-01～G2-04 与独立复验声明 | COMPLETE |
| EV-REG-001 | DOC | v2.25 §十一/§十二 P0/T0 登记册 | Final v2.25-d74 | 权威编号、主题与分层状态 | COMPLETE |
| EV-GIT-001 | QUERY | `097cae32..2475c6c4` commit compare | 2026-08-04 核验 | 唯一变化为 DEC-017 DOCX | COMPLETE |
| EV-DOC-001 | DOC | `Doc/Elite_Bonus_发奖规则说明.docx` | `2475c6c4` / 当前blob重新取证 | 三条件停止、保守传导、示例改写及删除段 | COMPLETE |
| EV-CODE-001~012 | CODE | 固定提交具名Python文件 | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` | 模型、金额、Active、Period、Elite、guard、consumer、Stream | COMPLETE（具名范围） |
| EV-CODE-013 | QUERY | `Common/PvAmount.py` | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` | 路径不存在 | COMPLETE |
| EV-SQL-001~003 | SQL | CALC_BE_E/PE/SE_COUNTRY | `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` | 候选、费率、TRUNCATE | COMPLETE |
| UV-001~005 | MISSING | 环境/schema/archive/audit pack | 本轮 | 无法验证边界 | PARTIAL |

## 附录 B：问题追踪矩阵

| 检查项 | 发现 | 处置项 | 施工项 | 验证项 | 当前闭环状态 |
|---|---|---|---|---|---|
| CHK-DATA-001/003/EVT-002 | R-001 | REM-001 | W-001 | V-001 | OPEN |
| CHK-ARCH-003 | R-002 | REM-002 | W-002 | V-002 | OPEN |
| CHK-DATA-001/CHK-DATA-002/CHK-ARCH-003/CHK-BIZ-011 | R-003 | REM-003 | W-003 | V-003 | OPEN |
| CHK-DATA-004/BIZ-007/008 | R-004 | REM-004 | W-004 | V-004 | OPEN |
| CHK-DATA-006/CHK-BIZ-007 | R-005 | REM-005 | W-005 | V-005 | OPEN |
| CHK-DATA-006/CHK-BIZ-007/CHK-BIZ-008/CHK-BIZ-009/CHK-BIZ-011 | R-006 | REM-006 | W-006 | V-006 | OPEN |
| CHK-DATA-005 | R-007 | REM-007 | W-007 | V-007 | OPEN |
| CHK-BIZ-006/EVT-005 | R-008 | REM-008 | W-008 | V-008 | OPEN |
| CHK-BIZ-006/EVT-003/PUB-001 | R-009 | REM-009 | W-009 | V-009 | OPEN |
| CHK-ARCH-002/EVT-003 | R-010 | REM-010 | W-010 | V-010 | OPEN |
| CHK-BIZ-005/006/PUB-001 | R-011 | REM-011 | W-011 | V-011 | OPEN |
| CHK-ARCH-002/CHK-EVT-006 | R-012（父项） | REM-012 | W-012 | V-012 | OPEN |
| CHK-ARCH-002/CHK-EVT-006/CHK-EVT-007/CHK-TEST-001/CHK-TEST-003 | R-012A（紧急ACK子项） | REM-012A | W-012A | V-012A | OPEN |
| CHK-ARCH-002/CHK-EVT-006/CHK-EVT-007/CHK-TEST-003 | R-012B（最终路由子项） | REM-012B | W-012B | V-012B | OPEN |
| CHK-EVT-007 | R-013 | REM-013 | W-013 | V-013 | OPEN |
| CHK-BIZ-002 | RISK-001 | — | — | UAT-005/012 | OPEN |
| CHK-DATA-007/BIZ-009/PUB-001 | UV-002 | — | — | UAT-011 | BLOCKED |

## 附录 C：报告自检清单

- [x] 待审版本和 commit 唯一、明确；
- [x] 已读取与未读取材料分别列出；
- [x] 排除项未被用于证明当前缺陷；
- [x] 所有 PASS 都有证据（本报告主状态无 PASS）；
- [x] 所有 FAIL 都有关联问题；
- [x] 所有已确认错误都有文件、稳定定位、原始证据和判定理由；
- [x] v1.4已更正历史版本中的3个错误函数名，当前活动锚点均在固定基线存在；
- [x] 静态检查未描述为运行测试；
- [x] 第三方意见已独立复核；
- [x] 后继文档修复已与代码实现状态分层登记；
- [x] 开发环境和测试环境验证边界明确；
- [x] 统计数字与明细一致；
- [x] P0 矩阵含 P0-2B-OPS、P0-3-TIME，且决议状态与实现状态分层；
- [x] 代码证据索引仅使用 `EV-CODE-001～013`；F-05/G2-03 点名的 R↔CHK 不对称已修复；
- [x] 最终结论符合检查方案判定规则。
