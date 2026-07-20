import unittest
import pandas as pd
import numpy as np
import dask.dataframe as dd
from decimal import Decimal
import logging
import warnings
from User.SuperEliteBonusService import SuperEliteBonusService

# 关闭底层警告日志输出，保持测试控制台整洁
logging.getLogger("User.SuperEliteBonusService").setLevel(logging.CRITICAL)


class SuperEliteBonusServiceTest(unittest.TestCase):
    """
    Super Elite Bonus 结算引擎全场景自动化测试用例 (100% 覆盖终极版)
    """

    def setUp(self):
        """初始化标准的 Happy Path 基础数据"""
        self.service = SuperEliteBonusService()
        self.period = 202310
        self.calc_month = 10

        # 忽略底层的 dtype 警告 (如 str vs string)
        warnings.simplefilter('ignore', category=UserWarning)

        self.base_config = pd.DataFrame({
            "config_name": ["superEliteRate"], "value": ["10"], "type": ["bonus"]
        })
        self.base_user_info = pd.DataFrame({
            'id': ['U001', 'U002'], 'country_id': ['TW', 'TW']
        })
        self.base_elite = pd.DataFrame({
            'user_id': ['U001', 'U002'], 'period_num': [self.period] * 2,
            'calc_month': [self.calc_month] * 2, 'rank': [30, 30]
        })
        self.base_orders = pd.DataFrame({
            'period_num': [self.period], 'country_id': ['TW'], 'pv': [1000.00]
        })
        self.base_perf = pd.DataFrame({
            'user_id': ['U001', 'U002'], 'is_active': [1, 1]
        })

    def _build_dask(self, pdf: pd.DataFrame, npartitions=1) -> dd.DataFrame:
        """辅助方法：将 pandas 转换为 cpu dask dataframe"""
        return dd.from_pandas(pdf, npartitions=npartitions)

    # =====================================================================
    # 1. 正常业务场景 (Happy Path & Robustness)
    # =====================================================================

    def test_tc1_1_single_country_all_active(self):
        """TC-1.1 单一国家全活跃发放"""
        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(self.base_elite),
            self._build_dask(self.base_orders), self._build_dask(self.base_perf),
            self.base_config, self.base_user_info
        ).compute()

        self.assertEqual(len(res_df), 2, "应生成2条奖金记录")
        self.assertTrue((res_df['bonus_se'].map(Decimal) == Decimal('50.00')).all(), "人均奖金计算错误")
        self.assertTrue((res_df['is_active'] == 1).all(), "活跃状态标识错误")
        self.assertTrue((res_df['bonus_country'] == 'TW').all(), "大区标识错误")

        # 断言期数与月份的字符串类型输出
        for _, row in res_df.iterrows():
            self.assertIsInstance(row['period_num'], str, "period_num 必须为字符串")
            self.assertIsInstance(row['calc_month'], str, "calc_month 必须为字符串")

    def test_tc1_2_multi_country_merge(self):
        """TC-1.2 多国合并大区计算 (MY, SG, BN -> MY)"""
        config = pd.DataFrame({
            "config_name": ["superEliteRate", "CountryMY", "CountrySG", "CountryBN"],
            "value": ["10", "MY", "MY", "MY"], "type": ["bonus", "bonus", "bonus", "bonus"]
        })
        user_info = pd.DataFrame({'id': ['U001', 'U002', 'U003'], 'country_id': ['MY', 'SG', 'BN']})
        elite = pd.DataFrame({
            'user_id': ['U001', 'U002', 'U003'], 'period_num': [self.period] * 3,
            'calc_month': [self.calc_month] * 3, 'rank': [30, 30, 30]
        })
        orders = pd.DataFrame(
            {'period_num': [self.period] * 3, 'country_id': ['MY', 'SG', 'BN'], 'pv': [1000, 2000, 0]})
        perf = pd.DataFrame({'user_id': ['U001', 'U002', 'U003'], 'is_active': [1, 1, 1]})

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(orders),
            self._build_dask(perf), config, user_info
        ).compute()

        self.assertEqual(len(res_df), 3, "应生成3条合并大区记录")
        self.assertTrue((res_df['bonus_se'].map(Decimal) == Decimal('100.00')).all(), "合并大区人均奖金错误")
        self.assertTrue((res_df['bonus_country'] == 'MY').all(), "大区标识未统一转换为 MY")

    def test_tc1_3_silent_filter_non_se(self):
        """TC-1.3 非 SE 会员静默过滤"""
        elite = self.base_elite.copy()
        # 加入 3 名 rank=20 的非 SE 会员
        elite.loc[2] = ['U003', self.period, self.calc_month, 20]
        elite.loc[3] = ['U004', self.period, self.calc_month, 20]
        elite.loc[4] = ['U005', self.period, self.calc_month, 20]
        user_info = pd.DataFrame(
            {'id': ['U001', 'U002', 'U003', 'U004', 'U005'], 'country_id': ['TW', 'TW', 'TW', 'TW', 'TW']})
        perf = pd.DataFrame({'user_id': ['U001', 'U002', 'U003', 'U004', 'U005'], 'is_active': [1, 1, 1, 1, 1]})

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(self.base_orders),
            self._build_dask(perf), self.base_config, user_info
        ).compute()

        self.assertEqual(len(res_df), 2, "rank=20 的会员应被静默过滤")

    def test_tc1_4_multi_partition_and_id_uniqueness(self):
        """TC-1.4 分布式多分区计算与生成的 ID 唯一性验证"""
        # 生成稍大的数据，分布到 2 个 Partition
        elite = pd.DataFrame({
            'user_id': [f'U{str(i).zfill(3)}' for i in range(1, 11)],
            'period_num': [self.period] * 10, 'calc_month': [self.calc_month] * 10, 'rank': [30] * 10
        })
        user_info = pd.DataFrame({
            'id': [f'U{str(i).zfill(3)}' for i in range(1, 11)], 'country_id': ['TW'] * 10
        })
        perf = pd.DataFrame({
            'user_id': [f'U{str(i).zfill(3)}' for i in range(1, 11)], 'is_active': [1] * 10
        })

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite, npartitions=2),
            self._build_dask(self.base_orders, npartitions=2), self._build_dask(perf, npartitions=2),
            self.base_config, user_info
        ).compute()

        self.assertEqual(len(res_df), 10)
        self.assertTrue(res_df['id'].is_unique, "多分区生成的明细 ID 必须保证全局唯一")

    def test_tc1_5_case_and_space_normalization(self):
        """TC-1.5 强健性验证：大小写混杂与前后空格自适应归一"""
        elite = pd.DataFrame(
            {'user_id': [' u001  '], 'period_num': [self.period], 'calc_month': [self.calc_month], 'rank': [30]})
        orders = pd.DataFrame({'period_num': [self.period], 'country_id': [' tw '], 'pv': [1000]})
        user_info = pd.DataFrame({'id': ['U001'], 'country_id': ['Tw']})
        perf = pd.DataFrame({'user_id': ['u001'], 'is_active': [1]})

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(orders),
            self._build_dask(perf), self.base_config, user_info
        ).compute()

        self.assertEqual(len(res_df), 1)
        self.assertEqual(res_df.iloc[0]['bonus_country'], 'TW', "底层应该自动完成剔除空格和转换大写")

    # =====================================================================
    # 2. 核心业务规则 (Business Logic Edge Cases)
    # =====================================================================

    def test_tc2_1_inactive_users_in_denominator(self):
        """TC-2.1 不活跃会员参与分母平分"""
        elite = pd.DataFrame({
            'user_id': ['U001', 'U002', 'U003'], 'period_num': [self.period] * 3,
            'calc_month': [self.calc_month] * 3, 'rank': [30, 30, 30]
        })
        user_info = pd.DataFrame({'id': ['U001', 'U002', 'U003'], 'country_id': ['TW', 'TW', 'TW']})
        perf = pd.DataFrame({'user_id': ['U001', 'U002', 'U003'], 'is_active': [1, 0, 1]})  # U002 不活跃
        orders = pd.DataFrame({'period_num': [self.period], 'country_id': ['TW'], 'pv': [3000]})

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(orders),
            self._build_dask(perf), self.base_config, user_info
        ).compute()

        self.assertEqual(len(res_df), 3, "不活跃会员不应被踢出分母")
        self.assertTrue((res_df['bonus_se'].map(Decimal) == Decimal('100.00')).all())

        # 验证不活跃标识
        inactive_record = res_df[res_df['user_id'] == 'U002']
        self.assertEqual(inactive_record.iloc[0]['is_active'], 0)

    def test_tc2_2_truncation_precision(self):
        """TC-2.2 计算精度向下截断"""
        elite = pd.DataFrame({
            'user_id': ['U001', 'U002', 'U003'], 'period_num': [self.period] * 3,
            'calc_month': [self.calc_month] * 3, 'rank': [30, 30, 30]
        })
        user_info = pd.DataFrame({'id': ['U001', 'U002', 'U003'], 'country_id': ['TW', 'TW', 'TW']})
        perf = pd.DataFrame({'user_id': ['U001', 'U002', 'U003'], 'is_active': [1, 1, 1]})

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(self.base_orders),
            self._build_dask(perf), self.base_config, user_info
        ).compute()

        self.assertTrue((res_df['bonus_se'].map(Decimal) == Decimal('33.33')).all(), "向下截断计算错误")

    def test_tc2_3a_global_no_se(self):
        """TC-2.3a 全局无 SE 会员提前返回空"""
        elite = self.base_elite.copy()
        elite['rank'] = 20
        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(self.base_orders),
            self._build_dask(self.base_perf), self.base_config, self.base_user_info
        ).compute()
        self.assertEqual(len(res_df), 0, "全局无 SE 应返回空结果集")

    def test_tc2_3b_specific_region_no_se_skipped(self):
        """TC-2.3b 特定大区无 SE 会员被跳过"""
        elite = pd.DataFrame(
            {'user_id': ['U001'], 'period_num': [self.period], 'calc_month': [self.calc_month], 'rank': [30]})
        orders = pd.DataFrame({'period_num': [self.period] * 2, 'country_id': ['TW', 'MY'], 'pv': [1000, 2000]})
        user_info = pd.DataFrame({'id': ['U001'], 'country_id': ['TW']})
        perf = pd.DataFrame({'user_id': ['U001'], 'is_active': [1]})

        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(elite), self._build_dask(orders),
            self._build_dask(perf), self.base_config, user_info
        ).compute()

        self.assertEqual(len(res_df), 1, "MY大区无SE，该大区业绩应该被静默丢弃")
        self.assertEqual(res_df.iloc[0]['bonus_country'], 'TW')
        self.assertEqual(Decimal(res_df.iloc[0]['bonus_se']), Decimal('100.00'),
                         "TW大区应正确计算出100.00奖金(不受MY影响)")

    def test_tc2_3c_empty_elite_dataframe(self):
        """TC-2.3c 评级底表完全为空 (连列头都无数据的物理空表)"""
        empty_elite = pd.DataFrame(columns=['user_id', 'period_num', 'calc_month', 'rank'])
        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(empty_elite), self._build_dask(self.base_orders),
            self._build_dask(self.base_perf), self.base_config, self.base_user_info
        ).compute()
        self.assertEqual(len(res_df), 0, "空表直接触发 warning 并返回结果")

    def test_tc2_4_zero_pv_filtered(self):
        """TC-2.4 无有效业绩 (PV=0) 被直接剔除"""
        orders = pd.DataFrame({'period_num': [self.period], 'country_id': ['TW'], 'pv': [0]})
        res_df = self.service.calculate_se_bonus(
            self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(orders),
            self._build_dask(self.base_perf), self.base_config, self.base_user_info
        ).compute()
        self.assertEqual(len(res_df), 0, "PV为0的奖金记录应被剔除不写入")

    # =====================================================================
    # 3. 配置拦截与校验 (Configuration Validation)
    # =====================================================================

    def test_tc3_1_missing_rate_config(self):
        """TC-3.1 奖金拨出比例缺失"""
        config = pd.DataFrame({"config_name": ["otherConfig"], "value": ["10"], "type": ["bonus"]})
        with self.assertRaisesRegex(ValueError, r"\[阻断\] df_config 中 superEliteRate\(type='bonus'\) 配置缺失"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), config, self.base_user_info
            )

    def test_tc3_2_duplicate_rate_config(self):
        """TC-3.2 奖金拨出比例重复"""
        config = pd.DataFrame({
            "config_name": ["superEliteRate", "superEliteRate"],
            "value": ["10", "15"], "type": ["bonus", "bonus"]
        })
        with self.assertRaisesRegex(ValueError, r"\[阻断\] superEliteRate 配置不唯一"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), config, self.base_user_info
            )

    def test_tc3_3a_invalid_rate_value_string(self):
        """TC-3.3a 比例数值非法 (空串/乱码)"""
        for invalid_val in ["abc", ""]:
            with self.subTest(invalid_val=invalid_val):
                config = pd.DataFrame({"config_name": ["superEliteRate"], "value": [invalid_val], "type": ["bonus"]})
                with self.assertRaisesRegex(ValueError, r"\[阻断\] superEliteRate 的 value 不是合法数值"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite),
                        self._build_dask(self.base_orders),
                        self._build_dask(self.base_perf), config, self.base_user_info
                    )

    def test_tc3_3b_missing_rate_value_nan(self):
        """TC-3.3b 比例数值缺失 (None/NaN)"""
        for missing_val in [None, np.nan, pd.NA, float('nan')]:
            with self.subTest(missing_val=missing_val):
                config = pd.DataFrame({"config_name": ["superEliteRate"], "value": [missing_val], "type": ["bonus"]})
                with self.assertRaisesRegex(ValueError, r"\[阻断\] superEliteRate 配置缺失 value 值"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite),
                        self._build_dask(self.base_orders),
                        self._build_dask(self.base_perf), config, self.base_user_info
                    )

    def test_tc3_3c_rate_value_negative_or_zero(self):
        """TC-3.3c 比例置零或负数防线拦截"""
        for bad_rate in ["0", "-10", "0.0"]:
            with self.subTest(bad_rate=bad_rate):
                config = pd.DataFrame({"config_name": ["superEliteRate"], "value": [bad_rate], "type": ["bonus"]})
                with self.assertRaisesRegex(ValueError, r"\[阻断\] superEliteRate 拨出比例必须大于0"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite),
                        self._build_dask(self.base_orders),
                        self._build_dask(self.base_perf), config, self.base_user_info
                    )

    def test_tc3_4_missing_self_mapping(self):
        """TC-3.4 大区映射主国缺失自身映射 (全局体检拦截)"""
        config = pd.DataFrame({
            "config_name": ["superEliteRate", "CountrySG"], "value": ["10", "MY"], "type": ["bonus", "bonus"]
        })
        with self.assertRaisesRegex(ValueError, r"\[阻断\] 目标大区主国未自映射"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), config, self.base_user_info
            )

    def test_tc3_5_country_type_not_bonus(self):
        """TC-3.5 大区映射 TYPE 字段非法"""
        config = pd.DataFrame({
            "config_name": ["superEliteRate", "CountrySG", "CountryMY"],
            "value": ["10", "MY", "MY"], "type": ["bonus", "other", "bonus"]
        })
        with self.assertRaisesRegex(ValueError, r"\[阻断\] 存在 TYPE 非 'bonus' 的大区映射配置"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), config, self.base_user_info
            )

    def test_tc3_6a_duplicate_mapping_definition(self):
        """TC-3.6a 映射配置存在重复定义 (同名 config_name)"""
        config = pd.DataFrame({
            "config_name": ["superEliteRate", "CountrySG", "CountrySG", "CountryMY"],
            "value": ["10", "MY", "MY", "MY"], "type": ["bonus", "bonus", "bonus", "bonus"]
        })
        with self.assertRaisesRegex(ValueError, r"\[阻断\] Country 映射配置存在重复定义"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), config, self.base_user_info
            )

    def test_tc3_6b_duplicate_source_country_parsing(self):
        """TC-3.6b 解析后存在重复源国家 (大小写变体)"""
        config = pd.DataFrame({
            "config_name": ["superEliteRate", "CountrySG", "Countrysg", "CountryMY"],
            "value": ["10", "MY", "MY", "MY"], "type": ["bonus", "bonus", "bonus", "bonus"]
        })
        with self.assertRaisesRegex(ValueError, r"\[阻断\] Country 映射解析后存在重复源国家"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), config, self.base_user_info
            )

    # =====================================================================
    # 4. 数据完整性与防重限制 (Data Integrity)
    # =====================================================================

    def test_tc4_1_mixed_periods_in_elite(self):
        """TC-4.1 评级底表混入多期数据"""
        elite = self.base_elite.copy()
        elite.loc[2] = ['U003', 202309, 9, 30]  # 混入上一期数据
        with self.assertRaisesRegex(ValueError, r"\[阻断\] 评级数据源混入了多期数据"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), self.base_config, self.base_user_info
            )

    def test_tc4_2_input_period_mismatch(self):
        """TC-4.2 输入期数与数据实际期数错位"""
        with self.assertRaisesRegex(ValueError, r"\[阻断\] 传入期数.*与数据期数.*严重错位"):
            self.service.calculate_se_bonus(
                202311, 11, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), self.base_config, self.base_user_info
            )

    def test_tc4_3_duplicate_perf_rows(self):
        """TC-4.3 活跃状态表存在多行记录"""
        perf = pd.DataFrame({'user_id': ['U001', 'U002', 'U001'], 'is_active': [1, 1, 0]})
        with self.assertRaisesRegex(ValueError, r"\[阻断\] AR_USER_PERF 存在单用户多行记录"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(perf), self.base_config, self.base_user_info
            )

    def test_tc4_4a_user_info_null_fields(self):
        """TC-4.4a 维表基础数据物理空缺拦截 (id 或 country_id 为 None)"""
        test_cases = [
            ({'id': ['U001', 'U002'], 'country_id': ['TW', None]}, "country_id为空"),
            ({'id': [None, 'U002'], 'country_id': ['TW', 'TW']}, "id为空")
        ]
        for ui_dict, desc in test_cases:
            with self.subTest(desc=desc):
                with self.assertRaisesRegex(ValueError, r"\[阻断\] df_user_info 维表中发现 .* 行的 ID/国籍为空"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite),
                        self._build_dask(self.base_orders),
                        self._build_dask(self.base_perf), self.base_config, pd.DataFrame(ui_dict)
                    )

    def test_tc4_4b_user_info_invalid_string_tokens(self):
        """TC-4.4b 维表基础数据非法字符拦截 ("null", "nan", "")"""
        invalid_tokens = ["", "null", "nan", "NA", "None"]

        # 1. 测试 country_id 字段非法
        for token in invalid_tokens:
            with self.subTest(field="country_id", token=token):
                ui = pd.DataFrame({'id': ['U001', 'U002'], 'country_id': ['TW', token]})
                with self.assertRaisesRegex(ValueError, r"\[阻断\] df_user_info 维表中存在国籍或ID为非法无效字符串"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite),
                        self._build_dask(self.base_orders),
                        self._build_dask(self.base_perf), self.base_config, ui
                    )

        # 2. 测试 id 字段非法
        for token in invalid_tokens:
            with self.subTest(field="id", token=token):
                ui = pd.DataFrame({'id': ['U001', token], 'country_id': ['TW', 'TW']})
                with self.assertRaisesRegex(ValueError, r"\[阻断\] df_user_info 维表中存在国籍或ID为非法无效字符串"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite),
                        self._build_dask(self.base_orders),
                        self._build_dask(self.base_perf), self.base_config, ui
                    )

    def test_tc4_4c_missing_se_in_user_info(self):
        """TC-4.4c SE 会员在维表中缺失"""
        user_info = pd.DataFrame({'id': ['U001'], 'country_id': ['TW']})  # U002 缺失
        with self.assertRaisesRegex(ValueError, r"\[阻断\] 发现 .* 名 SE 会员在维表中未能匹配到国籍"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), self.base_config, user_info
            )

    def test_tc4_5_duplicate_id_in_user_info(self):
        """TC-4.5 用户维表存在重复 ID"""
        user_info = pd.DataFrame({'id': ['U001', 'U002', 'U001'], 'country_id': ['TW', 'TW', 'SG']})
        with self.assertRaisesRegex(ValueError, r"\[阻断\] df_user_info 维表存在重复 ID"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), self.base_config, user_info
            )

    def test_tc4_6_invalid_pv_in_target_period(self):
        """TC-4.6 目标期订单底表 PV 异常 (乱码 或 NaN)"""
        invalid_pvs = ['NAN_STRING', np.nan, pd.NA, float('nan')]
        for pv in invalid_pvs:
            with self.subTest(pv=pv):
                orders = pd.DataFrame({'period_num': [self.period], 'country_id': ['TW'], 'pv': [pv]})
                with self.assertRaisesRegex(ValueError, r"\[阻断\] 订单底表存在非数值或不可解析的 PV"):
                    self.service.calculate_se_bonus(
                        self.period, self.calc_month, self._build_dask(self.base_elite), self._build_dask(orders),
                        self._build_dask(self.base_perf), self.base_config, self.base_user_info
                    )

    def test_tc4_7_duplicate_se_user_in_elite(self):
        """TC-4.7 同一 SE 用户在评级表中出现多行 (防污染分母阻断)"""
        elite = pd.DataFrame({
            'user_id': ['U001', 'U001'], 'period_num': [self.period] * 2,
            'calc_month': [self.calc_month] * 2, 'rank': [30, 30]
        })
        with self.assertRaisesRegex(ValueError, r"\[阻断\] 评级结果存在同一 SE 用户多行，严重污染分母"):
            self.service.calculate_se_bonus(
                self.period, self.calc_month, self._build_dask(elite), self._build_dask(self.base_orders),
                self._build_dask(self.base_perf), self.base_config, self.base_user_info
            )


if __name__ == '__main__':
    unittest.main(verbosity=2)