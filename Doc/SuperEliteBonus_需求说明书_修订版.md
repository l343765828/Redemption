# Super Elite Bonus（超级精英奖）结算需求说明书（修订版 · 合并评审意见）

> **适用对象**：存储过程 `CALC_BE_SE_COUNTRY`（上游依赖 `CALC_LV_ELITE`）。
> **本版变更**：在"最终定稿版"基础上合并第三方评审意见——修正 `AR_CALC_BONUS_SE` 字段顺序（2.2/6）、明确"不发"拦截归属（3.3）、补充配置重复会直接报错（4.1）、精确化单一国家分支判定（5·Step 4）、补充比例配置的唯一性/数值类型/缺失告警（3.2）、新增上游清理依赖（2.6）与并发/事务约束（2.7）、整理调度前置校验 SQL（7）。

---

## 1. 需求概述

Super Elite Bonus（超级精英奖）根据各国家或大区当期总业绩（PV），按系统配置比例提取奖金池，并由该国家或大区内所有符合 Super Elite 资格的会员平均分配。多国家在特定情况下会合并为一个大区进行统一平均分配计算。

---

## 2. 前置依赖条件与系统假设（核心风险区）

由于 `CALC_BE_SE_COUNTRY` 内部缺乏幂等控制与部分清洗逻辑，正确执行严格依赖以下前置条件与外部调度干预。

### 2.1 临时底表清理机制
每次执行前必须清空临时底表 `AR_CALC_LV_ELITE_1`。脚本使用追加插入（`INSERT INTO AR_CALC_LV_ELITE_1`），若未提前清空，再次执行将导致历史脏数据叠加，严重污染大区人数统计与奖金发放。

### 2.2 结果表重复执行清理与"数据驱动"漏洞（必须防重）
每次执行前必须由外部调度清理目标结果表 `AR_CALC_BONUS_SE` 的当期数据。

- **参数未使用漏洞**：入参 `IV_CALC_MONTH` 在整个过程中从未被使用。最终写入结果表的 `PERIOD_NUM` 和 `CALC_MONTH` 由数据本身驱动（直接来自底表 `AR_CALC_LV_ELITE` 的 `T.PERIOD_NUM` / `T.CALC_MONTH`）。
- **清理对齐要求**：外部调度清理旧数据时，清理键必须严格对齐源表数据里的实际周期与月份。若源表混入历史数据，即便按入参月份清理了结果表，也会出现"按入参清理、按源数据重写"的错位，导致历史期奖金重复生成。

### 2.3 当期评级数据隔离（分子分母脱节风险 — 绝对底线）
脚本导入评级数据时缺少 `WHERE` 周期过滤。

- **承重墙逻辑**：计算总奖金池（分子 PV）用入参 `IV_PERIOD_NUM` 过滤，但计算大区 SE 总人数（分母）取自底表、**完全没有周期过滤**。
- **强制兜底**：必须由外部预先确保前置表 `AR_CALC_LV_ELITE` 仅保留目标期的单一评级数据。一旦混入多期历史数据，分母会错误累加所有历史期的 SE 人数，而分子仅汇总当期 PV，将导致人均奖金被严重稀释。

### 2.4 活跃状态数据单行限制（ID 重复风险）
脚本按 `USER_ID` 左连接 `AR_USER_PERF` 取活跃标识时未加周期过滤。

- 必须确保 `AR_USER_PERF` 每个 `USER_ID` 有且仅有一条有效记录。
- **主键冲突风险**：若单用户关联出多行，不仅会重复发奖，还会破坏 ID 序号（`VV_ID`）推进逻辑；在同一秒内处理多个大区时，后续大区生成的主键存在重叠与冲突风险。

### 2.5 基础数据完整性保障（除零静默故障防范）
参与发奖的会员在 `AR_USER` 表中必须能匹配到记录，且提供非空的 `COUNTRY_ID`。

- **故障推演**：若 `AR_USER` 缺失导致左连接后 `BONUS_COUNTRY` 为 NULL，外层会把 NULL 聚成一组进入循环；但内层统计人数时 `WHERE BONUS_COUNTRY = VV_COUNTRY`（此时 `VV_COUNTRY` 为 NULL，`列 = NULL` 在 SQL 过滤中恒不成立）会得出 `VV_COUNT = 0`，随后人均计算触发除零（报错或返回 NULL），导致该组会员被静默跳过发奖。

### 2.6 上游 CALC_LV_ELITE 的清理依赖（新增）
`AR_CALC_LV_ELITE` 的"仅当期"要求不仅是本过程的前置，也取决于上游 `CALC_LV_ELITE` 的清理：

- 上游同样是多表追加写入，涉及中间表 `AR_CALC_LV_ELITE_MID1`～`AR_CALC_LV_ELITE_MID7`，以及最终的 `AR_CALC_LV_ELITE` / `AR_CALC_LV_ELITE_REAL`。
- 上游仅在第一步按 `IV_PERIOD_NUM` 从 `AR_PERF_MONTH` 取当期消费，但后续全部是直接 `INSERT INTO`，**未见任何清理动作**。
- **要求**：执行 `CALC_BE_SE_COUNTRY` 前，不仅要确保 `AR_CALC_LV_ELITE` 仅含目标期数据，还要确认上游 `CALC_LV_ELITE` 的中间表与结果表已按调度规范清理，避免多期、多次运行的数据叠加向下游传导。

### 2.7 并发与事务一致性（新增）
- **必须串行执行**：`AR_CALC_LV_ELITE_1` 是普通运行底表（非会话级临时表），且过程在循环内多次 `COMMIT`。本过程必须单实例串行执行，**禁止**同一环境并发执行不同周期或重复执行同一周期；调度层应加任务锁。
- **无整体回滚**：因循环内逐区提交，若中途某国家/大区失败，先前大区已提交的数据无法整体回滚。失败重跑前必须先按 2.1 / 2.2 清理底表与结果表当期数据，此点须纳入运维处理规范。

---

## 3. 核心业务与控制规则

### 3.1 严格资格判定（LAST_ELITE_CALC_ID = 30）
本脚本仅处理 `LAST_ELITE_CALC_ID = 30` 的会员。结合上游评级映射（`SONS_NUM > 2 THEN 30`），30 指代直属宽度拥有 **3 个及以上 Elite（含虚拟宽度）** 的 Super Elite 级别。

### 3.2 奖金拨出比例（SE Rate）与配置校验
比例由 `AR_CONFIG` 中 `CONFIG_NAME = 'superEliteRate'` 且 `TYPE = 'bonus'` 的设定值决定；脚本取值为 `IFNULL(MIN(T.VALUE),0) / 100`。

- **唯一性**：配置应在系统内唯一。若存在多条，脚本取 `MIN(VALUE)`。
- **数值类型（重要）**：若 `VALUE` 为字符型，`MIN(VALUE)` 按字符（字典序）比较而非数值语义，取出的可能并非数值最小值——例如 `'10'` 在字典序上小于 `'9'`，反而会取到较大的数。因此多值时结果偏离的方向不固定（不一定是"压低"），取决于字段类型。须确认 `VALUE` 字段类型，必要时显式数值转换后再比较。
- **缺失风险**：若配置缺失，`IFNULL(...,0)/100` 会把比例置 0，最终不写入任何奖金记录（静默不发）。这不应静默发生，应在调度前校验或在过程内抛错。
- **业务取值**：现行业务计划中 Super Elite B 比例已由 13% 调整为 10%；SQL 不写死，完全以配置为准，故 `superEliteRate` 应被校验为业务确认值（当前 10%）。

### 3.3 不活跃会员参与分母的平均分配规则
- **分母计算**：人均奖金的分母包含该大区所有 `LAST_ELITE_CALC_ID = 30` 的总人数，**不活跃会员仍作为分母参与平分**。
- **本过程职责边界（重要）**：本存储过程**不负责拦截**不活跃会员发奖。它仍会给不活跃 SE 插入一条带 `BONUS_SE` 金额（与活跃者同值）的记录，只是把 `IS_ACTIVE`（可能为 0）写入结果表。真正的"不发"必须由后续发放、钱包、财务或结算审核模块按 `IS_ACTIVE = 1` 执行。
  - **测试提示**：`AR_CALC_BONUS_SE` 中**会**出现不活跃会员的奖金记录，不要误以为本表已过滤掉不活跃会员。
- **份额处置**：不活跃会员对应的份额在本脚本口径下不会重新分配给其他活跃 SE；实际是否沉淀、回收或进入其他科目，由后续发放/财务模块决定。

---

## 4. 奖金计算与大区合并规则

### 4.1 大区合并配置规范与致命配置隐患
多国家汇总时大区算一个国家计算，强依赖 `AR_CONFIG` 的 `Country{ID}` 映射。配置时必须规避：

- **自身映射漏洞（漏主国）**：合并马新文为马来西亚（MY）大区时，不仅要配 `CountrySG = MY`、`CountryBN = MY`，还**必须**配 `CountryMY = MY`。若主国家未配置指向自己，主国会员仍会进分母，但 Step 4 汇总 PV 时取不到主国订单，**主国订单不会被计入分子（PV）**。
- **TYPE 过滤不一致漏洞（分子分母脱节）**：Step 3 执行映射时**不**过滤 `TYPE`，而 Step 4 汇总大区 PV 时**强制**要求 `TYPE = 'bonus'`。若配了 `CountrySG = MY (TYPE: bonus)` 和 `CountryBN = MY (TYPE: other)`，Step 3 会把 SG、BN 会员都并入 MY 分母；Step 4 因 BN 的 `TYPE` 不匹配，将 BN 订单 PV 排除在分子外，导致分母虚高、分子缩小，严重稀释该大区人均奖金。
- **配置重复导致运行报错（升级红线）**：Step 3 使用 `SELECT T.VALUE INTO VV_REGION FROM AR_CONFIG WHERE CONFIG_NAME = CONCAT('Country', VV_COUNTRY_ID)`，**无 `MIN` / `LIMIT 1` / `TYPE` 过滤**。若同一 `CONFIG_NAME`（如 `CountrySG`）配了多行，MySQL 会在 `SELECT ... INTO` 阶段抛"结果超过一行"运行错误，**直接中断存储过程**，而非"取错值"。
- **配置红线**：用于奖金大区映射的所有 `Country{ID}` 必须**全局唯一**，且强制 `TYPE = 'bonus'`，主国必须自映射。

### 4.2 奖金计算公式
```
VV_BONUS_SE = TRUNCATE(VV_TOTAL_PV * VV_SE_RATE / VV_COUNT, 2)
```
释义：大区总 PV × SE 奖金比例 ÷ 当前大区所有 SE 总人数，结果直接截断保留 2 位小数，**不四舍五入**。

---

## 5. 数据处理全流程推演

**Step 1 初始化全局参数**：从 `AR_CONFIG` 取 `superEliteRate`，转小数存入 `VV_SE_RATE`。

**Step 2 组装当期临时底表**：将 `AR_CALC_LV_ELITE` 关联 `AR_USER` 取原生 `COUNTRY_ID`，写入 `AR_CALC_LV_ELITE_1`（`BONUS_COUNTRY` 初始化为本人 `COUNTRY_ID`）。详见第 2 章各项前置要求。

**Step 3 全局国家大区映射转换**：遍历底表出现的所有国家 ID，匹配 `AR_CONFIG` 的 `Country{ID}`（**无 `TYPE` 过滤**），命中则把该国的 `BONUS_COUNTRY` 改为大区主国代码。

**Step 4 按大区平均分配计算**：提取所有存在 `LAST_ELITE_CALC_ID = 30` 的大区（`BONUS_COUNTRY`），逐个执行：

1. **统计人数**：该大区内 SE 总人数（含活跃与不活跃），作为分母 `VV_COUNT`。
2. **大区判定与汇总 PV**：
   - **合并大区**：若当前 `BONUS_COUNTRY` 作为 VALUE 出现于 `CONFIG_NAME LIKE 'Country%' AND TYPE = 'bonus'` 的配置中，则跨国汇总所有 `VALUE` 指向该大区**且 `TYPE = 'bonus'`** 的成员国在 `IV_PERIOD_NUM` 的 `AR_PERF_ORDER.PV`。
   - **单一国家**：若当前 `BONUS_COUNTRY` **没有**作为 `CONFIG_NAME LIKE 'Country%' AND TYPE = 'bonus'` 的 `VALUE` 出现，则走 ELSE 分支，仅汇总 `AR_PERF_ORDER.COUNTRY_ID = VV_COUNTRY` 在当期的 PV。
3. **计算金额**：套用 4.2 截断公式得人均奖金。

**Step 5 结果持久化**：若 `VV_BONUS_SE > 0`，将奖金明细插入 `AR_CALC_BONUS_SE`；左连接 `AR_USER_PERF` 取 `IS_ACTIVE`，用时间戳拼接顺序号生成主键 `ID`。

---

## 6. 数据字典与表结构依赖

| 表名 | 功能说明与依赖要求 | 核心使用字段 |
|---|---|---|
| `AR_CONFIG` | 系统参数表（极度依赖配置准确性与唯一性） | `superEliteRate`、`CONFIG_NAME`(`Country{ID}`)、`VALUE`、`TYPE` |
| `AR_CALC_LV_ELITE` | Elite 评级结果表（需外部确保仅含目标期单一数据；上游清理见 2.6） | `USER_ID`、`LAST_ELITE_CALC_ID`、`PERIOD_NUM`、`CALC_MONTH` |
| `AR_USER` | 用户基础表（必须提供非空合法的原属国家归属） | `ID`、`COUNTRY_ID` |
| `AR_CALC_LV_ELITE_1` | 运行时底表（每次执行前必须全表清空） | `USER_ID`、`PERIOD_NUM`、`CALC_MONTH`、`LAST_ELITE_CALC_ID`、`COUNTRY_ID`、`BONUS_COUNTRY` |
| `AR_PERF_ORDER` | 订单业绩明细表 | `PERIOD_NUM`、`COUNTRY_ID`、`PV` |
| `AR_USER_PERF` | 用户当期业绩表（需外部确保单人单行） | `USER_ID`、`IS_ACTIVE` |
| `AR_CALC_BONUS_SE` | 最终输出表（执行前必须按"数据驱动周期/月份"清理当期旧记录） | 见下方"字段顺序" |

**`AR_CALC_BONUS_SE` 字段顺序（重要 · 已按 SQL 修正）**：`INSERT INTO AR_CALC_BONUS_SE` **未写显式列名**，依赖 `SELECT` 位置一一对应。实际 `SELECT` 输出顺序为：

```
ID, PERIOD_NUM, CALC_MONTH, USER_ID, BONUS_SE, COUNTRY_ID, IS_ACTIVE, BONUS_COUNTRY
```

注意 `COUNTRY_ID` 在 `IS_ACTIVE` **之前**（旧文档把两者写反）。物理表列顺序必须与此 `SELECT` 完全一致，否则会出现字段错位。**强烈建议**将 INSERT 改为显式列名插入，彻底消除位置依赖。

---

## 7. 调度前置校验（建议落地）

执行 `CALC_BE_SE_COUNTRY` 前，调度层建议运行以下校验，任一返回非预期结果即应阻断并告警：

```sql
-- 1. SE 比例配置必须唯一（应返回 0 行）
SELECT CONFIG_NAME, TYPE, COUNT(*) AS CNT
FROM AR_CONFIG
WHERE CONFIG_NAME = 'superEliteRate' AND TYPE = 'bonus'
GROUP BY CONFIG_NAME, TYPE
HAVING COUNT(*) <> 1;

-- 2. Country 映射配置不能重复（应返回 0 行；多行会致 Step 3 的 SELECT...INTO 报错中断）
SELECT CONFIG_NAME, COUNT(*) AS CNT
FROM AR_CONFIG
WHERE CONFIG_NAME LIKE 'Country%'
GROUP BY CONFIG_NAME
HAVING COUNT(*) > 1;

-- 3. 奖金大区映射必须都是 TYPE='bonus'（应返回 0 行）
SELECT *
FROM AR_CONFIG
WHERE CONFIG_NAME LIKE 'Country%' AND (TYPE <> 'bonus' OR TYPE IS NULL);

-- 4. AR_CALC_LV_ELITE 必须只有目标期数据（应只返回目标期一组）
SELECT PERIOD_NUM, CALC_MONTH, COUNT(*) AS CNT
FROM AR_CALC_LV_ELITE
GROUP BY PERIOD_NUM, CALC_MONTH;

-- 5. SE 会员必须能匹配到国家（应返回 0 行）
SELECT T.USER_ID
FROM AR_CALC_LV_ELITE T
LEFT JOIN AR_USER U ON U.ID = T.USER_ID
WHERE T.LAST_ELITE_CALC_ID = 30
  AND (U.ID IS NULL OR U.COUNTRY_ID IS NULL);

-- 6. AR_USER_PERF 必须单用户单行（应返回 0 行）
SELECT USER_ID, COUNT(*) AS CNT
FROM AR_USER_PERF
GROUP BY USER_ID
HAVING COUNT(*) > 1;
```

> **非阻断补充检查**：另需确认 `AR_CALC_LV_ELITE_1` 已清空、`AR_CALC_BONUS_SE` 当期数据已按"数据驱动周期/月份"清理（见 2.2 / 2.3）、上游中间表与结果表已清理（见 2.6），并确保本过程串行执行（见 2.7）。
