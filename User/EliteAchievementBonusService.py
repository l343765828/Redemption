import logging
import numpy as np
import pandas as pd
import dask.dataframe as dd
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pandas.api.types import is_float_dtype, is_integer_dtype
from typing import Any, Dict, Optional, Set, Tuple

logger = logging.getLogger("Bonus.EliteAchievementBonusService")

_INVALID_STR_TOKENS = {"none", "nan", "null", "na", "nat", "<na>", ""}

_AMOUNT_DECIMALS = 2
_AMOUNT_SCALE = Decimal(10) ** _AMOUNT_DECIMALS
_AMOUNT_QUANT = Decimal(1).scaleb(-_AMOUNT_DECIMALS)
_ELITE_MARK_SCALED = 1000 * int(_AMOUNT_SCALE)


def build_eab_service_for_prod(required_region_sources: Set[str]) -> "EliteAchievementBonusService":
    if not required_region_sources:
        raise RuntimeError("[生产阻断] required_region_sources 不能为空。")
    return EliteAchievementBonusService(required_region_sources)


def reject_float_before_dask(pdf: pd.DataFrame, cols: Set[str], df_name: str) -> None:
    """调用方可在【构造 dask 前】先对 pandas 金额列做 float 预检（与服务内部 _reject_float_amount_inputs 同口径）。
    例： reject_float_before_dask(elite_users_pdf, {'gpv'}, 'ddf_elite_users')
         reject_float_before_dask(orders_pdf, {'pv'}, 'ddf_orders')
    """
    missing = cols - set(pdf.columns)
    if missing:
        raise ValueError(f"[阻断] {df_name} 缺少金额列: {sorted(missing)}")
    for c in cols:
        if is_float_dtype(pdf[c]):
            raise ValueError(f"[阻断] {df_name}['{c}'] 为 float dtype，禁止进入 EAB（须为字符串或整数）。")
        # 用纯 Python any() 而非 pandas .map().any()：后者在 pandas 3.0 下对【空的】
        # arrow-string 列做 .any() 会抛 'Cannot perform reduction any with string dtype'。
        if any(isinstance(x, (float, np.floating)) for x in pdf[c]):
            raise ValueError(f"[阻断] {df_name}['{c}'] 混入 float 值，禁止进入 EAB。")


class EliteAchievementBonusService:
    """
    Elite Achievement Bonus (EAB) 单期奖金明细计算服务（纯计算引擎，不持有任何 I/O 依赖）。

    =====================================================================
    一、入参契约：与 SuperEliteBonusService 对齐（关键修正）
    =====================================================================
    评级底表 ddf_elite_users 由 UserStats 在【适配层】组装而来（不含 country_id）；国籍必须由用户维表
    df_user_info(id, country_id) 关联补齐 —— 这与 SuperEliteBonusService 完全一致（SuperElite 亦先 drop
    掉评级表里的 country_id，再 left join df_user_info 取权威国籍）。原因：UserStats 只有 gpv/period/rank，
    没有国籍；国籍只存在于 UserInfo。所以一个"已带好 country_id 的现成评级表"并非现成可取，必须组装。

    ★ UserStats -> ddf_elite_users 字段适配（调用方在进入本服务前必须完成，否则 _require_columns 直接阻断）：
        UserStats.period   ->  period_num   （注意：模型字段名是 period，不是 period_num，必须 rename）
        UserStats.user_id  ->  user_id
        UserStats.gpv      ->  gpv
        不从 UserStats 取 country_id，国籍统一由 df_user_info 补齐。
      例： ddf_elite_users = ddf_user_stats.rename(columns={"period": "period_num"})[["period_num","user_id","gpv"]]
      （SuperElite 同样要求 period_num/不带 country_id，此适配是两者共用的既定约定。）

    calculate_eab_bonus 入参：
        period, calc_month
        ddf_elite_users : dask，含 period_num, user_id, gpv（评级底表；country_id 不需要，若误带也会被丢弃，
                          以 df_user_info 为唯一国籍来源）
        ddf_orders      : dask，含 period_num, country_id, pv
        ddf_user_perf   : dask，含 user_id, is_active（要求单用户单行的当期快照）。period_num 为【可选】列：
                          带上则服务内部按当期过滤，不带则视为调用方已过滤好（与 SuperElite 必填集一致）。
        df_config       : pandas，奖金配置（eabRate + Country* 映射）
        df_user_info    : pandas，含 id, country_id（用户维表快照，权威国籍来源）
        df_country_master: pandas，可选，含 country_id（国家主数据）。给定则额外做"国籍/大区∈主数据"硬校验；
                          不给则与 SuperElite 一样仅靠维表+映射自身校验（默认 None，保持与 SuperElite 入参对齐）。

    ★★ 上线前必须确认：country_id 三边同一编码空间！
       下面三处的 country_id 必须使用同一套编码，否则大区合并静默失效（每个不匹配国家各自成池）：
         (1) df_user_info.country_id
         (2) ddf_orders.country_id
         (3) df_config 的 Country* 配置名 / value
       风险点：UserInfo.country_id 在 schema 中是 IntegerType（数字 FK 可能性大），而配置常是 'CountryMY'->'MY'
       这类国家代码。若维表是数字 60、配置是 MY，归一化后得到 "60" 与 "MY"，永不匹配 -> 会员按 "60" 单独成区。
       两种对齐方案任选其一：
         A. 进入 EAB 前把维表数字 FK 换成国家代码：
            df_user_info = df_user_info.merge(df_country_master[['country_id','country_code']], on='country_id', how='left')
            df_user_info['country_id'] = df_user_info['country_code']
         B. 配置改成数字口径（Country60 -> 60），三边统一用数字。
       安全网：若传入【国家代码版】df_country_master，本服务的维表 ∈ 主数据 校验会把数字 "60" 判为不在主数据而
       直接熔断（_validate_and_prepare_user_info），从而把"静默失效"变成"硬阻断"。强烈建议生产环境传 master。

    待确认（源模型类型提示，与 SuperElite 同处理）：
      - UserStats.gpv 为 int。本服务按 BV 2 位小数口径解析（int 1500 视为 1500.00 BV）。若该 int 实为"分"，
        需改 _AMOUNT_DECIMALS 或在组装时换算。

    =====================================================================
    二、引擎 vs 持久化职责边界
    =====================================================================
    返回两张 dask 表：
      "AR_CALC_BONUS_EAB"        旧表兼容明细（仅 bonus_eab>0；id 置空占位，由持久化层生成）
      "AR_CALC_BONUS_EAB_AUDIT"  审计明细（calc_bonus/actual_bonus/region_country_id/record_type）
    持久化层必须：① 生成主键 id；② 按业务唯一键 UPSERT 保证幂等（见下）；③ 单期单事务覆盖。
      LEGACY_BUSINESS_KEY / AUDIT_BUSINESS_KEY = (period_num, user_id)
      record_type 是会随重算翻转的【结果字段】，不可进唯一键。
    审计表为新增表，需补 DDL：字段类型对齐 DECIMAL(16,2)，record_type 枚举 {'payable','audit'}，唯一键同上。

    =====================================================================
    三、全链路无 Float / Fail-Loud
    =====================================================================
    金额以整数"分"汇总，仅最终单人金额 ROUND_HALF_UP 一次；float dtype 金额输入直接拒收；
    PV/GPV 空值、非法、小数位超 2 位一律熔断；业务 ID（含维表）空值/非法熔断；活跃标志仅接受 0/1。
    """

    _COUNTRY_PREFIX_LEN = len("Country")
    ELITE_MARK = 1000
    LEGACY_BUSINESS_KEY: Tuple[str, ...] = ('period_num', 'user_id')
    AUDIT_BUSINESS_KEY: Tuple[str, ...] = ('period_num', 'user_id')

    def __init__(self, required_region_sources: Optional[Set[str]] = None):
        self.required_region_sources = {
            self._normalize_id_scalar(x) for x in required_region_sources
        } if required_region_sources else set()
        if not self.required_region_sources:
            logger.warning("[EAB] required_region_sources 为空：'应合并国家缺映射' 安全检查已禁用。")

    # ------------------------------------------------------------------ 基础工具
    @staticmethod
    def _to_local_pandas(df, name: str) -> pd.DataFrame:
        if hasattr(df, "result"): df = df.result()
        if hasattr(df, "compute"): df = df.compute()
        if hasattr(df, "to_pandas"): df = df.to_pandas()
        if not isinstance(df, pd.DataFrame):
            try:
                df = pd.DataFrame(df)
            except Exception:
                raise ValueError(f"[阻断] {name} 无法转换为 pandas.DataFrame。")
        return df

    @staticmethod
    def _assert_cpu_dask(df, name: str) -> None:
        if not hasattr(df, "map_partitions") or not hasattr(df, "_meta"):
            raise ValueError(f"[阻断] {name} 不是 CPU dask.DataFrame。")
        meta_module = type(df._meta).__module__
        if "cudf" in meta_module or "cupy" in meta_module:
            raise ValueError(f"[阻断] {name} 是 GPU 对象。")

    @staticmethod
    def _lower_columns(df, name: str):
        df = df.rename(columns=str.lower)
        cols = pd.Index(df.columns)
        dup = cols[cols.duplicated()].tolist()
        if dup: raise ValueError(f"[阻断] {name} 列名小写后出现重复: {dup}")
        return df

    @staticmethod
    def _strict_int(val, name: str) -> int:
        if isinstance(val, (float, np.floating)):
            if not float(val).is_integer():
                raise ValueError(f"[阻断] {name} 是带小数的非整数值: {val!r}。")
            return int(val)
        try:
            return int(str(val).strip())
        except (ValueError, TypeError):
            raise ValueError(f"[阻断] {name} 无法严格转换为整数: {val!r}")

    @staticmethod
    def _normalize_id_scalar(val) -> str:
        s = str(val).strip()
        if s.endswith('.0'):
            head = s[:-2]
            if head and head.lstrip('-').isdigit():
                s = head
        return s.strip().upper()

    @staticmethod
    def _normalize_id_series(s):
        return s.astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()

    @staticmethod
    def _require_columns(df, name: str, required: set) -> None:
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"[阻断] {name} 缺失必需字段: {sorted(missing)}")

    def _empty_result_dicts(self) -> Dict[str, dd.DataFrame]:
        legacy_df = pd.DataFrame(
            columns=['id', 'period_num', 'calc_month', 'user_id', 'gpv', 'bonus_eab', 'country_id', 'is_active'])
        audit_df = pd.DataFrame(
            columns=['period_num', 'calc_month', 'user_id', 'gpv', 'calc_bonus', 'actual_bonus', 'country_id',
                     'region_country_id', 'is_active', 'record_type'])
        return {"AR_CALC_BONUS_EAB": dd.from_pandas(legacy_df, npartitions=1),
                "AR_CALC_BONUS_EAB_AUDIT": dd.from_pandas(audit_df, npartitions=1)}

    # ------------------------------------------------------------------ 金额 float dtype 拒收
    @staticmethod
    def _reject_float_amount_inputs(ddf: dd.DataFrame, cols: Set[str], df_name: str) -> None:
        float_dtype_cols = [c for c in cols if is_float_dtype(ddf._meta[c])]
        if float_dtype_cols:
            raise ValueError(
                f"[阻断] {df_name} 金额列 {float_dtype_cols} 的 dtype 为 float，禁止进入 EAB（须为字符串或整数）。")
        check_cols = [c for c in cols if not is_float_dtype(ddf._meta[c]) and not is_integer_dtype(ddf._meta[c])]
        if not check_cols:
            return

        def detect_float_values(pdf):
            # 用纯 Python any() 而非 pandas .map().any()：周期过滤会在多分区上产生【空分区】，
            # 而 pandas 3.0 对空 arrow-string 列做 .map(...).any() 会抛
            # 'Cannot perform reduction any with string dtype' 直接崩溃。纯 Python any() 对空列返回 False，
            # 对含 float 的列仍返回 True，行为等价且不依赖 pandas 的 dtype 推断。
            return pd.DataFrame(
                [{c: any(isinstance(x, (float, np.floating)) for x in pdf[c]) for c in check_cols}])

        meta = pd.DataFrame({c: pd.Series(dtype="bool") for c in check_cols})
        has_float = ddf[check_cols].map_partitions(detect_float_values, meta=meta).any().compute()
        bad_cols = [c for c, v in has_float.items() if bool(v)]
        if bad_cols:
            raise ValueError(f"[阻断] {df_name} 金额列 {bad_cols} 中混入了 float 值，禁止进入 EAB。")

    # ------------------------------------------------------------------ 配置解析
    def _parse_eab_rate(self, df_config: pd.DataFrame) -> Decimal:
        df_cfg = self._lower_columns(self._to_local_pandas(df_config, "df_config").copy(), "df_config")
        self._require_columns(df_cfg, "df_config", {"config_name", "value", "type"})
        name_norm = df_cfg['config_name'].astype(str).str.strip()
        type_norm = df_cfg['type'].astype(str).str.strip().str.lower()
        df_rate = df_cfg[(name_norm == 'eabRate') & (type_norm == 'bonus')]
        if df_rate.empty:
            raise ValueError("[阻断] EAB_RATE 配置缺失 (TYPE='bonus')。")
        if len(df_rate) > 1:
            raise ValueError("[阻断] EAB_RATE 配置存在多条。")
        value = df_rate.iloc[0]['value']
        if pd.isna(value) or value is None:
            raise ValueError("[阻断] eabRate 配置的值为空。")
        if isinstance(value, (float, np.floating)):
            raise ValueError(f"[阻断] eabRate 配置值为 float({value!r})，请用字符串以免精度问题。")
        # 先 strip 判空：空串/纯空白归"配置的值为空"（而非走 Decimal 的 InvalidOperation）
        s = str(value).strip()
        if s == "":
            raise ValueError("[阻断] eabRate 配置的值为空。")
        try:
            rate_val = Decimal(s)
        except InvalidOperation:
            raise ValueError(f"[阻断] eabRate 值非法: {value!r}")
        # NaN 单独归"值非法"（Decimal('NaN') 本身合法但语义无效）；必须在 is_finite 之前判，
        # 因为 NaN 与 Infinity 都 not is_finite，但二者归类不同。
        if rate_val.is_nan():
            raise ValueError(f"[阻断] eabRate 值非法: {value!r}")
        if not rate_val.is_finite():
            raise ValueError(f"[阻断] eabRate 配置值不是有限数值: {value!r}")
        if rate_val <= 0 or rate_val > 100:
            raise ValueError(f"[阻断] eabRate 必须介于 (0, 100]，当前: {rate_val}")
        return rate_val / Decimal('100')

    def _parse_country_mapping(self, df_config: pd.DataFrame, valid_countries: Optional[set] = None) -> pd.DataFrame:
        df_cfg = self._lower_columns(self._to_local_pandas(df_config, "df_config").copy(), "df_config")
        self._require_columns(df_cfg, "df_config", {"config_name", "value", "type"})
        df_cfg['__name'] = df_cfg['config_name'].astype(str).str.strip()
        df_cfg['__type'] = df_cfg['type'].astype(str).str.strip().str.lower()
        df_bonus_cfg = df_cfg[df_cfg['__type'] == 'bonus'].copy()
        is_country = df_bonus_cfg['__name'].str.lower().str.startswith('country')
        df_country = df_bonus_cfg[is_country].copy()
        if df_country.empty:
            df_mapping = pd.DataFrame(columns=['source_country_id', 'region_default_id'])
        else:
            mapping = []
            for _, row in df_country.iterrows():
                config_name = row['__name']
                if len(config_name) <= self._COUNTRY_PREFIX_LEN:
                    raise ValueError(f"[阻断] Country 配置名过短非法: {config_name}")
                source_country = self._normalize_id_scalar(config_name[self._COUNTRY_PREFIX_LEN:])
                target_region = self._normalize_id_scalar(row['value'])
                if not source_country or source_country.lower() in _INVALID_STR_TOKENS:
                    raise ValueError(f"[阻断] 源国家ID非法: {config_name}")
                if not target_region or target_region.lower() in _INVALID_STR_TOKENS:
                    raise ValueError(f"[阻断] 目标大区 value 非法: {target_region}")
                mapping.append({"source_country_id": source_country, "region_default_id": target_region})
            df_mapping = pd.DataFrame(mapping, columns=['source_country_id', 'region_default_id'])
            if df_mapping['source_country_id'].duplicated().any():
                duplicates = df_mapping[df_mapping['source_country_id'].duplicated()]['source_country_id'].tolist()
                raise ValueError(f"[阻断] 重复源国家（含大小写变体）: {duplicates}")
        if self.required_region_sources:
            missing_req = self.required_region_sources - set(df_mapping['source_country_id'])
            if missing_req:
                raise ValueError(f"[阻断] 业务要求的可合并国家缺少映射: {missing_req}")
        if valid_countries is not None and not df_mapping.empty:
            invalid_targets = set(df_mapping['region_default_id']) - valid_countries
            if invalid_targets:
                raise ValueError(f"[阻断] 目标大区不在国家主数据: {invalid_targets}")
            invalid_sources = set(df_mapping['source_country_id']) - valid_countries
            if invalid_sources:
                raise ValueError(f"[阻断] 源国家不在国家主数据: {invalid_sources}")
        return df_mapping

    @staticmethod
    def _load_valid_countries(df_country_master) -> set:
        df_master = EliteAchievementBonusService._lower_columns(
            EliteAchievementBonusService._to_local_pandas(df_country_master, "df_country_master").copy(),
            "df_country_master")
        EliteAchievementBonusService._require_columns(df_master, "df_country_master", {"country_id"})
        valid = set(EliteAchievementBonusService._normalize_id_series(df_master['country_id']))
        valid = {c for c in valid if c.lower() not in _INVALID_STR_TOKENS}
        if not valid:
            raise ValueError("[阻断] df_country_master 中无有效国家。")
        return valid

    # ------------------------------------------------------------------ 用户维表校验（与 SuperElite 一致）
    def _validate_and_prepare_user_info(self, df_user_info, valid_countries: Optional[set]) -> pd.DataFrame:
        df_info = self._lower_columns(self._to_local_pandas(df_user_info, "df_user_info").copy(), "df_user_info")
        self._require_columns(df_info, "df_user_info", {"id", "country_id"})
        bad = df_info["id"].isna() | df_info["country_id"].isna()
        if bad.any():
            raise ValueError(f"[阻断] df_user_info 维表中发现 {int(bad.sum())} 行的 ID/国籍为空。")
        df_info = df_info.copy()
        df_info['id'] = self._normalize_id_series(df_info['id'])
        df_info['country_id'] = self._normalize_id_series(df_info['country_id'])
        if (df_info['id'].str.lower().isin(_INVALID_STR_TOKENS).any()
                or df_info['country_id'].str.lower().isin(_INVALID_STR_TOKENS).any()):
            raise ValueError("[阻断] df_user_info 维表中存在国籍或ID为非法无效字符串的数据。")
        dup = df_info[df_info["id"].duplicated()]["id"].tolist()
        if dup:
            raise ValueError(f"[阻断] df_user_info 维表存在重复 ID，将导致分母膨胀: {dup[:5]}")
        if valid_countries is not None:
            not_in = set(df_info['country_id']) - valid_countries
            if not_in:
                raise ValueError(f"[阻断] df_user_info 维表国籍不在国家主数据: {sorted(not_in)[:5]}")
        return df_info[['id', 'country_id']]

    # ------------------------------------------------------------------ 业务 ID Eager 校验
    def _eager_validate_ids(self, ddf, col_name, df_name, valid_countries=None):
        col = ddf[col_name]
        garbage_mask = col.isna() | col.astype(str).str.strip().str.lower().isin(_INVALID_STR_TOKENS)
        if garbage_mask.any().compute():
            raise ValueError(f"[阻断] {df_name}['{col_name}'] 存在空值/非法ID(None/NaN/<NA>/空串等)。")
        if valid_countries is not None:
            not_in_master = ~col.isin(list(valid_countries))
            if not_in_master.any().compute():
                bad = col[not_in_master].drop_duplicates().head(5, npartitions=-1).tolist()
                raise ValueError(f"[阻断] {df_name}['{col_name}'] 存在不在国家主数据中的国家: {bad}")

    # ------------------------------------------------------------------ 金额转换（无 Float）
    @staticmethod
    def _parse_amount_to_scaled_int(df_partition, col_name, df_name):
        def to_scaled(val):
            if pd.isna(val) or str(val).strip().lower() in _INVALID_STR_TOKENS:
                raise ValueError(f"[阻断] {df_name}['{col_name}'] 空值/非法: {val!r}")
            try:
                d = Decimal(str(val).strip())
            except InvalidOperation:
                raise ValueError(f"[阻断] {df_name}['{col_name}'] 脏数据: {val!r}")
            if not d.is_finite():
                raise ValueError(f"[阻断] {df_name}['{col_name}'] 非有限数值: {val!r}")
            if d != d.quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP):
                raise ValueError(
                    f"[阻断] {df_name}['{col_name}'] 小数位超 {_AMOUNT_DECIMALS} 位: {val!r}（请确认源精度，禁止静默舍入）")
            return int((d * _AMOUNT_SCALE).to_integral_value())

        return df_partition[col_name].apply(to_scaled).astype('int64')

    @staticmethod
    def _format_scaled_to_str(df_partition, scaled_col, out_col):
        df_partition = df_partition.copy()
        df_partition[out_col] = df_partition[scaled_col].apply(
            lambda c: str((Decimal(int(c)) / _AMOUNT_SCALE).quantize(_AMOUNT_QUANT)))
        return df_partition

    # ================================================================== 主流程
    def calculate_eab_bonus(self, period, calc_month, ddf_elite_users, ddf_orders, ddf_user_perf,
                            df_config, df_user_info, df_country_master=None):
        # region 参数验证
        period_int = self._strict_int(period, 'period')
        calc_month_int = self._strict_int(calc_month, 'calc_month')
        if not (1 <= calc_month_int <= 12):
            raise ValueError(f"[阻断] calc_month={calc_month_int} 非法。")

        self._assert_cpu_dask(ddf_elite_users, "ddf_elite_users(评级底表)")
        self._assert_cpu_dask(ddf_orders, "ddf_orders(订单底表)")
        self._assert_cpu_dask(ddf_user_perf, "ddf_user_perf(活跃底表)")

        ddf_elite_users = self._lower_columns(ddf_elite_users, "ddf_elite_users")
        ddf_orders = self._lower_columns(ddf_orders, "ddf_orders")
        ddf_user_perf = self._lower_columns(ddf_user_perf, "ddf_user_perf")

        # 评级底表【不要求 country_id】：国籍由 df_user_info 关联补齐（与 SuperElite 一致）
        self._require_columns(ddf_elite_users, "ddf_elite_users", {'period_num', 'user_id', 'gpv'})
        self._require_columns(ddf_orders, "ddf_orders", {'period_num', 'country_id', 'pv'})
        self._require_columns(ddf_user_perf, "ddf_user_perf", {'user_id', 'is_active'})

        # 国家主数据可选：给定则启用"∈主数据"硬校验，否则与 SuperElite 一样仅靠维表+映射自身校验
        valid_countries = self._load_valid_countries(df_country_master) if df_country_master is not None else None
        if valid_countries is None:
            logger.warning("[EAB] 未提供 df_country_master：国籍/大区 ∈ 主数据 校验已跳过（与 SuperElite 入参对齐）。")
        # endregion

        # region 获取汇率 并将国家 大区信息放到dask中
        eab_rate = self._parse_eab_rate(df_config)
        mapping_ddf = dd.from_pandas(self._parse_country_mapping(df_config, valid_countries), npartitions=1)
        # endregion

        # region 将ddf_elite_users放到内存中
        # 过滤当期 + 归一化 + persist。评级表丢弃可能误带的 country_id（唯一国籍来源 = 维表）
        ddf_elite_users = ddf_elite_users[dd.to_numeric(ddf_elite_users['period_num'], errors='coerce') == period_int]
        ddf_elite_users['user_id'] = self._normalize_id_series(ddf_elite_users['user_id'])
        ddf_elite_users = ddf_elite_users.drop(columns=['country_id'], errors='ignore').persist()
        # endregion

        # region 将ddf_orders放到内存中
        ddf_orders = ddf_orders[dd.to_numeric(ddf_orders['period_num'], errors='coerce') == period_int]
        ddf_orders['country_id'] = self._normalize_id_series(ddf_orders['country_id'])
        ddf_orders = ddf_orders.persist()
        # endregion

        # region 将ddf_user_perf放到内存中
        # ddf_user_perf：period_num 为可选列。带上则按当期过滤（容忍调用方传原始多期表）；
        # 不带则视为调用方已过滤好的当期单用户单行快照（与 SuperElite 必填集 {user_id,is_active} 一致）。
        if 'period_num' in ddf_user_perf.columns:
            ddf_user_perf = ddf_user_perf[dd.to_numeric(ddf_user_perf['period_num'], errors='coerce') == period_int]
        ddf_user_perf['user_id'] = self._normalize_id_series(ddf_user_perf['user_id'])
        ddf_user_perf = ddf_user_perf.persist()
        # endregion

        # region 金额 float dtype 拒收
        self._reject_float_amount_inputs(ddf_elite_users, {'gpv'}, 'ddf_elite_users')
        self._reject_float_amount_inputs(ddf_orders, {'pv'}, 'ddf_orders')
        # endregion

        # region 验证
        # 关联表底座校验
        self._eager_validate_ids(ddf_user_perf, 'user_id', 'ddf_user_perf')
        self._eager_validate_ids(ddf_orders, 'country_id', 'ddf_orders', valid_countries)

        # 活跃标志：已存在记录但空值 -> 熔断；真正缺记录的默认不活跃留到 left join 后
        raw_active = dd.to_numeric(ddf_user_perf['is_active'], errors='coerce')
        invalid_active_mask = raw_active.isna() | ~raw_active.isin([0, 1])
        if invalid_active_mask.any().compute():
            raise ValueError("[阻断] ddf_user_perf['is_active'] 存在空值或 0/1 之外的非法状态码。")
        ddf_user_perf['is_active'] = raw_active.astype(int)
        # endregion

        # region 数据验证
        perf_counts = ddf_user_perf.groupby('user_id').size().compute()
        if (perf_counts > 1).any():
            bad_perf = perf_counts[perf_counts > 1].index.tolist()
            raise ValueError(f"[阻断] ddf_user_perf 单用户多行: {bad_perf[:5]}")
        # endregion

        # region 新增pv_scaled -> ddf_orders中的PV -> 放大100倍 并立刻触发计算
        ddf_orders['pv_scaled'] = ddf_orders.map_partitions(self._parse_amount_to_scaled_int, 'pv', 'ddf_orders',
                                                            meta=('pv_scaled', 'int64'))
        ddf_orders = ddf_orders.persist()
        _ = int(ddf_orders['pv_scaled'].sum().compute())
        # endregion

        # region 创造qualified_users -> ddf_elite_users中的gpv 放大100倍 并取出gpv>=100的数据 放到内存中
        # GPV -> 整数分，截取达标会员（资格判断走整数口径，无 float）
        ddf_elite_users['gpv_scaled'] = ddf_elite_users.map_partitions(self._parse_amount_to_scaled_int, 'gpv',
                                                                       'ddf_elite_users', meta=('gpv_scaled', 'int64'))
        qualified_users = ddf_elite_users[ddf_elite_users['gpv_scaled'] >= _ELITE_MARK_SCALED].copy()
        qualified_users = qualified_users.persist()
        # endregion

        # region 验证
        # 全分区安全空表判断（修复 head(1) 仅看 partition 0 的误判）
        if int(qualified_users.map_partitions(len).sum().compute()) == 0:
            logger.info(f"当期 ({period_int}) 无符合 EAB 资格会员。")
            return self._empty_result_dicts()
        # endregion

        # region 数据验证
        # 达标后再校验 user_id（容错：未达标行的脏 ID 不阻断本期发奖）
        self._eager_validate_ids(qualified_users, 'user_id', 'qualified_users')
        user_counts = qualified_users.groupby('user_id').size().compute()
        if (user_counts > 1).any():
            bad = user_counts[user_counts > 1].index.tolist()
            raise ValueError(f"[阻断] 达标会员存在重复 user_id: {bad[:5]}")
        # endregion

        # ============== 国籍组装：关联用户维表 df_user_info（核心修正） ==============
        # region qualified_users联查df_user_info 获取country_id
        df_info = self._validate_and_prepare_user_info(df_user_info, valid_countries)
        qualified_users = qualified_users.drop(columns=['country_id'], errors='ignore').merge(
            df_info, left_on='user_id', right_on='id', how='left'
        ).drop(columns=['id'], errors='ignore')
        unmatched = (qualified_users['country_id'].isnull() | (qualified_users['country_id'] == "")).sum().compute()
        if unmatched > 0:
            raise ValueError(f"[阻断] 发现 {int(unmatched)} 名达标会员在 df_user_info 维表中未匹配到国籍。")
        # endregion

        # region GPV 输出 2 位小数（由分精确还原）
        meta_gpv = qualified_users._meta.copy()
        meta_gpv['gpv'] = pd.Series(dtype='object')
        qualified_users = qualified_users.map_partitions(self._format_scaled_to_str, 'gpv_scaled', 'gpv', meta=meta_gpv)
        # endregion

        # qualified_users联查mapping_ddf 获取region_country_id 有region赋值region，没有的赋值countryid
        # region 创造denominator -> 最后算出每个获取region_country_id有多少用户
        # 人员映射大区
        qualified_users = qualified_users.merge(mapping_ddf, left_on='country_id', right_on='source_country_id',
                                                how='left')
        qualified_users['region_country_id'] = qualified_users['region_default_id'].fillna(
            qualified_users['country_id'])
        qualified_users = qualified_users.drop(columns=['source_country_id', 'region_default_id', 'gpv_scaled'],
                                               errors='ignore')
        denominator = qualified_users.groupby('region_country_id').size().to_frame(name='eligible_nums').reset_index()
        # endregion

        # ddf_orders联查mapping_ddf 获取region_country_id 有region赋值region，没有的赋值countryid
        # region 创造numerator -> 算出每个大区的pv总和
        # 订单映射大区 + 整数分汇总
        mapped_orders = ddf_orders.merge(mapping_ddf, left_on='country_id', right_on='source_country_id', how='left')
        mapped_orders['region_country_id'] = mapped_orders['region_default_id'].fillna(mapped_orders['country_id'])
        mapped_orders = mapped_orders.drop(columns=['source_country_id', 'region_default_id', 'pv'], errors='ignore')
        numerator = mapped_orders.groupby('region_country_id')['pv_scaled'].sum().to_frame(
            name='region_total_pv_scaled').reset_index()
        numerator['region_total_pv_scaled'] = numerator['region_total_pv_scaled'].clip(lower=0).astype('int64')
        # endregion

        # region denominator联查numerator 每个大区有多少用户有多少总pv
        # 达标大区为主表（有人无单兜底 0）。left join 后 NaN 会把整数列提升为 float，强制回 int64
        region_pool = denominator.merge(numerator, on='region_country_id', how='left')
        region_pool['region_total_pv_scaled'] = region_pool['region_total_pv_scaled'].fillna(0).astype('int64')

        # endregion

        def _assert_int64_pv_scaled(df_partition):
            if df_partition['region_total_pv_scaled'].dtype != 'int64':
                raise TypeError("[阻断] region_total_pv_scaled 运行时 dtype 非 int64（疑似 float 提升）。")
            return df_partition

        region_pool = region_pool.map_partitions(_assert_int64_pv_scaled, meta=region_pool._meta.copy())

        # region 计算奖金：大区总pv * 汇率 / 大区总人数
        def calc_per_capita(df_partition, rate_dec):
            bonuses = []
            for pv_scaled, nums in zip(df_partition['region_total_pv_scaled'], df_partition['eligible_nums']):
                if nums <= 0 or pv_scaled <= 0:
                    bonuses.append("0.00");
                    continue
                pv_dec = Decimal(int(pv_scaled)) / _AMOUNT_SCALE
                val = (pv_dec * rate_dec / Decimal(str(nums))).quantize(_AMOUNT_QUANT, rounding=ROUND_HALF_UP)
                bonuses.append(str(val))
            df_partition = df_partition.copy()
            df_partition['calc_bonus'] = bonuses
            return df_partition

        meta_df = region_pool._meta.copy()
        meta_df['calc_bonus'] = pd.Series(dtype='object')
        region_pool = region_pool.map_partitions(calc_per_capita, rate_dec=eab_rate, meta=meta_df)
        # endregion

        # region 创造result_df -> qualified_users联查region_pool 非活跃用户奖金赋值0
        result_df = qualified_users.merge(region_pool[['region_country_id', 'calc_bonus']], on='region_country_id',
                                          how='inner')
        result_df = result_df.merge(ddf_user_perf[['user_id', 'is_active']], on='user_id', how='left')
        result_df['is_active'] = result_df['is_active'].fillna(0).astype(int)

        def apply_audit_and_active_status(df_partition):
            df_partition = df_partition.copy()
            actuals, record_types = [], []
            for is_act, calc_val in zip(df_partition['is_active'], df_partition['calc_bonus']):
                if int(is_act) == 1 and Decimal(calc_val) > 0:
                    actuals.append(str(calc_val));
                    record_types.append("payable")
                else:
                    actuals.append("0.00");
                    record_types.append("audit")
            df_partition['actual_bonus'] = actuals
            df_partition['record_type'] = record_types
            df_partition['bonus_eab'] = df_partition['calc_bonus']
            return df_partition

        _meta_audit = result_df._meta.copy()
        _meta_audit['actual_bonus'] = pd.Series(dtype='object')
        _meta_audit['record_type'] = pd.Series(dtype='object')
        _meta_audit['bonus_eab'] = pd.Series(dtype='object')
        result_df = result_df.map_partitions(apply_audit_and_active_status, meta=_meta_audit)

        result_df['period_num'] = period_int
        result_df['calc_month'] = calc_month_int

        # endregion

        # region 过滤出奖金大于0的人
        def filter_positive_legacy(df_partition):
            mask = df_partition['bonus_eab'].apply(lambda x: Decimal(str(x)) > 0)
            return df_partition[mask]

        legacy_df = result_df.map_partitions(filter_positive_legacy, meta=result_df._meta)
        legacy_df = legacy_df.assign(id="")  # 物理主键占位，由持久化层生成
        # endregion

        legacy_cols = ['id', 'period_num', 'calc_month', 'user_id', 'gpv', 'bonus_eab', 'country_id', 'is_active']
        audit_cols = ['period_num', 'calc_month', 'user_id', 'gpv', 'calc_bonus', 'actual_bonus', 'country_id',
                      'region_country_id', 'is_active', 'record_type']
        return {"AR_CALC_BONUS_EAB": legacy_df[legacy_cols], "AR_CALC_BONUS_EAB_AUDIT": result_df[audit_cols]}
