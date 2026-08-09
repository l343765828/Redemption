# WORK-PVAM-01C Flag Runtime Contract 与 Redis 原子配置施工任务书

> 本文档来源于待组织批准的 `TASK-PVAM-01C`；技术合同已由 DEC-019 固化，但组织施工授权、真实 UAT 与 Gate C 仍保持独立。

## 0. 填写与执行规则

1. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`。
2. 治理 validator 未全部 0 退出前，禁止编辑本卡 production 文件。
3. 只允许修改 §6 与 `WORK_SCOPE_ALLOWLIST.json` 登记的路径。
4. fake/stub 只形成 DEV 证据，真实 Redis UAT 继续由 WORK-PVAM-08/DEC-013 控制。

## 1. 文档信息与追溯关系

| 项目 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-01C` |
| 来源修改任务 | `TASK-PVAM-01C` |
| 来源检查项 | `CHK-ARCH-001、CHK-ARCH-003、CHK-DATA-003、CHK-EVT-003、CHK-TEST-003、CHK-TEST-004` |
| 来源问题 | `GAP-PVAM-FLAG-CONTRACT` |
| 关联决策 | `DEC-019` |
| 复核闭环追踪号 | `REM-014 / W-014 / V-014` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 文档版本 | `v1.3` |
| 文档状态 | `DRAFT` |
| 实施状态 | `BLOCKED` |
| 验证状态 | `NOT_RUN / PENDING_TEST_ENV` |

## 2. 施工目标与完成定义

- 在 `Redishelper` 建立唯一 Provider 和 MANUAL_BOOTSTRAP，不在 Common 或业务 Service 内复制配置 I/O。
- Provider 单次 Lua 原子读取 active pointer 与 versioned snapshot，严格解析 immutable run config。
- production admission 明确实现 00/01/10/11；当前不存在 11 production approval。
- run session 在开始时加载一次并冻结；无 refresh、无 stale cache。
- Bootstrap 使用 Lua/CAS 完成 strictly monotonic version 判断、snapshot 写入和 pointer 切换，并 read-after-write verify。

完成必须同时满足：TC-FLAG-01～13、22、23 在相应 DEV/UAT 边界有真实结果；不存在 fallback；scope 与治理 validator 通过。TC-FLAG-14～21 由条件化后的 WORK-PVAM-01 承接。

## 3. 当前事实与复用决定

| 检查对象 | 事实 | 决定 |
|---|---|---|
| `Redishelper/BaseRedisModel.py` | 已有项目 Redis 连接 | Provider 延迟复用该连接，并允许测试注入 fake client |
| ConfigService/revision/CAS | 未发现适用实现 | 本卡只为 PV amount flag 定义 versioned snapshot，不建立第二套通用配置框架 |
| run context | 未发现统一实现 | 在 Provider 文件内提供 frozen run session/admission；后续 WORK-PVAM-01 入口传递同一 config |
| Redis transaction helpers | pipeline/lock 存在，但无配置 CAS | 使用 Redis Lua 单原子边界，避免 GET→SET TOCTOU |

## 4. Redis 合同

### 4.1 Key 与 schema

| Key | 类型 | 内容 |
|---|---|---|
| `pvam:amount_config:active` | string | `config_version:checksum` |
| `pvam:amount_config:snapshot:<config_version>` | hash | READ、WRITE、config_version、load_mode、source、checksum |

canonical payload 至少为：

```json
{
  "PV_AMOUNT_V2_READ": "false",
  "PV_AMOUNT_V2_WRITE": "true",
  "config_version": "1",
  "load_mode": "MANUAL_BOOTSTRAP",
  "source": "AR_CONFIG"
}
```

### 4.2 原子读取与发布

- load Lua 在一个 Redis 执行边界内读取 pointer 与对应 hash；pointer/version/checksum 任一不一致即 fail-loud。
- publish Lua 在同一执行边界校验 active version、创建不可变 snapshot、切 pointer；`new_version <= active_version` 为 `STALE_CONFIG_VERSION`。
- 第一次发布只允许 active 不存在的 explicit initial-create；version 仍必须是非负整数。
- Provider/Bootstrap 不接受 env、常量默认、AR_CONFIG 直查或 cached stale fallback。

### 4.3 State admission 与 run-freeze

| 状态 | production admission |
|---|---|
| 00 | 允许，Legacy authoritative |
| 01 | 允许，当前批准配置；Legacy authoritative |
| 10 | `INVALID_STATE` |
| 11 | 当前 `V2_STATE_NOT_AUTHORIZED` |

`PVAmountRunSession.start(provider)` 是 production admission 边界；返回对象及其 config 均 immutable，不公开 refresh。运行期间 Provider 变化只影响下一次 start。

## 5. 分阶段依赖

- Phase A：本卡 Provider/bootstrap 与 TC-FLAG-01～13/22/23，无前置 production WORK。
- WORK-PVAM-01：在 Phase A 接口可用后，条件化 AC-02/AC-03 与 CHG-05～08，接入同一 run config。
- Phase B：在组合树执行 TC-FLAG-14～21 和全量 factory 扫描；这不是新的 production scope。

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 符号 | 类型 | 合同 |
|---|---|---|---|---|
| CHG-01C-01 | `Redishelper/PVAmountConfigProvider.py` | `PVAmountRunConfig`、`PVAmountConfigProvider.load_run_config` | 新增 | immutable、atomic load、strict parse、fail-loud |
| CHG-01C-02 | `Redishelper/PVAmountConfigProvider.py` | `PVAmountRunSession.start`、production admission | 新增 | 00/01允许、10拒绝、未批准11拒绝、run-freeze |
| CHG-01C-03 | `Redishelper/PVAmountConfigBootstrap.py` | `publish_manual_bootstrap`、CLI | 新增 | 原子发布01、stale protection、read-after-write、失败非零 |
| CHG-01C-04 | `tests/pvam/WORK-PVAM-01C/` | provider/bootstrap tests | 新增 | fake/in-memory DEV；真实 Redis 不伪造 |

禁止修改：`Common/PvAmount.py`、现有业务 Service、共享 Redis model 字段、奖金公式、AR_CONFIG→Delta producer。

## 7. 可执行施工步骤

### STEP-PVAM-01C-01：实现 snapshot 解析与 Provider

- 新建 frozen dataclass、错误类型、canonical bool/version/checksum 校验。
- 单次 Lua 读取 pointer + hash；Redis 异常统一 fail-loud，保留 cause。
- 禁止任何 fallback 或直接 AR_CONFIG/env 读取。

### STEP-PVAM-01C-02：实现 admission 与 run-freeze

- 实现 00/01/10/11 状态机。
- `PVAmountRunSession.start` 只调用 Provider 一次；session 无 refresh。
- 当前 production admission 不提供 test-only 或 11 approval bypass。

### STEP-PVAM-01C-03：实现 MANUAL_BOOTSTRAP

- CLI 接受显式 `config_version`，固定当前批准 READ=false/WRITE=true。
- Lua/CAS 原子发布 versioned snapshot + pointer；stale/conflict 失败。
- Provider read-after-write verify；任一失败非零退出。

### STEP-PVAM-01C-04：补齐 DEV/UAT 分层测试

- fake client 覆盖结构、异常、状态、冻结、stale、并发。
- AST 扫描 production consumer 无直接 flag GET/env/default。
- 隔离 Redis 未提供时，相关真实环境项保持 PENDING_TEST_ENV。

## 8. 数据与回滚

- Snapshot append-only；不删除已发布 version。
- 回滚通过发布更高 version 的合法 00/01 snapshot，不倒拨 config_version。
- 不允许部分字段更新或直接改 active snapshot。
- 任何需要新 V2 carrier 的行为以 `V2_CARRIER_NOT_APPROVED` 停工。

## 9. 测试设计

### 9.1 测试用例总表

| 测试编号 | 场景 | 精确预期 | 环境 | 状态 |
|---|---|---|---|---|
| TC-FLAG-01 | 合法01 load | immutable config 为 false/true/version | DEV+UAT | NOT_RUN |
| TC-FLAG-02 | snapshot 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-03 | READ 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-04 | WRITE 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-05 | version 缺失 | fail-loud | DEV | NOT_RUN |
| TC-FLAG-06 | 非法bool | fail-loud | DEV | NOT_RUN |
| TC-FLAG-07 | 状态10 | `INVALID_STATE` | DEV | NOT_RUN |
| TC-FLAG-08 | Provider exception | 无 AR_CONFIG/env/default fallback | DEV | NOT_RUN |
| TC-FLAG-09 | run中途01→11 | 当前 run 保持01 | DEV | NOT_RUN |
| TC-FLAG-10 | 下一 run 读未批准11 | `V2_STATE_NOT_AUTHORIZED` | DEV | NOT_RUN |
| TC-FLAG-11 | pointer/snapshot 跨version | fail-loud | DEV | NOT_RUN |
| TC-FLAG-12 | bootstrap发布01 | 单一原子提交并校验 | DEV+UAT | NOT_RUN |
| TC-FLAG-13 | consumer静态扫描 | 无直接 Redis flag GET | DEV | NOT_RUN |
| TC-FLAG-22 | stale publish | N/N-1 均失败 | DEV+UAT | NOT_RUN |
| TC-FLAG-23 | 并发 publish | 至多一个成功且 active 为较新合法 version | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-003, TC-024, TC-031, TC-032`。`TC-FLAG` 为本决策局部测试编号。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set WORK-PVAM-01C implementation commit}"
: "${PARENT_COMMIT_SHA:?set controlled parent}"
: "${PARENT_TREE_SHA:?set controlled parent tree}"
: "${PARENT_PROVENANCE_JSON:?set parent provenance}"
bash 05_CONTROL/check_baseline_preflight.sh --repo "$PWD" --base "$BASE_SHA" --work-id WORK-PVAM-01C
bash 05_CONTROL/validate_work_dev.sh \
  --repo "$PWD" --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" --work-id WORK-PVAM-01C \
  --scope "$PVAM_CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$PVAM_CONTROL_ROOT/work-test-commands/WORK-PVAM-01C.sh" \
  --out evidence/WORK-PVAM-01C/dev
```

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 合法 01 snapshot 原子加载成功并返回 immutable run config | STEP-PVAM-01C-01 | TC-FLAG-01 | EV-PVAM-01C-01 | DEV+UAT | 精确值、原子读取与不可变性成立 |
| AC-02 | active snapshot 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-02 | EV-PVAM-01C-01 | DEV | 无返回 config |
| AC-03 | READ 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-03 | EV-PVAM-01C-01 | DEV | 无 fallback |
| AC-04 | WRITE 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-04 | EV-PVAM-01C-01 | DEV | 无 fallback |
| AC-05 | config_version 缺失时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-05 | EV-PVAM-01C-01 | DEV | 无默认 version |
| AC-06 | 非 canonical bool 时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-06 | EV-PVAM-01C-01 | DEV | 非法值拒绝 |
| AC-07 | 状态 10 在 production admission 抛 `INVALID_STATE` | STEP-PVAM-01C-02 | TC-FLAG-07 | EV-PVAM-01C-02 | DEV | 不自动修正 |
| AC-08 | Provider 异常时不存在 AR_CONFIG/env/default fallback | STEP-PVAM-01C-01 | TC-FLAG-08 | EV-PVAM-01C-02 | DEV | 原异常链可审计 |
| AC-09 | run 加载 01 后 Redis 变 11，当前 run 仍固定 01 | STEP-PVAM-01C-02 | TC-FLAG-09 | EV-PVAM-01C-02 | DEV | Provider 仅调用一次 |
| AC-10 | 下一 production run 加载 11 且无正式 approval 时抛 `V2_STATE_NOT_AUTHORIZED` | STEP-PVAM-01C-02 | TC-FLAG-10 | EV-PVAM-01C-02 | DEV | test-only 不旁路 |
| AC-11 | active pointer 与 snapshot 跨 version 或 checksum 不一致时 fail-loud | STEP-PVAM-01C-01 | TC-FLAG-11 | EV-PVAM-01C-01 | DEV | 无部分 snapshot |
| AC-12 | bootstrap 以单一原子操作发布完整 01 并 read-after-write verify | STEP-PVAM-01C-03 | TC-FLAG-12 | EV-PVAM-01C-03 | DEV+UAT | 失败非零 |
| AC-13 | production consumer 无直接 Redis flag GET | STEP-PVAM-01C-04 | TC-FLAG-13 | EV-PVAM-01C-04 | DEV | AST 扫描零命中 |
| AC-14 | 当前 version=N 时发布 N 或 N-1 均抛 `STALE_CONFIG_VERSION` | STEP-PVAM-01C-03 | TC-FLAG-22 | EV-PVAM-01C-03 | DEV+UAT | active 不变 |
| AC-15 | 两个并发 bootstrap 至多一个成功，active version 为较新合法版本且无 lost update | STEP-PVAM-01C-03/04 | TC-FLAG-23 | EV-PVAM-01C-03 | DEV+UAT | CAS 结果确定 |

## 11. 风险、停工与回滚

- Redis client 不支持 Lua/EVAL 或无法证明 server-side atomicity：停工。
- 发现适用的既有统一 config revision/CAS：回到治理卡评估复用，禁止并存竞争版本机制。
- 需要独立 V2 carrier/keyspace：`V2_CARRIER_NOT_APPROVED`。
- 真实 Redis 不可用：DEV 可继续，UAT 保持 `PENDING_TEST_ENV`。

## 12. 交付物与完成证据

| 证据编号 | 内容 | 状态 |
|---|---|---|
| EV-PVAM-01C-01 | snapshot schema、atomic load 与 fail-loud 测试 | PENDING |
| EV-PVAM-01C-02 | 00/01/10/11 admission 与 run-freeze 测试 | PENDING |
| EV-PVAM-01C-03 | bootstrap stale/CAS/concurrency 测试 | PENDING |
| EV-PVAM-01C-04 | direct GET/fallback/static scan 与 DEV 报告 | PENDING |
| EV-PVAM-01C-P01 | scope、patch、parent provenance、命令/exit/SHA 包 | PENDING |

## 13. 执行记录

| 项目 | 当前状态 |
|---|---|
| 实际修改 | 待执行 |
| DEV | NOT_RUN |
| 真实 Redis UAT | PENDING_TEST_ENV |
| Gate C | OPEN |

## 14. 版本记录

| 版本 | 日期 | 变更内容 | 变更原因/来源 | 编制人 | 批准状态 |
|---|---|---|---|---|---|
| v1.3-r10 | 2026-08-08 | 新建 flag runtime Provider、atomic bootstrap、admission 与 run-freeze 施工卡 | `DEC-019 / TASK-PVAM-01C` | AI Agent（编制） | DRAFT |
