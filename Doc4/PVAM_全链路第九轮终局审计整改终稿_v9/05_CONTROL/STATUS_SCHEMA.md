# PVAM 状态 Schema v3

## 文档治理状态

`DRAFT | APPROVED | SUPERSEDED`

## 组织授权状态

`PENDING_ORGANIZATIONAL_APPROVAL | APPROVED_FOR_CONSTRUCTION | REVOKED`

## 实施状态

`NOT_STARTED | IN_PROGRESS | BLOCKED | COMPLETED | ROLLED_BACK`

## validation_status

仅用于测试、验证、环境准入和 Gate：

`NOT_RUN | PASS | FAIL | PENDING_TEST_ENV | BLOCKED`

## artifact_status

仅用于 patch、manifest、日志、报告等工件生命周期：

`PENDING | GENERATED | VERIFIED | REJECTED | SUPERSEDED`

## 强制规则

1. 证据或验证合同不得使用无域限定的 `status` 表达 `BLOCKED/PENDING/PASS`；必须写 `validation_status` 或 `artifact_status`。
2. 环境不足只能使用 `validation_status=PENDING_TEST_ENV` 或 `validation_status=BLOCKED`。
3. 尚未生成的工件使用 `artifact_status=PENDING`；不得据此改变验证状态。
4. 文档批准、代码实施、DEV、UAT 与生产 Gate 为不同状态域，禁止相互替代。
