---
name: redemption-sql-doc-map
description: >-
  Redemption 奖金结算项目里 sql_uat/ 存储过程与 Doc/ 需求文档的对应关系速查表。
  当你需要知道"某个 CALC_* 存储过程对应哪份需求文档""某个奖项（Elite / EAB / PE / SE / TB /
  Honor / Leadership 等）的规则文档在哪""哪些 SQL 还没写文档"，或在阅读、分析、对齐、补写
  Redemption 奖金 SQL 与文档时，先查本 skill 直接拿到映射，不必重新通读全部 SQL 和文档。
  与 redemption-file-filter 配合使用（那 8 个副本/旧版/废弃脚本不纳入本对应关系）。
---

# Redemption：`sql_uat/` 存储过程 ↔ `Doc/` 需求文档 对应速查

本表用于快速回答"某 SQL 对应哪份文档 / 某奖项文档在哪 / 哪些 SQL 还没转文档"。
映射依据：需求文档开头的自我声明（如「本文档基于存储过程 `CALC_BE_XXX`」）+ 文档引用的过程名/结果表 + 与 SQL 实际写入表交叉验证。

## 一、已转换：SQL → 正式需求 / 技术文档

| SQL（`sql_uat/`） | 奖项 / 功能 | 对应需求文档（`Doc/`） |
|---|---|---|
| `CALC_PV.sql` | 双轨制左右区业绩 1L/2L 基数 | `双轨制1L2L计算逻辑解析_修正版.md` |
| `CALC_BE_E.sql` | Elite Bonus（精英奖） | `CALC_BE_E_需求分析_修订建议版.md` |
| `CALC_BE_EAB.sql` | Elite Achievement Bonus（EAB） | `EAB_需求与重构规范_修正版.md` |
| `CALC_BE_PE.sql` | Pro Elite Bonus（PE 奖，15%） | `PE奖金_需求与技术实现文档_定稿.md` |
| `CALC_BE_SE_COUNTRY.sql` | Super Elite Bonus（SE 奖，按国家/大区均分） | `SuperEliteBonus_需求说明书_修订版.md` |
| `CALC_BE_TB.sql` | Team Bonus（团队奖，双轨对碰） | `团队奖金TB结算需求与技术规范说明书 (1).md` |
| `CALC_LV_HONOR_LAST.sql` + `CALC_LV_HONOR_HIGH.sql` | Honor 奖衔（当月判定 + 历史最高滚动） | `Honor Level奖金制度与结算引擎需求规格说明书.docx`；`奖金制度与结算引擎需求_最终版_代码严格对齐 (1).md` |
| `CALC_BE_LB_COUNTRY.sql` | Leadership Bonus（领导奖，大区 9 代 + 双重拦截） | `奖金制度与结算引擎需求_最终版_代码严格对齐 (1).md`（Leadership 章）；`Honor Level…说明书.docx` |
| `CALC_LV_ELITE.sql` | Elite / PE / SE 级别（rank）判定 | `Elite、PE、SE晋级规则.docx`（并作为 PE / SE / E / 最终版 文档的上游依赖） |

> `奖金制度与结算引擎需求_最终版_代码严格对齐 (1).md` 是跨奖项对齐文档，同时覆盖 Elite / Honor / Leadership 三块；主要对着 Python 服务写（`UserStatsService` / `HonorLevelGPUService` / `HonorLevelHighGPUService` / `LeadershipBonusGPUService`），业务口径对应上述 SQL。

## 二、业务规则文档（`.docx` 原始规则）对应的 SQL

这些 `.docx` 是业务侧原始规则（多数不含 SQL/表名引用），是上面需求文档的"来源规则"：

| 业务规则文档（`Doc/`） | 对应 SQL | 奖项 |
|---|---|---|
| `Elite_Bonus_发奖规则说明.docx` | `CALC_BE_E.sql` | Elite Bonus |
| `Elite Achievement Bonus (EAB) 奖金制度.docx` | `CALC_BE_EAB.sql` | EAB |
| `ProElite_Bonus_发奖规则 .docx` | `CALC_BE_PE.sql` | Pro Elite |
| `Super Elite Bonus（SE 奖金）_发奖规则.docx` | `CALC_BE_SE_COUNTRY.sql` | Super Elite |
| `Elite、PE、SE晋级规则.docx` | `CALC_LV_ELITE.sql` | 级别判定 |

> `新建 DOCX 文档.docx` 内容基本为空，无有效对应。

## 三、尚未转换的 SQL（暂无对应文档）

- **有奖项、缺文档**：`CALC_BE_CRB.sql`（CRB）、`CALC_BE_GPB.sql`（GPB）、`CALC_BE_PB.sql`（PB）、`CALC_BE_SFB.sql`（SFB 存货商奖）、`CALC_LV_ELITE_HIGHEST.sql`（历史最高 Elite 级别，仅被 E 文档提及）。
- **数据准备 / 网络 / 分摊**：`CALC_BE_REM_DATA.sql`（月度数据初始化）、`CALC_BE_NET.sql`（网络层数 `TOP_DEEP`）、`CALC_BE.sql`（得奖用户汇总 `AR_CALC_BONUS`）、`CALC_COUNTRY_SHARE.sql`、`CALC_COUNTRY_SHARE_LB.sql`。
- **调度 / 校验 / 状态 / 工具**：`AUTO_CALC_BONUS.sql`（调度+锁）、`CALC_BONUS.sql`（主编排入口）、`CALC_CHECK.sql`（自检）、`CALC_EFFECT.sql`（生效/续约）、`CALC_INACTIVE_DETAILS.sql`（不活跃明细）、`CALC_PERIOD_STATUS.sql`（周期状态）、`CALC_BACKUP.sql` / `CALC_BACKUP_COUNTRY_SHARE.sql`（备份）、`TABLE_COLUMN_COMMENT.sql` / `UPDATE_TABLE_COMMENT.sql`（注释工具）。

## 四、不纳入对应关系的文件（副本 / 旧版 / 废弃，直接排除）

以下 8 个由 `redemption-file-filter` 规则跳过，**不用考虑其对应文档**：

`CALC_BE_1.sql`、`CALC_BE_EAB_copy1.sql`、`CALC_BE_LB.sql`、`CALC_BE_REM_DATA_copy.sql`、`CALC_BONUS_copy.sql`、`CALC_BE_SE.sql`、`CALC_LV_HONOR_HIGH_copy.sql`、`CALC_LV_HONOR_HIGH_V1.sql`

## 用法

- 被问"这个存储过程/这个奖项的文档在哪"→ 查第一、二节。
- 被问"哪些 SQL 还没文档 / 该补哪些"→ 查第三节。
- 遇到第四节那 7 个文件 → 跳过，不读也不对应文档。
- 若映射与实际不符（例如新增/重命名了 SQL 或文档），以仓库现状为准并提示更新本表。