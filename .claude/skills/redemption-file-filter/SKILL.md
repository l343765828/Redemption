---
name: redemption-file-filter
description: >-
  Redemption 奖金结算项目的"文件跳过 + 业务查证"规则集：① 明确列出不用读取的过时备份 / 副本 /
  旧版本 / 废弃文件；② `run_bfs` 不纳入默认阅读与评审；③ 不确定的业务口径先从有效 sql_uat/ 脚本查证。
  每当你准备 Read / Glob / Grep / Explore、做代码审查 / 迁移检查，或需要确认某段奖金业务逻辑 /
  计算口径 / 字段含义时，先用本 skill：把已排除文件挡在上下文外，并遵循"先 sql_uat 查证、
  查不到就交业务方确认"的裁决顺序，分析 D:\Redemption 下的代码（尤其 sql_uat/、User/）时始终适用。
---

# Redemption 代码库：文件跳过与业务查证规则

阅读、检索、分析 Redemption 项目代码时，以下文件是过时的备份 / 副本 / 旧版本 / 废弃脚本，**不用读取，直接跳过**。

## 规则一：文件名含 `_bak` 或 `_final` 的，不用读取

只要文件名里带有 `_bak`、`_bakN`（如 `_bak2`、`_bak3`）或 `_final`，一律跳过。

## 规则二：`sql_uat/` 下这几个脚本，不用读取

- `sql_uat/CALC_BE_1.sql`
- `sql_uat/CALC_BE_EAB_copy1.sql`
- `sql_uat/CALC_BE_LB.sql`
- `sql_uat/CALC_BE_REM_DATA_copy.sql`
- `sql_uat/CALC_BE_SE.sql`
- `sql_uat/CALC_BONUS_copy.sql`
- `sql_uat/CALC_LV_HONOR_HIGH_copy.sql`
- `sql_uat/CALC_LV_HONOR_HIGH_V1.sql`

## 规则三：`run_bfs` 不纳入默认阅读和评审范围

- 默认不要读取、检索、分析或评审 `GraphService.run_bfs` 的实现。
- 搜索 `GraphService.py` 时，避免把 `run_bfs` 函数体读入上下文或作为项目当前业务逻辑的事实来源。
- `run_bfs` 中的问题不计入默认代码审查、迁移检查或验收结论。

## 规则四：不确定的业务问题先从 `sql_uat/` 查证

遇到无法仅凭已确认规则判断的业务逻辑、计算口径、边界条件或字段含义时，按以下顺序处理：

1. 先在 `sql_uat/` 中搜索和核对相关逻辑；搜索时仍须遵守规则一、规则二，不能把已排除的备份、
   副本、旧版本或废弃 SQL 当作依据。
2. 如果有效 SQL 中存在能够直接确认该业务规则的证据：
   - 给出确认后的结论；
   - 明确告诉用户依据来自哪个 `sql_uat/*.sql` 文件；
   - 可定位时，同时说明对应的存储过程、代码段或关键语句。
3. 如果有效 SQL 中没有找到直接证据，或者不同有效 SQL 的含义仍然冲突、存在歧义：
   - 明确告诉用户未能从 `sql_uat/` 确认；
   - 准确列出需要业务方确认的具体问题；
   - 不得自行猜测、补造规则，或把 Python 当前实现反向当成业务事实。

`Doc/` 和 Python 代码可以用于理解上下文、定位实现和发现差异，但对于尚未确认的业务问题，不能替代
有效 `sql_uat/` 脚本成为最终业务依据。

## 例外

如果用户明确要求查看上述某个文件本身，照做即可——本规则只约束"默认的扫描 / 阅读 / 分析"行为。