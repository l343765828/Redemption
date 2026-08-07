# WORK-PVAM-01 金额编码公共层与基础模型适配器施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-01`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-001、R-002` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；发现漂移立即登记 `BLOCK-PVAM-01-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-01` |
| 施工任务名称 | 金额编码公共层与基础模型适配器 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-01@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-001、R-002` |
| 复核闭环追踪号 | `REM-001、REM-002 / W-001、W-002 / V-001、V-002` |
| 来源检查项 | `CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002` |
| 关联决策 | `DEC-002、DEC-008、DEC-014` |
| 代码基线 | `l343765828/Redemption@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| SQL基线 | `sql_uat/*@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | 无 |
| 功能开关 | `PV_AMOUNT_V2_READ / PV_AMOUNT_V2_WRITE` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002
  └─ R-001、R-002
       └─ DEC-002、DEC-008、DEC-014
            └─ TASK-PVAM-01 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-01
                      ├─ STEP-PVAM-01-01 / STEP-PVAM-01-02 / STEP-PVAM-01-03 / STEP-PVAM-01-04 / STEP-PVAM-01-05
                      ├─ TC-PVAM-01-01 / TC-PVAM-01-02 / TC-PVAM-01-03 / TC-PVAM-01-04 / TC-PVAM-01-05 / TC-PVAM-01-06
                      └─ EV-PVAM-01-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-001、R-002 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-01` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002 | CONTROLLED |
| 正式决策 | DEC-002、DEC-008、DEC-014 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，工作树无未登记变更。
- [ ] `TASK-PVAM-01` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：无。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 新增最低层公共金额合同，并把所有持久化金额模型的新记录显式标记为 version=2；旧/未知编码只能被隔离读取，不得直接进入 v2 计算域。 |
| 当前行为 | `Model/User/UserStats.py::UserStats` 的 `pv/gpv/gpv_real/gpv_unreal/contrib` 及 1L/2L/结余字段均为 `Optional[int]`，基线没有 `amount_encoding_version`。；`Model/User/EliteBonusStats.py::EliteBonusStats` 没有编码版本，且 `estimated_bonus: Optional[float] = 0.0`。；`Redishelper/BaseRedisModel.py::BaseRedisModel` 仅绑定 Redis OM 连接，没有金额版本后置校验。；固定提交中 `Common/PvAmount.py` 不存在；金额缩放、ppm、cents、截断与溢出校验分散在奖金服务。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 / P1 |
| 证据位置 | 固定代码基线 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；来源 `TASK-PVAM-01`；检查项 `CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002` |

### 3.2 已确认代码事实

- `Model/User/UserStats.py::UserStats` 的 `pv/gpv/gpv_real/gpv_unreal/contrib` 及 1L/2L/结余字段均为 `Optional[int]`，基线没有 `amount_encoding_version`。
- `Model/User/EliteBonusStats.py::EliteBonusStats` 没有编码版本，且 `estimated_bonus: Optional[float] = 0.0`。
- `Redishelper/BaseRedisModel.py::BaseRedisModel` 仅绑定 Redis OM 连接，没有金额版本后置校验。
- 固定提交中 `Common/PvAmount.py` 不存在；金额缩放、ppm、cents、截断与溢出校验分散在奖金服务。

### 3.3 本任务目标

新增最低层公共金额合同，并把所有持久化金额模型的新记录显式标记为 version=2；旧/未知编码只能被隔离读取，不得直接进入 v2 计算域。

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
| 1 | Redis OM 反序列化 | `Redishelper/BaseRedisModel.py::BaseRedisModel` | 旧 JSON 可能不含 version | 直接构造业务模型 | 无统一版本门禁 |
| 2 | UserStats 新建 | `User/UserStatsService.py::_get_or_init_user` | period/user_id | 创建无 version 的 `UserStats` | 后续服务无法识别单位 |
| 3 | 全量零节点 | `User/GlobalRecalculationService.py::_new_zero_user_stats` | period/uid | 创建无 version 的 `UserStats` | 混合编码不可判定 |
| 4 | Elite 新建 | `User/EliteBonusService.py::_get_or_create_node` / `_build_blank_node` | period/user_id | 创建无 version 的 `EliteBonusStats` | 奖金 float 与 PV 单位不可审计 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| UserStats/Global | 金额字段和版本 | 读写需同步修改 | 是 | STEP-PVAM-01-03/TC-003 |
| Placement | 1L/2L/结余 | 新节点写 v2，旧记录阻断 | 是 | STEP-PVAM-01-03/TC-003 |
| Elite | pv_pcs/gpv/bonus | 新节点写 v2，奖金逐步迁移为 cents | 是 | STEP-PVAM-01-04/TC-003 |
| UserPeriodHighestRank | 无金额字段 | 保持不变 | 否 | TC-003 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/PvAmount.py`，公开 `parse_external_decimal_to_units`、`parse_db_amount_to_units`、`require_units_int`、`require_amount_version` 与受控整数乘除API；只依赖 Python 标准库与可选 NumPy/CuPy 类型探测，不导入 `User`、`Model.User` 或奖金模块。
- 常量固定：`PV_SCALE=1_000_000`、`RATE_PPM_SCALE=1_000_000`、`BONUS_CENT_SCALE=100`、`AMOUNT_ENCODING_VERSION_V2=2`。
- `require_units_int` 先拒绝 `bool`，再接受受控 signed integer，最后检查 int64 范围；内部域不接受 `str/Decimal/float`。
- 模型字段采用 `Optional[int] = None`；所有 v2 工厂显式传 `2`，绝不把默认值设为 2。
- legacy 记录仅允许通过 `Common/AmountModelAdapter.py`（新增）进入扫描、报表或受控重建；普通计算入口调用 `require_amount_version` 后 fail-loud。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| version 默认值设为2 | 旧 JSON 缺字段会被静默伪装成新编码 | TASK-PVAM-01/CHK-DATA-003 |
| 服务内复制 parser | 继续产生多套 scale | R-002 |
| 接受 float 后再 Decimal | 精度损失已经发生 | CHK-DATA-001/002 |
| 给 UserPeriodHighestRank 加 version | 该模型不持有金额 | TASK-PVAM-01 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + PV_AMOUNT_V2_READ / PV_AMOUNT_V2_WRITE | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/PvAmount.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/PvAmount.py` | 模块级常量与纯函数 | 新增 | 不存在 | 实现上述命名 parser、units/ppm/cents、int64/dtype 守卫 | 唯一公共金额 API | 不得导入业务层 |
| CHG-02 | `Common/AmountModelAdapter.py` | `AmountRecordState`、`classify_amount_record` | 新增 | 不存在 | 隔离 NEW/LEGACY_UNKNOWN/INCOMPATIBLE | 普通计算只能接收 NEW | 不得自动乘 scale |
| CHG-03 | `Model/User/UserStats.py` | `UserStats.amount_encoding_version` | 修改 | 无字段 | 增加 `Optional[int]=None` 与 units 注释 | 新记录显式2，旧记录保持None | 不得默认2 |
| CHG-04 | `Model/User/EliteBonusStats.py` | version、`estimated_bonus_cents` | 修改 | 无version；bonus float | additive 增加 version 与 integer cents；旧 float 只读兼容 | v2 不写 float | 不得删除旧字段 |
| CHG-05 | `User/UserStatsService.py` | `_get_or_init_user` | 修改 | 新节点无version | 显式 version=2；已存在记录校验 | 单位可审计 | 不得转换旧值 |
| CHG-06 | `User/GlobalRecalculationService.py` | `_new_zero_user_stats`、`_mget_users_with_exists` | 修改 | 无version校验 | 新节点写2；批量读阻断旧/未知 | 全量不混算 | 不得把缺失补2 |
| CHG-07 | `User/PlacementIncrementalService.py` / `User/PlacementRecalculationService.py` | 节点构造与批量读取 | 修改 | 无version | 新节点写2；跨期/批量读取校验 | placement全字段同单位 | 不得读取legacy结余 |
| CHG-08 | `User/EliteBonusService.py` / `User/GlobalEliteBonusRecalculationService.py` | `_build_blank_node` / `_new_blank_stats` 等 | 修改 | 无version | 新节点写2；现存节点校验 | Elite状态可判编码 | 不得自动重建 |
| CHG-09 | `User/Test/test_pv_amount_common.py` / `User/Test/test_amount_model_version.py` | pytest 用例 | 新增 | 不存在 | 覆盖类型、边界、序列化、mutation | 可自动验证 | 不得依赖GPU |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `Model/User/UserStats.py::UserStats` | 金额字段为`Optional[int]`，无`amount_encoding_version` | additive增加`Optional[int]=None`；所有v2工厂显式传2 |
| `Model/User/EliteBonusStats.py::EliteBonusStats` | 无version；`estimated_bonus`为`Optional[float]` | additive增加version与`estimated_bonus_cents`；legacy float只读兼容 |
| `User/GlobalRecalculationService.py::_new_zero_user_stats` | 新节点未写编码版本 | 显式写2，并在批量读取后统一校验 |
| `User/EliteBonusService.py::_build_blank_node`、`User/GlobalEliteBonusRecalculationService.py::_new_blank_stats` | 新Elite节点未写编码版本 | 显式写2；未知版本不得进入计算 |
| `Common/PvAmount.py` | 基线不存在 | 本任务新增；不得反向依赖User/Bonus |

### 6.2 规范补丁片段

以下片段是施工合同，不代替实施后的完整`git diff`：

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
--- a/Model/User/UserStats.py
+++ b/Model/User/UserStats.py
@@
 class UserStats(BaseRedisModel, index=True):
+    # None/缺失表示legacy或未知；只有显式2可进入micro-units计算域。
+    amount_encoding_version: Optional[int] = None
     id: str
```

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
--- a/Model/User/EliteBonusStats.py
+++ b/Model/User/EliteBonusStats.py
@@
 class EliteBonusStats(BaseRedisModel, index=True):
+    amount_encoding_version: Optional[int] = None
@@
     estimated_bonus: Optional[float] = 0.0
+    # v2权威写字段；legacy float字段仅用于兼容读取与对账。
+    estimated_bonus_cents: Optional[int] = 0
```

`Common/PvAmount.py`最低实现合同：

```python
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from numbers import Integral
from typing import Final

PV_SCALE: Final[int] = 1_000_000
RATE_PPM_SCALE: Final[int] = 1_000_000
BONUS_CENT_SCALE: Final[int] = 100
AMOUNT_ENCODING_VERSION_V2: Final[int] = 2
# 仅供隔离 legacy adapter 返回；不得写入模型或事件。
LEGACY_ADAPTER_VERSION: Final[int] = 0
INT64_MIN: Final[int] = -(2**63)
INT64_MAX: Final[int] = 2**63 - 1
_CANONICAL_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def require_int64(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{field_name} must be an integer, got {type(value).__name__}")
    result = int(value)
    if result < INT64_MIN or result > INT64_MAX:
        raise OverflowError(f"{field_name} is outside signed int64")
    return result


def require_units_int(value: object, field_name: str = "amount_units") -> int:
    return require_int64(value, field_name=field_name)


def _require_max_decimals(max_decimals: int) -> int:
    if isinstance(max_decimals, bool) or not isinstance(max_decimals, int) or max_decimals < 0:
        raise ValueError("max_decimals must be a non-negative integer")
    return max_decimals


def _decimal_to_units(
    value: Decimal,
    *,
    max_decimals: int,
    field_name: str,
) -> int:
    max_decimals = _require_max_decimals(max_decimals)
    decimal_places = max(0, -value.as_tuple().exponent)
    if decimal_places > max_decimals:
        raise ValueError(
            f"{field_name} has {decimal_places} decimal places; maximum is {max_decimals}"
        )
    scaled = value * PV_SCALE
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{field_name} has precision finer than micro-units")
    return require_int64(int(scaled), field_name=field_name)


def parse_external_decimal_to_units(
    raw: str,
    *,
    max_decimals: int = 2,
) -> int:
    if not isinstance(raw, str) or not _CANONICAL_DECIMAL.fullmatch(raw):
        raise TypeError("external amount must be a canonical decimal string")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("external amount is not a decimal") from exc
    return _decimal_to_units(
        value,
        max_decimals=max_decimals,
        field_name="external_amount",
    )


def parse_db_amount_to_units(
    raw: Decimal | str,
    *,
    max_decimals: int = 2,
) -> int:
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, str) and _CANONICAL_DECIMAL.fullmatch(raw):
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("DB amount is not a decimal") from exc
    else:
        raise TypeError("DB amount must be Decimal or canonical decimal string")
    if not value.is_finite():
        raise ValueError("DB amount must be finite")
    return _decimal_to_units(value, max_decimals=max_decimals, field_name="db_amount")


def require_amount_version(
    value: object,
    *,
    allow_legacy: bool = False,
) -> int:
    if value is None:
        if allow_legacy:
            return LEGACY_ADAPTER_VERSION
        raise ValueError("amount_encoding_version is missing/legacy")
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError("amount_encoding_version must be an integer")
    normalized = int(value)
    if normalized != AMOUNT_ENCODING_VERSION_V2:
        raise ValueError(f"unsupported amount_encoding_version={normalized}")
    return normalized


def trunc_div_zero(numerator: int, denominator: int) -> int:
    """整数除法向零截断；支持任意非零分母。"""
    if denominator == 0:
        raise ZeroDivisionError("denominator must not be zero")
    quotient = abs(numerator) // abs(denominator)
    return -quotient if (numerator < 0) ^ (denominator < 0) else quotient
```

禁止把上述parser用于内部units再次放大；禁止把缺失version补成2后继续计算。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-01-01：建立公共金额模块

- 目的：建立公共金额模块，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：无
- 修改文件：`Common/PvAmount.py`
- 目标符号：模块 API
- 精确操作：
1. 按 TASK 定义常量和类型标注
2. 实现向零整数除法、溢出检查和外部/DB 两类 parser
3. 对异常使用明确 `TypeError/ValueError/OverflowError`。
- 必须保持：不选择具体奖项舍入；不导入业务层
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/PvAmount.py`
- 本步单元验证：`TC-PVAM-01-01/02`
- 完成证据：`EV-PVAM-01-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何 parser 接受 float/bool 时停工

### STEP-PVAM-01-02：建立版本适配器

- 目的：建立版本适配器，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-01
- 修改文件：`Common/AmountModelAdapter.py`
- 目标符号：版本分类函数
- 精确操作：
1. 实现 `version=2`、legacy unknown、incompatible 三态
2. 普通入口默认不允许 legacy。
- 必须保持：不写数据、不自动转换
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/AmountModelAdapter.py`
- 本步单元验证：`TC-PVAM-01-03`
- 完成证据：`EV-PVAM-01-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：无法区分旧新记录时停工

### STEP-PVAM-01-03：扩展 UserStats 与工厂

- 目的：扩展 UserStats 与工厂，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-02
- 修改文件：`Model/User/UserStats.py`、三个 User/Placement 服务
- 目标符号：字段与节点工厂
- 精确操作：
1. additive 增加 version
2. 所有新建对象显式2
3. 批量读与跨期读调用门禁。
- 必须保持：保持字段名/Redis key/业务公式不变
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/User/UserStats.py User/UserStatsService.py User/GlobalRecalculationService.py User/PlacementIncrementalService.py User/PlacementRecalculationService.py`
- 本步单元验证：`TC-PVAM-01-03/04`
- 完成证据：`EV-PVAM-01-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：旧记录被静默写回2时立即回滚

### STEP-PVAM-01-04：扩展 EliteBonusStats 与工厂

- 目的：扩展 EliteBonusStats 与工厂，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-02
- 修改文件：`Model/User/EliteBonusStats.py`、Elite两服务
- 目标符号：version与cents additive字段
- 精确操作：
1. 新增 `estimated_bonus_cents`
2. v2 工厂写2
3. 保留 `estimated_bonus` 供旧读。
- 必须保持：不在本步骤改Elite公式
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Model/User/EliteBonusStats.py User/EliteBonusService.py User/GlobalEliteBonusRecalculationService.py`
- 本步单元验证：`TC-PVAM-01-03/05`
- 完成证据：`EV-PVAM-01-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：旧字段被删除或重新解释时停工

### STEP-PVAM-01-05：补齐自动测试与静态扫描

- 目的：补齐自动测试与静态扫描，落实 `TASK-PVAM-01` 的已批准目标。
- 前置条件：STEP-01-01~04
- 修改文件：`User/Test/test_pv_amount_common.py` 等
- 目标符号：测试
- 精确操作：
1. 加入固定样例、旧JSON、int64、dtype、import graph与反mutation。
- 必须保持：测试不得复制生产算法
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_pv_amount_common.py User/Test/test_amount_model_version.py`
- 本步单元验证：`TC-PVAM-01-01~06`
- 完成证据：`EV-PVAM-01-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一mutation存活不得合并

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| Redis UserStats/EliteBonusStats | 无version/legacy数值 | version=2 micro-units/cents additive字段 | 节点工厂/受控重建 | amount_encoding_version | legacy隔离；未知阻断 |

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
| TC-PVAM-01-01 | 单元 | 外部金额字符串 | `"30.00"`,`"-100.25"` | `30_000_000`、`-100_250_000` | STEP-01-01 | DEV | NOT_RUN |
| TC-PVAM-01-02 | 单元 | 非法输入 | `0.1`,`True`,`"1e2"`,`"NaN"`,`"Infinity"`, `Decimal("NaN")`, `Decimal("sNaN")`, `Decimal("Infinity")`, `Decimal("-Infinity")` | 分别抛受控异常；无返回units | STEP-01-01 | DEV | NOT_RUN |
| TC-PVAM-01-03 | 契约 | version隔离 | None/1/2/3/`"2"` | 仅整数2进入新域；None归LEGACY_UNKNOWN；其余阻断 | STEP-01-02~04 | DEV+UAT | NOT_RUN |
| TC-PVAM-01-04 | 迁移 | 旧UserStats JSON | 缺version且pv=100 | 可反序列化；计算入口抛版本错误；值不被乘scale | STEP-01-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-01-05 | 边界 | int64乘法 | 接近INT64_MAX的units*ppm | 溢出前结果精确；越界抛OverflowError | STEP-01-01 | DEV | NOT_RUN |
| TC-PVAM-01-06 | 静态 | 依赖/反模式 | AST全仓 | Common不导入User；新增代码无Decimal(str(float))/int(round(float)) | STEP-01-05 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-001, TC-002, TC-003, TC-008, TC-030, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-01}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-01"

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
  --work-id "WORK-PVAM-01" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-01.sh" \
  --out "evidence/WORK-PVAM-01/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Common.PvAmount import (
    parse_external_decimal_to_units,
    require_amount_version,
    require_units_int,
)


def test_pv_amount_contract() -> None:
    assert parse_external_decimal_to_units("30.00") == 30_000_000
    assert parse_external_decimal_to_units("-100.25") == -100_250_000
    assert require_units_int(30_000_000, field_name="pv") == 30_000_000
    assert require_amount_version(2) == 2
    with pytest.raises(TypeError):
        parse_external_decimal_to_units(30.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        require_units_int(True, field_name="pv")
    with pytest.raises(ValueError):
        require_amount_version(None)
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-01-01：混合编码 Redis 读取

- 对应受控测试：`TC-003、TC-008、TC-031`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：专用 Redis DB/前缀；固定commit；WORK-08 manifest已生成
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work01-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-01 --run-id "$RUN_ID" --tc TC-003,TC-008,TC-031
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
# N/A：本任务以 Redis JSON/version 与 Python 类型证据为准，不执行关系库写操作。
```

- 执行步骤：
1. 插入 legacy 缺version、version=2、version=3 三类记录
2. 运行批量读取与新节点构造
3. 导出前后JSON和异常日志
- 精确预期：
- version=2 正常；legacy/3阻断且原值不变
- 新记录全部显式 version=2
- 无旧记录被自动放大
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| 金额编码样例 | `30.00 PV` | N/A（公共层不改SQL） | `30_000_000 units` | 1 PV=1,000,000 units | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | `Common/PvAmount.py` 存在，import graph 无循环，公共层无业务模块 import | STEP-PVAM-01-01/05 | TC-002、TC-031 | EV-PVAM-01-01 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | UserStats、EliteBonusStats 新建记录均显式写 version=2 | STEP-PVAM-01-03/04 | TC-003 | EV-PVAM-01-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 旧 JSON 缺 version 可反序列化，但进入 v2 计算入口时必定阻断 | STEP-PVAM-01-02/03/04 | TC-003 | EV-PVAM-01-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | version=1、3、字符串2、bool 等非法值全部阻断 | STEP-PVAM-01-02/05 | TC-003 | EV-PVAM-01-04 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 外部/DB 边界 parser 与内部 `require_units_int` 职责分离 | STEP-PVAM-01-01/05 | TC-001、TC-002 | EV-PVAM-01-05 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | `0.1` float、`True`、NaN、Infinity、指数文本均被相应用例拒绝 | STEP-PVAM-01-01/05 | TC-001、TC-002 | EV-PVAM-01-06 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | 正负边界、int64 最大值、乘法溢出测试通过 | STEP-PVAM-01-01/05 | TC-008 | EV-PVAM-01-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 只有持久化金额模型新增 version；无金额模型零误加 | STEP-PVAM-01-03/04/05 | TC-003、TC-030 | EV-PVAM-01-08 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | 全仓新增代码没有 `Decimal(str(float))`、`int(round(float))` 等洗白模式 | STEP-PVAM-01-05 | TC-002、TC-031 | EV-PVAM-01-09 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | TASK-01 独立回滚测试通过，旧代码在不写 v2 新数据时可启动 | STEP-PVAM-01-05 | TC-031、TC-032 | EV-PVAM-01-10 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

### 10.1 AC-06 实施细化 / 派生测试

本小节只细化 `AC-06` 的实现测试边界，不改写上游 TASK 的来源验收文本，也不增加新的业务规则。来源 AC 仍严格限定为：`0.1` float、`True`、NaN、Infinity、指数文本均被相应用例拒绝。

| 类型 | 派生输入 | 预期异常合同 | TC 映射 | EV 映射 | 环境 |
|---|---|---|---|---|---|
| Decimal 非数扩展 | `Decimal("sNaN")` | 在缩放、指数或整数转换前显式抛 `ValueError("DB amount must be finite")` | `TC-PVAM-01-02` | `EV-PVAM-01-06` | DEV |
| Decimal 正无穷扩展 | `Decimal("Infinity")` | 在缩放、指数或整数转换前显式抛 `ValueError("DB amount must be finite")` | `TC-PVAM-01-02` | `EV-PVAM-01-06` | DEV |
| Decimal 负无穷扩展 | `Decimal("-Infinity")` | 在缩放、指数或整数转换前显式抛 `ValueError("DB amount must be finite")` | `TC-PVAM-01-02` | `EV-PVAM-01-06` | DEV |

派生输入只允许出现在本小节及其 `TC-PVAM-01-02` / `EV-PVAM-01-06` 映射中；不得回填到 AC 来源文本，不得据此把 DEV 结果解释为 UAT 或生产通过。

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 旧记录被默认成v2 | 模型默认值或反序列化补值 | 历史金额按错误倍率参与 | 字段默认None；入口强校验 | version扫描 | 停工并回滚reader enforcement |
| int64越界 | 极大聚合/乘ppm | wrap导致财务错误 | checked_add/mul | 异常与上界报告 | 阻断该run |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-01/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止v2新写；保留amount version与适配器；禁止把v2数据降级伪装成legacy；恢复旧镜像后仅允许读取旧数据，v2记录继续隔离。

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
| EV-PVAM-01-01 | AC-01验收证据：`Common/PvAmount.py` 存在，import graph 无循环，公共层无业务模块 import | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-01-02 | AC-02验收证据：UserStats、EliteBonusStats 新建记录均显式写 version=2 | STEP-PVAM-01-03/04 | evidence/WORK-PVAM-01/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-01-03 | AC-03验收证据：旧 JSON 缺 version 可反序列化，但进入 v2 计算入口时必定阻断 | STEP-PVAM-01-02/03/04 | evidence/WORK-PVAM-01/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-01-04 | AC-04验收证据：version=1、3、字符串2、bool 等非法值全部阻断 | STEP-PVAM-01-02/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-01-05 | AC-05验收证据：外部/DB 边界 parser 与内部 `require_units_int` 职责分离 | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-01-06 | AC-06验收证据：`0.1` float、`True`、NaN、sNaN、±Infinity（字符串与 Decimal）、指数文本均被相应用例拒绝 | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-01-07 | AC-07验收证据：正负边界、int64 最大值、乘法溢出测试通过 | STEP-PVAM-01-01/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-01-08 | AC-08验收证据：只有持久化金额模型新增 version；无金额模型零误加 | STEP-PVAM-01-03/04/05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-01-09 | AC-09验收证据：全仓新增代码没有 `Decimal(str(float))`、`int(round(float))` 等洗白模式 | STEP-PVAM-01-05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-01-10 | AC-10验收证据：TASK-01 独立回滚测试通过，旧代码在不写 v2 新数据时可启动 | STEP-PVAM-01-05 | evidence/WORK-PVAM-01/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-01-P01 | 公共金额模块与版本适配器 diff | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P02 | 模型/工厂 additive diff | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P03 | DEV pytest/JUnit与AST报告 | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P04 | UAT混合编码证据包 | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-01-P05 | 字段编码矩阵与回滚记录 | 对应STEP/TC | evidence/WORK-PVAM-01/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-01" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-01/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-01` 批准 allowlist；
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
| STEP-PVAM-01-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-01-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-01-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-05 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |
| TC-PVAM-01-06 | DEV | 待执行 | NOT_RUN | EV-PVAM-01-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-01-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-01` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
