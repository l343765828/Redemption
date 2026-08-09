# WORK-PVAM-04 monthActivePV 唯一取值与 Active 同源现算施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-04`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-005、R-006` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-04-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-04` |
| 施工任务名称 | monthActivePV 唯一取值与 Active 同源现算 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-04@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-005、R-006` |
| 复核闭环追踪号 | `REM-005、REM-006 / W-005、W-006 / V-005、V-006` |
| 来源检查项 | `CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011` |
| 关联决策 | `DEC-004、DEC-016、DEC-018` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01、WORK-PVAM-03 DEV_VERIFIED；真实供给链UAT仍BLOCKED |
| 功能开关 | `ACTIVE_RULE_V2` |

### 1.1 一对一追溯摘要

```text
CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011
  └─ R-005、R-006
       └─ DEC-004、DEC-016、DEC-018
            └─ TASK-PVAM-04 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-04
                      ├─ STEP-PVAM-04-01 / STEP-PVAM-04-02 / STEP-PVAM-04-03 / STEP-PVAM-04-04 / STEP-PVAM-04-05
                      ├─ TC-PVAM-04-01 / TC-PVAM-04-02 / TC-PVAM-04-03 / TC-PVAM-04-04 / TC-PVAM-04-05 / TC-PVAM-04-06 / TC-PVAM-04-07 / TC-PVAM-04-08
                      └─ EV-PVAM-04-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-005、R-006 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-04` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011 | CONTROLLED |
| 正式决策 | DEC-004、DEC-016、DEC-018 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-04` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01、WORK-PVAM-03 DEV_VERIFIED；真实供给链UAT仍BLOCKED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 实现唯一 monthActivePV getter 和纯函数 ActiveRule；PE/SE/EAB/LB及适用TB消费者每次从同一 v2 UserStats.pv 现算，外部IS_ACTIVE仅用于审计；本轮不建设延期的2B写入侧。 |
| 当前行为 | `PEBonusService.execute_batch` 在 `ddf_user_perf is None` 时直接以 `UserStats.pv >= 30` 派生。；PE、SE、EAB 等服务可接受外部 `IS_ACTIVE` 表/列并用于发奖，形成多权威源。；固定基线不存在唯一 monthActivePV getter，也不存在可证明的 AR_CONFIG→Delta→Redis 2B producer。；DEC-018 要求不物化共享Active snapshot，各消费方用同一pv源和同一门槛规则各自现算。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 / P1 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-04`；检查项 `CHK-DATA-006、CHK-BIZ-007、CHK-BIZ-008、CHK-BIZ-009、CHK-BIZ-011` |

### 3.2 已确认代码事实

- `PEBonusService.execute_batch` 在 `ddf_user_perf is None` 时直接以 `UserStats.pv >= 30` 派生。
- PE、SE、EAB 等服务可接受外部 `IS_ACTIVE` 表/列并用于发奖，形成多权威源。
- 固定基线不存在唯一 monthActivePV getter，也不存在可证明的 AR_CONFIG→Delta→Redis 2B producer。
- DEC-018 要求不物化共享Active snapshot，各消费方用同一pv源和同一门槛规则各自现算。

### 3.3 本任务目标

实现唯一 monthActivePV getter 和纯函数 ActiveRule；PE/SE/EAB/LB及适用TB消费者每次从同一 v2 UserStats.pv 现算，外部IS_ACTIVE仅用于审计；本轮不建设延期的2B写入侧。

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
| 1 | PE执行 | `User/PEBonusService.py::execute_batch` | ddf_user_perf可空 | 空时pv>=30；非空时外部权威 | 裸值/双权威 |
| 2 | SE执行 | `User/SuperEliteBonusService.py::calculate_se_bonus` | ddf_user_perf必需 | 直接使用外部is_active | 来源不可追溯 |
| 3 | EAB执行 | `User/EliteAchievementBonusService.py::calculate_eab_bonus` | ddf_user_perf | 外部is_active决定实际发放 | 来源不可追溯 |
| 4 | LB执行 | `LeadershipBonusGPUService`输入快照 | active字段/上游 | 无统一门槛manifest | 跨奖项漂移 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| PE | UserStats.pv + threshold | 替换裸30和外部权威 | 是 | STEP-04-03/TC-007/017 |
| SE | 同源现算 | 外部字段改audit | 是 | STEP-04-03/TC-018 |
| EAB | 同源现算 | 理论行保留，不活跃实际0 | 是 | STEP-04-03/TC-019 |
| LB | 同源现算 | 理论/实际语义不变 | 是 | STEP-04-03/TC-021 |
| Elite | Active=N/A | 不改 | 否 | TC-014 |
| TB oracle/未来consumer | 适用时同规则 | 只适配测试，不建生产服务 | 测试 | TC-007/013 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/MonthActivePvProvider.py`：读取顺序 Redis→sleep(2s)→Redis→Delta→fail-loud；依赖通过接口注入，便于DEV替身。
- 门槛原始值按 INTEGER_BV_ONLY scale=100 解析：30/30.00可规范，30.1阻断；随后转换为30,000,000 micro-units。
- 新增 `Common/ActiveRule.py::is_active(pv_units, threshold_units) -> bool`，先校验version/units，比较结果不持久化。
- run启动时取值一次并写 `threshold_raw/canonical/source/version/checksum` 到run manifest。
- `GAP-DEC004-2B` 保持DEFERRED：不得新增AR_CONFIG同步、Redis失效或Delta生产writer；UAT通过fixture只验证getter读侧。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 共享Active表/snapshot | 违反DEC-018 | DEC-018 |
| 硬编码30 | 配置变更无法生效 | R-005 |
| 最终失败回退30/全员活跃 | 违反DEC-004 fail-loud | DEC-004 |
| 本轮顺手建设2B producer | DEFERRED，无批准 | GAP-DEC004-2B |
| 外部IS_ACTIVE作为权威 | R-006 | R-006 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + ACTIVE_RULE_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/MonthActivePvProvider.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/MonthActivePvProvider.py` | provider/repository协议 | 新增 | 不存在 | 实现严格读取顺序与manifest | 唯一门槛getter | 不得写配置 |
| CHG-02 | `Common/ActiveRule.py` | `is_active` / vector helpers | 新增 | 不存在 | 以strict units比较 | 同源纯计算 | 不得物化结果 |
| CHG-03 | `User/PEBonusService.py` | `execute_batch` | 修改 | 裸30或外部perf | 注入threshold+从stats.pv现算；perf仅audit | 同源结果 | 不得改base/资格 |
| CHG-04 | `User/SuperEliteBonusService.py` | `calculate_se_bonus` | 修改 | 外部is_active权威 | 接UserStats pv与threshold现算 | 分母/不发规则保持 | 不得重分配份额 |
| CHG-05 | `User/EliteAchievementBonusService.py` | `calculate_eab_bonus` | 修改 | 外部is_active权威 | 现算；仅实际奖金受影响 | 理论池保持 | 不得改HALF_UP |
| CHG-06 | `User/LeadershipBonusGPUService.py` | `compute_leadership_bonus`输入组装 | 修改 | 上游active | 现算并审计差异 | 九代/双闸门不变 | 不得改Country政策 |
| CHG-07 | `User/run_monthly_bonus_pipeline_v2.py` | run manifest组装 | 修改 | 无统一threshold | 启动一次取值并传各消费者 | run内冻结 | 不得实现2B写侧 |
| CHG-08 | `User/Test/test_month_active_pv.py` | pytest | 新增 | 不存在 | provider顺序、阈值、跨奖项一致性 | 可自动验证 | 不得伪造生产供给链PASS |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `User/PEBonusService.py::execute_batch` | `ddf_user_perf is None`时按`pv>=30`派生 | 删除裸30与外部Active权威输入 |
| `User/SuperEliteBonusService.py` | 要求注入`ddf_user_perf.is_active` | 改为同run UserStats PV + threshold现算 |
| EAB/LB消费者 | 各自存在Active输入/组装路径 | 接入同一ActiveRule，不改变理论池/分母规则 |
| AR_CONFIG→Delta→Redis写入侧 | 固定基线无完整生产实现 | 保持`GAP-DEC004-2B / DEFERRED`，本任务不建设 |

### 6.2 读取侧参考接口

```python
from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

@dataclass(frozen=True)
class MonthActivePv:
    raw_value: str
    threshold_units: int
    source: str
    source_version: str
    checksum: str

class ConfigRowsReader(Protocol):
    def read_redis_rows(self, config_name: str) -> Sequence[dict]: ...
    def read_delta_rows(self, config_name: str) -> Sequence[dict]: ...

class MonthActivePvProvider:
    def __init__(self, reader: ConfigRowsReader, sleep_fn=time.sleep):
        self._reader = reader
        self._sleep = sleep_fn

    def load_for_run(self) -> MonthActivePv:
        rows = list(self._reader.read_redis_rows("monthActivePV"))
        source = "redis"
        if not rows:
            self._sleep(2)
            rows = list(self._reader.read_redis_rows("monthActivePV"))
        if not rows:
            rows = list(self._reader.read_delta_rows("monthActivePV"))
            source = "delta"
        if not rows:
            raise RuntimeError("monthActivePV missing from Redis and Delta")
        # 重复时按DEC-016取真实行之一；不得使用内置默认值。
        raw = str(rows[0]["value"])
        value = Decimal(raw)
        if value != value.to_integral_value():
            raise ValueError("monthActivePV must be INTEGER_BV_ONLY")
        threshold_units = int(value) * 1_000_000
        source_version = rows[0].get("source_version")
        checksum = rows[0].get("checksum")
        if not source_version or not checksum:
            raise RuntimeError("monthActivePV source_version/checksum missing")
        return MonthActivePv(raw, threshold_units, source,
                             str(source_version), str(checksum))


def derive_active(*, user_pv_units: int, threshold_units: int) -> bool:
    return user_pv_units >= threshold_units
```

实际实现必须由WORK-03公共parser校验类型/checksum；source_version或checksum缺失必须fail-loud，示例不授权自造排序规则。30与30.00规范到相同整数阈值；30.1因非INTEGER_BV阻断。

### 6.3 供给链边界

UAT可由DBA受控注入Redis/Delta fixture验证读取顺序，但证据必须记录来源、注入人、有效期和SHA-256；fixture通过不得把2B生产写入/失效链改为CLOSED或VERIFIED。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-04-01：实现provider读侧

- 目的：实现provider读侧，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：WORK-01/03 DEV_VERIFIED
- 修改文件：`Common/MonthActivePvProvider.py`
- 目标符号：provider接口
- 精确操作：
1. 实现Redis两读间隔2秒、Delta兜底和最终异常
2. 返回值含source/version/checksum。
- 必须保持：不新增写入/失效producer
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/MonthActivePvProvider.py`
- 本步单元验证：`TC-PVAM-04-01/02`
- 完成证据：`EV-PVAM-04-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法证明读源字段时BLOCK UAT，不猜

### STEP-PVAM-04-02：实现ActiveRule

- 目的：实现ActiveRule，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-01
- 修改文件：`Common/ActiveRule.py`
- 目标符号：纯函数/vector helper
- 精确操作：
1. 门槛scale=100规范后转units
2. pv/version严格校验。
- 必须保持：不写共享snapshot
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/ActiveRule.py`
- 本步单元验证：`TC-PVAM-04-03`
- 完成证据：`EV-PVAM-04-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：30.1未阻断则停工

### STEP-PVAM-04-03：改造奖金消费者

- 目的：改造奖金消费者，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-02
- 修改文件：PE/SE/EAB/LB服务
- 目标符号：执行入口
- 精确操作：
1. 移除外部active权威
2. 从同run stats.pv+threshold现算
3. 外部列只做audit mismatch。
- 必须保持：保持资格/分母/理论/实际业务语义
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Common`
- 本步单元验证：`TC-PVAM-04-04~07`
- 完成证据：`EV-PVAM-04-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何奖项结果非Active部分变化则停工

### STEP-PVAM-04-04：冻结门槛manifest

- 目的：冻结门槛manifest，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-01
- 修改文件：`User/run_monthly_bonus_pipeline_v2.py`
- 目标符号：run启动
- 精确操作：
1. 取一次threshold，记录manifest并显式传入全部消费者。
- 必须保持：不在run中热刷新
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/run_monthly_bonus_pipeline_v2.py`
- 本步单元验证：`TC-PVAM-04-08`
- 完成证据：`EV-PVAM-04-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：同run出现两个checksum即失败

### STEP-PVAM-04-05：补齐fixture纪律与测试

- 目的：补齐fixture纪律与测试，落实 `TASK-PVAM-04` 的已批准目标。
- 前置条件：STEP-04-01~04
- 修改文件：测试/uat fixture manifest
- 目标符号：pytest与manifest
- 精确操作：
1. DEV用repository替身
2. UAT fixture必须标记人工注入、来源/checksum/有效期，真实2B仍BLOCKED。
- 必须保持：不得把fixture当生产链
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_month_active_pv.py`
- 本步单元验证：`TC-PVAM-04-01~08`
- 完成证据：`EV-PVAM-04-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：证据标签缺失不得验收

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| monthActivePV配置 | 裸30/外部Active | 门槛units + 每消费方现算 | run启动getter | threshold checksum | 最终缺失阻断 |
| 外部IS_ACTIVE | 权威输入 | 仅审计字段 | 奖金入口 | audit flag | 不参与裁决 |

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
| TC-PVAM-04-01 | 单元 | Redis首读命中 | Redis=30,Delta=空 | 不sleep/不读Delta；返回30,000,000及Redis来源 | STEP-04-01 | DEV | NOT_RUN |
| TC-PVAM-04-02 | 故障 | Redis空→2s→空→Delta/空 | 受控clock与repositories | Delta有30则成功；Delta空抛明确错误且无奖金结果 | STEP-04-01 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-03 | 边界 | 阈值与PV | threshold 30/30.00/30.1；pv29.99/30 | 30.1阻断；29.99 inactive；30 active | STEP-04-02 | DEV | NOT_RUN |
| TC-PVAM-04-04 | 差分 | 跨奖项同源 | 同user/period/run pv=30 | PE/SE/EAB/LB active均1 | STEP-04-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-05 | 审计 | 外部active冲突 | 现算1、外部0 | 奖金按1裁决；产生audit mismatch | STEP-04-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-06 | 回归 | Elite不受Active | 同Elite输入，active切换 | Elite候选/奖金完全相同 | STEP-04-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-04-07 | 业务回归 | inactive语义 | qualified但pv29.99 | PE/SE/EAB/LB实际不发；理论/分母按各自SQL合同 | STEP-04-03 | UAT | NOT_RUN |
| TC-PVAM-04-08 | 集成 | run冻结 | 启动后源从30改40 | 当前run仍30/checksum不变；下一run40 | STEP-04-04 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-007, TC-013, TC-014, TC-017, TC-018, TC-019, TC-021, TC-030, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-04}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-04"

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
  --work-id "WORK-PVAM-04" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-04.sh" \
  --out "evidence/WORK-PVAM-04/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Common.ActiveRule import is_active
from Common.MonthActivePvProvider import MonthActivePvProvider


def test_active_threshold_contract(redis_repo, delta_repo, fake_clock) -> None:
    provider = MonthActivePvProvider(redis_repo=redis_repo, delta_repo=delta_repo, clock=fake_clock)
    threshold = provider.get_for_run(period="41", run_id="r1")
    assert threshold.units == 30_000_000
    assert is_active(29_990_000, threshold.units) is False
    assert is_active(30_000_000, threshold.units) is True
    redis_repo.clear()
    delta_repo.clear()
    with pytest.raises(RuntimeError):
        provider.get_for_run(period="42", run_id="r2")
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-04-01：Active同源与读链故障

- 对应受控测试：`TC-007、TC-013、TC-017、TC-018、TC-019、TC-021`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：WORK-08批准fixture；Redis/Delta隔离；真实2B状态标DEFERRED
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work04-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-04 --run-id "$RUN_ID" --tc TC-007,TC-013,TC-017,TC-018,TC-019,TC-021
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<SQL
SELECT CONFIG_NAME, TYPE, VALUE
  FROM AR_CONFIG
 WHERE CONFIG_NAME = 'monthActivePV';
SELECT PERIOD_NUM, USER_ID, PV_PCS, IS_ACTIVE
  FROM AR_PERF_MONTH
 WHERE PERIOD_NUM = ${PERIOD_NUM:?}
 ORDER BY USER_ID;
SQL
```

- 执行步骤：
1. 分别注入Redis命中、Redis空Delta命中、两者皆空
2. 以pv=29.99/30执行PE/SE/EAB/LB与TB oracle
3. 运行中改变fixture并启动下一run
- 精确预期：
- 当前run所有消费者Active一致
- 最终缺失时整run失败且无奖金发布
- fixture证据不关闭2B生产缺口
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| Active边界 | monthActivePV=30; pv=29.99/30 | SQL legacy active对照 | 0/1 | micro-units比较 | 0 |
| PE inactive | qualified, pv<30 | 理论金额存在但IS_ACTIVE=0不发（按当前合同） | 实际0 cents | Active仅最终拦截 | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 全仓生产路径不再出现裸 `>=30` Active 判定 | STEP-PVAM-04-03/05 | TC-007、TC-031 | EV-PVAM-04-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 唯一 getter 的 Redis→2秒→Redis→Delta→fail 顺序有单测和故障测试 | STEP-PVAM-04-01/05 | TC-007 | EV-PVAM-04-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 30、30.00 可规范；30.1 阻断；29.99PV不活跃，30PV活跃 | STEP-PVAM-04-01/02/05 | TC-007 | EV-PVAM-04-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | PE/SE/EAB/LB 在同一 user/period/run 下 Active 结果逐行一致 | STEP-PVAM-04-03/05 | TC-007、TC-017、TC-018、TC-019、TC-021 | EV-PVAM-04-04 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 各服务不读取持久化 Active 表或共享 snapshot 作为权威 | STEP-PVAM-04-03/05 | TC-007、TC-030 | EV-PVAM-04-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | 外部 `IS_ACTIVE` 修改不改变奖金裁决，只产生审计差异 | STEP-PVAM-04-03/05 | TC-007 | EV-PVAM-04-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | Elite Bonus 结果不因 Active 变化而变化 | STEP-PVAM-04-03/05 | TC-007、TC-014 | EV-PVAM-04-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | SE 分母、EAB理论行、LB理论计算和TB结余语义不被改写 | STEP-PVAM-04-03/05 | TC-007、TC-013、TC-018、TC-019、TC-021 | EV-PVAM-04-08 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | run manifest 包含 threshold raw/canonical/source/version/checksum | STEP-PVAM-04-04/05 | TC-007、TC-032 | EV-PVAM-04-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | 配置在运行中变化不造成 run 内结果分裂 | STEP-PVAM-04-04/05 | TC-007 | EV-PVAM-04-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-11 | UAT fixture 明确标记来源与 checksum；不得据 fixture 将 2B 生产供给链标为 PASS | STEP-PVAM-04-05 | TC-007、TC-032 | EV-PVAM-04-11 | UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| fixture误判生产链 | UAT只测读侧 | 虚假关闭CHK-DATA-006 | manifest标DEFERRED | evidence review | 保持BLOCKED |
| 多消费者接口不齐 | 任一继续用外部active | 结果漂移 | 全仓AST/callgraph | mismatch trace | 停工 |
| 门槛中途变化 | 重复getter | 同run分裂 | run冻结 | checksum | 回滚到旧run |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-04/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止奖金run；固定回滚前threshold checksum；恢复旧镜像后对受影响period干净重跑；不得物化共享Active结果或把fixture当生产供给链。

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
| EV-PVAM-04-01 | AC-01验收证据：全仓生产路径不再出现裸 `>=30` Active 判定 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-04-02 | AC-02验收证据：唯一 getter 的 Redis→2秒→Redis→Delta→fail 顺序有单测和故障测试 | STEP-PVAM-04-01/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-04-03 | AC-03验收证据：30、30.00 可规范；30.1 阻断；29.99PV不活跃，30PV活跃 | STEP-PVAM-04-01/02/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-04-04 | AC-04验收证据：PE/SE/EAB/LB 在同一 user/period/run 下 Active 结果逐行一致 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-04-05 | AC-05验收证据：各服务不读取持久化 Active 表或共享 snapshot 作为权威 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-04-06 | AC-06验收证据：外部 `IS_ACTIVE` 修改不改变奖金裁决，只产生审计差异 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-04-07 | AC-07验收证据：Elite Bonus 结果不因 Active 变化而变化 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-04-08 | AC-08验收证据：SE 分母、EAB理论行、LB理论计算和TB结余语义不被改写 | STEP-PVAM-04-03/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-04-09 | AC-09验收证据：run manifest 包含 threshold raw/canonical/source/version/checksum | STEP-PVAM-04-04/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-04-10 | AC-10验收证据：配置在运行中变化不造成 run 内结果分裂 | STEP-PVAM-04-04/05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-04-11 | AC-11验收证据：UAT fixture 明确标记来源与 checksum；不得据 fixture 将 2B 生产供给链标为 PASS | STEP-PVAM-04-05 | evidence/WORK-PVAM-04/attempt-*/ac/AC-11/ | 待指派QA | PENDING |
| EV-PVAM-04-P01 | MonthActivePvProvider/ActiveRule源码 | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P02 | PE/SE/EAB/LB接入diff | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P03 | run threshold manifest | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P04 | DEV provider/Active测试 | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-04-P05 | UAT跨奖项/失败链证据与2B缺口登记 | 对应STEP/TC | evidence/WORK-PVAM-04/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-04" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-04/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-04` 批准 allowlist；
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
| STEP-PVAM-04-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-04-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-04-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-03 | DEV | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-07 | UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |
| TC-PVAM-04-08 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-04-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-04-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-04` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
