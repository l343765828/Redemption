# Pro Elite Bonus（PE 奖金）需求与技术实现文档（定稿）

> **本定稿相对"最终版"的 3 处精确化（仅口径/证据严谨性，技术结论不变）**：① §2 将 `CALC_BE_E` 由"不属于上下文"改为"非数据依赖、属参考上下文"，消除与"它是参考过程"说法的冲突；② §3.2 将"`IS_ACTIVE` 正是为下游拦截而设"软化为"PE 结果需携带活跃快照；是否被下游消费待确认"，与"下游待确认"口径一致；③ 证据边界与附录 B 将三个 Python service 文件由核心证据降为"补充/对照参考"，明确 PE 主逻辑不依赖它们。

> **最终版说明**：本版为定稿。早前误传的 `CALC_BE.sql` 导致上一轮评审的"下游拦截"一条基于了错误前提，**本版不再考虑 `CALC_BE.sql`**——与之相关的内容（"活跃拦截在 `CALC_BE`／重读 `AR_USER_PERF`／`AR_CALC_BONUS_PE.IS_ACTIVE` 为冗余字段／集成风险（原风险八）"）已全部移除。关于活跃拦截，回到"本过程只打标、下游发放环节未在附件中、待确认"的口径；奖金计算的参考过程为 `CALC_BE_E.sql`（Elite 奖，兄弟过程）与本过程 `CALC_BE_PE.sql`。
>
> 上一轮评审中**与 `CALC_BE.sql` 无关、基于真实文件的修正全部保留**：① `CALC_LV_ELITE` 同期幂等（风险二）；② `SONS_NUM` 公式精确化（`≥2000` 启动、用封顶前 GPV）；③ `AR_USER_PERF` / `AR_USER` 措辞收紧；④ 样本只证公式与费率、截断由 SQL `TRUNCATE(...,2)` 证明。
>
> **证据边界**：
> - **核心证据（PE 结论的直接依据）**：`CALC_BE_PE.sql`、`CALC_LV_ELITE.sql`、`CALC_BE_E.sql`、`AR_USER_PERF.sql`、`AR_CALC_BONUS_PE.sql`、`Elite_PE_SE晋级规则.docx`、`EKPlan20250324`（制度 PDF）。PE 的字段语义、风险与修法均由这些文件独立支撑。
> - **补充/对照参考（非核心证据）**：`GlobalRecalculationService.py` / `UserStatsService.py` / `UserStats.py`（晋级的 Redis 实现）。它们仅用于附录 B 的 `is_elite` 对照，**PE 主逻辑不依赖**——`GPV_REAL`/`GPV_UNREAL`/`SONS_NUM`/`LAST_ELITE_CALC_ID` 的来源仅凭 `CALC_LV_ELITE.sql` 即可证明。若交付包不含此三文件，则附录 B 的 Redis 侧描述应视为待核对的参考。

---

## 1. 业务概述

| 项 | 内容 |
|---|---|
| 奖项 | Pro Elite Bonus（PE 奖金） |
| 比例 | 固定 15%，由 `AR_CONFIG`（`proEliteRate`/`bonus`）读取 ÷100；全局统一、无国家/大区微调（样本 `PE_RATE=0.150000` 佐证） |
| 资格 | 会员级别须为 Pro Elite 及以上（`AR_CALC_LV_ELITE.LAST_ELITE_CALC_ID >= 20`） |
| 基数 | 直属下级真实小组业绩汇总 + 本人虚拟宽度业绩 |
| 公式 | `BONUS_PE = TRUNCATE([ Σ子节点 GPV_REAL + IFNULL(本人 GPV_UNREAL,0) ] × 15%, 2)`（截断，不四舍五入） |
| 活跃 | 当期活跃（月个人消费 ≥ 30BV）方可发放；**本过程只打标 `IS_ACTIVE`、不拦截，由下游发放环节执行（该环节未在所获附件中，待确认）** |

---

## 2. 数据血缘与上下文边界

```
   晋级业务          ┌──────────────────────────────────────────────┐
   (promotion)       │ CALC_LV_ELITE  网体紧缩 + Elite/PE/SE 评级       │
                     │ 读 AR_PERF_MONTH / AR_USER_RELATION_NEW          │
                     │ （晋级另有 Redis 实现作对照参考，见证据边界）   │
                     └──────────────────────────────────────────────┘
                                       │ 纯 INSERT（时间戳 ID、含 PERIOD_NUM/CALC_MONTH、无自清理）
                                       ▼
                     ┌──────────────────────────────────────────────┐
                     │ AR_CALC_LV_ELITE          ★ CALC_BE_PE 核心上下文 │
                     │ PARENT_UID(已紧缩) GPV_REAL GPV_UNREAL          │
                     │ LAST_ELITE_CALC_ID = 10/20/30                   │
                     └──────────────────────────────────────────────┘
                                       │ 读取（须按 PERIOD_NUM+CALC_MONTH 过滤、自连接取直属）
                                       ▼
   奖金业务·本过程   ┌──────────────────────────────────────────────┐
   (per-bonus)       │ CALC_BE_PE  Pro Elite 奖金                      │
                     │ + AR_CONFIG + AR_USER + AR_USER_PERF            │
                     │ 产出 AR_CALC_BONUS_PE（含 IS_ACTIVE 活跃快照）/ _SOURCE│
                     └──────────────────────────────────────────────┘
                                       │
                                       ▼
   发放侧            ┌──────────────────────────────────────────────┐
   (downstream)      │ 发放/结算环节（未在所获附件中）                  │
                     │ 据"不活跃不发"对活跃受限奖金拦截                 │
                     │ 是否消费 AR_CALC_BONUS_PE.IS_ACTIVE？待确认      │
                     └──────────────────────────────────────────────┘

   奖金业务·兄弟过程 ┌──────────────────────────────────────────────┐
   (sibling)         │ CALC_BE_E  Elite 奖金   ✗ 不读 AR_CALC_LV_ELITE  │
                     │ 自己从 AR_PERF_MONTH 重走网体 → 与本过程无数据依赖  │
                     │ 其产出 AR_CALC_BONUS_E 无 IS_ACTIVE 列（见 §3.2）  │
                     └──────────────────────────────────────────────┘
```

**输入**：`AR_CALC_LV_ELITE`（决定性，晋级产出）、`AR_CONFIG`、`AR_USER`、`AR_USER_PERF`。
**输出**：`AR_CALC_BONUS_PE`、`AR_CALC_BONUS_PE_SOURCE`。
**不属于 `CALC_BE_PE` 的数据依赖**：`CALC_BE_E`。它是独立的 Elite 奖过程，不读取 `AR_CALC_LV_ELITE`；但作为兄弟过程，用于同构对照与边界参考（属参考上下文，非数据血缘）。

---

## 3. 业务规则

### 3.1 资格与级别门槛

PE 资格取自晋级评级 `LAST_ELITE_CALC_ID >= 20`。编码已由上游源码坐实：`10=Elite / 20=Pro Elite / 30=Super Elite`，与晋级文档口径一一对应（详见附录 A）。

### 3.2 活跃与发放（"算出来不发"）

PE 奖金属"只有活跃会员可获得"的奖项，制度口径"不活跃：算出来不发"。本过程（`CALC_BE_PE`）对所有满足级别门槛者一律算出 `BONUS_PE` 并落库 `AR_CALC_BONUS_PE`，同时写入 `IS_ACTIVE = IFNULL(AR_USER_PERF.IS_ACTIVE, 0)` 作为该会员当期活跃状态快照。**本过程只打标、不拦截**：`BONUS_PE` 无论活跃与否都照算照存。

- `IS_ACTIVE` 业务含义：会员当期活跃状态（活跃=当期个人消费 ≥ 30BV），是**发放闸门标记，不参与金额计算**。
- fail-closed：源端 `AR_USER_PERF.IS_ACTIVE` 可空，取用处 `IFNULL(...,0)`，缺行/NULL → 0（按不活跃）。
- 对照佐证：兄弟过程 `CALC_BE_E`（Elite 奖）产出表 `AR_CALC_BONUS_E` **无 `IS_ACTIVE` 列**，而 `AR_CALC_BONUS_PE` 有——与制度一致（Elite Bonus 不在活跃受限清单、PE 在），**说明 PE 结果需要携带活跃状态快照**；该字段是否被下游发放/结算环节实际消费，仍需确认。
- **待确认**：执行"不活跃不发"的下游发放/结算环节**未在所获附件中**；其是否消费 `AR_CALC_BONUS_PE.IS_ACTIVE` 及具体机制，需向下游确认（见 §8）。

### 3.3 业绩基数与计算公式

```
TOTAL_BASE_GPV = Σ(直属下级 AR_CALC_LV_ELITE.GPV_REAL) + IFNULL(本人 AR_CALC_LV_ELITE.GPV_UNREAL, 0)
BONUS_PE       = TRUNCATE(TOTAL_BASE_GPV × proEliteRate, 2)
```

样本核验：基数 `1046.20 × 0.15 = 156.93 = BONUS_PE`，与公式及 15% 费率吻合。**两位截断（而非四舍五入）由 `CALC_BE_PE.sql` 中 `TRUNCATE(...,2)` 直接证明**；该样本因结果恰为两位小数，不足以单独区分截断与四舍五入。

> 上游字段精确语义（详见 §4）：直属下级 `GPV_REAL` 为"封顶后真实小组业绩 + 上推净额"；本人 `GPV_UNREAL` **仅为虚拟宽度超额**（上推业绩在 `GPV_REAL` 内并对来源子节点做 −净额抵扣）。

### 3.4 级别过滤与留痕口径

本过程对未达 PE 者 `WHERE LAST_ELITE_CALC_ID >= 20` 硬过滤、不生成记录（全系统一致约定，兄弟过程 `CALC_BE_E` 同样只为合格者落库）。因 PE+ 资格由直属宽度（旁线结构）决定，可归入"旁线级别不够：不计算"；而"算出来不发"经活跃维度实现（见 3.2）。`AR_USER_PERF` 是活跃/市场统计表，无级别列、无理论奖金列，对"未达 PE 是否留痕"不提供证据——该口径属业务决策（见 §8）。

---

## 4. 上游数据契约与字段语义（来自 `CALC_LV_ELITE`，已坐实）

| 字段 | `CALC_LV_ELITE` 生成逻辑 | 在 `CALC_BE_PE` 的用途 |
|---|---|---|
| `PARENT_UID` | MID3（紧缩+虚拟宽度）→ MID4（按用户取最上层去重）→ MID5（重算层数）后的**有效直属关系**，已剔除未达标中间层 | 自连接取直属下级 |
| `GPV_REAL` | `MID5.GPV_REAL`（`≥2000` 时**封顶 1000**）+ `SUM(MID7)` 上推净额（"自己未达标且直属≥2 达标"时下属最小 Elite 业绩，父 +、子 −） | `SUM(子节点 GPV_REAL)` 作基数主体 |
| `GPV_UNREAL` | MID3：`CASE WHEN GPV_REAL≥2000 THEN GPV_REAL−1000 ELSE 0`，**纯虚拟宽度超额** | 加本人 `GPV_UNREAL` 进基数 |
| `SONS_NUM` | 真实合格线数 + `CASE WHEN 封顶前GPV_REAL≥2000 THEN FLOOR(封顶前GPV_REAL/1000) ELSE 0 END` = "综合总宽度" | 经 `LAST_ELITE_CALC_ID` 间接体现 |
| `LAST_ELITE_CALC_ID` | `CASE SONS_NUM>2→30, =0→10, ELSE→20` | `WHERE >= 20` 取 PE+ |

> **`SONS_NUM` 公式精确说明**：虚拟宽度**仅在封顶前 `GPV_REAL ≥ 2000` 时启动**（`1000–1999` 不产生虚拟宽度），且 `FLOOR` 用的是**封顶前**的 `MID2.GPV_REAL`。与晋级文档"GPV 达 2000 及以上启动虚拟宽度、每满 1000BV 折算 1 个虚拟直属下级"一致。

**两项契约现确认已由上游实现**：
- **网络紧缩契约**：MID3/4/5 已完成 PE 口径重新紧缩，`PARENT_UID` 即紧缩后有效直属——本过程盲信 `PARENT_UID` 成立。
- **真实/虚拟互斥（防重算）契约**：① `GPV_REAL` 封顶 1000、超额转 `GPV_UNREAL`；② 上推为净额移动（父 +、子 −），非复制。

> **编排与同期一致前提（硬性）**：`CALC_LV_ELITE` 必须在 `CALC_BE_PE` 之前、同一期运行；且 `AR_CALC_LV_ELITE` 须呈现该期的**单期且无重复**内容——后者不能仅靠 `CALC_BE_PE` 的周期过滤保证（见风险二）。

---

## 5. 技术架构与数据流转

**步骤一**：取 `proEliteRate`；以紧缩后的 `AR_CALC_LV_ELITE`（按期过滤）为驱动，汇总子节点 `GPV_REAL` 写入 `AR_CALC_BE_PE_MID1`。
**步骤二**：直属真实汇总 + 本人 `GPV_UNREAL` 得基数，套比例算 `BONUS_PE`，关联活跃快照落盘 `AR_CALC_BONUS_PE`。
**步骤三**：`UNION ALL` 分记下级 `GPV_REAL` 贡献与本人 `GPV_UNREAL` 贡献至 `AR_CALC_BONUS_PE_SOURCE`。

---

## 6. 现网风险与重构清单

> **🔴坐实**＝表结构/源码确证、必修；**🟡条件**＝触发依外部条件，但建议无条件加固。

### 🔴 风险一：幂等性缺失与重复入账（表结构坐实）

`AR_CALC_BONUS_PE` 主键随机 `ID`、`USER_ID` 非唯一索引、**无 (期,人) 唯一键**；过程入口无 `DELETE`。同一期重跑生成 ID 不同、(期,人)相同的重复行 → 下游重复入账。
**重构**：入口按期 `DELETE` + 加 `(PERIOD_NUM, CALC_MONTH, USER_ID)` 唯一键 + 统一事务/异常回滚。

### 🔴 风险二：`AR_CALC_LV_ELITE` 跨期污染 **与同期重复追加**（上游源码坐实）

上游 `CALC_LV_ELITE` 对 `AR_CALC_LV_ELITE` 纯追加（时间戳 ID）、含 `PERIOD_NUM/CALC_MONTH`、无自清理。

- **跨期污染**：本过程不按期过滤会跨期错配父子 → 行翻倍。**修法**：所有读取处补 `PERIOD_NUM`+`CALC_MONTH`（该表两列都有）。
- **同期重复追加（关键）**：周期过滤**只能解决跨期，不能解决同期重复**。若 `CALC_LV_ELITE` 对同一 `PERIOD_NUM+CALC_MONTH` 重跑且不先删旧数据，会追加第二批同期同用户评级；此时即便 `CALC_BE_PE` 已加周期过滤，仍读到同期重复行、继续金额放大。
  **修法（必须在上游）**：`CALC_LV_ELITE` 执行前按 `PERIOD_NUM+CALC_MONTH` 清理，或对 `AR_CALC_LV_ELITE` 加 `(PERIOD_NUM, CALC_MONTH, USER_ID)` 唯一约束/覆盖策略。否则 `CALC_BE_PE` 无法仅靠自身周期过滤保证结果正确。

### 🔴 风险三：`AR_USER_PERF` 关联放大（表结构坐实）

`AR_USER_PERF` 有 `PERIOD_NUM`、主键随机 `ID`、`USER_ID` 非唯一索引——可一人多期，且 **DDL 未强制"每人每期唯一"**。本过程 `LEFT JOIN AR_USER_PERF T3 ON T3.USER_ID=T.USER_ID` 不带周期条件，多期共存时一人命中多行 → **主表/明细表成倍放大**。
**重构**：补 `AND T3.PERIOD_NUM = IV_PERIOD_NUM`。**`AR_USER_PERF` 无 `CALC_MONTH` 列，只能按 `PERIOD_NUM` 过滤**。若该表可能一人每期多行，还需在源头保证每人每期唯一，否则周期过滤后仍可能放大。

### 🔴 风险四：基数字段命名误导财务对账（表结构坐实）

`AR_CALC_BONUS_PE.GPV_REAL`（注释"实际小组业绩"）实存"Σ直属真实 + 本人虚拟"的 PE 奖金总基数（样本 `1046.20` 佐证）。
**重构**：列改名 `TOTAL_BASE_GPV`、注释改"PE奖金基数(直属真实+本人虚拟)"，同步下游映射。

### 🔴 风险五：缺 `IFNULL` 导致金额置空
`T.GPV_REAL + T1.GPV_UNREAL` 中 `T1.GPV_UNREAL` 为 `NULL` 时整体变 `NULL`。**重构**：补 `IFNULL(T1.GPV_UNREAL,0)`，金额计算同步覆盖。

### 🔴 风险六：主明细表 `AR_USER` 关联不一致
主表 `LEFT JOIN`、Source 表 `INNER JOIN` → "主表有奖、明细无源"。**重构**：Source 对 `AR_USER` 统一 `LEFT JOIN`（对 `AR_CALC_LV_ELITE T1` 的 `INNER JOIN` 有意保留）。

### 🟡 风险七：伪并发主键（样本坐实方案，触发依并发）
`ID = CONCAT(时间戳到秒, 8位ROWNUM)`（样本 `2026060203012300000001`），同秒并发主键冲突致 `INSERT` 失败。**重构**：`REPLACE(UUID(),'-','')`（32 位十六进制，恰配 `varchar(32)`，无需改列）；需时间有序则 Snowflake。

---

## 7. 修正后的完整存储过程（`CALC_BE_PE` 参考实现）

`AR_CALC_LV_ELITE`（含 `PERIOD_NUM/CALC_MONTH`）与 `AR_USER_PERF`（仅 `PERIOD_NUM`）的周期过滤已按各自表结构精确启用。

```sql
CREATE DEFINER=`ibs_calc_appl`@`%` PROCEDURE `CALC_BE_PE`(
  IN IV_PERIOD_NUM INT,
  IN IV_CALC_MONTH TINYINT
)
BEGIN
  DECLARE VV_PE_RATE DECIMAL(16,6);

  -- 【风险一·事务】异常处理器须声明在所有可执行语句之前
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    RESIGNAL;
  END;

  SELECT IFNULL(MIN(T.VALUE), 0) / 100
    INTO VV_PE_RATE
    FROM AR_CONFIG T
   WHERE T.CONFIG_NAME = 'proEliteRate' AND T.TYPE = 'bonus';

  START TRANSACTION;

  -- 【风险一·幂等】按当期双维度清理（建议另加 (PERIOD_NUM,CALC_MONTH,USER_ID) 唯一键）
  DELETE FROM AR_CALC_BONUS_PE_SOURCE WHERE PERIOD_NUM = IV_PERIOD_NUM AND CALC_MONTH = IV_CALC_MONTH;
  DELETE FROM AR_CALC_BONUS_PE        WHERE PERIOD_NUM = IV_PERIOD_NUM AND CALC_MONTH = IV_CALC_MONTH;
  DELETE FROM AR_CALC_BE_PE_MID1      WHERE PERIOD_NUM = IV_PERIOD_NUM AND CALC_MONTH = IV_CALC_MONTH;

  -- 步骤一：汇总直属下级真实业绩 → MID1
  -- 【风险二】AR_CALC_LV_ELITE 按期留存，须按期过滤（注:仍需上游保证同期不重复，见风险二）
  INSERT INTO AR_CALC_BE_PE_MID1 (PERIOD_NUM, CALC_MONTH, USER_ID, GPV_REAL)
  SELECT IV_PERIOD_NUM,
         IV_CALC_MONTH,
         T.USER_ID,
         IFNULL(SUM(T1.GPV_REAL), 0) AS GPV_REAL
    FROM AR_CALC_LV_ELITE T
    LEFT JOIN AR_CALC_LV_ELITE T1
           ON T1.PARENT_UID = T.USER_ID
          AND T1.PERIOD_NUM = IV_PERIOD_NUM
          AND T1.CALC_MONTH = IV_CALC_MONTH
   WHERE T.LAST_ELITE_CALC_ID >= 20
     AND T.PERIOD_NUM = IV_PERIOD_NUM
     AND T.CALC_MONTH = IV_CALC_MONTH
   GROUP BY T.USER_ID;

  -- 步骤二：合并本人虚拟业绩并计算奖金 → 主表
  INSERT INTO AR_CALC_BONUS_PE
         (ID, PERIOD_NUM, CALC_MONTH, USER_ID, TOTAL_BASE_GPV, PE_RATE, BONUS_PE, COUNTRY_ID, IS_ACTIVE)
  SELECT REPLACE(UUID(), '-', '')                                            AS ID,            -- 【风险七】
         T.PERIOD_NUM,
         T.CALC_MONTH,
         T.USER_ID,
         T.GPV_REAL + IFNULL(T1.GPV_UNREAL, 0)                               AS TOTAL_BASE_GPV, -- 【风险四/五】
         VV_PE_RATE                                                          AS PE_RATE,
         TRUNCATE((T.GPV_REAL + IFNULL(T1.GPV_UNREAL, 0)) * VV_PE_RATE, 2)   AS BONUS_PE,
         T2.COUNTRY_ID,
         -- 活跃快照（仅打标；"不活跃不发"由下游发放环节执行，该环节未在附件中、待确认）
         IFNULL(T3.IS_ACTIVE, 0)                                            AS IS_ACTIVE
    FROM AR_CALC_BE_PE_MID1 T
    LEFT JOIN AR_CALC_LV_ELITE T1
           ON T1.USER_ID = T.USER_ID
          AND T1.PERIOD_NUM = IV_PERIOD_NUM           -- 【风险二】
          AND T1.CALC_MONTH = IV_CALC_MONTH
    LEFT JOIN AR_USER T2
           ON T2.ID = T.USER_ID                       -- AR_USER 作主数据使用（一人一行需 DDL 确认）
    LEFT JOIN AR_USER_PERF T3
           ON T3.USER_ID = T.USER_ID
          AND T3.PERIOD_NUM = IV_PERIOD_NUM           -- 【风险三】仅 PERIOD_NUM（无 CALC_MONTH）
   WHERE T.PERIOD_NUM = IV_PERIOD_NUM
     AND T.CALC_MONTH = IV_CALC_MONTH;

  -- 步骤三：记录奖金追溯来源 → Source
  INSERT INTO AR_CALC_BONUS_PE_SOURCE
         (PERIOD_NUM, CALC_MONTH, BONUS_USER_ID, BONUS_USER_NAME, BONUS_REAL_NAME,
          SOURCE_USER_ID, SOURCE_USER_NAME, SOURCE_REAL_NAME,
          SOURCE_GPV, SOURCE_GPV_UNREAL, PE_RATE, IS_ACTIVE)
  SELECT IV_PERIOD_NUM, IV_CALC_MONTH,                       -- 明细 A：下级真实业绩贡献
         T.USER_ID,  U.USER_NAME,  U.REAL_NAME,
         T1.USER_ID, U1.USER_NAME, U1.REAL_NAME,
         T1.GPV_REAL, 0, VV_PE_RATE,
         IFNULL(T3.IS_ACTIVE, 0)
    FROM AR_CALC_LV_ELITE T
    LEFT JOIN AR_USER U   ON U.ID  = T.USER_ID               -- 【风险六】INNER → LEFT
    INNER JOIN AR_CALC_LV_ELITE T1
            ON T1.PARENT_UID = T.USER_ID
           AND T1.PERIOD_NUM = IV_PERIOD_NUM
           AND T1.CALC_MONTH = IV_CALC_MONTH
    LEFT JOIN AR_USER U1  ON U1.ID = T1.USER_ID              -- 【风险六】INNER → LEFT
    LEFT JOIN AR_USER_PERF T3
           ON T3.USER_ID = T.USER_ID
          AND T3.PERIOD_NUM = IV_PERIOD_NUM
   WHERE T.LAST_ELITE_CALC_ID >= 20
     AND T.PERIOD_NUM = IV_PERIOD_NUM
     AND T.CALC_MONTH = IV_CALC_MONTH
     AND T1.GPV_REAL > 0
  UNION ALL
  SELECT IV_PERIOD_NUM, IV_CALC_MONTH,                       -- 明细 B：本人虚拟业绩贡献
         T.USER_ID, U.USER_NAME, U.REAL_NAME,
         T.USER_ID, U.USER_NAME, U.REAL_NAME,
         0, T.GPV_UNREAL, VV_PE_RATE,
         IFNULL(T3.IS_ACTIVE, 0)
    FROM AR_CALC_LV_ELITE T
    LEFT JOIN AR_USER U   ON U.ID = T.USER_ID                -- 【风险六】INNER → LEFT
    LEFT JOIN AR_USER_PERF T3
           ON T3.USER_ID = T.USER_ID
          AND T3.PERIOD_NUM = IV_PERIOD_NUM
   WHERE T.LAST_ELITE_CALC_ID >= 20
     AND T.PERIOD_NUM = IV_PERIOD_NUM
     AND T.CALC_MONTH = IV_CALC_MONTH
     AND T.GPV_UNREAL > 0;

  COMMIT;
END
```

**上线前配套（DDL / 跨过程）**：
- 风险四：`ALTER TABLE AR_CALC_BONUS_PE CHANGE GPV_REAL TOTAL_BASE_GPV DECIMAL(16,2) NOT NULL DEFAULT 0.00 COMMENT 'PE奖金基数(直属真实+本人虚拟)';` + 下游映射同步。
- 风险一：`ALTER TABLE AR_CALC_BONUS_PE ADD UNIQUE KEY UK_PE_PERIOD_USER (PERIOD_NUM, CALC_MONTH, USER_ID);`
- 风险二：`CALC_LV_ELITE` 须同期幂等（执行前按期清理或 `AR_CALC_LV_ELITE` 加 `(PERIOD_NUM,CALC_MONTH,USER_ID)` 唯一约束）。
- 风险三：确认 `AR_USER_PERF` 每人每期唯一（DDL 未强制）。

---

## 8. 待确认事项

| # | 事项 | 性质 | 说明 |
|---|---|---|---|
| 1 | 下游"不活跃不发"执行点 | 外部模块 | 本过程只打标 `IS_ACTIVE` 不拦截；执行该规则的发放/结算环节未在所获附件中，其是否消费 `AR_CALC_BONUS_PE.IS_ACTIVE` 及具体机制待确认。 |
| 2 | `CALC_LV_ELITE` 同期幂等 | 上游必修 | `AR_CALC_LV_ELITE` 纯追加无清理；同期重跑会重复，`CALC_BE_PE` 周期过滤救不了。须上游先删/唯一约束。 |
| 3 | `AR_USER_PERF` 每人每期唯一 | 核对/DDL | DDL 未强制唯一；若可能多行，周期过滤后仍会放大。 |
| 4 | `AR_USER` 一人一行 | 核对/DDL | 当前附件无 `AR_USER.sql`；按代码作主数据使用，通常应一人一行，需表结构/唯一键确认。 |
| 5 | 未达 PE 是否留痕 | 业务决策 | 现状硬过滤不留痕（全系统一致）；若需"算出标记不发"，属新增需求。 |
| 6 | 基数构成端到端对账 | 测试 | 语义已对齐，建议用例核验基数=业务期望"直属宽度总 PGS"。 |
| 7 | `IS_ACTIVE` fail-closed 默认 | 业务确认 | 缺行/NULL → 0（不发），确认符合预期。 |

---

## 附录 A：级别编码与晋级口径对照

| `LAST_ELITE_CALC_ID` | 级别 | 上游判定（`SONS_NUM`=综合总宽度） | 晋级文档口径 |
|---|---|---|---|
| 10 | Elite | `SONS_NUM = 0`（自身 GPV≥1000） | 个人小组 GPV 达 1000 |
| 20 | Pro Elite | `1 ≤ SONS_NUM ≤ 2` | 自身 Elite+1 条线，或 非 Elite+2 条线（含虚拟宽度） |
| 30 | Super Elite | `SONS_NUM ≥ 3` | 直属 3 条 Elite 线（含虚拟宽度） |
| — | PE+ 门槛 | `LAST_ELITE_CALC_ID >= 20` | Pro Elite 及以上 |

`SONS_NUM = 真实合格线数 + (CASE WHEN 封顶前GPV_REAL ≥ 2000 THEN FLOOR(封顶前GPV_REAL/1000) ELSE 0 END)`；即虚拟宽度仅 `≥2000` 启动、用封顶前 GPV。

## 附录 B：`is_elite` 与 `IS_ACTIVE` 辨析（正交两概念）

> 本辨析的核心是"级别维度 vs 活跃维度"两者正交，该结论可由**核心证据独立支撑**：级别取自 `CALC_LV_ELITE.sql`（Elite ⇔ `ELITE_CALC_ID=10` ⇔ GPV≥1000），活跃取自 `AR_USER_PERF.sql`（`IS_ACTIVE` ⇔ 月消费≥30BV）。其中 `is_elite` 是晋级 Redis 实现的字段（属补充/对照参考）；**如该 Redis 实现已随包核对**，其 `UserStatsService._recalc_rank` 中 `is_self_elite = gpv >= 1000` 与 SQL 侧一致；若未提供该实现，则以 SQL 侧 `LAST_ELITE_CALC_ID`/`ELITE_CALC_ID` 为准。

| 维度 | `is_elite`（晋级 Redis 字段；SQL 侧对应 `LAST_ELITE_CALC_ID`/`ELITE_CALC_ID`） | `IS_ACTIVE`（AR_USER_PERF / AR_CALC_BONUS_PE） |
|---|---|---|
| 含义 | 网体小组业绩达 Elite 门槛（`gpv ≥ 1000`） | 个人当期活跃（月消费 ≥ 30BV） |
| 维度 | 级别/晋级资格 | 活跃/发放资格 |
| 产出 | 晋级引擎（SQL：`CALC_LV_ELITE`；Redis 实现如已核对：`UserStatsService._recalc_rank`） | `AR_USER_PERF` 子系统 |
| 用途 | 决定 `rank`(0/10/20/30) | 供下游发放环节"不活跃不发"拦截 |
| 关系 | 正交：可"是 Elite 但不活跃"或"活跃但非 Elite" | |

## 附录 C：`AR_USER_PERF` 与 `AR_CALC_BONUS_PE` 关键事实

- `AR_USER_PERF`：含 `PERIOD_NUM`，主键随机 `ID`，`USER_ID` 非唯一索引，**无 `CALC_MONTH`**；按 `PERIOD_NUM` 保存、**应保证每人每期唯一，但 DDL 未强制唯一**；`IS_ACTIVE` 可空。
- `AR_CALC_BONUS_PE`：`ID`(随机, PK)、`PERIOD_NUM`、`CALC_MONTH`、`USER_ID`、`GPV_REAL`(注释"实际小组业绩"——实为奖金基数，建议改名 `TOTAL_BASE_GPV`)、`PE_RATE`、`BONUS_PE`、`COUNTRY_ID`、`IS_ACTIVE`(`NOT NULL`)；主键随机 `ID`、`USER_ID` 非唯一索引、**无 (期,人) 唯一键**。
- 样本：`ID='2026060203012300000001'`=时间戳 `20260602030123`+序号 `00000001`；`1046.20×0.15=156.93`；`PE_RATE=0.150000`；`IS_ACTIVE=1`。（样本证明公式与费率；截断由 SQL `TRUNCATE(...,2)` 证明。）
