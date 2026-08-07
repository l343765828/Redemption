# TRACEABILITY_MANIFEST v3

- 基线：`2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`
- 规范 JSON：`TRACEABILITY_MANIFEST.json`
- 校验器：`validate_traceability_v3.py`
- 状态：文档与控制资产可静态核验；代码、DEV、UAT 与生产状态不由本清单自动升格。

## 上游元数据双向等价合同

对每个 TASK/WORK，校验器分别聚合其全部核心与非核心执行边，并强制：

```text
文档 source_checks  == 对应执行边 checks 并集
文档 source_issues  == 对应执行边 issue_id/item_id 并集
文档 decisions      == 对应执行边 decisions 并集
```

`R-012A/R-012B` 的 `parent_issue_id=R-012` 同时计入合法 `source_issues`；除此之外，任何仅写入 TASK/WORK 元数据、但未被执行边引用的 CHK/R/DEC 均为反向孤儿并以非零退出拦截。JSON 中的 `task_contracts`、`work_contracts` 只是文档解析镜像，不能替代执行边连接。

## 跨层权威双向等价合同

每条核心执行边还必须同时满足下列上游继承关系；同步篡改 edge、TASK、WORK 与 JSON 镜像不能改变权威来源：

```text
edge.checks == REPORT 对应 R/R-012A/R-012B 的权威 CHK 集合
按顶层 R 聚合的 edge.task_id 集合 == MODPLAN 对应 R 的 TASK 分配集合
WORK.来源修改任务 == edge.task_id == WORK 编号对应的同号 TASK
```

`R-012A/R-012B` 以 `parent_issue_id=R-012` 回归 MODPLAN 父项，并要求两条子边聚合后的 TASK 集合精确等于 MODPLAN 的 `07A/07B` 分配。非核心边同样必须满足 WORK 来源 TASK 与 edge TASK 一致。三类负例 `false_report_check_edge`、`wrong_issue_task_route`、`wrong_task_work_pair` 均由 `selftest_traceability_v3.sh` 定向拦截。

## 核心问题八级边

| CHK | Issue | Parent | DEC | TASK | WORK | REM/W/V | STEP/TC/EV |
|---|---|---|---|---|---|---|---|
| CHK-DATA-001、CHK-DATA-003、CHK-EVT-002 | R-001 | — | DEC-002、DEC-008、DEC-014 | TASK-PVAM-01 | WORK-PVAM-01 | REM-001/W-001/V-001 | 5/6/15 |
| CHK-ARCH-003 | R-002 | — | DEC-002、DEC-008、DEC-014 | TASK-PVAM-01 | WORK-PVAM-01 | REM-002/W-002/V-002 | 5/6/15 |
| CHK-DATA-001、CHK-DATA-002、CHK-ARCH-003、CHK-BIZ-011 | R-003 | — | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | TASK-PVAM-02 | WORK-PVAM-02 | REM-003/W-003/V-003 | 7/8/17 |
| CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008 | R-004 | — | DEC-001、DEC-002、DEC-003、DEC-009、DEC-014 | TASK-PVAM-03 | WORK-PVAM-03 | REM-004/W-004/V-004 | 6/7/15 |
| CHK-DATA-006、CHK-BIZ-007 | R-005 | — | DEC-004、DEC-016、DEC-018 | TASK-PVAM-04 | WORK-PVAM-04 | REM-005/W-005/V-005 | 5/8/16 |
| CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011 | R-006 | — | DEC-004、DEC-016、DEC-018 | TASK-PVAM-04 | WORK-PVAM-04 | REM-006/W-006/V-006 | 5/8/16 |
| CHK-DATA-005 | R-007 | — | DEC-002、DEC-005、DEC-006、DEC-007、DEC-010 | TASK-PVAM-02 | WORK-PVAM-02 | REM-007/W-007/V-007 | 7/8/17 |
| CHK-BIZ-006、CHK-EVT-005 | R-008 | — | DEC-007、DEC-008、DEC-011、DEC-017 | TASK-PVAM-05 | WORK-PVAM-05 | REM-008/W-008/V-008 | 6/8/16 |
| CHK-BIZ-006、CHK-EVT-003、CHK-PUB-001 | R-009 | — | DEC-007、DEC-008、DEC-010、DEC-012 | TASK-PVAM-06 | WORK-PVAM-06 | REM-009/W-009/V-009 | 6/9/18 |
| CHK-ARCH-002、CHK-EVT-003 | R-010 | — | DEC-007、DEC-008、DEC-010、DEC-012 | TASK-PVAM-06 | WORK-PVAM-06 | REM-010/W-010/V-010 | 6/9/18 |
| CHK-BIZ-005、CHK-BIZ-006、CHK-PUB-001 | R-011 | — | DEC-007、DEC-008、DEC-011、DEC-017 | TASK-PVAM-05 | WORK-PVAM-05 | REM-011/W-011/V-011 | 6/8/16 |
| CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003 | R-012A | R-012 | DEC-010 | TASK-PVAM-07A | WORK-PVAM-07A | REM-012A/W-012A/V-012A | 4/7/13 |
| CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-003 | R-012B | R-012 | DEC-007、DEC-010 | TASK-PVAM-07B | WORK-PVAM-07B | REM-012B/W-012B/V-012B | 6/9/15 |
| CHK-EVT-007 | R-013 | — | DEC-007、DEC-010 | TASK-PVAM-07B | WORK-PVAM-07B | REM-013/W-013/V-013 | 6/9/15 |

## 非核心问题域

| Item | Domain | Status | TASK | WORK |
|---|---|---|---|---|
| RISK-001 | RISK | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| RISK-002 | RISK | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| UV-001 | UV | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| UV-002 | UV | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| UV-003 | UV | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| UV-004 | UV | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| UV-005 | UV | UAT_VERIFY | TASK-PVAM-08 | WORK-PVAM-08 |
| OPT-001 | OPT | ACCEPTED | TASK-PVAM-08 | WORK-PVAM-08 |
| OPT-002 | OPT | ACCEPTED | TASK-PVAM-08 | WORK-PVAM-08 |
| GAP-DEC004-2B | GAP | DEFERRED | TASK-PVAM-08 | WORK-PVAM-08 |
| FIX-001 | FIX | CONFIRMED_CLOSED | — | — |

## 受控 TC 映射

| WORK | 受控 TC 数 | 本地 TC 数 |
|---|---:|---:|
| WORK-PVAM-01 | 7 | 6 |
| WORK-PVAM-02 | 17 | 8 |
| WORK-PVAM-03 | 6 | 7 |
| WORK-PVAM-04 | 10 | 8 |
| WORK-PVAM-05 | 11 | 8 |
| WORK-PVAM-06 | 9 | 9 |
| WORK-PVAM-07A | 3 | 7 |
| WORK-PVAM-07B | 8 | 9 |
| WORK-PVAM-08 | 32 | 9 |

> 受控 TC 并集必须精确等于 PLAN 活动集合 `TC-001～TC-032`；`TC-000` 为 RETIRED。
