# TASK-PVAM-01C Flag Runtime Contract 与 Redis 原子配置

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 任务编号 | `TASK-PVAM-01C` |
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 文档版本 | `v1.2` |
| 文档状态 | `DRAFT` |
| 授权状态 | `PENDING_ORGANIZATIONAL_APPROVAL` |
| 来源检查项 | `CHK-ARCH-001、CHK-ARCH-003、CHK-DATA-003、CHK-EVT-003、CHK-TEST-003、CHK-TEST-004` |
| 来源问题 | `GAP-PVAM-FLAG-CONTRACT` |
| 关联决策 | `DEC-019` |
| 处置项 | `REM-014` |
| 施工项 | `W-014` |
| 验证项 | `V-014` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |

## 2. 已核实事实与任务目标

### 2.1 已核实事实

- 现有 `Redishelper/BaseRedisModel.py` 提供项目 Redis 连接；仓库没有可复用的 flag ConfigService、配置 revision/epoch 或配置 CAS primitive。
- 现有 settlement/recalculation 入口拥有各自 `run_id`，但没有统一 PV amount flag run context。
- 原 WORK-PVAM-01 的机器 allowlist 不含 Config Provider、Redis runtime loader、MANUAL_BOOTSTRAP 或 run admission 文件。
- 当前执行台账真实存在的 `BLOCK-PVAM-01-FLAG-CONTRACT` 已在本轮治理接线、三个主 validator 与 `selftest_all_controls.sh` 全部 0 退出后解除；该解除仅允许进入 WORK-PVAM-01C 实现，不等于组织授权、生产 11、Gate C 或 UAT 通过。仓库中未发现需被本决策替换的旧 `USER-DECISION-PVAM-01-FLAG`。

### 2.2 目标

1. 复用现有 Redis 连接，在 infrastructure 层建立唯一 `PVAmountConfigProvider.load_run_config()`。
2. 返回 immutable `PVAmountRunConfig(read_v2, write_v2, config_version)`，并保留 active pointer/checksum 原子性证明。
3. 建立生产 run admission 与 run-freeze：每个 run 只加载一次，运行途中不刷新。
4. 建立 MANUAL_BOOTSTRAP，原子发布当前批准状态 01，并拒绝 stale version/lost update。
5. 提供 DEV stub/fake 与隔离 Redis UAT 的分层证据，禁止 fake 冒充真实 UAT。

## 3. 正式运行合同

### 3.1 Source of Truth 与 Provider

```text
AR_CONFIG（业务 Source of Truth）
  -> MANUAL_BOOTSTRAP（当前）
  -> Redis（唯一 runtime Provider）
  -> PVAmountConfigProvider
  -> immutable PVAmountRunConfig
```

未来 AR_CONFIG→Delta→Redis 只替换 Redis 供数机制，不改变 Provider、getter、snapshot schema、flag 语义、fail-loud、run-freeze 或 admission。本任务不实现该自动同步。

### 3.2 Redis snapshot schema

| 对象 | 字段/值 | 合同 |
|---|---|---|
| active pointer | `config_version:checksum` | 指向唯一不可变 versioned snapshot |
| versioned snapshot | `PV_AMOUNT_V2_READ` | canonical `true` 或 `false` |
| versioned snapshot | `PV_AMOUNT_V2_WRITE` | canonical `true` 或 `false` |
| versioned snapshot | `config_version` | 严格单调、可比较的非负整数 |
| versioned snapshot | `load_mode` | 当前必须为 `MANUAL_BOOTSTRAP` |
| versioned snapshot | `source` | 当前为 `AR_CONFIG` |
| versioned snapshot | `checksum` | 与 active pointer 及 canonical payload 一致 |

Provider 以单次 Redis Lua 原子读取同时取得 active pointer 与对应 hash；任何缺失、非法、不一致、Redis 异常或无法证明原子性均 fail-loud。禁止 AR_CONFIG/env/default/stale-cache fallback。

### 3.3 四态 admission

| READ | WRITE | 生产 admission | 业务语义 |
|---:|---:|---|---|
| false | false | 允许 | 00，Legacy authoritative |
| false | true | 允许 | 01，当前批准状态；Legacy authoritative，只有批准且独立的安全 V2 carrier 才可 shadow write |
| true | false | 拒绝 `INVALID_STATE` | 10 结构非法，不自动修正 |
| true | true | 当前拒绝 `V2_STATE_NOT_AUTHORIZED` | 11 结构合法，但当前没有正式 Gate/UAT/migration approval |

### 3.4 Run freeze 与 TEST-ONLY

- production run 只能通过 production admission 取得 config；run 创建后 config 不可变。
- 当前 run 对 Redis 中途更新不可见；下一 run 才重新加载。
- unit/domain test 可直接构造 11 snapshot 验证 V2 factory，但不得经过 production admission、写真实 Redis、产生正式 run 或暴露为普通 production 配置 bypass。

### 3.5 MANUAL_BOOTSTRAP

- 发布前校验完整 payload；使用同一 Lua/CAS 边界判断 `new_version > active_version`、写 versioned snapshot、切 active pointer。
- 初次发布显式走 initial-create；发布 N 或 N-1 到当前 N 必须 `STALE_CONFIG_VERSION`。
- 发布后通过 Provider read-after-write verify；失败非零退出；禁止分字段 SET。
- 当前批准 payload 为 `READ=false / WRITE=true / load_mode=MANUAL_BOOTSTRAP / source=AR_CONFIG`。

## 4. 文件范围

### 4.1 批准 production 文件

- `Redishelper/PVAmountConfigProvider.py`
- `Redishelper/PVAmountConfigBootstrap.py`

### 4.2 批准测试文件

- `tests/pvam/WORK-PVAM-01C/`

### 4.3 明确排除

- 不修改 `Common/PvAmount.py`，不在 Common 引入 Redis/config I/O。
- 不新增独立 V2 keyspace、影子表或 AR_CONFIG→Delta→Redis 自动同步。
- 不在本卡修改 UserStats/EliteBonusStats 共享字段或奖金业务公式；这些条件化 factory 行为仍由 WORK-PVAM-01 承接。
- 不以 env、常量、True/True、silent fallback 或 stale cache 作为正式 Provider。

## 5. 验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | 合法 01 snapshot 原子加载成功并返回 immutable run config | DEV+UAT | TC-FLAG-01 |
| AC-02 | active snapshot 缺失时 fail-loud | DEV | TC-FLAG-02 |
| AC-03 | READ 缺失时 fail-loud | DEV | TC-FLAG-03 |
| AC-04 | WRITE 缺失时 fail-loud | DEV | TC-FLAG-04 |
| AC-05 | config_version 缺失时 fail-loud | DEV | TC-FLAG-05 |
| AC-06 | 非 canonical bool 时 fail-loud | DEV | TC-FLAG-06 |
| AC-07 | 状态 10 在 production admission 抛 `INVALID_STATE` | DEV | TC-FLAG-07 |
| AC-08 | Provider 异常时不存在 AR_CONFIG/env/default fallback | DEV | TC-FLAG-08 |
| AC-09 | run 加载 01 后 Redis 变 11，当前 run 仍固定 01 | DEV | TC-FLAG-09 |
| AC-10 | 下一 production run 加载 11 且无正式 approval 时抛 `V2_STATE_NOT_AUTHORIZED` | DEV | TC-FLAG-10 |
| AC-11 | active pointer 与 snapshot 跨 version 或 checksum 不一致时 fail-loud | DEV | TC-FLAG-11 |
| AC-12 | bootstrap 以单一原子操作发布完整 01 并 read-after-write verify | DEV+UAT | TC-FLAG-12 |
| AC-13 | production consumer 无直接 Redis flag GET | DEV | TC-FLAG-13 |
| AC-14 | 当前 version=N 时发布 N 或 N-1 均抛 `STALE_CONFIG_VERSION` | DEV+UAT | TC-FLAG-22 |
| AC-15 | 两个并发 bootstrap 至多一个成功，active version 为较新合法版本且无 lost update | DEV+UAT | TC-FLAG-23 |

> `DEV+UAT` 条目可先用 injected fake 验证功能合同；真实 Redis 证据缺失时必须保留 `PENDING_TEST_ENV`，不得以 fake/stub 升格。

受控检查方案用例映射：`TC-003, TC-024, TC-031, TC-032`。`TC-FLAG-01～13/22/23` 是本卡局部执行用例，不新增或改号 PLAN 的受控 TC。

## 6. 依赖与执行顺序

1. Phase G 先完成 DEC/GAP/TASK/WORK、allowlist、traceability、version/document manifest、test command 与 SHA 闭包。
2. Phase I 先实现本卡 Provider/bootstrap；随后 WORK-PVAM-01 才可接入 conditional factory/run config。
3. Phase D 在组合树执行全部 TC-FLAG；真实环境继续由 WORK-PVAM-08/DEC-013 管理。

## 7. DEV / UAT 边界

- DEV：允许 injected stub、in-memory fake；执行结构解析、状态 admission、run-freeze、Lua/CAS 模拟和静态扫描。
- UAT：仅隔离 Redis 可证明真实 Lua/CAS 与并发发布；无环境时为 `PENDING_TEST_ENV/BLOCKED`。
- 禁止把静态阅读或 fake 结果写成真实 Redis UAT PASS。

## 8. 回滚与停止条件

- Provider/bootstrap 可独立回滚；已发布的 versioned snapshot 不删除，保留审计。
- active pointer 不得由非 CAS 普通 SET 回退；如需回退必须发布更高 config_version 的合法 00/01 snapshot。
- 任一实现需要独立 V2 carrier 时立即以 `V2_CARRIER_NOT_APPROVED` 停工并回到 DEC/TASK/MODPLAN/WORK。

## 9. 版本记录

| 版本 | 日期 | 变更 | 治理状态 |
|---|---|---|---|
| v1.2-r10 | 2026-08-08 | 依据 DEC-019 新建独立 flag runtime contract 任务卡 | DRAFT |
