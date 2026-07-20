# Elite Achievement Bonus (EAB) 业务需求与系统重构规范（修正版 v8）

> **校正说明**：本版依据 EAB 存储过程 `CALC_BE_EAB`、最终表 `AR_CALC_BONUS_EAB` 的 DDL，以及产品 Plan（EKPlan）逐条校正。
> 当 PDF / Plan 与旧 SQL 存在口径差异时，**以旧 SQL 的实际线上行为作为历史还原基准**；
> 凡本文已明确标注为"历史漏洞""重构修正""行为变更"的部分，**新系统不得继续继承旧 SQL 缺陷**。
>
> **运行环境**：实际数据库为 **MariaDB 10.6.24**（非 MySQL）。涉及 DECIMAL 舍入、`SELECT ... INTO` 多行报错等行为已按 MariaDB 核对；差异处单独标注。
> **已确认表结构**：本版已并入最终表 `AR_CALC_BONUS_EAB` 的完整 DDL（见附录 A）。**注意：仅最终结果表的 DDL 已知，源表 / 中间表 DDL 仍待补，相关结论不得由最终表 DDL 外推**。
> 带 ⚠️ 的条目为相对前版的重点订正。

---

## 1. 业务背景与概述

Elite Achievement Bonus (EAB) 是一项以国家或大区为单位的业绩分红奖金，与会员级别无关，旨在奖励当月个人小组业绩（PGS）达标的会员。符合"计算资格"的会员平均分配其所属国家或大区当期**有效订单业绩**的特定配置比例；最终实际发放受会员活跃状态严格控制。

---

## 2. 业务核心规则定义

### 2.1 计算资格与资金池分配

- **计算资格**：会员在当期网络业绩源数据中，按 Elite Bonus 同口径计算出的个人小组业绩（PGS）≥ 1000 BV，即具备"计算资格"。
- **工程基准**：原 SQL 中 `AR_CALC_BE_E_NET.GPV` 承载 EAB 所需的 PGS 口径；新系统若字段名变化，以"Elite Bonus 同口径计算出的当期个人小组业绩"为唯一基准。
- **阈值常量**：1000 BV 是跨奖项共用的 Elite 核心业务常量。原 SQL 声明了 `VV_ARRIVE_PV DEFAULT 1000` 却硬编码 `GPV >= 1000`（声明的变量并未被使用）。新系统应将其定义为统一的全局业务常量或集中配置，避免硬编码散落。
- **配置比例 (EAB_RATE)**：拨出比例须由系统配置动态获取，统一抽象为 `EAB_RATE`（旧系统来源 `AR_CONFIG.CONFIG_NAME='eabRate'、TYPE='bonus'`）。当前业务值为 10%。
- **分配公式**：单人应得 EAB = 大区当期有效总订单 PV × EAB_RATE ÷ 大区当期具备计算资格的总人数。
- **资金池不二次分配**：符合计算资格的所有人共同构成计算分母。

### 2.2 发放资格（活跃状态拦截）

- **考核指标**：会员当月是否"活跃"，即每月个人消费累计达 30 BV。
- **活跃会员**：实际发放 = 单人应得 EAB。
- **不活跃会员**："算出来不发"——作为分母参与均摊，但实际发放强制置 0；未发出的资金直接沉淀，**不退回资金池二次分配**。
- ⚠️ **实现归属说明**：上述"活跃=应得、不活跃=0"属业务规则 / 新系统数据契约。旧 `CALC_BE_EAB` **仅**计算理论 `BONUS_EAB` 并输出 `IS_ACTIVE` 标记，过程内**并未**对不活跃会员置 0、也未生成 `Actual_Bonus`（无 `CASE WHEN IS_ACTIVE=1 THEN BONUS_EAB ELSE 0 END`）。"算出来不发"的拦截在旧系统中由下游消费 `IS_ACTIVE` 实现；新系统须在本模块显式区分 `Calc_Bonus` 与 `Actual_Bonus`（见 §3.1）。

### 2.3 大区归一化映射规则

- **大区定义**：多个国家合并为一个大区，按一个国家口径结算。EAB 适用多国家计算。
- **实现基准**：以数据库系统国家 ID 为准，经配置表映射到默认大区国家 ID。映射的**权威来源是 `AR_CONFIG` 配置**（旧 SQL 用 `VALUE AS COUNTRY_ID1, SUBSTRING(CONFIG_NAME,8) AS COUNTRY_ID2` 动态解析），下列 MY/SG/BN/TW/HK 仅为业务沟通标签，不得在代码写死字面量。
  - 新马文大区：马来西亚、新加坡、文莱 → 默认国家**马来西亚**（具体 ID 以配置为准）。
  - 港台大区：台湾、香港 → 默认国家**台湾**（具体 ID 以配置为准）。
  - 其他国家：保持原国家 ID。
- ⚠️ **字段类型（依 DDL，避免过度推断）**：最终表 `AR_CALC_BONUS_EAB.COUNTRY_ID` 为 `varchar(32)`、注释"国家简称"，**仅能确认最终结果表以字符串保存国家代码**。源表 `AR_PERF_ORDER / AR_CALC_BE_E_NET`、配置表 `AR_CONFIG.VALUE`、国家主数据的实际类型仍须以各自 DDL 为准（见附录 A 待补项）。新系统应把计算链路中的国家 ID 统一按配置值规范化处理，不应仅凭最终表 DDL 推断所有源表类型。

### 2.4 财务精度与舍入处理

- **数据类型**：全链路严禁 Float，必须使用 Decimal / 高精度数值。
- **业绩精度**：BV/PV 按系统原有精度，BV 保留 2 位小数。
- **奖金精度与舍入**：旧 SQL 无 `ROUND/TRUNCATE/FLOOR`，结果 `PV * EAB_RATE / NUMS`（`EAB_RATE` 为 `decimal(16,6)`，除法中间结果精度更高）依赖写入 DECIMAL 列时的列精度处理。
  - **✅ 已确认（旧系统最终落库）**：`AR_CALC_BONUS_EAB.BONUS_EAB = decimal(16,2)`（`GPV` 亦为 `decimal(16,2)`），即最终金额 **2 位小数**；MariaDB 写入 DECIMAL 列按 **round half away from zero** 舍入，对正数奖金即"四舍五入到 2 位"。**确认旧系统最终行为不是"向下截断"。**
  - ⚠️ **建议实库回归验证（审计严谨性）**：上述舍入规则建议在 **MariaDB 10.6.24 实库**用 tie case 验证一次（尤其 `.005` 边界）。**用字符串字面量传入，彻底排除数值字面量被当作近似数解析的可能**：
    ```sql
    SELECT
      CAST('1.234' AS DECIMAL(16,2)) AS a,      -- 期望 1.23
      CAST('1.235' AS DECIMAL(16,2)) AS b,      -- 期望 1.24（round half away from zero）
      CAST('1.236' AS DECIMAL(16,2)) AS c,      -- 期望 1.24
      CAST('-1.235' AS DECIMAL(16,2)) AS neg_b; -- 期望 -1.24（远离 0）
    ```
    由于 EAB 不产生负奖金，业务只依赖**正数金额的四舍五入**结果；负数 tie 行为仅作数据库行为验证，不参与 EAB 发放逻辑。
  - ⚠️ **未确认（旧系统中间舍入点）**：`AR_CALC_BE_EAB_MID3.BONUS_EAB / MID1.BONUS_EAB` 的 DDL 尚未取得。**若它们也是 `decimal(16,2)`，旧系统在中间表就已发生第一次舍入**，最终表只是再次落库——旧系统真实舍入点可能为多处，不能断言"只舍入一次"。
  - **新系统策略（须明确选择并标注）**：
    - 若目标是 **100% 复刻旧系统边界金额**：必须取得 MID1/MID3 DDL，按旧系统真实落库点逐处模拟舍入。
    - 若新系统选择 **只在最终金额处舍入一次**（更清晰的新实现）：则在极端边界值上可能与旧系统的多重舍入产生 **1 分差异**，须作为**重构实现策略**标注，并经财务确认是否接受。
    - 无论何种选择，全链路严禁 Float，统一 Decimal；舍入方向（四舍五入 vs 向下截断）以财务签字为准（默认对齐旧系统的四舍五入）。

---

## 3. 系统边界与数据契约

### 3.1 订单口径与字段定义

- **⚠️ 有效订单口径属上游职责，非 EAB 自行判断**：取消单、退款单、无 BV/PV 的兑换/积分类订单、eSAC/赠品等不产生 BV/PV 的记录、跨期补单等的排除，由**上游订单业绩汇总逻辑保证**。原 SQL 仅 `FROM AR_PERF_ORDER WHERE PERIOD_NUM=当期 GROUP BY COUNTRY_ID`，并未判断任何订单状态/类型。EAB 模块原则上**不**凭订单类型字符自行判断，而是消费上游已净化的 `AR_PERF_ORDER.PV`；若上游未完成净化，必须在进入 EAB 之前建立统一的有效订单口径。
- **净额确认**：以 `AR_PERF_ORDER.PV` 被上游确认为本期有效计奖 PV 为准；合法负向调整/冲销由上游净化后提供最终净 PV。
- **周期参数**：`PERIOD_NUM` 为唯一结算周期键；`CALC_MONTH` 仅作展示/审计辅列，不参与核心计算匹配。
- **⚠️ 活跃默认值（区分新系统契约与旧 SQL 行为）**：**新系统中**，当期 `AR_USER_PERF` 查不到该会员时，默认 `IS_ACTIVE=0`、`Actual_Bonus=0`。旧 SQL 仅在**未关联到任何 `AR_USER_PERF` 用户记录**时通过 `IFNULL(T3.IS_ACTIVE,0)` 兜底；由于旧 SQL 关联 `AR_USER_PERF` 时**缺少周期过滤**，`IS_ACTIVE` 可能被其他周期记录错误命中（详见漏洞 3），**并不保证"当期查不到即默认 0"**。此外最终表 `IS_ACTIVE int NOT NULL` 无默认值，依赖该 IFNULL 兜底。
- **⚠️【口径陷阱】最终表 `COUNTRY_ID` 是会员原始国家，不是大区**：旧 SQL 最终 `INSERT INTO AR_CALC_BONUS_EAB` 选取的是 **`T.COUNTRY_ID`（会员源数据中的原始国家）**，而非映射后的 `T.COUNTRY_ID_1`（大区）。旧 SQL 各字段的实际用途如下：
  - **订单侧**映射后的国家进入 `MID2 / MID3`，形成大区**资金池**（订单 PV 与人数聚合）；
  - **人员侧 `MID1.COUNTRY_ID_1`**（经 WHILE 循环更新为大区）主要用于与 `MID3.COUNTRY_ID` 匹配，把算出的 `BONUS_EAB` **回写**到会员行；
  - **最终落表仍写 `T.COUNTRY_ID`，即会员原始国家**；最终表**并无大区列**。
  - 注：旧 SQL 的人数分母并非"先按大区 `COUNTRY_ID_1` 映射再聚合"，而是**先按原国家 join 人数、之后才更新 `COUNTRY_ID_1`**，这正是漏洞 2 的根因。

  因此：
  - 直接对最终表 `GROUP BY COUNTRY_ID` 汇总，会看到 SG/BN 会员的奖金挂在 **SG/BN 名下而非合并到 MY 大区**。⚠️ 在**正确的大区聚合口径下**，金额应按 MY 大区池子均摊；但**旧 SQL 历史结果仍可能受漏洞 2 影响**，出现分母缩小、超发或漏发，**不能假定旧表金额一定是正确均摊后的值**。报表/对账若误以为 `COUNTRY_ID` 已是大区默认国家，口径会出错。
  - 新系统若需同时支持旧表兼容与大区审计，建议**同时输出 `original_country_id` 与 `region_country_id` 两个字段**；若仅兼容旧表，则 `COUNTRY_ID` 必须保持旧含义（会员原始国家），不可改写为大区 ID。
- **⚠️ Calc_Bonus / Actual_Bonus 为新系统数据契约，非旧 SQL 字段（DDL 已确认）**：最终表 DDL 仅含 `BONUS_EAB decimal(16,2)` 与 `IS_ACTIVE int`，**确无 Actual_Bonus 列**；且 `BONUS_EAB` 存的是**理论应得金额**（旧 SQL 未对不活跃者置 0）。本契约为新系统重构新增：
  - `Calc_Bonus`：按财务精度处理后的理论应得金额；达标但不活跃者该字段也有值；仅为理论结果，**不作发放依据**。
  - `Actual_Bonus`：实际发放金额，财务以此为准；活跃 = Calc_Bonus，不活跃 = 0。

### 3.2 异常与边界场景熔断策略

| 场景 | 业务处理规则 | 系统降级 / 熔断策略 |
|---|---|---|
| EAB_RATE 配置多条有效记录 | 视为配置污染，严禁 MIN/MAX 静默取值（旧 SQL 用 `MIN(VALUE)` 静默取最小值） | 阻断并告警，必须熔断 |
| EAB_RATE 配置缺失（0 条） | 旧 SQL 经 `IFNULL(MIN(VALUE),0)/100` 会**静默置 0**，导致整期无 EAB 且无告警；新系统视为配置错误 | 阻断并告警，**禁止静默按 0 计算** |
| EAB_RATE 格式 / 范围非法 | 百分数存储（值 10 表示 10%，读取转 `Decimal("0.10")`）；值须 > 0 且 ≤ 100（上限需财务确认，防 100% 全额拨出风险） | 阻断，批次状态记 `EAB_FAILED`；是否放行其他奖项由大调度决定，但批次状态须体现 EAB 未成功 |
| 国家映射缺失 / 一对多冲突 / 值非法 | ⚠️ 见 §4.1 分级处理：**普通国家无映射属正常**（保持原 ID）；可合并国家缺映射=配置缺失；同源多条 bonus 映射=冲突；`VALUE` 空串或非法=配置错误 | 配置缺失、一对多冲突、值非法均硬熔断并告警，防资金错配 |
| 大区有达标人，但有效净 PV ≤ 0 | EAB 不产生负奖金：`region_pool_pv = max(SUM(有效净 PV), 0)`，PV ≤ 0 时按 0 池处理，单人 Calc=0 | ⚠️ **新系统审计增强，非旧 SQL 对齐行为**（旧 SQL 因 `WHERE BONUS_EAB > 0` 直接丢弃此类记录）。生成 `Calc_Bonus=0` 审计明细；**下游若只消费"应发明细"，必须过滤 `Actual_Bonus > 0`，或以 `record_type = audit / payable` 明确区分**，避免把 0 元审计记录误认为应发账单 |
| 大区有 PV，但无达标人 | 触发除零保护，无人分钱 | 不计算，不产生 EAB 账单明细 |

---

## 4. 新系统重构数据流转逻辑

1. **加载强校验配置**：
   - 读取 EAB_RATE：强校验 `TYPE='bonus'`、唯一性、**非缺失**、合法区间（> 0 且 ≤ 100）。
   - 读取国家大区映射字典（`TYPE='bonus'`），⚠️ **按是否需要合并分级处理**：
     - **无需合并的国家**（大区默认国家如 MY/TW，以及独立国家）：**允许无映射，默认保持原 `COUNTRY_ID`**（对应旧 SQL `IF(M.COUNTRY_ID1 IS NULL, N.COUNTRY_ID, …)` 与 `IF VV_REGION 非空 THEN UPDATE`）。不得把"普通国家没有映射"判为错误。
     - **需要合并的国家**（如 SG/BN/HK）缺映射：视为**配置缺失**并告警（检出依赖业务维护的"应合并国家"参照表）。
     - **同一源国家存在多条 `TYPE='bonus'` 映射**：视为**一对多冲突，硬熔断**。
     - ⚠️ **映射值合法性**：`Country*` 配置的 `CONFIG_NAME` 后缀须能解析为合法源国家 ID，`VALUE` 目标大区国家 ID 须**非空、格式合法、存在于国家主数据**；空字符串、非法 ID、无法识别的后缀均视为配置错误。**依据**：旧 SQL 订单侧 `IF(M.COUNTRY_ID1 IS NULL, N.COUNTRY_ID, …)` 对 `VALUE=''` 会把国家映射成空串，而人员侧 `IF VV_REGION != '' THEN …` 会跳过空串保留原值——两侧对空串行为不一致，会造成静默错配。
2. **提取并映射分母**：取当期 `PERIOD_NUM` 下 `GPV ≥ 1000` 的会员，以当期源数据的会员归属 `COUNTRY_ID` 作结算国家快照（同时保留原始国家），映射为 `REGION_COUNTRY_ID`。**分母须保证当期 `user_id` 唯一**（见漏洞 6）。
3. **提取并映射分子**：取当期有效净 PV 订单，将订单来源 `COUNTRY_ID` 映射为 `REGION_COUNTRY_ID`。
4. **独立聚合 + 并发/残留/事务隔离**：人员池与订单池**分别**完成大区映射与聚合。架构约束：
   - 摒弃旧系统共享物理中间表（`MID1/MID2/MID3`）模式——旧 SQL **过程内部无清理逻辑**；⚠️ **若外部调度未在调用前按周期/job 清理**，单任务重跑也会累积残留，并发/多任务调度更会互相污染。新系统须用内存结构、临时表或按 `job_id/period_num` 硬隔离。
   - ⚠️ **事务不完整放大残留**：旧 SQL 在 `MID1` 插入后**立即 `COMMIT`**，若后续步骤失败（如映射 `SELECT...INTO` 报 1172、或后续 INSERT 失败），已提交的 `MID1` 数据**不随整批回滚**，下次重跑（即便外部未清理）会继续被污染。新系统应以 job 隔离 + 批次状态 + 原子化持久化，杜绝半成品数据参与下次计算。
   - ⚠️ **并发主键冲突（DDL 已确认为硬失败）**：最终表 `PRIMARY KEY(ID)`，而 `ID` 由"秒级时间戳 `%Y%m%d%H%i%s` + 会话内行号 `@ROWNUM`（从 0 起）"拼成；**同秒并发执行两个 EAB 任务会生成相同 ID → 触发 `PRIMARY KEY` 重复键错误、其中一个任务中断**（非静默覆盖）。新系统应改用数据库序列、雪花 ID、UUID，或由统一持久化层生成主键。
5. **分发匹配（左关联，以达标大区为主表）**：以"达标人员池/达标大区"为基准，左关联该大区订单净 PV。有达标人但无 PV → PV 按 0；有 PV 但无达标人 → 不产生账单。**严禁以订单产生国为主表反向 join 人数**（见漏洞 2）。
6. **状态匹配**：取会员当期活跃状态，**强制附加 `PERIOD_NUM=当期`** 过滤，并保证活跃源表 `(period_num, user_id)` 唯一（见漏洞 3）。
7. **持久化**：生成 `Calc_Bonus` 与 `Actual_Bonus`，**按业务唯一键 `(period_num, [bonus_code,] user_id)` 做 Upsert**（最终表当前仅有 `PRIMARY KEY(ID)`，无业务唯一键，须由新系统补建）。**输出的 `period_num / calc_month` 必须来源于当前结算周期，不得从未过滤源数据随行带出**（见漏洞 1）。国家维度按 §3.1：若兼容旧表则 `COUNTRY_ID` 写原始国家，新增大区审计则另出 `region_country_id`。最终金额按 §2.4 选定的舍入策略处理。

---

## 5. 历史遗留系统高危 Bug 档案（核心测试用例覆盖范围）

### 🚨 漏洞 1：跨期不对称数据污染
- **原貌**：订单池有 `WHERE PERIOD_NUM=IV_PERIOD_NUM`，但人员池仅 `WHERE GPV>=1000`，**完全缺周期过滤**。`AR_CALC_BE_E_NET` 若存多期数据，历史期达标人员混入本期分母；且最终 `AR_CALC_BONUS_EAB` 写入的 `PERIOD_NUM/CALC_MONTH` 取自 `T.PERIOD_NUM/T.CALC_MONTH`（源行自带），**可能不是入参 `IV_PERIOD_NUM/IV_CALC_MONTH`**，本期重算会把历史结果一并插入。
- **对策**：分子、分母、状态表查询最内层一律加 `PERIOD_NUM=当前结算期`；输出周期列须来源于当前结算周期。

### 🚨 漏洞 2：主副表驱动颠倒（既致超发，也致漏发）
- **原貌**：以"订单产生国"为主表 `LEFT JOIN` 达标人数，且**先按原国家 join、后做大区映射**（人数 `Q` 按 `MID1.COUNTRY_ID` 原国家计数，`COUNTRY_ID_1` 此时尚未更新为大区）。
  - **超发**：大区内某子国家有达标人但无订单 → 该国人数未并入分母 → 分母缩小 → 全区超发。
  - **漏发**：大区内订单集中在 A 国、达标人集中在另一无订单 B 国（如 SG 有单无达标人、MY 有达标人无单）→ 订单行能 join 到的人数为 0 → 该大区 `NUMS=0` → 被 `MID3 ... WHERE NUMS>0` 过滤 → **整区不发**，本应分享该大区订单池的达标人颗粒无收。
- **对策**：人员池与订单池**先各自完成大区映射与聚合**，再以"达标大区"为主表左关联订单 PV。

### 🚨 漏洞 3：跨期状态一对多扇出（One-to-many Fan-out）
- **原貌**：`LEFT JOIN AR_USER_PERF T3 ON T3.USER_ID=T.USER_ID` 缺周期限制。同一会员多期记录导致终表行翻倍膨胀；即便不膨胀，若返回非本期活跃记录，也会**错判本期活跃状态**（亦使 §3.1 的"查不到默认 0"在旧系统中不成立）。
- **对策**：活跃状态严格按 `PERIOD_NUM=当期` 匹配。⚠️ **仅加周期过滤还不够**：还须保证活跃源表 `(period_num, user_id)` 唯一；若同期同一用户存在多条活跃记录，应熔断或按明确优先级归并，否则即使过滤了周期，仍会 fan-out 导致终表奖金行膨胀。

### 🚨 漏洞 4：非幂等重复插入
- **原貌（DDL 已确认）**：最终表主键为 `PRIMARY KEY(ID)`，`ID`=秒级时间戳+会话行号；**没有** `(period_num, user_id)` 或 `(period_num, bonus_type, user_id)` 业务唯一键（仅另有非唯一索引 `EAB_USER_ID(USER_ID)`）。最终 `INSERT INTO AR_CALC_BONUS_EAB SELECT ...` 无删除当期旧结果、无 Upsert，**重跑会用新 ID 不断重复插入，无任何约束阻止**。
- **对策**：以业务唯一键去重/覆盖——统一奖金明细表用 `(period_num, bonus_code, user_id)`；EAB 专表至少保证 `(period_num, user_id)` 唯一。单周期重跑只覆盖当前 `period_num + bonus_type=EAB`，不得波及其他周期与奖项。

### 🚨 漏洞 5：配置映射条件不一致（静默漏发 + 硬报错 + 空串错配）
- **原貌**：订单侧映射带 `AND TYPE='bonus'`，人员侧 `SELECT VALUE INTO VV_REGION ... WHERE CONFIG_NAME=CONCAT('Country',VV_COUNTRY_ID)` **无 TYPE 约束**。
  - ① 静默误导/漏发：遇同名非 bonus 项，人员侧与订单侧大区映射不一致 → **`MID1` 与 `MID3` 回写匹配失配**（回写语句 `UPDATE MID1 INNER JOIN MID3 ON M.COUNTRY_ID_1 = N.COUNTRY_ID` 中 `MID1.COUNTRY_ID_1` ≠ `MID3.COUNTRY_ID`）→ `MID1.BONUS_EAB` **保持初始 0**（非"被置 0"）→ 最终 `INSERT` 因 `WHERE T.BONUS_EAB > 0` 被过滤，**通常不产生该会员 EAB 记录，形成静默漏发**。
  - ② 硬报错：人员侧 `SELECT ... INTO` 命中多行时，MariaDB/MySQL 抛 **1172 / "Result consisted of more than one row"**（与是否 strict 模式无关），中断存储过程。
  - ③ 空串错配：若 `VALUE=''`，订单侧 `IF(M IS NULL,…)` 把国家映射成空串、人员侧 `IF VV_REGION!=''` 保留原值，两侧大区不一致（后果同 ①：回写匹配失配 → `BONUS_EAB` 保持 0 → 被 `>0` 过滤漏发；见 §4.1 映射值合法性）。
- **对策**：加载字典时统一 `TYPE='bonus'` 类型校验 + 单国唯一映射 + 值合法性校验；测试需同时覆盖"多条同名配置（硬报错）""干扰类型配置（静默误导）""空串/非法值（错配）"三子场景。

### 🚨 漏洞 6：达标人员源表未做唯一性校验（分配关系扭曲）
- **原貌**：分母用 `SELECT COUNT(*) ... GROUP BY COUNTRY_ID`（非 `COUNT(DISTINCT user_id)`）。DDL 确认最终表**无 `(period_num,user_id)` 唯一约束**，故重复用户的多行可被全部插入。若 `AR_CALC_BE_E_NET` 同期同一 `user_id` 存在多行，会**同时污染分母与结果行**：
  - 分母被放大 → 单行奖金被拉低；
  - 重复用户的每一行都进入 MID1、并都可能插入 `AR_CALC_BONUS_EAB` → **重复用户产生多条记录、被重复发放**；
  - 非重复用户则被**少发**；
  - 若同一用户重复出现在不同国家，还会同时污染不同大区的分配。
- ⚠️ **后果须严谨表述**：仅在"旧 SQL 按行插入、全员活跃、忽略多处 DECIMAL 舍入尾差"的**窄条件**下，理论 `Calc` 行汇总才可能仍接近资金池总额；但从**会员维度**看，重复用户多拿、非重复用户少拿，且 `Actual` 实发总额还会受活跃拦截、落库唯一键策略（重复用户被覆盖 vs 多行发放）的影响。**本质问题是会员维度分配关系被扭曲，不能仅看资金池总额是否接近。**
- **对策**：保证当期 `period_num + user_id` 唯一；源表若存在重复，应在进入 EAB 前显式去重或熔断，严禁静默 `COUNT(*)`。

---

## 6. 低优先级可移植性 / 健壮性风险

- **⚠️ MID2 选取非聚合字段 + ONLY_FULL_GROUP_BY（按 MariaDB 校正）**：`SELECT O.COUNTRY_ID, O.COUNTRY_ID_1, SUM(O.PV), SUM(O.NUMS) ... GROUP BY O.COUNTRY_ID` 中，`COUNTRY_ID_1` 非聚合非 group-by。MariaDB 10.6 默认 `sql_mode` 不含 `ONLY_FULL_GROUP_BY`；**但存储过程按其创建时的 `SQL_MODE` 运行**——若该过程创建时未开启该模式，当前查询通常不报错（但 `COUNTRY_ID_1` 取值非确定）；若迁移到启用了 `ONLY_FULL_GROUP_BY` 的环境，或过程创建时 `SQL_MODE` 含该模式，则该非聚合字段会报 **1055**。`COUNTRY_ID_1` 后续 MID3 未使用（旧 SQL 注释已标"没用，可以删除"），新系统应直接删除。
- **国家循环顺序非确定**：WHILE 循环用 `SELECT COUNTRY_ID ... GROUP BY COUNTRY_ID LIMIT VV_COUNT1,1` 逐个取国家，**无 `ORDER BY`，SQL 语义上无稳定顺序保证**。⚠️ 注意循环只更新 `COUNTRY_ID_1`、不更新 `GROUP BY` 字段 `COUNTRY_ID`，故漏处理/重复处理**并非必然**；但该写法依赖执行计划稳定性，不宜作为新系统实现方式。新系统应**一次性加载映射字典后批量映射**。
- **⚠️ 字符串大小写敏感（收敛表述）**：最终表 `AR_CALC_BONUS_EAB` 使用 `COLLATE=utf8mb4_bin`，因此**最终表上**的字符串查询/比较/去重大小写敏感。但计算阶段的国家映射 JOIN 发生在 `AR_CONFIG / AR_PERF_ORDER / AR_CALC_BE_EAB_MID*` 上，**其是否大小写敏感取决于这些表/列的 collation，须取得对应 DDL 后确认**，不能由最终表 collation 推定。新系统仍建议统一国家代码大小写，或在映射前显式归一化，避免配置与业绩数据大小写不一致导致错配。

---

## 附录 A：已确认的表结构与待补 DDL

### ✅ 已确认 —— `AR_CALC_BONUS_EAB` 完整字段（MariaDB 10.6.24，schema `ibs_calc_serve`，`ENGINE=InnoDB`、`CHARSET=utf8mb4`、`COLLATE=utf8mb4_bin`）

> 字段顺序与 DDL 一致，便于与建表语句逐行对照。

| 字段 | 类型（含默认值） | 对文档的支撑 |
|---|---|---|
| `ID` | `varchar(32) NOT NULL DEFAULT ''` | 主键，由"秒级时间戳 + 会话行号"拼成 → 印证漏洞 4、并发 ID 硬冲突 |
| `PERIOD_NUM` | `int(11) NOT NULL DEFAULT 0` | 周期字段；最终写入取自源行 `T.PERIOD_NUM`，存在**漏洞 1 跨期污染**风险（可能非入参周期）|
| `CALC_MONTH` | `tinyint(4) NOT NULL DEFAULT 0` | 展示/审计月份；最终写入取自源行 `T.CALC_MONTH`（§3.1：仅辅列，不参与匹配，同受漏洞 1 影响）|
| `USER_ID` | `varchar(32) NOT NULL DEFAULT ''` | 会员字段；仅有非唯一索引 `EAB_USER_ID(USER_ID)`、**无业务唯一约束** → 印证漏洞 4 / 6（重跑与重复用户行污染）|
| `GPV` | `decimal(16,2) NOT NULL DEFAULT 0.00` | 金额精度口径，2 位小数 |
| `BONUS_EAB` | `decimal(16,2) NOT NULL DEFAULT 0.00` | 最终金额 2 位小数、四舍五入（非截断）→ §2.4；中间舍入点仍待 MID DDL |
| `COUNTRY_ID` | `varchar(32) NOT NULL DEFAULT ''`「国家简称」| ⚠️ 写入的是**会员原始国家**（`T.COUNTRY_ID`），**非大区**（§3.1 口径陷阱）；仅证明最终表用字符串存国家代码，源表类型待 DDL |
| `IS_ACTIVE` | `int(11) NOT NULL`（**无默认值**）| 旧 SQL 由 `IFNULL(T3.IS_ACTIVE,0)` 兜底写入；该列无默认值，依赖此 IFNULL → §3.1 默认值说明 |
| **索引** | `PRIMARY KEY(ID)` + 非唯一索引 `EAB_USER_ID(USER_ID)` | **无 `(period_num,user_id)` 业务唯一键** → 印证漏洞 4/6，新系统须补建 |

**说明**：最终表无 `REGION_COUNTRY_ID` / `Actual_Bonus` 字段——大区仅用于计算、不落表；不活跃拦截由下游消费 `IS_ACTIVE` 实现。

### ⏳ 仍待补 DDL（用于关闭剩余不确定性）

- `AR_CALC_BE_EAB_MID1 / MID2 / MID3`：确认中间精度，**关闭"是否中间表提前舍入 / 双重舍入"问题**（§2.4），并确认中间表 collation（§6）。
- 源表 `AR_CALC_BE_E_NET / AR_PERF_ORDER / AR_USER_PERF / AR_CONFIG`：确认各 `COUNTRY_ID / VALUE` 类型与 collation、`PV/GPV` 精度，以及是否存在 `(period_num,user_id)` 等唯一约束（关系到漏洞 3/6 的源头治理与 §2.3 类型推断）。
