# TASK-PVAM-03 配置解析、ppm Parser 与硬编码清理

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 所属总方案 | `MODPLAN-PVAM_v1.2` |
| 任务编号 | `TASK-PVAM-03` |
| 来源检查项 | `CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008` |
| 来源问题 | `R-004` |
| 处置项 | `REM-004` |
| 施工项 | `W-004` |
| 验证项 | `V-004` |
| 关联决策 | `DEC-001、DEC-002、DEC-003、DEC-009、DEC-014` |
| 严重级别 | `P0` |
| 当前状态 | `DRAFT` |
| 受控基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| 编制日期 | `2026-08-04` |
| 审批人 | `待组织授权人签署` |
| 审批日期 | `待签署` |
| 前置任务 | `TASK-PVAM-01` |

> `DRAFT` 表示技术内容已修订但尚无可核验组织施工授权；不得启动代码施工、部署或生产发布。


### 1.1A 授权与执行状态分层

- 授权状态依据：`AUTHORIZATION_STATUS-PVAM-v2`；当前为 `PENDING_ORGANIZATIONAL_APPROVAL`。
- 本TASK治理状态：`DRAFT`；授权状态：`PENDING_ORGANIZATIONAL_APPROVAL`。
- 代码实现状态：`NOT_STARTED`；UAT依赖项：`PENDING_TEST_ENV`。
- 批准不改变来源报告的`REJECTED`结论，也不允许绕过WORK级patch、rollback和环境门禁。

## 2. 问题与代码证据

- `PEBonusService.__init__` 固定 `_pro_elite_rate_ppm = 150000`，绕过冻结配置。
- `SuperEliteBonusService._parse_se_rate` 对 name/type 执行 strip/lower，并对 `rate_val<=0` 阻断；这与 signed rate、显式0和 exact raw 合同不一致。
- Elite 服务在未提供 loader 时默认 `0.15`，属于 T0-8 要求清理的无来源默认。
- 各奖金模块分别解析百分比、Country、TYPE，缺少统一 ConfigRequirementMatrix、snapshot id 和 checksum。

## 3. 本任务修改目标

1. 建立统一、可配置的 signed ppm parser 和 ConfigRequirementMatrix。
2. 删除 PE/Elite 等无来源硬编码默认；每次 run 冻结配置行、raw value、canonical value、snapshot id、checksum。
3. 严格区分各奖项的 requiredness、missing/0、负值、重复、Country/TYPE 和 exact raw 规则，禁止用一个“万能 normalize”覆盖差异。
4. 为 TASK-04 的 monthActivePV getter提供底层配置快照接口，但不在本任务决定 Active。

## 4. 处置决定与方案选择

### 4.1 采用方案

新增 `Common/BonusConfig.py`（或等价低层模块），定义：

```python
ConfigRequirement(
    key,
    type_rule,
    cardinality,
    missing_policy,
    zero_policy,
    signed_policy,
    raw_canonical_policy,
    value_encoding,
)
```

统一 API：

```text
load_frozen_config_snapshot(source, period_snapshot) -> ConfigSnapshot
parse_rate_ppm(snapshot, requirement) -> int
parse_country_mapping(snapshot, requirement) -> Mapping
snapshot_manifest(snapshot) -> dict
```

### 4.2 奖项差异

- PE/Elite/EAB/SE/LB/TB 的配置逐项登记，不允许从另一个奖项推断。
- DEC-001：负费率不得仅因负号阻断，作为有符号 ppm 进入既有公式。
- DEC-002：不重复验证业务最大值；仍检查 int64 运算安全。
- DEC-003：EAB/LB 的 Country 空/0和非 bonus TYPE 属上游校验豁免；SE 的 exact raw TYPE/name 仍按其批准合同执行。
- required config 的缺失/重复按具体矩阵处理；SQL/DEC 定义 missing=0 的配置返回0，不能一概强制报错。

### 4.3 被否决方案

- 保留 15% 默认作为“兜底”；会隐藏配置缺失和版本漂移。
- 对所有 name/type `.strip().lower()`；会把不规范原始配置自动修复，破坏 exact canonical 审计。
- 所有负值一律报错；违反 DEC-001。
- 在每个服务里自行读 AR_CONFIG；无法冻结同一 run 快照。
- 用数据库唯一键代替 DataFrame/Delta/Redis 同步后的 cardinality 校验。

## 5. 修改范围与受影响模块

- 新增 `Common/BonusConfig.py`、`Model/Config/ConfigSnapshot.py`（或等价结构）。
- 修改 `User/PEBonusService.py`：删除 `_pro_elite_rate_ppm=150000`，接收冻结 ppm。
- 修改 `User/EliteBonusService.py` 与 `GlobalEliteBonusRecalculationService.py`：删除默认 0.15 生产路径。
- 修改 `User/SuperEliteBonusService.py`：按 exact raw/配置矩阵解析，不做未授权 normalize/阻断。
- 修改 `User/EliteAchievementBonusService.py`、`LeadershipBonusGPUService.py` 的配置入口，复用 snapshot/ppm。
- `User/team_bonus_tb.py` 保持 SQL oracle 身份；增加/更新配置矩阵测试，不把其接入生产。
- 修改结算 orchestrator：run 启动时冻结一次配置并传给所有模块。

## 6. 明确排除项（防越界红线）

- 不更改各奖金业务比例本身；比例来自受控配置。
- 不新增 P0-5B 未签字的 requiredness；未确认子项进入 TASK-08 外部边界。
- 不在本任务实现 monthActivePV Redis/Delta 回退；由 TASK-04 完成。
- 不对 DEC-002/003 已明确由上游校验的业务值做二次阻断。
- 不建设生产 Team Bonus 服务。
- 不修改有效 SQL。

## 7. 前置条件与依赖关系

- 依赖 TASK-01 的 ppm、int64 和版本 API。
- TASK-04、TASK-05 依赖本任务的冻结配置 snapshot。
- UAT 最终验收依赖 TASK-08 提供有来源的 AR_CONFIG 快照及 checksum。
- DEC-004 2B 写入侧本轮选择“缓建”；T03 不得预设真实 Delta/Redis 同步链已存在，只消费 T04 getter 可读取的受控 fixture。

## 8. 修改后行为与技术设计

### 8.1 ConfigSnapshot

至少记录：

```text
period_num / calc_month
source (Redis/Delta/DB fixture)
source_version
loaded_at
raw_row_count
raw_rows_checksum
requirements_version
canonical_values
canonical_checksum
```

同一 run 的所有服务只使用同一 snapshot，不在运行中刷新。

### 8.2 ppm

- 通过 Decimal/string 精确解析百分比到有符号 ppm。
- 显式0保留为0；缺失按 requirement 的 missing policy。
- 任何 float raw value 阻断；不接受科学计数法。
- 负值允许，但后续乘法进行 int64 checked arithmetic。

### 8.3 exact raw

SE 要求 exact raw 的字段使用原始字符串精确比较；不能先 strip/lower。用于审计的 raw row必须原样进入 manifest。非 exact 项可有独立 canonicalizer，但必须由 requirement 明确声明。

## 9. 任务验收标准（AC）

| AC | 验收标准 | 环境 | 关联 TC |
|---|---|---|---|
| AC-01 | PE 和 Elite 生产路径无硬编码 15%/150000 默认 | DEV+UAT | TC-004、TC-031 |
| AC-02 | 所有生产奖金费率使用同一 signed ppm parser | DEV+UAT | TC-004 |
| AC-03 | 缺失、0、负值、重复、非法文本、float、exact raw 的逐奖项矩阵通过 | DEV+UAT | TC-004、TC-005 |
| AC-04 | 负费率不因负号被拒绝，结果按既有有符号公式计算 | DEV+UAT | TC-004 |
| AC-05 | SE raw TYPE/name 的空格和大小写变体不会被静默修复 | DEV+UAT | TC-005、TC-018 |
| AC-06 | DEC-003 豁免项不被错误判失败；SE 独立规则不被豁免覆盖 | DEV+UAT | TC-005、TC-018 |
| AC-07 | run manifest 含 raw/canonical checksum，同一 run 各服务一致 | DEV+UAT | TC-004、TC-032 |
| AC-08 | 配置运行中变化不影响已启动 run；下一个 run 使用新 snapshot | DEV+UAT | TC-004、TC-032 |
| AC-09 | TB oracle 的 missing/0/capping=0 测试保持 SQL parity | DEV+UAT | TC-004、TC-013 |
| AC-10 | ConfigRequirementMatrix 可机器读取并覆盖当前范围内所有配置键 | DEV | TC-031、TC-032 |

> 本任务只验证配置读取/解析契约，不把 DEC-004 2B 写入侧 fixture 冒充真实生产同步链。

## 10. 环境验证与回传证据

### DEV

- parser、matrix、exact raw、checksum 单元测试；
- mutation：恢复硬编码、添加 `.lower()`、拒绝负值，测试必须失败；
- E/PE/SE/EAB/LB/TB 配置 fixture 差分。

### UAT

关联 `UAT-002、UAT-005`：

- DBA/环境方受控注入的 AR_CONFIG/Delta/Redis fixture；记录来源、注入人、版本和 checksum，不据此宣称生产同步链已存在；
- 缺失/0/负/重复/非法 TYPE/Country；
- 同一 snapshot 运行 PE/SE/EAB/LB；
- 与有效 SQL 同数据差分；
- 回传 raw rows、snapshot/checksum、parser trace、奖金结果。

## 11. 独立回滚与风险控制

1. 新 parser 通过 `CONFIG_PARSER_V2` 开关逐服务切换。
2. 回滚时使用最后一个已验证冻结 snapshot，不恢复硬编码默认。
3. snapshot 格式版本化；旧 reader 不读取新字段时仍可启动。
4. 若某奖项矩阵存在争议，只冻结该奖项切换，不影响其他已通过模块。
5. 所有回滚记录 snapshot id、受影响 run/period 和前后 checksum。
