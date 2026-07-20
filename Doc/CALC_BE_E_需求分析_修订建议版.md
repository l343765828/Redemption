# `CALC_BE_E` 存储过程需求分析（修订建议版）

> Elite Bonus（精英奖金）核算  
> 修订说明：本版在原 `CALC_BE_E_需求分析.md` 基础上，补充了 `PV_PSS / PV_PCS` 字段矛盾的定性边界、`VV_CALC_MONTH` 未使用可能造成的误解与修订建议，以及 `ELITE_CALC_ID = 10` 魔法数字与 `AR_ELITE_LEVEL.CALC_ID` 编码约定的耦合风险。另补充一个建议确认项：`AR_CALC_BONUS_E_SOURCE` 的 `BONUS_LAYER` 去重排序语义与“最近得奖人”的文字解释可能不完全一致。

---

## 0. 本版修订摘要

| 修订点 | 原文问题 | 修订建议 |
|---|---|---|
| `PV_PSS / PV_PCS` | 原文已标记为疑点，但容易被理解为已经确认 typo | 明确这是 **SQL 自身存在字段使用不一致**，在未核对 `AR_PERF_MONTH` 表结构前，不能直接定性为 typo |
| `VV_CALC_MONTH = 202304` | 原文只写“死代码”，没有说明影响 | 补充可能误导读者以为历史特别奖励已实现；建议确认是历史残留还是未完成功能 |
| `ELITE_CALC_ID = 10` | 原文把风险描述为 `CALC_ID` 数值大小隐式假设，偏向 `CALC_LV_ELITE_HIGHEST` | 改为本过程更直接的风险：**魔法数字 10 与 `AR_ELITE_LEVEL.CALC_ID` 编码约定耦合**，本过程不查级别表，编码变更不会自动跟随 |
| `BONUS_LAYER` 去重 | 原文解释“`BONUS_LAYER` 最小 = 最靠近源头的得奖人” | 建议改为忠实描述 SQL：取 `BONUS_LAYER` 最小的记录；由于 `TOP_DEEP` 越深值越大，业务语义是否等价于“最近得奖人”需结合传播停止逻辑确认 |

---

## 1. 业务背景与目标

### 1.1 业务定位

`CALC_BE_E` 对应奖金制度文档（EKPlan20250324）“奖项概况”中的 **Elite B（Elite Bonus）**。

| 字段 | 内容 |
|---|---|
| 奖项名 | Elite Bonus |
| 比例 | 15%（实际从配置 `eliteRate` 动态读取） |
| 公式 | 合格小组业绩 × 比例 |
| 合格门槛 | 合格小组业绩达到 1000 BV；另存在“下线有 Elite 时取得 Elite 奖金获取资格”的特殊路径 |
| 级别耦合 | **业务上与 Elite 三档级别评定无关**：发奖不读取 `CALC_LV_ELITE` 产出的 `LAST_ELITE_CALC_ID`，而是在本过程内部独立标记是否满足 Elite Bonus 计算资格 |
| 活跃要求 | 本过程内不判断活跃；是否发放需以下游聚合/发放流程规则为准。按当前制度文档，Elite Bonus 不在“只有活跃会员可以获得”的奖金清单中 |

### 1.2 与其他奖金模块的边界

- 本过程**只**计算 Elite Bonus 一项；其他奖金（PE、SE、LB、TB、PB、SFB、GPB、CRB、EAB 等）由对应过程独立计算。
- 本过程输出 `AR_CALC_BONUS_E` 和 `AR_CALC_BONUS_E_SOURCE`，供下游聚合、发放、对账或查询使用。
- 本过程使用的“网体业绩”是**独立计算**的，写入自有中间表 `AR_CALC_BE_E_NET`，**不复用** `CALC_LV_ELITE` 的级别评定结果。
- 这种设计可以理解为制度中“Elite Bonus 与 Elite 级别无关”的工程实现：
  - Elite 三档级别评定：由 `CALC_LV_ELITE` 负责；
  - Elite Bonus 资格与金额：由 `CALC_BE_E` 依据真实推荐关系和本过程内部规则独立计算。

---

## 2. 输入与输出

### 2.1 输入

| 表 | 用途 |
|---|---|
| `AR_CONFIG` | 取 `CONFIG_NAME='eliteRate' AND TYPE='bonus'` 的奖金比例 |
| `AR_PERF_MONTH` | 当月业绩归集；按 `PERIOD_NUM = IV_PERIOD_NUM` 过滤；SQL 中 `SELECT` 使用 `PV_PCS`，但 `WHERE` 使用 `PV_PSS`，字段口径需确认 |
| `AR_USER_RELATION_NEW` | 真实推荐关系，含 `PARENT_UID`、`TOP_DEEP`，未经 `CALC_LV_ELITE` 紧缩处理 |
| `AR_USER` | 会员基础信息，主要用于来源溯源表中的 `USER_NAME`、`REAL_NAME` |

### 2.2 输出

**正式产出：**

| 表 | 内容 |
|---|---|
| `AR_CALC_BONUS_E` | 最终 Elite Bonus 发奖记录；每个得奖会员一条；含 ID、周期、用户、网体位置、`GPV_REAL`、`E_RATE`、`BONUS_E`、`COUNTRY_ID` |
| `AR_CALC_BONUS_E_SOURCE` | 业绩来源溯源；用于记录底层业绩源头与被归账的会员之间的关系 |

**过程中间表：**

| 表 | 内容 |
|---|---|
| `AR_CALC_BE_E_NET` | Elite Bonus 计算专用网体，记录每个会员的 GPV、GPV_REAL、ELITE_CALC_ID 等 |
| `AR_CALC_BE_E_MID1` | 算出奖金但尚未生成最终 ID 的中间结果 |
| `AR_CALC_BE_E_MID2` | 业绩贡献链累积记录；一个 `SOURCE_USER_ID` 在传播过程中可能临时对应多个 `BONUS_USER_ID` |

### 2.3 入参

| 参数 | 类型 | 含义 |
|---|---|---|
| `IV_PERIOD_NUM` | INT | 计算周期编号 |
| `IV_CALC_MONTH` | TINYINT | 计算月份；本过程在写入 `AR_CALC_BONUS_E_SOURCE` 时使用该参数 |

---

## 3. 核心业务规则

### 3.1 合格判定（双路径）

会员在本过程内部被标记为 Elite Bonus 合格时，写入：

```sql
ELITE_CALC_ID = 10
```

并将本轮可用于发奖的小组业绩写入：

```sql
GPV_REAL = GPV + 下线未合格节点向上贡献的 GPV
```

满足以下任一条件即被标记为合格：

1. **路径 A：自身/小组业绩达标**  
   `GPV + 下线未合格节点向上贡献的 GPV >= 1000 BV`

2. **路径 B：连带合格**  
   下一层存在已被本过程标记为合格的 Elite（`ELITE_CALC_ID = 10`），即使本人累计业绩不足 1000 BV，也可取得 Elite Bonus 计算资格。

> 路径 B 对应制度文档 Description 第 5 条：“会员未达到 Elite，所属下线有任一达到 Elite，此会员可取得 Elite 奖金获取资格，小组业绩不向上累计。仅适用于 Elite。”这是 Elite Bonus 区别于 PE / SE 等奖金的关键规则，不能简化为“只有 `GPV_REAL >= 1000` 才合格”。

### 3.2 业绩传导规则

- **未合格节点**：`GPV` 继续 100% 向上累加到上级。SQL 条件为：

```sql
A.GPV > 0
AND A.GPV_REAL = 0
AND A.ELITE_CALC_ID = 0
```

- **已合格节点**：业绩截断，不再继续向上贡献。SQL 通过排除 `GPV_REAL > 0` 或 `ELITE_CALC_ID = 10` 的下线实现。
- 该规则配合自下而上的层级循环，逐层把底层未合格节点的业绩向上推，并在某一层合格后停止继续向上贡献。

### 3.3 奖金计算公式

```sql
BONUS_E = TRUNCATE(GPV_REAL * eliteRate, 2)
```

- `eliteRate` 从 `AR_CONFIG` 动态读取：

```sql
SELECT IFNULL(MIN(T.VALUE),0)/100
FROM AR_CONFIG T
WHERE T.CONFIG_NAME = 'eliteRate'
  AND T.TYPE = 'bonus';
```

- 制度文档默认比例为 15%，但实际执行以配置值为准。
- `TRUNCATE(..., 2)` 表示直接截断到 2 位小数，不四舍五入。
- 仅满足以下条件的会员进入奖金中间表：

```sql
T.GPV_REAL > 0
AND T.ELITE_CALC_ID = 10
```

### 3.4 业绩来源溯源与去重规则

SQL 在循环过程中写入 `AR_CALC_BE_E_MID2`，记录业绩源头向上贡献过程中经过的链路。最后写入 `AR_CALC_BONUS_E_SOURCE` 时，对每个 `SOURCE_USER_ID` 只保留一条：

```sql
ROW_NUMBER() OVER (
  PARTITION BY SOURCE_USER_ID
  ORDER BY BONUS_LAYER
) AS rn
```

并取：

```sql
WHERE rn = 1
```

因此，**从 SQL 字面看，本过程保留的是同一 `SOURCE_USER_ID` 下 `BONUS_LAYER` 数值最小的那条记录**。

需要注意：`BONUS_LAYER` 在本过程里取自 `VV_MAX_LAYER`，而 `VV_MAX_LAYER` 来源于 `AR_USER_RELATION_NEW.TOP_DEEP`。注释中说明“网体越往下越大”，即根节点层数较小、底层会员层数较大。因此：

- `BONUS_LAYER` 数值最小，通常意味着更靠近推荐网顶端；
- “最靠近源头的得奖人”这个业务表述，需要结合传播停止逻辑确认是否一定成立；
- 若业务目标确实是“最近的实际得奖人”，建议确认是否需要在来源去重前/后关联 `AR_CALC_BONUS_E` 或 `AR_CALC_BE_E_MID1`，确保最终保留对象确实有奖金记录。

### 3.5 隐式约束：`ELITE_CALC_ID = 10` 是魔法数字

本过程不读取 `AR_ELITE_LEVEL` 表，也不通过级别配置表解析“Elite”的 `CALC_ID`，而是在多处硬编码：

```sql
ELITE_CALC_ID = 10
```

这意味着当前实现依赖一个外部约定：**`AR_ELITE_LEVEL.CALC_ID = 10` 表示 Elite**。

风险如下：

- 如果未来 `AR_ELITE_LEVEL` 的编码方案调整，例如 Elite 不再是 10，本过程不会自动跟随；
- 如果新增中间级别或重排编码，本过程仍会继续把 10 当作 Elite；
- `CALC_LV_ELITE`、`CALC_LV_ELITE_HIGHEST` 和本过程之间虽然不直接共享结果，但都可能依赖同一套 `CALC_ID` 编码约定，需统一维护。

建议：

1. 最低限度：在文档和代码注释中明确 `10 = Elite` 是固定约定；
2. 更稳妥：过程启动时从 `AR_ELITE_LEVEL` 查询 Elite 对应的 `CALC_ID`，赋给变量，例如 `VV_ELITE_CALC_ID`；
3. 若暂不改代码，至少在级别编码变更 checklist 中加入 `CALC_BE_E` 排查项。

---

## 4. 处理流程

```text
                  ┌─────────────────────────────┐
  Step 1          │ 取配置 eliteRate            │
                  └─────────────────────────────┘
                                ↓
                  ┌─────────────────────────────┐
  Step 2          │ 初始化 AR_CALC_BE_E_NET     │
                  │ SELECT 使用 PV_PCS          │
                  │ WHERE 使用 PV_PSS，需确认   │
                  │ 关联 AR_USER_RELATION_NEW   │
                  └─────────────────────────────┘
                                ↓
                  ┌─────────────────────────────┐
  Step 3          │ 自下而上层级循环             │ ← 取 MAX(TOP_DEEP) 起算
  (loop)          │  a. UPDATE 当层 GPV/        │
                  │     GPV_REAL/ELITE_CALC_ID  │
                  │  b. 累积 MID2 业绩来源链    │
                  │ TOP_DEEP - 1，直到 0         │
                  └─────────────────────────────┘
                                ↓
                  ┌─────────────────────────────┐
  Step 4          │ 计算奖金 → MID1             │
                  │ GPV_REAL × E_RATE，截断 2 位│
                  └─────────────────────────────┘
                                ↓
                  ┌─────────────────────────────┐
  Step 5          │ 写入 AR_CALC_BONUS_E         │
                  │ 加 ID：时间戳14 + 序号8      │
                  │ BONUS_E > 0 才入库          │
                  └─────────────────────────────┘
                                ↓
                  ┌─────────────────────────────┐
  Step 6          │ 业绩来源去重 → SOURCE 表    │
                  │ 每个 SOURCE_USER_ID 取      │
                  │ BONUS_LAYER 最小的一条      │
                  └─────────────────────────────┘
```

### 4.1 Step 1：读取 Elite Bonus 比例

从 `AR_CONFIG` 中读取 `eliteRate`：

```sql
SELECT IFNULL(MIN(T.VALUE),0)/100 INTO VV_E_RATE
FROM AR_CONFIG T
WHERE T.CONFIG_NAME = 'eliteRate'
  AND T.TYPE = 'bonus';
```

### 4.2 Step 2：初始化 `AR_CALC_BE_E_NET`

将当期有业绩的会员铺入 Elite Bonus 计算专用网体。

SQL 当前字段使用存在不一致：

```sql
SELECT T.PV_PCS AS GPV,
       T.PV_PCS,
       ...
FROM AR_PERF_MONTH T
...
WHERE T.PERIOD_NUM = IV_PERIOD_NUM
  AND T.PV_PSS > 0;
```

说明：

- `SELECT` 中使用 `PV_PCS` 作为 GPV 和个人业绩；
- `WHERE` 中却使用 `PV_PSS > 0` 作为过滤条件；
- 这是 SQL 自身存在的字段口径矛盾，文档不能直接定性为 typo，必须先核对 `AR_PERF_MONTH` 表结构和字段含义。

建议核查 SQL：

```sql
SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE, COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<实际库名>'
  AND TABLE_NAME = 'AR_PERF_MONTH'
  AND COLUMN_NAME IN ('PV_PCS', 'PV_PSS');
```

判定建议：

| 核查结果 | 定性 | 建议 |
|---|---|---|
| 只有 `PV_PCS`，没有 `PV_PSS` | 明确 typo / 无法执行 | 改为 `PV_PCS > 0` |
| 两个字段都存在，且含义不同 | 口径不一致 | 找业务确认应以哪个字段作为 Elite Bonus 业绩过滤口径 |
| 两个字段都存在，且 `PV_PSS` 是历史/废弃字段 | 高风险历史残留 | 改为 `PV_PCS > 0`，并清理字段口径说明 |
| 两个字段都存在，且业务要求用 `PV_PSS` 过滤、用 `PV_PCS` 计奖 | 特殊业务设计 | 需在需求文档中明确说明两者差异，避免后续误改 |

### 4.3 Step 3：自下而上层级循环

每一层执行两个动作。

**动作 A：更新当前层 GPV / GPV_REAL / ELITE_CALC_ID**

- 汇总下一层未合格节点向上贡献的 GPV；
- 判断下一层是否存在已经合格的 Elite；
- 若当前节点达到 1000 BV 或存在合格下线，则设置为本过程内部合格。

**动作 B：累计业绩来源链到 `AR_CALC_BE_E_MID2`**

- 当前层有 `PV_PCS > 0` 的会员，先记录一条“自己贡献给自己”；
- 对上一轮仍未合格、需要继续上推的链路，整体向其父级推进一层；
- 后续通过 `ROW_NUMBER()` 对同一来源进行去重。

### 4.4 Step 4：计算奖金到 `AR_CALC_BE_E_MID1`

将满足 `GPV_REAL > 0 AND ELITE_CALC_ID = 10` 的会员写入中间奖金表，并按配置比例计算奖金。

### 4.5 Step 5：写入 `AR_CALC_BONUS_E`

按如下格式生成 ID：

```sql
CONCAT(VV_TIME_STR, LPAD(@ROWNUM:=@ROWNUM+1, 8, '0'))
```

即：

```text
年月日时分秒14位 + 8位序号 = 22位字符
```

仅 `BONUS_E > 0` 的记录写入正式奖金表。

### 4.6 Step 6：写入 `AR_CALC_BONUS_E_SOURCE`

按 `SOURCE_USER_ID` 分组，取 `BONUS_LAYER` 最小的一条来源链记录。

建议在文档中避免直接写成“最近得奖人”，除非已经确认：

1. `BONUS_LAYER` 最小在当前传播机制下确实等价于“最近得奖人”；
2. 被选中的 `BONUS_USER_ID` 一定存在于 `AR_CALC_BONUS_E` 或 `AR_CALC_BE_E_MID1` 中。

更严谨的描述可以是：

> 当前 SQL 将同一来源会员在传播链中的多条记录按 `BONUS_LAYER` 升序排序，并保留层数最小的一条，作为该来源业绩在 `AR_CALC_BONUS_E_SOURCE` 中的归属记录。该归属记录是否一定等价于“最近实际得奖人”，需结合传播停止规则和奖金表结果进一步验证。

---

## 5. 边界与异常处理

### 5.1 制度文档已规定但本过程不处理的项

| 项 | 本过程处理情况 | 备注 |
|---|---|---|
| 活跃状态 | 本过程不判断 | 按当前制度文档，Elite Bonus 不在“只有活跃会员可以获得”的奖金清单中；下游如有统一过滤需单独确认是否排除 Elite Bonus |
| 会员级别不够 | 本过程不读取会员当前 Elite 三档级别 | Elite Bonus 按本过程内部 GPV / 连带合格规则计算 |
| 旁线级别不够 | 本过程不处理 | 该概念更适用于其他奖金或奖衔限制场景 |
| 多国家 / 大区合算 | 本过程不处理 | 制度文档中多国家计算主要涉及 Elite Achievement Bonus、Super Elite Bonus、Leadership Bonus |
| 虚拟宽度 | 本过程未显式使用 `VV_ARRIVE_PV2 = 2000` | 代码声明了变量但未用于 Elite Bonus 计算，虚拟宽度主要出现在 Elite / PE / SE 级别评定规则中 |
| Elite 历史最高 | 本过程不处理 | 由 `CALC_LV_ELITE_HIGHEST` 维护 |

### 5.2 当前代码存在的疑点与修订建议

#### 疑点 1：`PV_PSS` / `PV_PCS` 字段口径不一致

代码片段：

```sql
SELECT T.PV_PCS AS GPV,
       T.PV_PCS,
       ...
FROM AR_PERF_MONTH T
...
WHERE T.PERIOD_NUM = IV_PERIOD_NUM
  AND T.PV_PSS > 0;
```

结论：

- SQL 内部同时出现 `PV_PCS` 和 `PV_PSS`；
- 这不是文档描述问题，而是 SQL 自身存在字段口径不一致；
- 在未核对 `AR_PERF_MONTH` 表结构前，不能直接断言是 typo。

建议：

1. 查询 `AR_PERF_MONTH` 实际字段；
2. 核对两个字段的业务含义；
3. 若确认是笔误，修正为：

```sql
AND T.PV_PCS > 0
```

4. 若确认两字段都有业务含义，应在本需求文档 `2.1 输入` 和 `4.2 Step 2` 中明确“用 A 字段过滤、用 B 字段计奖”的业务原因。

#### 疑点 2：`VV_CALC_MONTH = 202304` 未使用，且注释容易造成误解

代码片段：

```sql
DECLARE VV_CALC_MONTH INT DEFAULT(202304);-- 2023.11.1 – 2024.4.30;Elite附加奖励100eSAC，150USD
```

现象：

- `VV_CALC_MONTH` 声明后未在过程体内被引用；
- 注释提到 “2023.11.1 – 2024.4.30; Elite 附加奖励 100 eSAC，150 USD”；
- 但当前 SQL 没有看到与 100 eSAC / 150 USD 相关的计算、输出字段或入库逻辑。

可能造成的误解：

1. 读者可能误以为本过程已经实现了历史“Elite 附加奖励”；
2. 读者可能误以为 `IV_CALC_MONTH` 或 `VV_CALC_MONTH` 会控制特别奖励活动期；
3. 测试人员可能设计 2023.11.1 – 2024.4.30 的特别奖励用例，但执行结果不会出现对应奖金；
4. 后续维护人员可能误删/误保留这段变量，无法判断它是历史残留还是未完成功能。

建议追问原作者或业务方：

- 注释中的“100 eSAC、150 USD”是否是历史需求残留？
- 是否曾计划在 `CALC_BE_E` 中实现 Elite 附加奖励，但最终改由其他过程处理？
- 是否存在尚未上线的未完成功能？

修订建议：

| 确认结果 | 建议处理 |
|---|---|
| 历史需求残留，已无业务意义 | 删除 `VV_CALC_MONTH` 变量和相关注释 |
| 功能由其他过程实现 | 在注释中明确“特别奖励不在本过程处理，见 XXX 过程 / 表” |
| 功能尚未实现但仍需实现 | 新增明确需求章节，定义活动期、资格、金额、币种/eSAC 口径、输出表字段和验收用例 |
| 暂时无法确认 | 保留为 `TODO`，但文档中明确“当前过程未实现该特别奖励” |

#### 疑点 3：`ELITE_CALC_ID = 10` 魔法数字与级别编码耦合

代码中多处写死：

```sql
ELITE_CALC_ID = 10
```

结论：

- 本过程不读取外部级别表，因此“与 `CALC_LV_ELITE` 产出的 Elite 三档级别无关”在工程上成立；
- 但它仍然依赖“10 表示 Elite”的编码约定；
- 如果 `AR_ELITE_LEVEL.CALC_ID` 编码方案变更，本过程不会自动跟随。

建议：

1. 文档中明确 `10 = Elite` 是当前编码约定；
2. 代码层面可增加变量：

```sql
DECLARE VV_ELITE_CALC_ID INT DEFAULT(10);
```

并统一使用该变量，减少散落魔法数字；

3. 更进一步，可从级别表读取：

```sql
SELECT CALC_ID
INTO VV_ELITE_CALC_ID
FROM AR_ELITE_LEVEL
WHERE <能够唯一识别 Elite 的条件>;
```

4. 在级别编码调整或新增级别的变更清单中，明确纳入 `CALC_BE_E`。

#### 疑点 4：`BONUS_LAYER` 最小是否一定等价于“最近得奖人”

代码片段：

```sql
ROW_NUMBER() OVER (PARTITION BY SOURCE_USER_ID ORDER BY BONUS_LAYER) AS rn
...
WHERE rn = 1;
```

结合代码注释：

```sql
VV_MAX_LAYER -- 个人消费的用户在推荐网中层数最大（网体越往下越大）
```

风险：

- 如果 `TOP_DEEP` 越往下越大，则 `BONUS_LAYER` 越小越靠近网体上层；
- 原文“`BONUS_LAYER` 最小 = 最靠近源头的得奖人”不够严谨；
- 如果传播链上出现未实际得奖的记录，`SOURCE` 表可能保留的不是最终奖金表中的得奖会员。

建议：

1. 先用测试数据验证 `AR_CALC_BONUS_E_SOURCE.BONUS_USER_ID` 是否必然存在于 `AR_CALC_BONUS_E.USER_ID`；
2. 若业务要求是“最近实际得奖人”，建议来源表写入前关联 `AR_CALC_BONUS_E` 或 `AR_CALC_BE_E_MID1` 过滤实际有奖金的会员；
3. 若当前 SQL 结果就是预期，应把文档描述改为“保留传播链中 `BONUS_LAYER` 最小的归属记录”，不要直接解释为“最近源头”。

#### 疑点 5：中间表未在过程内清理

当前过程向以下表直接 `INSERT`：

- `AR_CALC_BE_E_NET`
- `AR_CALC_BE_E_MID1`
- `AR_CALC_BE_E_MID2`
- `AR_CALC_BONUS_E`
- `AR_CALC_BONUS_E_SOURCE`

但未看到过程入口处按周期删除或清空历史数据。

风险：

- 若调度框架没有在调用前清理，会与上次执行结果混在一起；
- 中间表 `MAX(TOP_DEEP)`、上推汇总、来源去重都可能受历史数据污染；
- 重跑同一期可能产生重复奖金记录。

建议：

1. 确认外部调度是否统一清理；
2. 若没有，建议过程入口增加按 `IV_PERIOD_NUM` / `IV_CALC_MONTH` 清理逻辑；
3. 对正式奖金表是否允许重跑覆盖，需要结合系统总账策略确认。

---

## 6. 与其他模块的依赖关系

### 6.1 上游依赖

```text
AR_CONFIG              ← 配置管理模块（eliteRate）
AR_PERF_MONTH          ← 业绩归集模块（PV_PCS / PV_PSS 字段口径需确认）
AR_USER_RELATION_NEW   ← 推荐关系维护模块（真实关系，未紧缩）
AR_USER                ← 会员主数据
```

### 6.2 下游消费方

```text
AR_CALC_BONUS_E         → 下游奖金聚合 / 发放 / 对账
AR_CALC_BONUS_E_SOURCE  → 财务对账、业绩归因报表、客服查询
```

> 注：原文写到 `CALC_BE.sql` 聚合入 `AR_CALC_BONUS` 总账，这一描述需要结合实际是否存在并执行 `CALC_BE.sql` 确认。若总账聚合过程名称不同，应以实际调度链路为准。

### 6.3 同级模块（独立但功能相邻）

```text
CALC_LV_ELITE.sql           （网体紧缩 + Elite / Pro Elite / Super Elite 三档级别评定）
CALC_LV_ELITE_HIGHEST.sql   （Elite 历史最高快照 / 回写前置结果）
CALC_BX_X.sql 系列           （其他奖金计算）
```

`CALC_BE_E` 和 `CALC_LV_ELITE` 各自维护独立网体，**不共享中间结果**。这符合“Elite Bonus 与 Elite 级别无关”的工程边界，但也意味着：

- 某会员在 `CALC_BE_E` 中被标记为 `ELITE_CALC_ID = 10`，并不代表他在 `CALC_LV_ELITE` 中一定是 Elite / PE / SE；
- 本过程的 `ELITE_CALC_ID` 更准确地说是“Elite Bonus 合格标记”，不是会员正式 Elite Level 的最终结算级别。

建议在后续字段命名或文档中区分：

| 字段/概念 | 建议解释 |
|---|---|
| `CALC_LV_ELITE.LAST_ELITE_CALC_ID` | 当月 Elite 三档级别评定结果 |
| `CALC_BE_E_NET.ELITE_CALC_ID` | 本过程内部 Elite Bonus 资格标记 |

---

## 7. 验收要点

建议测试用例至少覆盖以下场景。

### 7.1 基础计算类

1. **基础合格**：会员个人业绩 1000 BV，发奖 `1000 × 15% = 150`。
2. **累计合格**：会员自身 200 BV + 下线未合格贡献 800 BV = 1000 BV，会员合格发奖 150。
3. **截断验证**：会员合格后，其 GPV 不再继续向上贡献。
4. **连带合格**：会员 GPV 仅 200 BV，但下一层存在已合格 Elite，会员被标记为合格并按 200 BV 计奖。
5. **配置生效**：`AR_CONFIG.eliteRate` 从 15 改为 12 后，本期奖金按 12% 计算。
6. **截断精度**：若 `GPV_REAL × E_RATE` 出现三位以上小数，按 `TRUNCATE(..., 2)` 截断，不四舍五入。

### 7.2 字段口径类

7. **`PV_PCS / PV_PSS` 口径验证**：构造 `PV_PCS > 0` 但 `PV_PSS = 0`、以及 `PV_PCS = 0` 但 `PV_PSS > 0` 的数据，确认当前 SQL 实际纳入范围是否符合业务预期。
8. **零业绩**：用于过滤口径的 PV 字段为 0 时，不进入初始化网体。

### 7.3 来源溯源类

9. **来源归属是否为实际得奖人**：验证 `AR_CALC_BONUS_E_SOURCE.BONUS_USER_ID` 是否均存在于 `AR_CALC_BONUS_E.USER_ID`。
10. **`BONUS_LAYER` 排序语义**：构造多层链路，验证 `ORDER BY BONUS_LAYER ASC` 保留的是哪一层会员，并确认是否符合“最近得奖人”或“传播链最小层级归属”的业务要求。
11. **无合格上级场景**：A → B → C → D 全部不合格但有业绩一路上推，确认 `SOURCE` 表是否会生成归属记录；如生成，确认是否符合业务预期。

### 7.4 重跑与清理类

12. **同一期重跑**：不清理中间表直接重跑，观察是否产生重复记录或历史污染。
13. **跨期执行**：连续执行两个不同 `PERIOD_NUM`，确认中间表和正式表是否互相影响。

### 7.5 魔法数字类

14. **`ELITE_CALC_ID = 10` 约定验证**：确认当前 `AR_ELITE_LEVEL` 中 Elite 对应的 `CALC_ID` 是否确实为 10。
15. **编码变更影响评估**：模拟或评审级别编码调整时，确认 `CALC_BE_E` 是否在影响范围内。

---

## 附录 A：字段对照表

### A.1 `AR_CALC_BE_E_NET`

| 字段 | 含义 |
|---|---|
| `PERIOD_NUM` | 计算周期 |
| `CALC_MONTH` | 计算月份，来自 `AR_PERF_MONTH.CALC_MONTH` |
| `USER_ID` | 会员 ID |
| `PARENT_UID` | 推荐人 ID |
| `TOP_DEEP` | 推荐网层数；代码注释说明“网体越往下越大” |
| `GPV` | 当前节点累计小组业绩，含下线未合格节点向上贡献 |
| `GPV_REAL` | 本过程内部认定可用于 Elite Bonus 计奖的小组业绩；未合格时为 0 |
| `PV_PCS` | 个人业绩；当前 SQL 用其作为 GPV 初始值和奖金来源 PV |
| `ELITE_CALC_ID` | 本过程内部 Elite Bonus 合格标记；当前硬编码 0=未合格，10=合格 |
| `COUNTRY_ID` | 国家 / 地区 ID |

### A.2 `AR_CALC_BONUS_E_SOURCE`

| 字段 | 含义 |
|---|---|
| `PERIOD_NUM` / `CALC_MONTH` | 周期与月份，其中 `CALC_MONTH` 来自入参 `IV_CALC_MONTH` |
| `BONUS_USER_ID` / `BONUS_USER_NAME` / `BONUS_REAL_NAME` | 来源业绩被归属到的会员信息 |
| `SOURCE_USER_ID` / `SOURCE_USER_NAME` / `SOURCE_REAL_NAME` | 业绩来源会员信息 |
| `SOURCE_PV` | 来源会员的个人业绩 |
| `BONUS_LAYER` | 归属会员在推荐网中的层数；去重时按升序取第一条 |

---

## 附录 B：建议修改原文的重点段落

### B.1 原 §3.4 建议替换为

> `AR_CALC_BONUS_E_SOURCE` 中每个 `SOURCE_USER_ID` 按 `BONUS_LAYER` 升序仅保留一条记录，即 SQL 字面上的 `BONUS_LAYER` 最小记录。由于 `TOP_DEEP` / `BONUS_LAYER` 的数值越小通常越靠近网体上层，不能仅凭该排序直接断言其一定是“最靠近源头的得奖人”。若业务要求是“最近实际得奖人”，需进一步确认传播停止规则，并验证被保留的 `BONUS_USER_ID` 是否一定存在于 `AR_CALC_BONUS_E`。

### B.2 原 §5.2 第 2 点建议补充为

> `VV_CALC_MONTH = 202304` 声明后未被引用，但注释中出现 “2023.11.1 – 2024.4.30; Elite 附加奖励 100 eSAC，150 USD”。这可能导致读者误以为本过程已实现该历史特别奖励，或误以为 `IV_CALC_MONTH` / `VV_CALC_MONTH` 会控制特别奖励活动期。建议向原作者确认该注释是历史残留、其他过程已实现，还是未完成功能；确认后删除、迁移说明或补全需求与代码。

### B.3 原 §5.2 第 3 点建议替换为

> 本过程多处硬编码 `ELITE_CALC_ID = 10`，不读取 `AR_ELITE_LEVEL`。因此它虽然不依赖 `CALC_LV_ELITE` 的输出级别，但依赖 “10 表示 Elite” 的编码约定。如果 `AR_ELITE_LEVEL.CALC_ID` 编码方案调整，本过程不会自动跟随。建议将 10 抽成变量，或从级别配置表读取，并在级别编码变更 checklist 中加入 `CALC_BE_E`。
