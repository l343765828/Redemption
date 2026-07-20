# Team Bonus（团队奖金 / TB）结算需求与技术规范说明书

> **裁决原则**：本文档结合 `奖金制度.pdf` 的业务描述与存储过程 `CALC_BE_TB` 的实际实现编写。**当 PDF 描述与 SQL 执行逻辑发生冲突时，一律以 SQL 为准。** 文中所有公式、过滤条件、精度与默认值，均以存储过程 `CALC_BE_TB` 当前激活（未注释）的代码为准；PDF 中的固定数值（如 24%、各会员类型固定比例）在 SQL 中均为**配置驱动**，非硬编码。

---

## 一、业务概述

Team Bonus（团队奖金，简称 TB）是基于会员左右双区（1L / 2L）市场业绩进行"对碰"后，按会员等级对应的对碰比例形成个人计奖基数，再通过全盘奖金池加权分配的奖金。

整体计算链路（以 SQL 实际执行为准）：

1. 按结算周期读取会员当期 1L、2L 双区总业绩快照；
2. 取左右区**较小值**作为对碰业绩（TOUCH_PV）；
3. 按会员当前等级映射到的配置序号（CALC_ID），取对应**对碰比例**计算原始对碰基数；
4. 按等级对应的**封顶值**对对碰基数封顶；
5. 仅汇总**活跃会员**的对碰基数，形成全盘有效总基数；
6. 以**全盘 PV**（不区分活跃与否）乘以**团队奖拨出率**形成奖金池；
7. 奖金池 ÷ 有效总基数 = TB Rate（加权比例）；
8. 对**活跃且有有效基数**的会员，按 TB Rate 计算个人团队奖并入库；
9. 回写用户业绩表（AR_USER_PERF）的结余业绩与双区总业绩，供后续周期使用。

> 本过程**不负责**网络拓扑计算、不递归汇总左右区业绩、不校验旁线/奖衔资格（相关代码在 SQL 中已全部注释）。这些前置条件必须由上游快照、等级评定或配置层提前处理完成。

---

## 二、存储过程接口与参数

```
CALC_BE_TB(IN IV_PERIOD_NUM INT, IN IV_CALC_MONTH TINYINT)
```

| 参数 | 类型 | 实际作用 |
| --- | --- | --- |
| `IV_PERIOD_NUM` | INT | **核心过滤条件**。用于过滤 `AR_PERF_MONTH.PERIOD_NUM`，决定本次结算读取哪一期的业绩快照 |
| `IV_CALC_MONTH` | TINYINT | **在激活代码中未作为核心过滤条件使用**。结果表中的 `CALC_MONTH` 实际来源于 `AR_PERF_MONTH.CALC_MONTH`，而非该入参 |

**关键说明**：`IV_CALC_MONTH` 仅在已注释的 MID3 相关代码中以 `IV_CALC_MONTH AS CALC_MONTH` 出现；在当前激活流程中，写入中间表与结果表的 `CALC_MONTH` 一律取自快照表的 `CALC_MONTH` 字段。

过程内部声明的关键变量（均为 `DECIMAL(16,6)`）：`VV_TOTAL_PV`（全盘 PV）、`VV_TOTAL_BASE`（有效总基数）、`VV_TOTAL_TB`（奖金池）、`VV_TB_RATE`（加权比例）、`VV_TB_BISECT_RATE`（拨出率）。

---

## 三、数据来源与核心表

### 3.1 月度业绩快照表 `AR_PERF_MONTH`（主输入）

本过程**直接使用该表已生成的快照值**，不负责拆解 `TOTAL_1L`、`TOTAL_2L` 的前置来源。

| 字段 | 用途 |
| --- | --- |
| `PERIOD_NUM` | 结算周期（主过滤键） |
| `CALC_MONTH` | 计算月份（最终写入结果表的来源） |
| `USER_ID` | 会员 ID |
| `TOTAL_1L` | 1 市场（左区）总业绩 |
| `TOTAL_2L` | 2 市场（右区）总业绩 |
| `PV_PCS` | 当期 PV，用于汇总全盘 PV |
| `IS_ACTIVE` | 当期活跃状态（1 = 活跃） |

### 3.2 会员表与等级表 `AR_USER` / `AR_MEMBER_LEVEL`

用于获取会员当前等级并映射为配置序号 CALC_ID。关联关系（**注意 JOIN 键**）：

```
AR_PERF_MONTH.USER_ID  →  AR_USER.ID
AR_USER.MEMBER_LV      →  AR_MEMBER_LEVEL.ID      （JOIN 键是 ID，不是 CALC_ID）
                          取出 AR_MEMBER_LEVEL.CALC_ID 用于后续拼接配置项名称
```

即：会员等级 `MEMBER_LV` 与 `AR_MEMBER_LEVEL.ID` 关联，匹配行的 `CALC_ID` 字段才是用于动态拼接配置名的"配置序号"。若等级无法匹配（LEFT JOIN 未命中），`CALC_ID` 为 NULL，导致配置名拼接为 NULL，最终比例与封顶均取默认 0（见 3.3 边界）。

### 3.3 动态配置表 `AR_CONFIG`（强依赖）

团队奖的拨出率、对碰比例、封顶值**全部来自配置表**，均要求 `TYPE = 'bonus'`：

| 配置项（CONFIG_NAME） | 业务含义 | SQL 取值逻辑 | 默认 / 缺失行为 |
| --- | --- | --- | --- |
| `teamBisectRate` | 团队奖全局拨出率 | `IFNULL(MIN(VALUE), 0) / 100` | 不存在则为 **0**（奖金池为 0） |
| `teamTouchRate{CALC_ID}` | 指定等级的对碰比例 | `IFNULL(VALUE, 0) / 100` | 不存在则比例为 **0** |
| `teamTouchCapping{CALC_ID}` | 指定等级的对碰基数封顶 | `IFNULL(VALUE, 0)` | 不存在则封顶值为 **0**，代表**不封顶** |

**精度细节（极易出错）**：
- `teamBisectRate` 与 `teamTouchRate` 取值后**除以 100**（百分比 → 小数）；
- `teamTouchCapping` 取值后**不除以 100**（为绝对金额上限）；
- `teamBisectRate` 使用 `MIN()` 聚合（若同名多行取最小值），其余两项为直接取值（LEFT JOIN）。

### 3.4 中间表 `AR_CALC_BE_TB_MID1` / `AR_CALC_BE_TB_MID2`

均通过 `INSERT INTO` 写入，过程内部**无 DELETE / TRUNCATE**。详见第四章风险控制。

### 3.5 输出表 `AR_CALC_BONUS_TB`（最终发奖明细）

字段清单见第八章。同样仅 `INSERT`，**无幂等控制**。

### 3.6 业绩主表 `AR_USER_PERF`（结转刷新对象）

阶段五通过 `LEFT JOIN MID1 ON USER_ID` 回写。该 SQL **隐含假设** `AR_USER_PERF` 为"用户当前业绩状态表"（USER_ID 在该表中具备唯一当前行语义）。详见第五章阶段五。

---

## 四、执行前置条件与风险控制（高危项）

### 4.1 中间表清理要求（防跨期污染）

- SQL 直接向 `MID1`、`MID2` 执行 `INSERT`，内部**无任何清理语句**。
- `MID1` 的 INSERT 虽带 `PERIOD_NUM = IV_PERIOD_NUM` 过滤，但因表不清理，会**跨次累积**历史数据。
- `MID2` 的 INSERT 来源是 `MID1` 且**不带周期过滤**（`WHERE TOUCH_PV > 0`），会读到 MID1 中的所有历史行。
- `TOTAL_BASE` 汇总自 `MID2` 且**不带周期过滤**（`WHERE IS_ACTIVE = 1`）。
- 最终 `AR_CALC_BONUS_TB` 的来源是 `MID2` 且**不带周期过滤**（`WHERE TOUCH_BASE > 0 AND IS_ACTIVE = 1`）。

> **结论**：按当前 SQL 口径，**执行前必须全量清空 `MID1` 与 `MID2`**，确保两表只保留本次过程刚生成的数据。仅清理本期数据不一定安全，除非同步改造 SQL 在 MID2/汇总/发奖处统一增加周期过滤。

### 4.2 最终发奖表的幂等控制（防重复发奖）

- 当前 SQL **本身没有任何防重复发奖机制**。
- 如存在同期重算场景，必须在执行前**清理 `AR_CALC_BONUS_TB` 该期旧发奖记录**，或通过唯一约束 / 批次号控制保证幂等。

### 4.3 上游快照唯一性要求

- `AR_PERF_MONTH` 必须已正确生成本期完整数据。
- **唯一性约束**：`AR_PERF_MONTH` 必须保证同一 `PERIOD_NUM + USER_ID` 唯一。若同周期同用户存在多行：
  - 中间表会出现重复行；
  - 对碰基数被异常放大；
  - 同一用户重复发奖；
  - `AR_USER_PERF` 更新匹配到多条来源记录，结果不可控。

---

## 五、计算流程详解（按阶段）

### 阶段一：生成会员对碰基础信息（写入 `MID1`）

从 `AR_PERF_MONTH`（按 `PERIOD_NUM = IV_PERIOD_NUM` 过滤）读取，关联会员、等级、配置后写入 MID1。**包含全部会员（活跃与不活跃均写入）。**

| 字段 | 计算规则（以 SQL 为准） |
| --- | --- |
| `SURPLUS_1L`（1 区结余） | `CASE WHEN TOTAL_1L - TOTAL_2L >= 0 THEN TOTAL_1L - TOTAL_2L ELSE 0` = **MAX(TOTAL_1L − TOTAL_2L, 0)** |
| `SURPLUS_2L`（2 区结余） | `CASE WHEN TOTAL_2L - TOTAL_1L > 0 THEN TOTAL_2L - TOTAL_1L ELSE 0` = **MAX(TOTAL_2L − TOTAL_1L, 0)** |
| `TOUCH_PV`（对碰业绩） | `CASE WHEN TOTAL_1L - TOTAL_2L >= 0 THEN TOTAL_2L ELSE TOTAL_1L` = **MIN(TOTAL_1L, TOTAL_2L)** |
| `TOUCH_RATE`（对碰比例） | `IFNULL(teamTouchRate{CALC_ID}.VALUE, 0) / 100` |
| `TOUCH_CAPPING`（封顶值） | `IFNULL(teamTouchCapping{CALC_ID}.VALUE, 0)` |
| `LAST_MEMBER_LV` | 取自 `AR_USER.MEMBER_LV` |
| `LAST_MEMBER_CALC_ID` | 取自 `AR_MEMBER_LEVEL.CALC_ID` |
| `IS_ACTIVE` | 取自快照 |

> 结余口径：两区业绩较大一方保留差额，较小一方结余为 0；两边相等时双方均为 0。
> 注：SURPLUS_1L 的判断用 `>= 0`、SURPLUS_2L 用 `> 0`，但在相等边界两者结果一致（均为 0），不影响实际结果。

### 阶段二：生成对碰计奖基数（写入 `MID2`）

从 `MID1` 中筛选 `TOUCH_PV > 0` 的记录写入 MID2（**仍不区分活跃状态**）。

| 字段 | 计算规则 |
| --- | --- |
| `ORI_TOUCH_BASE`（封顶前基数） | `TOUCH_PV × TOUCH_RATE` |
| `TOUCH_BASE`（封顶后基数） | 见下方封顶判定 |

**封顶判定逻辑**：

```
IF  TOUCH_CAPPING = 0                         → TOUCH_BASE = ORI_TOUCH_BASE   （不封顶）
IF  TOUCH_CAPPING <= ORI_TOUCH_BASE           → TOUCH_BASE = TOUCH_CAPPING    （触发封顶）
ELSE（未达封顶值）                              → TOUCH_BASE = ORI_TOUCH_BASE   （保持不变）
```

### 阶段三：计算全盘奖金池与加权比例（TB Rate）

| 量 | 计算规则 | 过滤条件 |
| --- | --- | --- |
| `TOTAL_PV`（全盘 PV） | `IFNULL(SUM(PV_PCS), 0)` | `AR_PERF_MONTH.PERIOD_NUM = IV_PERIOD_NUM`，**不校验活跃状态** |
| `TOTAL_BASE`（有效总基数） | `IFNULL(SUM(TOUCH_BASE), 0)` | `MID2.IS_ACTIVE = 1`，**仅活跃会员**，不带周期过滤 |
| `TB_BISECT_RATE`（拨出率） | `IFNULL(MIN(VALUE), 0) / 100` | 配置 `teamBisectRate` |
| `TOTAL_TB`（奖金池） | `TOTAL_PV × TB_BISECT_RATE` | — |
| `TB_RATE`（加权比例） | `CASE WHEN TOTAL_BASE = 0 THEN 0 ELSE TRUNCATE(TOTAL_TB / TOTAL_BASE, 6)` | 总基数为 0 时为 0；**截断保留 6 位小数** |

> **核心不对称（重要）**：奖金池基数 `TOTAL_PV` 含**全部会员**（活跃 + 不活跃）的 PV，而有效基数 `TOTAL_BASE` 仅含**活跃会员**。即不活跃会员的 PV 会推高奖金池，但其基数既不稀释比例、也不参与发奖，最终由活跃会员分享。

### 阶段四：生成个人团队奖金（写入 `AR_CALC_BONUS_TB`）

**仅当 `TB_RATE > 0` 时整段执行**（`IF(VV_TB_RATE > 0) THEN ... END IF`）。

发奖记录的产生需**同时满足**三个条件：

```
TOUCH_BASE > 0   且   IS_ACTIVE = 1   且   TB_RATE > 0（外层 IF 守卫）
```

| 字段 | 计算规则 |
| --- | --- |
| `BONUS_TB`（个人团队奖） | `TRUNCATE(TOUCH_BASE × TB_RATE, 2)`，**截断保留 2 位小数** |
| `TB_RATE` | 写入本期统一的加权比例 |
| `ID`（流水号） | `DATE_FORMAT(NOW(), '%Y%m%d%H%i%s')`（14 位年月日时分秒） + `LPAD(序号, 8, '0')`（8 位递增），共 **22 位**，如 `2026062315304500000001` |
| `COUNTRY_ID` | `IFNULL(AR_USER.COUNTRY_ID, '-1')`（无国家则置 `-1`） |

> 序号通过用户变量 `@ROWNUM`（`SELECT @ROWNUM := 0` 初始化后逐行 `@ROWNUM := @ROWNUM + 1`）生成，仅在单次插入语句内有序、连续。

### 阶段五：业绩结转刷新（更新 `AR_USER_PERF`）

通过 `LEFT JOIN MID1 ON AR_USER_PERF.USER_ID = MID1.USER_ID` 回写，**不带 `PERIOD_NUM` 过滤，仅按 USER_ID 关联**。

```sql
SET T.SURPLUS_1L = IF(T1.USER_ID IS NULL, T.SURPLUS_1L, T1.SURPLUS_1L),
    T.SURPLUS_2L = IF(T1.USER_ID IS NULL, T.SURPLUS_2L, T1.SURPLUS_2L),
    T.TOTAL_1L   = IF(T1.USER_ID IS NULL, T.SURPLUS_1L, T1.TOTAL_1L),
    T.TOTAL_2L   = IF(T1.USER_ID IS NULL, T.SURPLUS_2L, T1.TOTAL_2L);
```

| 用户类型 | SURPLUS_1L / 2L | TOTAL_1L | TOTAL_2L |
| --- | --- | --- | --- |
| **匹配到本期（参与过 MID1）** | 覆写为 MID1 的本期值 | 覆写为 MID1 的 `TOTAL_1L` | 覆写为 MID1 的 `TOTAL_2L` |
| **未匹配到本期（未参与 MID1）** | **保持原值不变** | 置为该行**原 `SURPLUS_1L`** | 置为该行**原 `SURPLUS_2L`** |

**实现要点（需备案，已订正表述）**：本语句是**多表 UPDATE**（`UPDATE AR_USER_PERF T LEFT JOIN AR_CALC_BE_TB_MID1 T1 ...`）。按 MySQL 官方文档：**单表 UPDATE 的 SET 赋值一般从左到右求值，但多表 UPDATE 不保证赋值顺序**。因此当前结果的正确性**并不依赖赋值顺序**，原因有二：

- "未匹配"分支中 `SURPLUS_1L/2L` 为**自赋值**（`IF(NULL, T.SURPLUS_x, ...)` → `T.SURPLUS_x`，新值 = 原值），故无论先算 SURPLUS 还是先算 TOTAL，`TOTAL_x = 原 SURPLUS_x` 的结果都成立；
- "匹配"分支中 `TOTAL_1L/2L` 取自联表 `T1`（联表值在本次更新中为常量），与赋值顺序无关。

**维护提醒**：请勿将该逻辑改写为依赖 SET 列顺序（或依赖"读到已更新列值"）的写法。若要让未匹配用户的 `TOTAL` 取"原结余"，应继续保持 `SURPLUS_*` 自赋值，或显式引用确定的源值，避免因多表 UPDATE 顺序不确定而产生歧义。

> **唯一性强关联**：由于按 USER_ID LEFT JOIN MID1 更新，若 MID1 中同一 USER_ID 存在多行（上游脏数据），同一目标行可能匹配多条来源记录，更新结果不可控。必须由上游 `AR_PERF_MONTH` 的 `PERIOD_NUM + USER_ID` 唯一性保证 MID1 不重复。
> **跨期风险提示**：该更新不带周期条件，隐含 `AR_USER_PERF` 为单期"当前状态表"。若该表实为多期明细表，则存在跨期误更新风险。

---

## 六、字段级计算公式汇总（速查）

```
SURPLUS_1L      = MAX(TOTAL_1L − TOTAL_2L, 0)
SURPLUS_2L      = MAX(TOTAL_2L − TOTAL_1L, 0)
TOUCH_PV        = MIN(TOTAL_1L, TOTAL_2L)
TOUCH_RATE      = IFNULL(cfg[teamTouchRate{CALC_ID}], 0) / 100
TOUCH_CAPPING   = IFNULL(cfg[teamTouchCapping{CALC_ID}], 0)        # 不除以 100
ORI_TOUCH_BASE  = TOUCH_PV × TOUCH_RATE
TOUCH_BASE      = (CAPPING = 0)              ? ORI_TOUCH_BASE
                : (CAPPING ≤ ORI_TOUCH_BASE) ? CAPPING
                :                              ORI_TOUCH_BASE

TOTAL_PV        = SUM(PV_PCS)            WHERE PERIOD_NUM = IV_PERIOD_NUM      # 含不活跃
TOTAL_BASE      = SUM(TOUCH_BASE)        WHERE IS_ACTIVE = 1                   # 仅活跃
TB_BISECT_RATE  = IFNULL(MIN(cfg[teamBisectRate]), 0) / 100
TOTAL_TB        = TOTAL_PV × TB_BISECT_RATE
TB_RATE         = (TOTAL_BASE = 0) ? 0 : TRUNCATE(TOTAL_TB / TOTAL_BASE, 6)    # 6 位截断

BONUS_TB        = TRUNCATE(TOUCH_BASE × TB_RATE, 2)                            # 2 位截断
                  仅当 TOUCH_BASE > 0 且 IS_ACTIVE = 1 且 TB_RATE > 0
```

---

## 七、关键业务规则与边界

| 规则 | SQL 实际行为 |
| --- | --- |
| **活跃 / 不活跃** | 不活跃会员仍会走完结余、对碰、基数（含封顶）计算并进入 MID1/MID2；但**不计入 `TOTAL_BASE`、不生成发奖记录**。即"算得出、不发放、不进有效大盘"。 |
| **会员级别不够** | 无独立"级别不够不发"判断。其效果由配置实现：若该等级 CALC_ID 对应的 `teamTouchRate` 配置为 0（或缺失），则 `TOUCH_RATE = 0 → TOUCH_BASE = 0`，被 `TOUCH_BASE > 0` 过滤掉，自然不发奖。 |
| **旁线级别不够** | **本过程完全不处理**。SQL 中无任何网络/旁线/递归逻辑（相关 MID3 代码已全部注释）。若需限制，必须由上游快照或等级评定提前完成。 |
| **奖衔限制** | **本过程不校验**。无奖衔相关判断。 |
| **等级无法匹配** | LEFT JOIN 未命中导致 `CALC_ID = NULL`，配置名 `CONCAT('teamTouchRate', NULL) = NULL`，比例与封顶取默认 0，该会员对碰基数为 0、不发奖。 |
| **配置缺失** | 拨出率缺失 → 奖金池为 0 → `TB_RATE = 0` → 整段发奖不执行；比例缺失 → 个人基数为 0；封顶缺失 → 视为不封顶。 |

---

## 八、`AR_CALC_BONUS_TB` 输出字段清单

按 INSERT 顺序，共 19 列：

| 序 | 字段 | 含义 / 来源 |
| --- | --- | --- |
| 1 | `ID` | 22 位流水号（14 位时间 + 8 位序号） |
| 2 | `PERIOD_NUM` | 周期（来自 MID2） |
| 3 | `CALC_MONTH` | 计算月份（源头为 AR_PERF_MONTH.CALC_MONTH） |
| 4 | `USER_ID` | 会员 ID |
| 5 | `TOTAL_1L` | 1 市场总业绩 |
| 6 | `TOTAL_2L` | 2 市场总业绩 |
| 7 | `SURPLUS_1L` | 1 市场结余业绩 |
| 8 | `SURPLUS_2L` | 2 市场结余业绩 |
| 9 | `TOUCH_PV` | 对碰业绩 |
| 10 | `LAST_MEMBER_LV` | 会员等级 |
| 11 | `LAST_MEMBER_CALC_ID` | 等级对应配置序号 |
| 12 | `TOUCH_RATE` | 对碰比例 |
| 13 | `TOUCH_CAPPING` | 对碰封顶值 |
| 14 | `ORI_TOUCH_BASE` | 封顶前对碰基数 |
| 15 | `TOUCH_BASE` | 封顶后对碰基数 |
| 16 | `TB_RATE` | 全盘加权比例 |
| 17 | `BONUS_TB` | 个人团队奖金额 |
| 18 | `COUNTRY_ID` | `IFNULL(AR_USER.COUNTRY_ID, '-1')` |
| 19 | `IS_ACTIVE` | 活跃状态（恒为 1，受发奖条件约束） |

---

## 九、PDF 与 SQL 差异对照（裁决表，以 SQL 为准）

| 项目 | PDF 描述 | SQL 实际实现 | 裁决（以 SQL 为准） |
| --- | --- | --- | --- |
| 拨出率 | "固定拨出 24%"（原 27% 划掉）；"月 BV × 24% = 奖金池" | `teamBisectRate` 配置的 `MIN(VALUE)/100` | **配置驱动，非硬编码**；24% 仅为当前期望配置值 |
| 对碰比例 | 顾客 0%、D 10%、SD 15%、GD 20%、PD 20% | `teamTouchRate{CALC_ID}` 配置 / 100 | **配置驱动**，按等级 CALC_ID 取配置，非硬编码 |
| 封顶 | TB 段落未明确描述封顶 | `teamTouchCapping{CALC_ID}` 配置，0 = 不封顶 | **存在封顶逻辑**，按配置执行 |
| 奖金池基数 | "月 BV" | `SUM(PV_PCS)` | 实际字段为 **`PV_PCS`**（按周期汇总，含不活跃） |
| 不活跃 | 自相矛盾：既"算出来不发"，又"团队奖：不活跃不参与计算" | 走完基数计算，但不计入 `TOTAL_BASE`、不发奖 | **算得出但不入有效基数、不发奖**（澄清 PDF 内部矛盾） |
| 会员级别不够 | "算出来不发" | 无独立判断，靠配置比例为 0 自然落为 0 | **无硬编码级别校验** |
| 旁线级别不够 | "不计算" | 无任何网络/旁线逻辑（已注释） | **本过程不处理**，须上游处理 |
| 奖衔限制 | 各会员类型有奖衔限制 | 无奖衔判断 | **本过程不校验** |
| 个人奖金 | "个人基数 × 比例 = 个人 TB" | `TRUNCATE(TOUCH_BASE × TB_RATE, 2)` | 一致，补充**截断 2 位**精度 |
| 比例 | "奖金池 ÷ TB 基数总和 = 比例" | `TRUNCATE(TOTAL_TB / TOTAL_BASE, 6)` | 一致，补充**截断 6 位**精度与零基数保护 |

---

## 十、已知风险与改进建议

1. **中间表跨期污染**：`MID1`、`MID2` 无清理，且 MID2/汇总/发奖均无周期过滤。建议执行前显式清空两表，或改造 SQL 在所有下游环节统一加 `PERIOD_NUM` 过滤。
2. **发奖无幂等**：`AR_CALC_BONUS_TB` 无防重机制。建议重算前清理本期记录，或增加 `(PERIOD_NUM, USER_ID)` 唯一约束 / 批次号。
3. **上游唯一性**：必须保证 `AR_PERF_MONTH` 同期同用户唯一，否则基数放大、重复发奖、结转更新不可控。
4. **业绩结转无周期条件**：`AR_USER_PERF` 更新仅按 USER_ID，隐含"当前状态表"假设。若为多期明细表需重新评估。
5. **多表 UPDATE 赋值顺序**：阶段五为多表 UPDATE，MySQL **不保证** SET 赋值顺序。当前结果因"未匹配"分支 `SURPLUS_*` 为自赋值、"匹配"分支 `TOTAL_*` 取自联表常量，**与赋值顺序无关**，结果正确；维护时切勿改写为依赖赋值顺序（或依赖读到已更新列值）的逻辑。
6. **配置缺失静默降级**：拨出率/比例/封顶缺失时静默取 0，无告警。建议增加配置完整性校验或结算前置巡检。
7. **等级未匹配静默置 0**：会员等级在 `AR_MEMBER_LEVEL` 无匹配时对碰比例落 0，无告警，可能造成漏发。
8. **用户变量序号**：`@ROWNUM` 方式在单次插入内安全；如未来改为分批/并发执行需重新评估序号连续性。

---

## 附录：他人描述文档（《Team Bonus 结算需求与技术规范说明书》）正确性核查

**总体结论：该描述文档整体准确度很高，核心逻辑、过滤口径、精度、风险点的描述与 SQL 一致。仅存在一处技术表述上的小瑕疵，以及若干可补充项。**

### A. 描述正确的关键点（与 SQL 一致）

- 入参口径：`IV_PERIOD_NUM` 为核心过滤、`IV_CALC_MONTH` 在主体未用、`CALC_MONTH` 源自快照表 —— **正确**。
- 三个配置项的取值与默认行为（`teamBisectRate` 用 MIN/100、`teamTouchRate` 用 IFNULL/100、`teamTouchCapping` 用 IFNULL 不除 100、0 表示不封顶）—— **正确**。
- 结余 `MAX(差,0)`、对碰 `MIN`、原始基数与封顶三段判定 —— **正确**。
- 全盘 PV 不校验活跃、有效基数仅活跃、`TB_RATE` 截断 6 位与零基数保护、`BONUS_TB` 截断 2 位 —— **正确**。
- 发奖三重条件（`TOUCH_BASE > 0`、`IS_ACTIVE = 1`、`TB_RATE > 0`）与 22 位流水号格式 —— **正确**。
- 中间表无清理/无周期过滤导致的跨期污染风险、发奖无幂等、上游唯一性要求 —— **正确且有价值**。
- 阶段五结转：匹配用户四字段覆写、未匹配用户 SURPLUS 不变且 `TOTAL = 原 SURPLUS` —— **正确**（这是最易错的部分，描述准确）。
- 不活跃会员"算得出但不入有效基数、不发奖"，以及 SQL 不含奖衔/旁线判断 —— **正确**。

### B. 需要修正的表述（小瑕疵）

- **第二章第 3 节，关于等级关联的 JOIN 键**：原文写"通过 `AR_USER.MEMBER_LV` 关联 `AR_MEMBER_LEVEL.CALC_ID`"。
  - **实际 SQL**：`LEFT JOIN AR_MEMBER_LEVEL T2 ON T2.ID = T1.MEMBER_LV`，即 JOIN 键是 **`AR_MEMBER_LEVEL.ID`**，`CALC_ID` 是匹配后**被读取/拼接到配置名**的字段，并非关联键。
  - 数据流向（用等级最终拿到 CALC_ID）方向无误，但"关联到 CALC_ID"这一措辞在 JOIN 键上不精确，建议改为"`AR_USER.MEMBER_LV` 关联 `AR_MEMBER_LEVEL.ID`，再取该行的 `CALC_ID` 拼接配置名"。

### C. 建议补充的内容（原文未提及，非错误）

- **输出表 `COUNTRY_ID` 字段**：原文未描述，SQL 中为 `IFNULL(AR_USER.COUNTRY_ID, '-1')`，建议补入输出字段说明。
- **`AR_CALC_BONUS_TB` 完整字段清单**（19 列）：原文未逐列列出，建议补充以便对账。
- **阶段五的 MySQL 赋值顺序表述**：该多表 UPDATE 的结果**与赋值顺序无关**（未匹配分支 `SURPLUS_*` 自赋值、匹配分支 `TOTAL_*` 取联表常量）。**特别更正**：本人前述"结果正确依赖现有 SET 列顺序"的说法不严谨——MySQL 多表 UPDATE 本就不保证赋值顺序，正确写法是给出"结果与顺序无关 + 不要改成依赖顺序"的维护提醒（本文档第五章已据此订正）。
- **等级在 `AR_MEMBER_LEVEL` 未匹配（CALC_ID = NULL）的边界**：原文以"配置不存在则为 0"概括覆盖了该情形，可显式点明该边界来源，便于排障。

> 除上述 B 中一处措辞需修正外，原描述文档可作为可靠的口径依据使用。
