# WORK-PVAM-03 配置解析、ppm 与硬编码清理施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-03`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-004` 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；发现漂移立即登记 `BLOCK-PVAM-03-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-03` |
| 施工任务名称 | 配置解析、ppm 与硬编码清理 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-03@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-004` |
| 复核闭环追踪号 | `REM-004 / W-004 / V-004` |
| 来源检查项 | `CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008` |
| 关联决策 | `DEC-001、DEC-002、DEC-003、DEC-009、DEC-014` |
| 代码基线 | `l343765828/Redemption@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb` |
| SQL基线 | `sql_uat/*@2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | WORK-PVAM-01 DEV_VERIFIED |
| 功能开关 | `BONUS_CONFIG_SNAPSHOT_V2` |

### 1.1 一对一追溯摘要

```text
CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008
  └─ R-004
       └─ DEC-001、DEC-002、DEC-003、DEC-009、DEC-014
            └─ TASK-PVAM-03 (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-03
                      ├─ STEP-PVAM-03-01 / STEP-PVAM-03-02 / STEP-PVAM-03-03 / STEP-PVAM-03-04 / STEP-PVAM-03-05 / STEP-PVAM-03-06
                      ├─ TC-PVAM-03-01 / TC-PVAM-03-02 / TC-PVAM-03-03 / TC-PVAM-03-04 / TC-PVAM-03-05 / TC-PVAM-03-06 / TC-PVAM-03-07
                      └─ EV-PVAM-03-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-004 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-03` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008 | CONTROLLED |
| 正式决策 | DEC-001、DEC-002、DEC-003、DEC-009、DEC-014 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`，工作树无未登记变更。
- [ ] `TASK-PVAM-03` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：WORK-PVAM-01 DEV_VERIFIED。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 建立不可变、可审计的 ConfigSnapshot 和逐奖项 ConfigRequirementMatrix；费率只以 signed ppm 进入计算，移除生产硬编码默认并保持各奖项独立的 raw/TYPE/requiredness 规则。 |
| 当前行为 | `PEBonusService.__init__` 固定 `_pro_elite_rate_ppm = 150000`。；`EliteBonusService.__init__` 在未提供 loader 时告警后使用 `Decimal('0.15')`。；`SuperEliteBonusService._parse_se_rate` 对 name/type 执行 strip/lower，要求 rate>0；这与 signed ppm、exact raw SE 合同不一致。；当前各奖项 requiredness、0/负值/重复/非法值处理不集中，run 也没有统一配置 checksum。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb`；来源 `TASK-PVAM-03`；检查项 `CHK-DATA-004、CHK-BIZ-007、CHK-BIZ-008` |

### 3.2 已确认代码事实

- `PEBonusService.__init__` 固定 `_pro_elite_rate_ppm = 150000`。
- `EliteBonusService.__init__` 在未提供 loader 时告警后使用 `Decimal('0.15')`。
- `SuperEliteBonusService._parse_se_rate` 对 name/type 执行 strip/lower，要求 rate>0；这与 signed ppm、exact raw SE 合同不一致。
- 当前各奖项 requiredness、0/负值/重复/非法值处理不集中，run 也没有统一配置 checksum。

### 3.3 本任务目标

建立不可变、可审计的 ConfigSnapshot 和逐奖项 ConfigRequirementMatrix；费率只以 signed ppm 进入计算，移除生产硬编码默认并保持各奖项独立的 raw/TYPE/requiredness 规则。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

本任务不存在附件二提出的新增`BLOCK-PVAM-03`；逐键missing/duplicate/exact规则已由上游TASK固定。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | PE初始化 | `User/PEBonusService.py::PEBonusService.__init__` | 无配置参数 | 固定150000ppm | 绕过AR_CONFIG |
| 2 | Elite初始化 | `User/EliteBonusService.py::EliteBonusService.__init__` | 可选loader | 缺失时0.15 | 假成功 |
| 3 | SE配置 | `User/SuperEliteBonusService.py::_parse_se_rate` | DataFrame config | strip/lower、rate<=0阻断 | 误改raw/负值 |
| 4 | TB oracle | `User/team_bonus_tb.py` 配置函数 | AR_CONFIG fixture | 按SQL模拟 | 必须保持oracle |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| PE | proEliteRate | 从snapshot读signed ppm | 是 | STEP-03-03/TC-004 |
| Elite | eliteRate | 删除0.15 fallback | 是 | STEP-03-03/TC-014 |
| SE | superEliteRate/Country* | exact raw TYPE与signed ppm | 是 | STEP-03-04/TC-005/018 |
| EAB/LB | 各自配置 | 使用同一snapshot但独立矩阵 | 是 | STEP-03-04/TC-019/021 |
| TB oracle | teamBisectRate/TouchRate/Capping | 保持SQL忠实，仅接snapshot fixture | 测试调整 | TC-004/013 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `Common/BonusConfig.py`，定义 `ConfigRequirement`、`ConfigSnapshot`、`ConfigSnapshotLoader` 和 `parse_signed_percent_to_ppm`。
- snapshot 保留 raw 行、canonical 值、row count、source/version/checksum；run 启动后冻结。
- 矩阵逐键声明 missing/zero/negative/duplicate/invalid/type/country 行为，不将 SE exact raw 规则套给 EAB/LB。
- 负费率允许为 signed ppm；最大值/专项上限由上游系统保证，本仓不二次决定。
- DEC-004 2B 写入侧不在本任务建设，配置 snapshot 可由UAT受控fixture或现有只读加载适配器提供。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 硬编码15%兜底 | 缺配置应fail-loud或按矩阵为0 | R-004 |
| 统一strip/lower所有配置 | 改变SE exact raw | DEC-003 |
| rate<=0一律阻断 | 负费率已允许，0按键矩阵 | DEC-001/002 |
| 重写TB生产服务 | 超出范围 | EX-005 |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + BONUS_CONFIG_SNAPSHOT_V2 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `Common/BonusConfig.py`、`Model/Config/ConfigSnapshot.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `Common/BonusConfig.py` | `ConfigRequirement`/`ConfigSnapshot`/parser | 新增 | 不存在 | 建立矩阵、raw/canonical/checksum和signed ppm | 运行期唯一配置对象 | 不得包含业务默认 |
| CHG-02 | `Model/Config/ConfigSnapshot.py` | 可序列化manifest模型 | 新增 | 不存在 | 记录period/run/source/raw checksum | 证据可追溯 | 不得含密钥 |
| CHG-03 | `User/PEBonusService.py` | `__init__`、`execute_batch` | 修改 | 固定150000 | 强制注入snapshot/ppm | 无硬编码 | 不得改PE base公式 |
| CHG-04 | `User/EliteBonusService.py` | `__init__` | 修改 | loader缺失用0.15 | 生产模式缺snapshot fail-loud；测试显式fixture | 无占位默认 | 不得改资格 |
| CHG-05 | `User/GlobalEliteBonusRecalculationService.py` | `__init__` | 修改 | 默认elite_rate=0.15 | 改显式ConfigSnapshot/ppm | 全量增量同run | 不得保留生产默认 |
| CHG-06 | `User/SuperEliteBonusService.py` | `_parse_se_rate`、`_parse_country_mapping` | 修改 | strip/lower与正值限制 | 按SE矩阵exact raw、signed ppm | 非法与豁免分开 | 不得把EAB/LB规则套入 |
| CHG-07 | `User/EliteAchievementBonusService.py` / `User/LeadershipBonusGPUService.py` | 配置读取接口 | 修改 | 各自解析 | 接snapshot与公共ppm，保留专项规则 | 同run checksum | 不得改业务公式 |
| CHG-08 | `User/team_bonus_tb.py` 测试适配 | oracle config输入 | 修改 | DataFrame直接读 | 接受受控snapshot导出的等价fixture | SQL parity不变 | 不得生产接线 |
| CHG-09 | `User/Test/test_bonus_config.py` | pytest | 新增 | 不存在 | 矩阵、checksum、freeze、mutation | 配置合同可测 | 不得依赖真实DB |

### 6.1 固定基线锚点复验

| 文件与符号 | 基线事实 | 施工动作 |
|---|---|---|
| `User/PEBonusService.py::PEBonusService.__init__` | `_pro_elite_rate_ppm=150000` | 改为必传冻结ConfigSnapshot |
| `User/EliteBonusService.py::EliteBonusService.__init__` | loader缺失时回退`Decimal('0.15')` | 生产路径缺配置必须fail-loud |
| `User/GlobalEliteBonusRecalculationService.py::__init__` | `elite_rate: float=0.15` | 改为signed ppm或受控Decimal/string，不接受float默认 |
| `User/SuperEliteBonusService.py::_parse_se_rate` | strip/lower并拒绝`rate<=0` | 按逐键矩阵解析；负值不因负号被拒绝 |
| `User/SuperEliteBonusService.py::_normalize_id_series` | strip/upper/删除`.0` | exact-raw字段先校验原值，禁止洗白 |
| `User/team_bonus_tb.py` | SQL faithful oracle | 只补配置矩阵测试，不接入生产 |

### 6.2 ConfigRequirementMatrix合同

```python
from dataclasses import dataclass
from enum import Enum

class MissingPolicy(str, Enum):
    ZERO = "ZERO"
    ERROR = "ERROR"

@dataclass(frozen=True)
class ConfigRequirement:
    config_name: str
    type_exact: str | None
    missing_policy: MissingPolicy
    duplicate_is_error: bool
    exact_raw_name: bool = False
    exact_raw_type: bool = False
    allow_negative: bool = True
```

`missing_policy`不得由施工人员重新决定，必须来自TASK-03已批准的逐奖项矩阵和有效SQL：SQL/DEC定义缺失为0的键使用ZERO；正式required键使用ERROR；重复、TYPE、Country规则按奖项独立处理。附件二提出的新`BLOCK-PVAM-03`不成立，本终稿不新增DEC。

### 6.3 费率转换约束

- raw只允许Decimal或canonical decimal string；float、NaN、Infinity和科学计数法阻断。
- 百分数转ppm必须证明乘法结果为整数；显式0保留为0，负值保留符号。
- 同一run只加载一次ConfigSnapshot，并记录raw rows、source、version、checksum和canonical checksum。
- 不因上游负责的最大值/Country空值/EAB或LB非bonus TYPE而新增二次业务阻断；SE exact TYPE规则仍独立执行。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-03-01：建立配置矩阵与snapshot

- 目的：建立配置矩阵与snapshot，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：WORK-01 DEV_VERIFIED
- 修改文件：`Common/BonusConfig.py`、`Model/Config/ConfigSnapshot.py`
- 目标符号：新模块
- 精确操作：
1. 编码每个配置键的requiredness/0/负值/重复/exact规则
2. 计算稳定SHA-256。
- 必须保持：不读取MySQL；不内置比例
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile Common/BonusConfig.py Model/Config/ConfigSnapshot.py`
- 本步单元验证：`TC-PVAM-03-01/02`
- 完成证据：`EV-PVAM-03-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：矩阵与DEC冲突时BLOCK

### STEP-PVAM-03-02：实现signed ppm解析

- 目的：实现signed ppm解析，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01
- 修改文件：`Common/BonusConfig.py`
- 目标符号：parser
- 精确操作：
1. 只接受Decimal/string
2. 15→150000、-15→-150000、0→0
3. 拒绝float/NaN。
- 必须保持：不设业务最大值
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_bonus_config.py -k ppm`
- 本步单元验证：`TC-PVAM-03-01`
- 完成证据：`EV-PVAM-03-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：出现float中转立即停工

### STEP-PVAM-03-03：移除PE/Elite硬编码

- 目的：移除PE/Elite硬编码，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01/02
- 修改文件：PE与Elite两套服务
- 目标符号：构造器与执行入口
- 精确操作：
1. 强制显式snapshot
2. 生产缺失fail-loud
3. 测试传fixture。
- 必须保持：保持公式/资格/表结构
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile User/PEBonusService.py User/EliteBonusService.py User/GlobalEliteBonusRecalculationService.py`
- 本步单元验证：`TC-PVAM-03-03`
- 完成证据：`EV-PVAM-03-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任何生产fallback残留不合并

### STEP-PVAM-03-04：改造SE/EAB/LB配置入口

- 目的：改造SE/EAB/LB配置入口，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01/02
- 修改文件：三个奖金服务
- 目标符号：parse/compute入口
- 精确操作：
1. 接snapshot
2. SE exact raw
3. EAB/LB按自身矩阵
4. 负ppm可计算。
- 必须保持：不新增上游合法性校验
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m compileall -q User Common Model`
- 本步单元验证：`TC-PVAM-03-04/05`
- 完成证据：`EV-PVAM-03-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：合法SQL样例变化则停工

### STEP-PVAM-03-05：保护TB oracle并补回归

- 目的：保护TB oracle并补回归，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01
- 修改文件：`User/team_bonus_tb.py`与测试
- 目标符号：配置fixture
- 精确操作：
1. 保持SQL的missing/0/capping=0/重复行为
2. snapshot仅做输入适配。
- 必须保持：不把oracle接生产
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_team_bonus_tb.py User/Test/test_bonus_config.py`
- 本步单元验证：`TC-PVAM-03-06`
- 完成证据：`EV-PVAM-03-05`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：oracle结果变化阻断

### STEP-PVAM-03-06：建立run冻结与manifest测试

- 目的：建立run冻结与manifest测试，落实 `TASK-PVAM-03` 的已批准目标。
- 前置条件：STEP-03-01~05
- 修改文件：测试与run入口
- 目标符号：manifest
- 精确操作：
1. 同一run各奖项使用相同snapshot id/checksum
2. 中途源变化不影响当前run。
- 必须保持：不实现DEC-004 2B producer
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q User/Test/test_bonus_config.py`
- 本步单元验证：`TC-PVAM-03-02/07`
- 完成证据：`EV-PVAM-03-06`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：checksum不稳定不得合并

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| AR_CONFIG快照 | 原始行由各服务解析 | ConfigSnapshot + signed ppm | run启动适配 | snapshot_id/checksum | 缺失按矩阵fail-loud |

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
| TC-PVAM-03-01 | 单元 | signed ppm | `15`,`0`,`-15`,`float(15)` | 150000、0、-150000；float拒绝 | STEP-03-02 | DEV | NOT_RUN |
| TC-PVAM-03-02 | 单元 | snapshot checksum/freeze | 同一行集不同输入顺序；run中改源 | canonical checksum相同；已冻结对象不变 | STEP-03-01/06 | DEV | NOT_RUN |
| TC-PVAM-03-03 | 回归 | 硬编码清理 | PE/Elite缺配置 | 生产模式抛明确错误；无150000/0.15 fallback | STEP-03-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-04 | 契约 | SE exact TYPE | `bonus`,` BONUS `,`Bonus` | 只按已批准exact raw接受；变体不被strip/lower救回 | STEP-03-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-05 | 差分 | 负费率 | 合法输入1000 BV、-15% | 产生signed结果并与专项SQL/oracle口径比较；不因负号阻断 | STEP-03-04 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-06 | oracle | TB capping=0 | touch=600,rate=10%,capping=0 | TOUCH_BASE=60 | STEP-03-05 | DEV+UAT | NOT_RUN |
| TC-PVAM-03-07 | 集成 | 多服务同snapshot | PE/SE/EAB/LB同run | manifest中的snapshot id/checksum一致 | STEP-03-06 | DEV+UAT | NOT_RUN |

受控检查方案用例映射：`TC-004, TC-005, TC-013, TC-018, TC-031, TC-032`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="2475c6c49e60089b28f8ef1c0b75e86b2ceb6ebb"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-03}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-03"

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
  --work-id "WORK-PVAM-03" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-03.sh" \
  --out "evidence/WORK-PVAM-03/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
import pytest
from Common.BonusConfig import ConfigSnapshot, parse_signed_percent_to_ppm


def test_signed_ppm_and_snapshot_contract() -> None:
    assert parse_signed_percent_to_ppm("15") == 150_000
    assert parse_signed_percent_to_ppm("0") == 0
    assert parse_signed_percent_to_ppm("-15") == -150_000
    with pytest.raises(TypeError):
        parse_signed_percent_to_ppm(15.0)  # type: ignore[arg-type]
    a = ConfigSnapshot.from_rows([{"config_name": "proEliteRate", "type": "bonus", "value": "15"}])
    b = ConfigSnapshot.from_rows([{"value": "15", "type": "bonus", "config_name": "proEliteRate"}])
    assert a.checksum == b.checksum
    assert a.require_ppm("proEliteRate") == 150_000
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-03-01：真实配置快照与SQL/oracle差分

- 对应受控测试：`TC-004、TC-005、TC-013、TC-017、TC-018、TC-021`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：脱敏AR_CONFIG快照；DB/SQL oracle可用；fixture有checksum
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work03-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-03 --run-id "$RUN_ID" --tc TC-004,TC-005,TC-013,TC-017,TC-018,TC-021
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
mysql --defaults-extra-file="${MYSQL_CNF:?}" --batch --raw <<'SQL'
SELECT CONFIG_NAME, TYPE, VALUE
  FROM AR_CONFIG
 WHERE CONFIG_NAME IN ('eliteRate','proEliteRate','superEliteRate','teamBisectRate')
    OR CONFIG_NAME LIKE 'teamTouchRate%'
    OR CONFIG_NAME LIKE 'teamTouchCapping%'
 ORDER BY CONFIG_NAME, TYPE, VALUE;
SQL
```

- 执行步骤：
1. 导出配置原始行及checksum
2. 执行各奖项配置矩阵和TB oracle
3. 导出manifest、解析ppm和SQL/Python差分
- 精确预期：
- PE/Elite无硬编码兜底
- 负费率按合同计算；SE exact raw成立
- TB missing/0/capping=0与SQL一致
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| PE 15% | AR_CONFIG proEliteRate=15 | `MIN(VALUE)/100=0.15` | `150000 ppm` | signed ppm | 0 |
| TB capping=0 | touch=600,rate=10%,capping=0 | TOUCH_BASE=60 | 60 units-domain equivalent | SQL capping semantics | 0 |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | PE 和 Elite 生产路径无硬编码 15%/150000 默认 | STEP-PVAM-03-03 | TC-004、TC-031 | EV-PVAM-03-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 所有生产奖金费率使用同一 signed ppm parser | STEP-PVAM-03-01/02/03/04 | TC-004 | EV-PVAM-03-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 缺失、0、负值、重复、非法文本、float、exact raw 的逐奖项矩阵通过 | STEP-PVAM-03-01/02/04/05 | TC-004、TC-005 | EV-PVAM-03-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | 负费率不因负号被拒绝，结果按既有有符号公式计算 | STEP-PVAM-03-02/04 | TC-004 | EV-PVAM-03-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | SE raw TYPE/name 的空格和大小写变体不会被静默修复 | STEP-PVAM-03-01/04 | TC-005、TC-018 | EV-PVAM-03-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | DEC-003 豁免项不被错误判失败；SE 独立规则不被豁免覆盖 | STEP-PVAM-03-01/04 | TC-005、TC-018 | EV-PVAM-03-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | run manifest 含 raw/canonical checksum，同一 run 各服务一致 | STEP-PVAM-03-01/06 | TC-004、TC-032 | EV-PVAM-03-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 配置运行中变化不影响已启动 run；下一个 run 使用新 snapshot | STEP-PVAM-03-06 | TC-004、TC-032 | EV-PVAM-03-08 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | TB oracle 的 missing/0/capping=0 测试保持 SQL parity | STEP-PVAM-03-05 | TC-004、TC-013 | EV-PVAM-03-09 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-10 | ConfigRequirementMatrix 可机器读取并覆盖当前范围内所有配置键 | STEP-PVAM-03-01/06 | TC-031、TC-032 | EV-PVAM-03-10 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| 配置矩阵误合并奖项 | 一套规则套所有奖项 | 合法输入被拒/脏值被洗白 | 逐奖项矩阵 | TC-004/005差分 | 回滚相关consumer |
| snapshot不稳定 | 源顺序影响hash | 同run不一致 | canonical排序与hash | manifest | 停工 |
| 2B链不存在 | UAT误把fixture当生产 | 虚假PASS | 显式DEFERRED标签 | evidence manifest | 保持BLOCKED |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-03/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：冻结配置snapshot与run checksum；恢复旧镜像和上一个已批准配置对象；保留新snapshot审计，不删除负ppm或raw证据。

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
| EV-PVAM-03-01 | AC-01验收证据：PE 和 Elite 生产路径无硬编码 15%/150000 默认 | STEP-PVAM-03-03 | evidence/WORK-PVAM-03/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-03-02 | AC-02验收证据：所有生产奖金费率使用同一 signed ppm parser | STEP-PVAM-03-01/02/03/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-03-03 | AC-03验收证据：缺失、0、负值、重复、非法文本、float、exact raw 的逐奖项矩阵通过 | STEP-PVAM-03-01/02/04/05 | evidence/WORK-PVAM-03/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-03-04 | AC-04验收证据：负费率不因负号被拒绝，结果按既有有符号公式计算 | STEP-PVAM-03-02/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-03-05 | AC-05验收证据：SE raw TYPE/name 的空格和大小写变体不会被静默修复 | STEP-PVAM-03-01/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-03-06 | AC-06验收证据：DEC-003 豁免项不被错误判失败；SE 独立规则不被豁免覆盖 | STEP-PVAM-03-01/04 | evidence/WORK-PVAM-03/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-03-07 | AC-07验收证据：run manifest 含 raw/canonical checksum，同一 run 各服务一致 | STEP-PVAM-03-01/06 | evidence/WORK-PVAM-03/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-03-08 | AC-08验收证据：配置运行中变化不影响已启动 run；下一个 run 使用新 snapshot | STEP-PVAM-03-06 | evidence/WORK-PVAM-03/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-03-09 | AC-09验收证据：TB oracle 的 missing/0/capping=0 测试保持 SQL parity | STEP-PVAM-03-05 | evidence/WORK-PVAM-03/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-03-10 | AC-10验收证据：ConfigRequirementMatrix 可机器读取并覆盖当前范围内所有配置键 | STEP-PVAM-03-01/06 | evidence/WORK-PVAM-03/attempt-*/ac/AC-10/ | 待指派QA | PENDING |
| EV-PVAM-03-P01 | BonusConfig/ConfigSnapshot源码 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P02 | PE/Elite/SE/EAB/LB接入diff | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P03 | ConfigRequirementMatrix机器文件 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P04 | DEV矩阵与TB oracle报告 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-03-P05 | UAT配置快照/SQL差分包 | 对应STEP/TC | evidence/WORK-PVAM-03/attempt-*/package/ | 待指派QA | PENDING |

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
  --work-id "WORK-PVAM-03" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-03/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-03` 批准 allowlist；
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
| STEP-PVAM-03-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-05 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-03-06 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-03-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-02 | DEV | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |
| TC-PVAM-03-07 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-03-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-03-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

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
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-03` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：统一 `RecalcProcessResult` 类名并补齐 `should_ack`；历史版本曾调整施工套件审批状态，不改变 CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
