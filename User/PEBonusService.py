import logging
import uuid
import dask_cudf
import cudf
import pandas as pd
from typing import Dict, List, Optional
from dask.distributed import get_client, wait as dask_wait, futures_of

from Common.BonusConfig import ConfigSnapshot
from Common.PvAmount import (
    BONUS_CENT_SCALE,
    PV_SCALE,
    RATE_PPM_SCALE,
    assert_integer_amount_dtype,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("Bonus.PEBonusBatchServiceGPU")

# ============================================================
# 严格契约定义
# ============================================================
REQUIRED_ELITE_COLS = ['PERIOD_NUM', 'CALC_MONTH', 'USER_ID', 'PARENT_UID', 'GPV_REAL', 'GPV_UNREAL',
                       'LAST_ELITE_CALC_ID']
REQUIRED_PERF_COLS = ['PERIOD_NUM', 'USER_ID', 'IS_ACTIVE']
REQUIRED_USER_COLS = ['id', 'country_id', 'user_name', 'real_name']
REQUIRED_STATS_COLS = ['rank', 'is_elite', 'gpv_real', 'gpv_unreal']

MAIN_COLUMNS = ['ID', 'PERIOD_NUM', 'CALC_MONTH', 'USER_ID', 'TOTAL_BASE_GPV', 'PE_RATE_PPM', 'BONUS_PE_CENTS', 'COUNTRY_ID',
                'IS_ACTIVE']
SOURCE_COLUMNS = ['PERIOD_NUM', 'CALC_MONTH', 'BONUS_USER_ID', 'BONUS_USER_NAME', 'BONUS_REAL_NAME',
                  'SOURCE_USER_ID', 'SOURCE_USER_NAME', 'SOURCE_REAL_NAME',
                  'SOURCE_GPV', 'SOURCE_GPV_UNREAL', 'PE_RATE_PPM', 'IS_ACTIVE']


class PEBonusService:
    def __init__(self, config_snapshot: ConfigSnapshot):
        if not isinstance(config_snapshot, ConfigSnapshot):
            raise TypeError("PEBonusService requires an explicit frozen ConfigSnapshot")
        self._max_compression_depth = 1000
        self.config_snapshot = config_snapshot
        self._pro_elite_rate_ppm = config_snapshot.require_ppm(
            "proEliteRate", award="PE"
        )

    @staticmethod
    def _generate_uuids(df: cudf.DataFrame, id_col_name: str = 'ID') -> cudf.DataFrame:
        df[id_col_name] = [uuid.uuid4().hex for _ in range(len(df))]
        return df

    @staticmethod
    def _apply_truncate(df: cudf.DataFrame) -> cudf.DataFrame:
        import cupy as cp

        # region 按 SQL 最终截断点一次换算奖金分
        # SQL 的 TRUNCATE 只发生在“总基数 × 费率”之后；基数不得预舍入到分。
        base_units = df['TOTAL_BASE_GPV'].astype('int64')
        rate_ppm = df['PE_RATE_PPM'].astype('int64')
        units_per_cent = PV_SCALE // BONUS_CENT_SCALE
        denominator = RATE_PPM_SCALE * units_per_cent

        # CuPy 的 abs(INT64_MIN) 和后续整数乘积会溢出；金额域必须先 fail-loud。
        int64_min = -(2 ** 63)
        int64_max = 2 ** 63 - 1
        if bool(((base_units == int64_min) | (rate_ppm == int64_min)).any()):
            raise OverflowError('PE amount or rate cannot equal INT64_MIN')

        amount_sign = cp.where((base_units < 0) ^ (rate_ppm < 0), -1, 1)
        base_magnitude = cp.abs(base_units)
        rate_magnitude = cp.abs(rate_ppm)
        quotient = base_magnitude // denominator
        remainder = base_magnitude % denominator
        safe_rate = cp.maximum(rate_magnitude, 1)
        if bool(((quotient > int64_max // safe_rate) | (remainder > int64_max // safe_rate)).any()):
            raise OverflowError('PE bonus cents intermediate is outside signed int64')

        whole_product = quotient * rate_magnitude
        fractional_product = remainder * rate_magnitude
        fractional_cents = fractional_product // denominator
        if bool((whole_product > int64_max - fractional_cents).any()):
            raise OverflowError('PE bonus cents is outside signed int64')
        bonus_magnitude = whole_product + fractional_cents
        df['BONUS_PE_CENTS'] = (amount_sign * bonus_magnitude).astype('int64')
        # endregion
        return df

    @staticmethod
    def _require_columns(ddf: dask_cudf.DataFrame, required: List[str], name: str) -> None:
        missing = [c for c in required if c not in ddf.columns]
        if missing:
            raise ValueError(f"{name} 缺少必需列 {missing}。外部输入表必须符合契约！")

    @staticmethod
    def _resolve_user_id(ddf: dask_cudf.DataFrame) -> dask_cudf.DataFrame:
        if 'user_id' not in ddf.columns:
            if 'id' in ddf.columns:
                ddf = ddf.rename(columns={'id': 'user_id'})
            else:
                raise ValueError("外部输入表缺少 user_id 或 id 字段！")
        return ddf

    @staticmethod
    def _dedup_or_raise(ddf: dask_cudf.DataFrame, value_cols: List[str], key_cols: List[str],
                        name: str) -> dask_cudf.DataFrame:
        # 先按“完整值”去重：同键且每一列都相同的纯重复行视为无害，直接折叠
        ddf = ddf.drop_duplicates(subset=value_cols)

        # 【关键修复】不要在 dask 侧做 sizes[sizes > 1] 布尔自掩码，也不要对 dask_cudf
        # 对象直接调用 len()/.any() —— 在当前 dask_cudf 版本里，这些操作的 meta / reduction
        # 计算会触发 cuDF 的 "Series object is not iterable"，导致所有用例在第一次去重时就崩。
        # 正确做法：先把分组计数 compute 成具体的 cuDF Series（这步本身安全），再 to_pandas()
        # 落回主机，所有“找冲突 / 判空 / 取样”逻辑都放到 pandas 侧完成（pandas 的真值与 len
        # 都是确定的）。分组计数结果只有“每个键一行”，体量远小于原始数据，落主机开销可忽略。
        sizes_host = ddf.groupby(key_cols).size().compute().to_pandas()

        bad = sizes_host[sizes_host > 1]
        if len(bad) > 0:
            bad_keys = bad.head(10).index.tolist()
            raise ValueError(f"【严重错误】{name} 存在同键冲突数据！冲突键示例: {bad_keys}")
        return ddf

    # =====================================================================
    # 财务级连环净额上推网络 (SQL MID6/MID7 深度复刻)
    # =====================================================================
    def _apply_nested_push_up_net(self, snapshot: dask_cudf.DataFrame, client) -> dask_cudf.DataFrame:
        logger.info("开始执行自底向上的嵌套上推净额结算 (Nested Push-Up Net)...")

        # region 将snapshot中的数据初始化
        def _init_push_up(df):
            import cupy as cp
            # 判断是否为路径B晋升，路径B：自己业绩未达标，但是下级是elite了
            df['IS_PATH_B'] = (df['rank'] >= 20) & (~df['is_elite'])
            df['GPV_REAL_BASE'] = cp.where(df['is_elite'], df['gpv_real'], 0).astype('int64')
            df['CURRENT_GPV'] = df['GPV_REAL_BASE']
            # 如果不是路径 B，默认已经结算完成；如果是路径 B，默认还没结算完成。
            df['RESOLVED'] = ~df['IS_PATH_B']
            return df
        # endregion

        snapshot = snapshot.map_partitions(_init_push_up)

        iteration = 0
        while iteration < 5000:
            # region 当未结算的数量为0时 跳出循环
            unresolved_count = snapshot[~snapshot['RESOLVED']].map_partitions(len).sum().compute()
            if unresolved_count == 0:
                logger.info(f"上推净额在第 {iteration} 轮迭代收敛完成。")
                break
            # endregion

            # region 创造child_status -> snapshot 'user_id', 'compressed_parent_id', 'RESOLVED'
            child_status = snapshot[['user_id', 'compressed_parent_id', 'RESOLVED']]
            # endregion

            # region 创造parent_res child_status聚合compressed_parent_id compressed_parent_id：user_id RESOLVED：CHILD_RESOLVED
            # 取min 当RESOLVED出现false时 RESOLVED为false
            parent_res = child_status.groupby('compressed_parent_id').agg({'RESOLVED': 'min'}).reset_index()
            parent_res = parent_res.rename(columns={'compressed_parent_id': 'user_id', 'RESOLVED': 'CHILD_RESOLVED'})
            # endregion

            # region 创造merged snapshot左联parent_res on='user_id 'user_id','compressed_parent_id','RESOLVED','CHILD_RESOLVED'
            merged = snapshot.merge(parent_res, on='user_id', how='left')
            merged['CHILD_RESOLVED'] = merged['CHILD_RESOLVED'].fillna(True)
            # endregion

            # region 创造结算条件：RESOLVED=false 且 CHILD_RESOLVED=true的条件
            ready_mask = (~merged['RESOLVED']) & merged['CHILD_RESOLVED']
            ready_count = merged[ready_mask].map_partitions(len).sum().compute()
            # endregion

            # region 验证是否符合跳出条件
            if ready_count == 0:
                logger.warning("上推净额结算网络出现死锁（疑似图环），强制中断循环。")
                break
            # endregion

            # region 创造ready_parents，从merged取出能结算的数据，userId重命名为READY_PID
            ready_parents = merged[ready_mask][['user_id']].rename(columns={'user_id': 'READY_PID'})
            # endregion

            # region 找到这些 ready 父节点的直属孩子
            children = merged[['user_id', 'compressed_parent_id', 'CURRENT_GPV']].merge(
                ready_parents, left_on='compressed_parent_id', right_on='READY_PID', how='inner'
            )
            # endregion

            # region 从父节点的直属子节点中找出CURRENT_GPV最小的子节点，如果CURRENT_GPV相同，取userId最大的行
            # 聚合compressed_parent_id，每个父节点先找出最小 CURRENT_GPV；
            min_vals = children.groupby('compressed_parent_id').agg({'CURRENT_GPV': 'min'}).reset_index()
            # 把 CURRENT_GPV 等于最小值的孩子全部筛出来；
            tied = children.merge(min_vals, on=['compressed_parent_id', 'CURRENT_GPV'], how='inner')
            # 对于 GPV 相同的平局，按 USER_ID 降序取第一条（即取最大的 user_id）
            # 在这些“最小值候选孩子”里取 user_id 最大的那个。
            max_uid_vals = tied.groupby('compressed_parent_id').agg({'user_id': 'max'}).reset_index()
            # 从 tied 这批“最小 CURRENT_GPV 候选孩子”里面，筛出 user_id 等于最大 user_id 的那一条，得到最终被选中的孩子。
            chosen = tied.merge(max_uid_vals, on=['compressed_parent_id', 'user_id'], how='inner')
            # 极限防呆兜底
            chosen = chosen.drop_duplicates(subset=['compressed_parent_id'])
            # endregion

            # region 生成父级加钱、子级扣钱
            gains = chosen[['compressed_parent_id', 'CURRENT_GPV']].rename(
                columns={'compressed_parent_id': 'user_id', 'CURRENT_GPV': 'STEP_GAIN'})
            losses = chosen[['user_id', 'CURRENT_GPV']].rename(
                columns={'user_id': 'user_id', 'CURRENT_GPV': 'STEP_LOSS'})
            # endregion

            # region 先把加业绩、扣业绩合并回 snapshot、再把“本轮完成结算的父节点”标记合并进来
            snapshot = snapshot.merge(gains, on='user_id', how='left').merge(losses, on='user_id', how='left')

            # 消除同款 Anti-pattern：改用 on='user_id'，并以 MARK_FLAG 标记本轮已结算父节点
            mark_df = ready_parents.rename(columns={'READY_PID': 'user_id'})
            mark_df['MARK_FLAG'] = 1
            snapshot = snapshot.merge(mark_df, on='user_id', how='left')
            # endregion

            # region 执行CURRENT_GPV加减和更改RESOLVED
            def _apply_step(df):
                df['STEP_GAIN'] = df['STEP_GAIN'].fillna(0).astype('int64')
                df['STEP_LOSS'] = df['STEP_LOSS'].fillna(0).astype('int64')
                df['CURRENT_GPV'] = (df['CURRENT_GPV'] + df['STEP_GAIN'] - df['STEP_LOSS']).astype('int64')
                # 依赖普通值列判空，不触碰关联键
                is_marked = ~df['MARK_FLAG'].isnull()
                df['RESOLVED'] = df['RESOLVED'] | is_marked
                return df
            # endregion

            # region 收尾将数据放到内存中
            snapshot = snapshot.map_partitions(_apply_step)
            snapshot = snapshot.drop(columns=['STEP_GAIN', 'STEP_LOSS', 'MARK_FLAG'])

            snapshot = client.persist(snapshot)
            dask_wait(futures_of(snapshot))
            iteration += 1
            # endregion

        # region 验证
        unresolved_final = snapshot[~snapshot['RESOLVED']].map_partitions(len).sum().compute()
        if unresolved_final > 0:
            raise RuntimeError(
                f"【致命错误】上推净额结算在 {iteration} 轮后仍有 {unresolved_final} 个节点未收敛，疑似存在死锁或网体过深！")
        # endregion

        # region GPV_REAL=CURRENT_GPV
        def _finalize_push_up(df):
            df['GPV_REAL'] = df['CURRENT_GPV']
            return df
        # endregion

        snapshot = snapshot.map_partitions(_finalize_push_up)
        return snapshot

    # =====================================================================
    # 核心网体紧缩与法定快照生成
    # =====================================================================
    def _reconstruct_elite_snapshot(self,
                                    period_num: int,
                                    calc_month: int,
                                    ddf_users: dask_cudf.DataFrame,
                                    ddf_stats: dask_cudf.DataFrame) -> dask_cudf.DataFrame:
        client = get_client()
        logger.info("开始在 GPU 中执行网体紧缩，生成法定快照...")

        # region ddf_stats_clean验证并初始化
        self._require_columns(ddf_stats, ['user_id'] + REQUIRED_STATS_COLS, 'UserStats')

        ddf_stats_clean = ddf_stats[['user_id'] + REQUIRED_STATS_COLS].copy()
        assert_integer_amount_dtype(
            ddf_stats_clean._meta, ['gpv_real', 'gpv_unreal'], 'UserStats'
        )
        ddf_stats_clean['user_id'] = ddf_stats_clean['user_id'].astype('int64')
        ddf_stats_clean['rank'] = ddf_stats_clean['rank'].fillna(0).astype('int32')
        ddf_stats_clean['is_elite'] = ddf_stats_clean['is_elite'].fillna(False).astype('bool')
        ddf_stats_clean['gpv_real'] = ddf_stats_clean['gpv_real'].fillna(0).astype('int64')
        ddf_stats_clean['gpv_unreal'] = ddf_stats_clean['gpv_unreal'].fillna(0).astype('int64')
        # endregion

        # region ddf_edges_clean初始化
        ddf_edges_clean = ddf_users[['src', 'dst']].rename(columns={'src': 'user_id', 'dst': 'parent_id'})
        ddf_edges_clean['user_id'] = ddf_edges_clean['user_id'].astype('int64')
        ddf_edges_clean['_has_relation'] = 1
        # endregion

        # region 创建ddf_tree ddf_stats_clean左联ddf_edges_clean
        ddf_tree = ddf_stats_clean.merge(ddf_edges_clean, on='user_id', how='left')

        matched_edges = ddf_tree[ddf_tree['_has_relation'] == 1].map_partitions(len).sum().compute()
        if matched_edges == 0 and len(ddf_tree.head(1)) > 0:
            raise ValueError(
                "【致命错误】边表与统计表关联匹配率为0！请检查 ddf_users 是否传入了被 cuGraph renumber 过的 ID！")
        # endregion

        # region 过滤出没有上级的用户
        orphan_count = ddf_tree['_has_relation'].isnull().sum().compute()
        if orphan_count > 0:
            logger.warning(f"发现 {orphan_count} 个 UserStats 用户在图关系中缺失，按业务规则予以静默过滤排除。")
            ddf_tree = ddf_tree[ddf_tree['_has_relation'].notnull()]
        # endregion

        # region 将df_tree加载到内存中
        ddf_tree['parent_id'] = ddf_tree['parent_id'].astype('float64').fillna(0).astype('int64')
        ddf_tree['compressed_parent_id'] = ddf_tree['parent_id']
        ddf_tree = client.persist(ddf_tree)
        dask_wait(futures_of(ddf_tree))
        # endregion

        # ----------------------------------------------------
        # 1. 倍增式指针跳跃
        # ----------------------------------------------------
        iteration = 0
        is_converged = False

        # region 网体紧锁，保证上级的rank>=10
        while iteration < self._max_compression_depth:
            iteration += 1
            # region 创建ddf_lookup -> ddf_tree copy
            ddf_lookup = ddf_tree[['user_id', 'compressed_parent_id', 'rank']].rename(columns={
                'user_id': 'L_ID', 'compressed_parent_id': 'L_PID', 'rank': 'L_RANK'
            })
            # endregion

            # region 创建merged -> ddf_tree左联ddf_lookup compressed_parent_id=L_ID
            merged = ddf_tree.merge(ddf_lookup, left_on='compressed_parent_id', right_on='L_ID', how='left')
            merged['L_RANK'] = merged['L_RANK'].fillna(0)
            # endregion

            # region 当前上级不是系统根节点、上级只是普通的非达标会员 跳出循环
            needs_skip = (merged['compressed_parent_id'] != 0) & (merged['L_RANK'] < 10)
            # endregion

            # region 有没有人挂在“未达 Elite 的上级”下面 如果为0 跳出循环
            still_jumping = merged[needs_skip].map_partitions(len).sum().compute()
            if still_jumping == 0:
                is_converged = True
                ddf_tree = merged
                logger.info(f"网体紧缩在第 {iteration} 轮极速收敛。")
                break
            # endregion

            # region 网体紧缩 / 跳过未达标中间人
            merged['compressed_parent_id'] = merged['compressed_parent_id'].where(~needs_skip, merged['L_PID'])
            ddf_tree = merged[
                ['user_id', 'parent_id', 'rank', 'is_elite', 'gpv_real', 'gpv_unreal', 'compressed_parent_id']]
            ddf_tree = client.persist(ddf_tree)
            dask_wait(futures_of(ddf_tree))
            # endregion
        # endregion

        if not is_converged:
            raise RuntimeError(f"网体紧缩达到 {self._max_compression_depth} 轮未收敛！")

        # ----------------------------------------------------
        # 2. 过滤有效级别，交由嵌套网络进行净额结算
        # ----------------------------------------------------
        # 过滤底层用户不是elite以上的行
        snapshot = ddf_tree[ddf_tree['rank'] >= 10].copy()
        # 计算CURRENT_GPV
        snapshot = self._apply_nested_push_up_net(snapshot, client)

        # ----------------------------------------------------
        # 3. 生成输出快照
        # ----------------------------------------------------
        # region 组装计算结果
        snapshot['PERIOD_NUM'] = period_num
        snapshot['CALC_MONTH'] = calc_month
        snapshot['USER_ID'] = snapshot['user_id']
        snapshot['PARENT_UID'] = snapshot['compressed_parent_id']
        snapshot['GPV_UNREAL'] = snapshot['gpv_unreal'].fillna(0).astype('int64')
        snapshot['LAST_ELITE_CALC_ID'] = snapshot['rank']

        ddf_calc_lv_elite = snapshot[REQUIRED_ELITE_COLS]
        ddf_calc_lv_elite = client.persist(ddf_calc_lv_elite)
        dask_wait(futures_of(ddf_calc_lv_elite))
        # endregion

        return ddf_calc_lv_elite

    # =====================================================================
    # 发钱主流程
    # =====================================================================
    def execute_batch(self,
                      period_num: int,
                      calc_month: int,
                      ddf_users: dask_cudf.DataFrame,
                      ddf_stats: dask_cudf.DataFrame,
                      ddf_user: dask_cudf.DataFrame,
                      ddf_user_perf: Optional[dask_cudf.DataFrame] = None) -> Dict[str, dask_cudf.DataFrame]:

        # region 参数与配置快照验证
        self.config_snapshot.assert_run(period_num, calc_month)
        client = get_client()
        logger.info(f"启动期数: {period_num}, 月份: {calc_month} 奖金流...")
        self._require_columns(ddf_user, REQUIRED_USER_COLS, 'UserInfo维表')
        ddf_stats = self._resolve_user_id(ddf_stats)
        # endregion

        # 1. 动态生成合规快照
        # region 生成计算real后的表格
        ddf_calc_lv_elite = self._reconstruct_elite_snapshot(period_num, calc_month, ddf_users, ddf_stats)
        # endregion

        # region 当ddf_user_perf为空时，组装ddf_user_perf
        if ddf_user_perf is None:
            logger.info("未提供外部活跃表，将基于 UserStats.pv >= 30 内部派生 IS_ACTIVE")
            self._require_columns(ddf_stats, ['pv'], 'UserStats (用于派生活跃)')
            ddf_perf = ddf_stats[['user_id', 'pv']].rename(columns={'user_id': 'USER_ID'}).copy()
            ddf_perf['PERIOD_NUM'] = period_num
            ddf_perf['IS_ACTIVE'] = (ddf_perf['pv'].fillna(0) >= 30 * PV_SCALE).astype('int32')
            ddf_user_perf = ddf_perf[REQUIRED_PERF_COLS]
        # endregion

        # region 创造ddf_perf 从ddf_user_perf过滤出当前期的数据
        self._require_columns(ddf_user_perf, REQUIRED_PERF_COLS, 'AR_USER_PERF')
        ddf_perf = ddf_user_perf[ddf_user_perf['PERIOD_NUM'] == period_num]
        # endregion

        # 2. 严格去重熔断
        # region 数据验证
        ddf_elite = self._dedup_or_raise(
            ddf_calc_lv_elite, value_cols=REQUIRED_ELITE_COLS, key_cols=['PERIOD_NUM', 'CALC_MONTH', 'USER_ID'],
            name='AR_CALC_LV_ELITE')
        ddf_perf = self._dedup_or_raise(
            ddf_perf, value_cols=REQUIRED_PERF_COLS, key_cols=['PERIOD_NUM', 'USER_ID'], name='AR_USER_PERF')
        ddf_user = self._dedup_or_raise(
            ddf_user, value_cols=REQUIRED_USER_COLS, key_cols=['id'], name='UserInfo维表')
        # endregion

        # ======================================================
        # 步骤一：提取合格者 + 汇总下级真实业绩
        # ======================================================
        # 筛选出PE以上的数据
        eligible_users = ddf_elite[ddf_elite['LAST_ELITE_CALC_ID'] >= 20]

        # region 创建children_gpv_sum -> 对PARENT_UID分组 对GPV_REAL进行求和，'PARENT_UID': 'USER_ID', 'GPV_REAL': 'CHILDREN_GPV_REAL'
        assert_integer_amount_dtype(ddf_elite._meta, ['GPV_REAL', 'GPV_UNREAL'], 'AR_CALC_LV_ELITE')
        children_all = ddf_elite[['USER_ID', 'PARENT_UID', 'GPV_REAL']]
        children_gpv_sum = children_all.groupby('PARENT_UID').agg({'GPV_REAL': 'sum'}).reset_index()
        assert_integer_amount_dtype(children_gpv_sum._meta, ['GPV_REAL'], 'PE children aggregate')
        children_gpv_sum = children_gpv_sum.rename(columns={'PARENT_UID': 'USER_ID', 'GPV_REAL': 'CHILDREN_GPV_REAL'})
        # endregion

        # region 创建mid1 -> eligible_users左联children_gpv_sum
        mid1 = eligible_users.merge(children_gpv_sum, on='USER_ID', how='left')
        mid1['CHILDREN_GPV_REAL'] = mid1['CHILDREN_GPV_REAL'].fillna(0).astype('int64')
        mid1['GPV_UNREAL'] = mid1['GPV_UNREAL'].fillna(0).astype('int64')
        # endregion

        # ======================================================
        # 步骤二：计算基数与奖金金额 (整数截断)
        # ======================================================
        # region 计算出TOTAL_BASE_GPV -> CHILDREN_GPV_REAL+GPV_UNREAL
        mid1['TOTAL_BASE_GPV'] = (
            mid1['CHILDREN_GPV_REAL'] + mid1['GPV_UNREAL']
        ).astype('int64')
        assert_integer_amount_dtype(mid1._meta, ['TOTAL_BASE_GPV'], 'PE bonus base')
        mid1['PE_RATE_PPM'] = self._pro_elite_rate_ppm
        # endregion

        # region 计算出奖金
        mid1 = mid1.map_partitions(self._apply_truncate)
        # endregion

        # ======================================================
        # 步骤三：关联信息与落盘
        # ======================================================
        # region mid1左联ddf_user 获取用户信息
        # 先 rename，再直接使用 on='USER_ID'，避免 drop(id) 触发 KeyError
        user_info_mid = ddf_user[['id', 'country_id', 'user_name', 'real_name']].rename(columns={'id': 'USER_ID'})
        mid1 = mid1.merge(user_info_mid, on='USER_ID', how='left')
        mid1 = mid1.rename(columns={'country_id': 'COUNTRY_ID', 'user_name': 'USER_NAME', 'real_name': 'REAL_NAME'})
        # endregion

        # region mid1左联ddf_perf 获取IS_ACTIVE
        mid1 = mid1.merge(ddf_perf[['USER_ID', 'IS_ACTIVE']], on='USER_ID', how='left')
        mid1['IS_ACTIVE'] = mid1['IS_ACTIVE'].fillna(0).astype('int32')
        # endregion

        # region mid1新增id列 并将mid1放置内存
        meta_df = mid1._meta.copy()
        meta_df['BONUS_ID'] = cudf.Series(dtype='object')
        mid1 = mid1.map_partitions(self._generate_uuids, id_col_name='BONUS_ID', meta=meta_df)

        mid1 = mid1.rename(columns={'BONUS_ID': 'ID'})
        ar_calc_bonus_pe = mid1[MAIN_COLUMNS]

        ar_calc_bonus_pe = client.persist(ar_calc_bonus_pe)
        dask_wait(futures_of(ar_calc_bonus_pe))
        # endregion

        # ======================================================
        # 步骤四：处理 Source 追溯明细表
        # ======================================================
        # region 初始化
        source_parts = []
        static_pe_rate_ppm = self._pro_elite_rate_ppm
        # endregion

        # region 创造detaila -> 直属下级真实业绩
        # 先过滤掉 GPV_REAL <= 0 的下级，只保留有真实贡献的节点，并把 USER_ID 改名为 SOURCE_USER_ID
        valid_children = children_all[children_all['GPV_REAL'] > 0].rename(columns={'USER_ID': 'SOURCE_USER_ID'})
        detail_a = eligible_users[['PERIOD_NUM', 'CALC_MONTH', 'USER_ID']].merge(
            valid_children, left_on='USER_ID', right_on='PARENT_UID', how='inner')

        try:
            len_a = int(detail_a.map_partitions(len).sum().compute())
        except Exception:
            len_a = 0

        if len_a > 0:
            # region 补齐user和SOURCE_USER的用户信息和user的IS_ACTIVE
            # 分别 rename 左右关联表主键，并用 on= 合并，规避 drop
            user_info_bonus = ddf_user[['id', 'user_name', 'real_name']].rename(columns={'id': 'USER_ID'})
            detail_a = detail_a.merge(user_info_bonus, on='USER_ID', how='left')

            user_info_source = ddf_user[['id', 'user_name', 'real_name']].rename(columns={'id': 'SOURCE_USER_ID'})
            detail_a = detail_a.merge(user_info_source, on='SOURCE_USER_ID', how='left', suffixes=('_BONUS', '_SOURCE'))

            detail_a = detail_a.merge(ddf_perf[['USER_ID', 'IS_ACTIVE']], on='USER_ID', how='left')
            # endregion

            # region 补齐REAL和UNREAL相关信息
            detail_a['SOURCE_GPV'] = detail_a['GPV_REAL']
            detail_a['SOURCE_GPV_UNREAL'] = 0
            detail_a['PE_RATE_PPM'] = static_pe_rate_ppm
            # endregion

            # region 将detail_a添加到source_parts
            detail_a = detail_a.rename(columns={
                'USER_ID': 'BONUS_USER_ID',
                'user_name_BONUS': 'BONUS_USER_NAME',
                'real_name_BONUS': 'BONUS_REAL_NAME',
                'user_name_SOURCE': 'SOURCE_USER_NAME',
                'real_name_SOURCE': 'SOURCE_REAL_NAME',
            })
            source_parts.append(detail_a[SOURCE_COLUMNS])
            # endregion
        # endregion

        # region 创造detailb -> 本人虚拟业绩来源
        detail_b = eligible_users[eligible_users['GPV_UNREAL'] > 0][
            ['PERIOD_NUM', 'CALC_MONTH', 'USER_ID', 'GPV_UNREAL']]

        try:
            len_b = int(detail_b.map_partitions(len).sum().compute())
        except Exception:
            len_b = 0

        # region 给 detail_b 补用户信息和活跃状态
        if len_b > 0:
            # 同样先 rename 再 on= 合并
            user_info_b = ddf_user[['id', 'user_name', 'real_name']].rename(columns={'id': 'USER_ID'})
            detail_b = detail_b.merge(user_info_b, on='USER_ID', how='left')

            detail_b = detail_b.merge(ddf_perf[['USER_ID', 'IS_ACTIVE']], on='USER_ID', how='left')

            detail_b['SOURCE_USER_ID'] = detail_b['USER_ID']
            detail_b['BONUS_USER_NAME'] = detail_b['user_name']
            detail_b['BONUS_REAL_NAME'] = detail_b['real_name']
            detail_b['SOURCE_USER_NAME'] = detail_b['user_name']
            detail_b['SOURCE_REAL_NAME'] = detail_b['real_name']

            detail_b['SOURCE_GPV'] = 0
            detail_b['SOURCE_GPV_UNREAL'] = detail_b['GPV_UNREAL'].astype('int64')
            detail_b['PE_RATE_PPM'] = static_pe_rate_ppm

            detail_b = detail_b.rename(columns={'USER_ID': 'BONUS_USER_ID'})
            source_parts.append(detail_b[SOURCE_COLUMNS])
        # endregion
        # endregion

        # region 创造ar_calc_bonus_pe_source -> 合并 detail_a 和 detail_b
        if source_parts:
            ar_calc_bonus_pe_source = dask_cudf.concat(source_parts, ignore_index=True)
            ar_calc_bonus_pe_source['IS_ACTIVE'] = ar_calc_bonus_pe_source['IS_ACTIVE'].fillna(0).astype('int32')
        else:
            empty_meta = pd.DataFrame(columns=SOURCE_COLUMNS)
            for col in ['SOURCE_GPV', 'SOURCE_GPV_UNREAL', 'PE_RATE_PPM']:
                empty_meta[col] = pd.Series(dtype='int64')
            empty_meta['IS_ACTIVE'] = pd.Series(dtype='int32')

            empty_gdf = cudf.from_pandas(empty_meta)
            ar_calc_bonus_pe_source = dask_cudf.from_cudf(empty_gdf, npartitions=1)

        ar_calc_bonus_pe_source = client.persist(ar_calc_bonus_pe_source)
        dask_wait(futures_of(ar_calc_bonus_pe_source))
        # endregion

        return {
            'AR_CALC_BONUS_PE': ar_calc_bonus_pe,
            'AR_CALC_BONUS_PE_SOURCE': ar_calc_bonus_pe_source,
        }