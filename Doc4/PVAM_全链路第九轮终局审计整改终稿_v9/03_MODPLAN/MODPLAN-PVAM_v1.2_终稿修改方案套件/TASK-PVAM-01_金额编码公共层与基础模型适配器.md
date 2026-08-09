# TASK-PVAM-01 金额编码公共层与基础模型适配器

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-01` |
| 来源检查项 | `CHK-ARCH-003、CHK-DATA-001、CHK-DATA-003、CHK-EVT-002` |
| 来源问题 | `R-001、R-002` |
| 处置项 | `REM-001、REM-002` |
| 施工项 | `W-001、W-002` |
| 验证项 | `V-001、V-002` |
| 关联决策 | `DEC-002、DEC-008、DEC-014、DEC-019` |
| 严重级别 | `P0 / P1` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | `WORK-PVAM-01C` Phase A Provider/bootstrap 接口先完成 DEV 验证 |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。


### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

### 2.1 已核实事实

- `Model/User/UserStats.py::UserStats` 的共享 Legacy 刻度字段为 `pv/gpv/gpv_real/gpv_unreal/contrib/pv_1l/pv_2l/pre_surplus_1l/pre_surplus_2l/total_1l/total_2l/remain_surplus_1l/remain_surplus_2l`，没有 `amount_encoding_version`；不得用不存在的 `pre_surplus/total/remain` 作静态锚点。
- `Model/User/EliteBonusStats.py::EliteBonusStats` 的共享 Legacy 整数域为 `pv_pcs/gpv/gpv_real/contrib_to_parent`，同样没有金额编码版本；`estimated_bonus` 是 legacy float，additive `estimated_bonus_cents` 只表示 V2 blank/init，不能证明 bonus parity。
- 固定提交中 `Common/PvAmount.py` 不存在；PE、SE、EAB、Leadership、Elite 各自保留金额/精度处理，形成多套 scale 和舍入语义。
- `UserPeriodHighestRank` 不持有金额字段，不属于 amount version 模型，禁止误加版本字段。

### 2.2 稳定定位

| 证据 | 稳定定位 | 当前事实 |
|---|---|---|
| EV-CODE-001 | `Model/User/UserStats.py::UserStats` | 无 amount version |
| EV-CODE-002 | `Model/User/EliteBonusStats.py::EliteBonusStats` | 无 amount version；奖金 float |
| EV-CODE-013 | `Common/PvAmount.py` | 文件不存在 |
| 目标合同 | v2.25 §四、T0-3/4/5/7 | units/version/ppm/cents/无 float |

## 3. 本任务修改目标

1. 建立项目唯一的公共金额域，统一 micro-units、integer cents、ppm、严格类型检查和 int64 上界保护。
2. 为持久化金额模型建立可审计编码版本；只有真正进入获批 V2 domain 且全部共享金额字段满足 V2 合同的记录才显式写2；00/01 共享-key Legacy record 不写2，legacy/unknown 只在 V2 calculation entry 阻断。
3. 提供只在两个批准边界使用的转换 API，并为后续 TASK 提供稳定、无业务反向依赖的底层接口。
4. 采用 additive-first 兼容策略，使本任务可先独立合入、独立测试和独立回滚。

## 4. 处置决定与方案选择

### 4.1 采用方案

新增 `Common/PvAmount.py`，作为最低层纯函数模块；模型增加可空 `amount_encoding_version`。工厂只有在获批 V2 domain 且完整记录满足 V2 编码合同时才显式传入 `2`；当前 production 01 的共享-key Legacy record 统一为 `V2_WRITE_NOT_AVAILABLE`。

核心常量：

```python
PV_SCALE = 1_000_000
BONUS_CENT_SCALE = 100
RATE_PPM_SCALE = 1_000_000
AMOUNT_ENCODING_VERSION_V2 = 2
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
```

目标 API 至少包含：

```text
parse_external_decimal_to_units(raw: str, *, max_decimals: int = 2) -> int
parse_db_amount_to_units(raw: Decimal | str, *, max_decimals: int = 2) -> int
require_units_int(value, field_name: str) -> int
require_amount_version(value, *, allow_legacy: bool = False) -> int
units_to_decimal_string(units: int) -> str
parse_percent_to_ppm(raw: Decimal | str) -> int
mul_units_by_ppm(units: int, ppm: int) -> int
units_ppm_to_bonus_cents(units: int, ppm: int, rounding_mode: str) -> int
checked_add_int64(*values: int) -> int
checked_mul_int64(a: int, b: int) -> int
assert_integer_amount_dtype(df, columns, df_name: str) -> None
```

### 4.2 版本策略

- 模型字段定义采用 `Optional[int] = None`，防止旧 Redis JSON 因字段缺失而无法反序列化。
- 只有真正进入获批 V2 domain 且全部共享金额字段满足 V2 编码合同的工厂才显式写 `amount_encoding_version=2`；00/01 的共享-key Legacy authoritative record 不写2。禁止把模型默认值设置为2。
- 读路径：version gate 只作用于 V2 calculation entry；`READ=false` 的 Legacy authoritative path 不得无条件 require 2。`None/缺失` 可进入 Legacy path 或只读审计 adapter，但不得进入 V2 calculation；其他值在 V2 入口 fail-loud。
- 不在本任务自动把 legacy 数值乘以 `1_000_000`。历史转换必须由有来源、有审计清单的 migration/rebuild 完成。

### 4.3 被否决方案

| 方案 | 否决理由 |
|---|---|
| 给 version 字段默认值 2 | 旧 JSON 缺字段时会被静默解释成新编码 |
| 在每个奖金服务各自写转换函数 | 延续 R-002 的多实现漂移 |
| 接受 float 后 `Decimal(str(float))` | 已经发生二进制精度损失，不是修复 |
| 在 `Until/Common.py` 混入奖金规则 | 公共层会反向依赖业务模块，破坏单向依赖 |
| 给 `UserPeriodHighestRank` 加 version | 该模型无金额，属于范围越界 |

## 5. 修改范围与受影响模块

### 5.1 新增文件

- `Common/PvAmount.py`：公共金额、ppm、cents、int64/dtype 守卫。
- `Common/AmountModelAdapter.py`（可选独立文件）：模型版本读取、legacy 隔离、序列化辅助。
- `User/Test/test_pv_amount_common.py`：公共 API 测试。
- `User/Test/test_amount_model_version.py`：版本和旧 JSON 兼容测试。

### 5.2 修改文件

| 文件 | 修改点 |
|---|---|
| `Model/User/UserStats.py` | 新增 `amount_encoding_version: Optional[int] = None`；金额字段注释统一为 units |
| `Model/User/EliteBonusStats.py` | 新增 version；增加 integer-cents 目标字段或标注 legacy float 字段只读 |
| `Redishelper/BaseRedisModel.py` | 如需，增加模型后置版本校验 hook；不得耦合奖金业务 |
| `User/UserStatsService.py` | 接收同一 immutable run config；00/01 共享-key Legacy 工厂不写2，获批11 V2 factory 显式传2 |
| `User/GlobalRecalculationService.py` | run 前加载/冻结一次 config；version gate 仅在 V2 entry；00/01 工厂不写2 |
| `User/PlacementIncrementalService.py` | batch/run config 冻结；00/01 共享 UserStats 工厂不写2 |
| `User/PlacementRecalculationService.py` | run config 冻结；批量 version gate 仅在 V2 entry |
| `User/EliteBonusService.py` | `_get_or_create_node` 按 frozen config 条件化；01 不把 legacy float 洗白为 cents |
| `User/GlobalEliteBonusRecalculationService.py` | frozen config；00/01 新节点不写2，V2 entry 才校验 version |

### 5.3 DEC-019 条件化字段与 factory 合同

- UserStats 精确共享字段：`pv`、`gpv`、`gpv_real`、`gpv_unreal`、`contrib`、`pv_1l`、`pv_2l`、`pre_surplus_1l`、`pre_surplus_2l`、`total_1l`、`total_2l`、`remain_surplus_1l`、`remain_surplus_2l`。
- EliteBonusStats 精确共享整数域：`pv_pcs`、`gpv`、`gpv_real`、`contrib_to_parent`；`estimated_bonus` 为 legacy float，禁止折算成 cents；`estimated_bonus_cents=0` 只证明 blank/init。
- 当前基线使用共享 Redis key/字段，故 production 01 下所有真实 UserStats/EliteBonusStats factory 均为 `V2_WRITE_NOT_AVAILABLE`；不得自行新建影子 key/table/namespace。
- 00/01 的 Legacy path 不做 V2 version gate；获批11的 V2 entry 必须 gate 并 stamping2。
- DEV/unit test 可直接构造 test-only 11 snapshot 验证 factory/domain；它不能进入 production admission、写真实 Redis 或构成生产 approval。
- factory 覆盖必须由 AST 扫描真实构造点产生，不得只锚定预写函数名单；TC-FLAG-14～21 承接此合同。
## 6. 明确排除项（防越界红线）

- 不在本任务重写 PE/SE/EAB/LB/Elite 具体奖金公式；它们在 TASK-02/03/04/05 迁移到公共 API。
- 不自动转换现有 Redis 数据，不执行生产清库，不生成没有审计来源的 seed。
- 不修改 `UserPeriodHighestRank`。
- 不修改有效 SQL 的业务公式。
- 不删除旧 `estimated_bonus` 字段；先 additive 兼容，最终停写由 TASK-02/05 完成。
- 不读取 `_bak`/`_final`、废弃 SQL 或 `GraphService.run_bfs`。

## 7. 前置条件与依赖关系

- 无前置 TASK。
- 依赖 P0-0/DEC-009 的 schema manifest 仅用于最终 UAT，不阻止公共层 DEV 实施。
- 本任务完成后，TASK-02～07 只能调用本任务 API，不得复制实现。

## 8. 修改后行为与技术设计

### 8.1 类型门禁

`require_units_int` 必须拒绝：

- `bool`（Python 中是 int 子类）；
- Python/NumPy/CuPy float；
- Decimal/string（内部域不负责转换）；
- NaN、Infinity、指数文本；
- 超出 int64 的值。

允许 Python int 与明确支持的 NumPy/CuPy signed integer，转换后再次检查 int64。

### 8.2 模型读取状态机

```text
version=2            -> NEW_DOMAIN_OK
version=None/缺字段   -> LEGACY_UNKNOWN，默认阻断
version=其他          -> INCOMPATIBLE，阻断并记录
```

所有异常日志包含：模型、Redis key、period、user_id、version、run_id，不打印敏感业务内容。

### 8.3 算术与舍入

- units 计算保持整数；每次加、乘、聚合前后检查 int64。
- `mul_units_by_ppm` 明确向零截断，不使用 `/` 产生 float。
- 最终奖金到 cents 的 rounding mode 由奖项合同调用参数决定：E/PE/SE/LB/TB 使用 SQL 对应截断；EAB 使用已确认最终一次 `ROUND_HALF_UP`。
- 公共层只实现算法，不自行选择奖项 rounding mode。

### 8.4 依赖方向

```text
Common/PvAmount
  ↑
Model adapters / User / Placement / Bonus
```

`Common` 禁止导入 `User`、`Model.User` 或任何奖金服务。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | `Common/PvAmount.py` 存在，import graph 无循环，公共层无业务模块 import | DEV | TC-002、TC-031 |
| AC-02 | 只有真正进入获批 V2 domain 且全部共享金额字段满足 V2 编码合同的 UserStats/EliteBonusStats record 才显式写 version=2；00/01 共享-key Legacy record 不得 stamping 2 | DEV+UAT | TC-003 |
| AC-03 | 旧 JSON 缺 version 可反序列化；legacy/unknown version 仅在进入 v2 计算入口时必定阻断，READ=false 的 Legacy authoritative path 不得无条件 require version=2 | DEV+UAT | TC-003 |
| AC-04 | version=1、3、字符串2、bool 等非法值全部阻断 | DEV | TC-003 |
| AC-05 | 外部/DB 边界 parser 与内部 `require_units_int` 职责分离 | DEV | TC-001、TC-002 |
| AC-06 | `0.1` float、`True`、NaN、Infinity、指数文本均被相应用例拒绝 | DEV | TC-001、TC-002 |
| AC-07 | 正负边界、int64 最大值、乘法溢出测试通过 | DEV+UAT | TC-008 |
| AC-08 | 只有持久化金额模型新增 version；无金额模型零误加 | DEV | TC-003、TC-030 |
| AC-09 | 全仓新增代码没有 `Decimal(str(float))`、`int(round(float))` 等洗白模式 | DEV | TC-002、TC-031 |
| AC-10 | TASK-01 独立回滚测试通过，旧代码在不写 v2 新数据时可启动 | DEV+UAT | TC-031、TC-032 |

> 环境规则：仅标记 UAT 或 DEV+UAT 的条目在环境不可用时只能记为 `PENDING_TEST_ENV`，不得以 DEV 结果替代最终关闭。

## 10. 环境验证与回传证据

### 10.1 DEV

- `python -m compileall` 与 AST/import graph。
- 公共 parser/version/int64/dtype 单元测试。
- Redis OM 旧 JSON/new JSON 序列化往返测试（可用隔离 Redis）。
- mutation：把 version 校验删除、把 bool 当 int、把 float 放行，测试必须失败。

### 10.2 UAT

关联 `UAT-001、UAT-011`：

- 混合 legacy/new Redis 样本读取；
- schema manifest 中金额字段、范围和 assignment 核对；
- 大批量聚合 int64 上界与错误阻断；
- 回传 Redis 前后样本、dtype、命令、exit code、完整输出、checksum。

无法提供 UAT 时，本任务只能标记 `DEV_ACCEPTED / PENDING_TEST_ENV`，不得关闭 Gate A。

## 11. 独立回滚与风险控制

1. flag 只能由 `PVAmountConfigProvider` 的 frozen run config 提供；当前批准状态为01且 Legacy authoritative。00/01 共享-key record 不写2，10/未批准11不得进入 production run。
2. 回滚时关闭 v2 新写并恢复旧读路径，但保留 version 字段和 v2 键供审计。
3. 已经写入的 v2 数值禁止除以 `1_000_000` 回写旧键；需要回退时以最后一个 committed legacy snapshot 服务。
4. 如果模型新增字段导致兼容问题，只回滚 reader enforcement，不删除 Redis JSON 字段。
5. 回滚后重跑版本扫描，确保没有 v2 数据被 legacy 代码误读。


### 第四轮补充：有符号整数除法合同

`trunc_div_zero(numerator, denominator)` 必须支持任意非零分母，并对 `(+,+)、(+,-)、(-,+)、(-,-)` 四象限均向零截断；分母为零必须抛出异常。
## 12. 版本记录

| 版本 | 日期 | 变更 | 治理状态 |
|---|---|---|---|
| v1.2-r10 | 2026-08-08 | 依据 DEC-019 条件化 AC-02/03、共享-key factory stamping、version gate 与 TEST-ONLY V2 domain | DRAFT |
