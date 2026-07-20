import logging
import time
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import dask.dataframe as dd
import pandas as pd
from typing import Any

logger = logging.getLogger("User.SuperEliteBonusService")

# 统一的"非法/空"字符串集合（小写）
_INVALID_STR_TOKENS = {"none", "nan", "null", "na", ""}


class SuperEliteBonusService:
    """
    Super Elite Bonus（超级精英奖）单期奖金明细计算服务。

    =======================================================================
    架构：纯计算引擎（Pure Calculation Engine）
    =======================================================================
    本服务不持有 config_service / user_info_service 等任何外部 I/O 依赖。
    所有前置数据均由调用方备好后以 DataFrame 注入：
        - ddf_elite_users : CPU dask.DataFrame，需含 user_id, period_num, calc_month, rank (30 = Super Elite)
        - ddf_orders      : CPU dask.DataFrame，需含 period_num, country_id, pv
        - ddf_user_perf   : CPU dask.DataFrame，需含 user_id, is_active（单用户单行）
        - df_config       : 需含 config_name, value, type（即 AR_CONFIG 快照）
        - df_user_info    : 需含 id, country_id（用户维表快照）
    """

    _COUNTRY_PREFIX_LEN = len("Country")

    def __init__(self):
        pass

    # =====================================================================
    # 入参适配与通用工具
    # =====================================================================
    @staticmethod
    def _to_local_pandas(df, name: str) -> pd.DataFrame:
        if hasattr(df, "result"):
            df = df.result()
        if hasattr(df, "compute"):
            df = df.compute()
        if hasattr(df, "to_pandas"):
            df = df.to_pandas()
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
            except Exception:
                raise ValueError(f"[阻断] {name} 无法转换为 pandas.DataFrame。")
        return df

    @staticmethod
    def _assert_cpu_dask(df, name: str) -> None:
        if not hasattr(df, "map_partitions") or not hasattr(df, "_meta"):
            raise ValueError(f"[阻断] {name} 不是 dask.DataFrame；本服务要求 CPU dask.DataFrame 输入。")
        meta_module = type(df._meta).__module__
        if "cudf" in meta_module or "cupy" in meta_module:
            raise ValueError(
                f"[阻断] {name} 是 GPU(dask_cudf/cudf) 对象，本服务为 CPU dask 实现；请先转为 CPU dask。"
            )

    @staticmethod
    def _lower_columns(df, name: str):
        df = df.rename(columns=str.lower)
        cols = pd.Index(df.columns)
        dup = cols[cols.duplicated()].tolist()
        if dup:
            raise ValueError(f"[阻断] {name} 列名小写归一后出现重复列: {dup}。")
        return df

    @staticmethod
    def _normalize_id_series(s):
        return s.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()

    @staticmethod
    def _require_config_cols(df_cfg: pd.DataFrame, name: str) -> None:
        required = {"config_name", "value", "type"}
        missing = required - set(df_cfg.columns)
        if missing:
            raise ValueError(f"[阻断] {name} 缺失必需字段: {sorted(missing)}")

    def _empty_result_df(self) -> dd.DataFrame:
        empty_df = pd.DataFrame(columns=[
            'id', 'period_num', 'calc_month', 'user_id',
            'bonus_se', 'country_id', 'is_active', 'bonus_country'
        ])
        return dd.from_pandas(empty_df, npartitions=1)

    # =====================================================================
    # 配置解析
    # =====================================================================
    def _parse_se_rate(self, df_config) -> Decimal:
        df_cfg = self._lower_columns(self._to_local_pandas(df_config, "df_config").copy(), "df_config")
        self._require_config_cols(df_cfg, "df_config")

        # region 获取配置名字和类型
        name_norm = df_cfg['config_name'].astype(str).str.strip()
        type_norm = df_cfg['type'].astype(str).str.strip().str.lower()
        # endregion

        # 筛选出汇率
        df_rate = df_cfg[(name_norm == 'superEliteRate') & (type_norm == 'bonus')]

        # region 验证
        if df_rate.empty:
            raise ValueError("[阻断] df_config 中 superEliteRate(type='bonus') 配置缺失")
        if len(df_rate) > 1:
            raise ValueError(f"[阻断] superEliteRate 配置不唯一，当前行数: {len(df_rate)}")
        # endregion

        # 获取数据
        value = df_rate.iloc[0]['value']

        # region 验证
        if value is None or pd.isna(value):
            raise ValueError("[阻断] superEliteRate 配置缺失 value 值")
        # endregion

        # region 转成decimal
        try:
            rate_val = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError(f"[阻断] superEliteRate 的 value 不是合法数值: {value!r}")
        if rate_val <= 0:
            raise ValueError(f"[阻断] superEliteRate 拨出比例必须大于0，当前值: {rate_val}")
        # endregion

        return rate_val / Decimal('100')

    def _parse_country_mapping(self, df_config) -> pd.DataFrame:
        df_cfg = self._lower_columns(self._to_local_pandas(df_config, "df_config").copy(), "df_config")
        self._require_config_cols(df_cfg, "df_config")

        # region 获取名称和类型
        df_cfg['__name'] = df_cfg['config_name'].astype(str).str.strip()
        df_cfg['__type'] = df_cfg['type'].astype(str).str.strip().str.lower()
        # endregion

        # region 创造df_country -> 从df_cfg筛选出来
        is_country = df_cfg['__name'].str.lower().str.startswith('country')
        df_country = df_cfg[is_country].copy()
        # endregion

        # region 验证
        if df_country.empty:
            return pd.DataFrame(columns=['source_country_id', 'region_default_id'])

        too_short = df_country['__name'].str.len() <= self._COUNTRY_PREFIX_LEN
        if too_short.any():
            bad = df_country.loc[too_short, '__name'].tolist()
            raise ValueError(f"[阻断] Country 配置名非法或过短: {bad}")

        bad_types = df_country[df_country['__type'] != 'bonus']
        if not bad_types.empty:
            raise ValueError(f"[阻断] 存在 TYPE 非 'bonus' 的大区映射配置:\n{bad_types['__name'].tolist()}")

        dup_names = df_country.loc[df_country['__name'].duplicated(), '__name'].tolist()
        if dup_names:
            raise ValueError(f"[阻断] Country 映射配置存在重复定义: {dup_names}")
        # endregion

        mapping = []
        target_regions = set()

        # region 创造df_mapping -> df_country
        for _, row in df_country.iterrows():
            config_name = row['__name']
            source_country = config_name[self._COUNTRY_PREFIX_LEN:].strip().upper()
            target_region = str(row['value']).strip().upper()

            # region 验证
            if not source_country or source_country.lower() in _INVALID_STR_TOKENS:
                raise ValueError(f"[阻断] 解析后源国家ID非法或为空: {config_name} -> {source_country}")
            if not target_region or target_region.lower() in _INVALID_STR_TOKENS:
                raise ValueError(f"[阻断] 目标大区 value 非法或为空: {target_region}")
            # endregion

            mapping.append({"source_country_id": source_country, "region_default_id": target_region})
            target_regions.add(target_region)

        df_mapping = pd.DataFrame(mapping, columns=['source_country_id', 'region_default_id'])
        # endregion

        # region 验证
        if df_mapping['source_country_id'].duplicated().any():
            duplicates = df_mapping[df_mapping['source_country_id'].duplicated()]['source_country_id'].tolist()
            raise ValueError(f"[阻断] Country 映射解析后存在重复源国家（含大小写变体）: {duplicates}")
        # endregion

        # region 将df_mapping转成字典
        mapping_dict = dict(zip(df_mapping['source_country_id'], df_mapping['region_default_id']))
        # endregion

        # region 验证
        bad_self_maps = [region for region in target_regions if mapping_dict.get(region) != region]
        if bad_self_maps:
            raise ValueError(
                f"[阻断] 目标大区主国未自映射: {bad_self_maps}。\n"
                f"该配置缺失将导致旧 SQL 引擎计算大区金额时漏掉主国订单，必须补充配置（例如 CountryMY=MY）。"
            )
        # endregion

        return df_mapping

    # =====================================================================
    # 主入口
    # =====================================================================
    def calculate_se_bonus(
        self,
        period: Any,
        calc_month: Any,
        ddf_elite_users: dd.DataFrame,
        ddf_orders: dd.DataFrame,
        ddf_user_perf: dd.DataFrame,
        df_config: pd.DataFrame,
        df_user_info: pd.DataFrame,
    ) -> dd.DataFrame:
        """
        计算单期 Super Elite Bonus 明细。

        由于底层数据模型 UserStats 已经严格定义了级别字段为 rank，
        因此本引擎直接且仅依赖 rank 列（30 = Super Elite）进行资格判定。
        """

        # region 获取期数、月数
        try:
            period_int = int(period)
            calc_month_int = int(calc_month)
        except (ValueError, TypeError):
            raise ValueError(f"[阻断] period 或 calc_month 参数无法转换为整数: {period}, {calc_month}")
        # endregion

        # region 获取汇率和国家信息
        se_rate = self._parse_se_rate(df_config)
        country_mapping = self._parse_country_mapping(df_config)
        # endregion

        # ==========================================
        # Step 0.1: 入口后端校验与必需字段强校验
        # ==========================================
        # region 数据验证
        self._assert_cpu_dask(ddf_elite_users, "ddf_elite_users(评级底表)")
        self._assert_cpu_dask(ddf_orders, "ddf_orders(订单底表)")
        self._assert_cpu_dask(ddf_user_perf, "ddf_user_perf(活跃底表)")

        ddf_elite_users = self._lower_columns(ddf_elite_users, "ddf_elite_users").persist()
        ddf_orders = self._lower_columns(ddf_orders, "ddf_orders").persist()
        ddf_user_perf = self._lower_columns(ddf_user_perf, "ddf_user_perf").persist()
        df_user_info = self._lower_columns(
            self._to_local_pandas(df_user_info, "df_user_info").copy(), "df_user_info"
        )

        # 严格要求 rank 字段
        required_elite = {"user_id", "period_num", "calc_month", "rank"}
        required_orders = {"period_num", "country_id", "pv"}
        required_perf = {"user_id", "is_active"}
        required_info = {"id", "country_id"}

        for name, df, required in [
            ("ddf_elite_users(评级底表)", ddf_elite_users, required_elite),
            ("ddf_orders(订单底表)", ddf_orders, required_orders),
            ("ddf_user_perf(活跃底表)", ddf_user_perf, required_perf),
            ("df_user_info(用户维表)", df_user_info, required_info),
        ]:
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"[阻断] {name} 缺少必需参与计算的字段: {sorted(missing)}")
        # endregion

        # ==========================================
        # Step 0.2: 活跃状态表清洗 (防发奖重复)
        # ==========================================
        # region 验证
        ddf_user_perf['user_id'] = self._normalize_id_series(ddf_user_perf['user_id'])
        perf_counts = ddf_user_perf.groupby('user_id').size().compute()
        if (perf_counts > 1).any():
            bad_users = perf_counts[perf_counts > 1].index.tolist()
            raise ValueError(f"[阻断] AR_USER_PERF 存在单用户多行记录，存在重复发奖风险。异常用户(部分): {bad_users[:5]}")
        # endregion

        # ==========================================
        # Step 0.3: 评级周期验证与隔离
        # ==========================================
        # region 验证
        period_groups = ddf_elite_users[['period_num', 'calc_month']].drop_duplicates().compute()
        if len(period_groups) == 0:
            logger.warning("当期(%s/%s) 评级底表为空，提前结束计算。", period_int, calc_month_int)
            return self._empty_result_df()
        elif len(period_groups) > 1:
            raise ValueError(f"[阻断] 评级数据源混入了多期数据！实际包含:\n{period_groups}")

        source_period = int(period_groups.iloc[0]['period_num'])
        source_month = int(period_groups.iloc[0]['calc_month'])
        if source_period != period_int or source_month != calc_month_int:
            raise ValueError(
                f"[阻断] 传入期数({period_int}/{calc_month_int}) 与数据期数({source_period}/{source_month}) 严重错位！"
            )
        # endregion

        # region 创造elite_target -> 从ddf_elite_users筛选出当期数据
        elite_target = ddf_elite_users[
            (dd.to_numeric(ddf_elite_users['period_num'], errors='coerce') == period_int) &
            (dd.to_numeric(ddf_elite_users['calc_month'], errors='coerce') == calc_month_int)
        ]
        # endregion

        # ==========================================
        # Step 0.4: 提取 Super Elite 会员 (严格依赖 rank == 30)
        # ==========================================
        # region 创造se_users -> 筛选出rank == 30的数据
        rank_col = dd.to_numeric(elite_target['rank'], errors='coerce').fillna(0)
        se_mask = (rank_col == 30)

        se_users = elite_target[se_mask]
        se_users['user_id'] = self._normalize_id_series(se_users['user_id'])
        se_users = se_users.persist()
        # endregion

        # region 验证
        se_dup_counts = se_users.groupby("user_id").size().compute()
        if (se_dup_counts > 1).any():
            bad_users = se_dup_counts[se_dup_counts > 1].index.tolist()
            raise ValueError(f"[阻断] 评级结果存在同一 SE 用户多行，严重污染分母。异常用户(部分): {bad_users[:5]}")

        if len(se_dup_counts) == 0:
            logger.warning("当期(%s/%s) 无人满足 SE 条件，提前结束计算。", period_int, calc_month_int)
            return self._empty_result_df()
        # endregion

        se_users = se_users.drop(columns=['country_id'], errors='ignore')

        # ==========================================
        # Step 1: 维表国籍校验与关联
        # ==========================================
        # region 验证
        bad_id_country = df_user_info["id"].isna() | df_user_info["country_id"].isna()
        if bad_id_country.any():
            raise ValueError(f"[阻断] df_user_info 维表中发现 {int(bad_id_country.sum())} 行的 ID/国籍为空。")

        df_user_info['id'] = self._normalize_id_series(df_user_info['id'])
        df_user_info['country_id'] = self._normalize_id_series(df_user_info['country_id'])

        if (df_user_info['id'].str.lower().isin(_INVALID_STR_TOKENS).any()
                or df_user_info['country_id'].str.lower().isin(_INVALID_STR_TOKENS).any()):
            raise ValueError("[阻断] df_user_info 维表中存在国籍或ID为非法无效字符串的数据。")

        dup_user_info = df_user_info[df_user_info["id"].duplicated()]["id"].tolist()
        if dup_user_info:
            raise ValueError(f"[阻断] df_user_info 维表存在重复 ID，将导致分母膨胀。异常用户(部分): {dup_user_info[:5]}")
        # endregion

        # region se_users联查df_user_info 补充用户信息
        se_users = se_users.merge(
            df_user_info[['id', 'country_id']],
            left_on='user_id', right_on='id', how='left'
        ).drop(columns=['id'], errors='ignore')
        # endregion

        # region 验证
        bad_users_count = (
            se_users['country_id'].isnull() | (se_users['country_id'] == "")
        ).sum().compute()
        if bad_users_count > 0:
            raise ValueError(
                f"[阻断] 发现 {int(bad_users_count)} 名 SE 会员在维表中未能匹配到国籍"
            )
        # endregion

        # ==========================================
        # Step 2: 组装分母
        # ==========================================
        mapping_ddf = dd.from_pandas(country_mapping, npartitions=1)

        # se_users联查mapping_ddf 补充source_country_id、region_default_id
        # region 新增bonus_country 值为region_default_id region_default_id为空时赋值补充se_users的country_id
        se_users = se_users.merge(
            mapping_ddf, left_on='country_id', right_on='source_country_id', how='left'
        )
        se_users['bonus_country'] = se_users['region_default_id'].fillna(se_users['country_id'])
        se_users = se_users.drop(columns=['source_country_id', 'region_default_id'], errors='ignore')
        # endregion

        # region 创造denominator -> 统计每个大区（bonus_country）里拥有资格的超级精英（Super Elite）总人数
        denominator = se_users.groupby('bonus_country').size().to_frame(name='vv_count').reset_index()
        # endregion

        # ==========================================
        # Step 3: 组装分子
        # ==========================================
        # region 筛选当前的国家总业绩
        orders = ddf_orders[dd.to_numeric(ddf_orders['period_num'], errors='coerce') == period_int]
        orders['pv'] = dd.to_numeric(orders['pv'], errors='coerce')
        orders = orders.persist()
        # endregion

        # region 验证
        bad_pv_count = orders['pv'].isna().sum().compute()
        if bad_pv_count > 0:
            raise ValueError(f"[阻断] 订单底表存在非数值或不可解析的 PV: 发现 {int(bad_pv_count)} 条，禁止入池计算。")
        # endregion

        # region order联查mapping_ddf 补充source_country_id region_default_id
        orders['pv_mills'] = (orders['pv'] * 1000).round().astype('int64')
        orders['country_id'] = self._normalize_id_series(orders['country_id'])

        orders = orders.merge(
            mapping_ddf, left_on='country_id', right_on='source_country_id', how='left'
        )
        orders['bonus_country'] = orders['region_default_id'].fillna(orders['country_id'])
        orders = orders.drop(columns=['source_country_id', 'region_default_id', 'pv'], errors='ignore')
        # endregion

        # region 创造numerator -> 按大区（bonus_country）汇总当期的总订单业绩（PV）
        numerator = (
            orders.groupby('bonus_country')['pv_mills'].sum()
            .to_frame(name='vv_total_pv_mills').reset_index()
        )
        # endregion

        # ==========================================
        # Step 4: 奖金计算
        # ==========================================
        # region 创造pool -> denominator联查numerator 通过bonus_country
        pool = denominator.merge(numerator, on='bonus_country', how='inner')
        pool = pool[pool['vv_count'] > 0]
        # endregion

        # region 计算se奖金=大区总 PV × 比例 ÷ 大区内 SE 总人数
        def calc_bonus_decimal(df_partition, rate_dec: Decimal):
            bonuses = []
            for pv_mills, count in zip(df_partition['vv_total_pv_mills'], df_partition['vv_count']):
                pv_dec = Decimal(int(pv_mills)) / Decimal('1000')
                count_dec = Decimal(int(count))
                val = (pv_dec * rate_dec / count_dec).quantize(Decimal('0.00'), rounding=ROUND_DOWN)
                bonuses.append(str(val))

            df_partition = df_partition.copy()
            df_partition['bonus_se'] = bonuses
            mask = pd.to_numeric(df_partition['bonus_se'], errors='coerce').fillna(0) > 0
            return df_partition[mask]
        # endregion

        # region 算出每个大区的每个人的bonus_se
        meta_df = pool._meta.copy()
        meta_df['bonus_se'] = pd.Series(dtype='object')
        pool = pool.map_partitions(calc_bonus_decimal, rate_dec=se_rate, meta=meta_df)
        # endregion

        # ==========================================
        # Step 5: 回挂明细与写出
        # ==========================================
        # region 创造result_df -> se_users联查pool联查ddf_user_perf
        result_df = se_users.merge(pool[['bonus_country', 'bonus_se']], on='bonus_country', how='inner')
        result_df = result_df.merge(ddf_user_perf[['user_id', 'is_active']], on='user_id', how='left')
        # endregion

        # region 补充期数和活跃状态
        result_df['is_active'] = result_df['is_active'].fillna(0).astype(int)
        result_df['period_num'] = str(period_int)
        result_df['calc_month'] = str(calc_month_int)
        # endregion

        # region 生成id
        timestamp_str = time.strftime('%Y%m%d%H%M%S')

        def generate_partition_ids(pdf, partition_info=None):
            part_no = (partition_info or {}).get("number", 0)
            if part_no > 999:
                raise ValueError(f"[阻断] Dask 分区号({part_no})超过 999，超出 22 位安全 ID 生成限制。")
            if len(pdf) > 99999:
                raise ValueError(f"[阻断] 单分区行数({len(pdf)})超过 99999，超出 22 位安全 ID 生成限制。")
            return pd.Series(
                [f"{timestamp_str}{part_no:03d}{i + 1:05d}" for i in range(len(pdf))],
                index=pdf.index,
                dtype="object",
            )

        result_df['id'] = result_df.map_partitions(generate_partition_ids, meta=('id', 'object'))
        # endregion

        output_columns = [
            'id', 'period_num', 'calc_month', 'user_id',
            'bonus_se', 'country_id', 'is_active', 'bonus_country'
        ]
        return result_df[output_columns]


# ==========================================
# 测试入口代码
# ==========================================
def main():
    period_num = 202310
    calc_month = 10

    df_config = pd.DataFrame({
        "config_name": ["superEliteRate", "CountryMY", "CountrySG", "CountryBN", "CountryTW"],
        "value": ["10", "MY", "MY", "MY", "TW"],
        "type": ["bonus", "bonus", "bonus", "bonus", "bonus"]
    })

    df_user_info = pd.DataFrame({
        'id': ['U001', 'U002', 'U003', 'U004'],
        'country_id': ['MY', 'SG', 'BN', 'TW']
    })

    pdf_elite = pd.DataFrame({
        'user_id': ['U001', 'U002', 'U003', 'U004'],
        'period_num': [period_num] * 4,
        'calc_month': [calc_month] * 4,
        'rank': [30, 30, 30, 30]
    })
    ddf_elite = dd.from_pandas(pdf_elite, npartitions=2)

    pdf_orders = pd.DataFrame({
        'period_num': [period_num] * 3,
        'country_id': ['MY', 'SG', 'TW'],
        'pv': [1000.50, 2000.00, 1000.00]
    })
    ddf_orders = dd.from_pandas(pdf_orders, npartitions=2)

    pdf_perf = pd.DataFrame({
        'user_id': ['U001', 'U002', 'U003', 'U004'],
        'is_active': [1, 0, 1, 1]
    })
    ddf_perf = dd.from_pandas(pdf_perf, npartitions=2)

    se_service = SuperEliteBonusService()

    result_ddf = se_service.calculate_se_bonus(
        period=period_num,
        calc_month=calc_month,
        ddf_elite_users=ddf_elite,
        ddf_orders=ddf_orders,
        ddf_user_perf=ddf_perf,
        df_config=df_config,
        df_user_info=df_user_info
    )

    final_df = result_ddf.compute()
    print("\n>>> 计算完成！最终的 AR_CALC_BONUS_SE:")
    print(final_df.to_string(index=False))


if __name__ == "__main__":
    main()