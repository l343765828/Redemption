---
name: redemption-file-filter
description: >-
  Redemption 奖金结算项目的"文件跳过"规则：明确列出不用读取的过时备份 / 副本 / 旧版本文件。
  每当你准备 Read / Glob / Grep / Explore，或以任何方式阅读、检索、分析 D:\Redemption 下的代码
  （尤其是 sql_uat/、User/）时，先用本 skill 把这些文件排除掉——不用读进上下文，也不要当成事实来源。
---

# Redemption 代码库：不用读取的文件

阅读、检索、分析 Redemption 项目代码时，以下文件是过时的备份 / 副本 / 旧版本，**不用读取，直接跳过**。

## 规则一：文件名含 `_bak` 或 `_final` 的，不用读取

只要文件名里带有 `_bak`、`_bakN`（如 `_bak2`、`_bak3`）或 `_final`，一律跳过。

## 规则二：`sql_uat/` 下这几个脚本，不用读取

- `sql_uat/CALC_BE_1.sql`
- `sql_uat/CALC_BE_EAB_copy1.sql`
- `sql_uat/CALC_BE_LB.sql`
- `sql_uat/CALC_BE_REM_DATA_copy.sql`
- `sql_uat/CALC_BONUS_copy.sql`
- `sql_uat/CALC_LV_HONOR_HIGH_copy.sql`
- `sql_uat/CALC_LV_HONOR_HIGH_V1.sql`

## 例外

如果用户明确要求查看上述某个文件本身，照做即可——本规则只约束"默认的扫描 / 阅读 / 分析"行为。