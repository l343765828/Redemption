from dask.distributed import Client
from redis_om import Migrator
from Model.User.UserLevel import UserLevel
from Model.User.UserStats import UserStats

ELITE_MARK = 1000
VIRTUAL_MARK = 2000
SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"


class UserStatsService:

    # =================================================================
    # 辅助方法
    # =================================================================
    @staticmethod
    def _bump_highest_rank(user: UserStats) -> None:
        """
        高水位维护:只升不降。

        每次 rank 评定完成后调用,把 user.highest_rank 推到 max(历史, 当前)。
        rank 下降时不动作,与"历史最高奖衔"语义一致。

        合并依据:UserHistoricalStats 已被废弃,历史最高直接落在 UserStats 上。
        EliteHighestService 期末拍快照时直接读 highest_rank,不再做高水位比对。
        """
        cur = user.rank or 0
        hist = user.highest_rank or 0
        if cur > hist:
            user.highest_rank = cur

    # =================================================================
    # 模拟数据造数逻辑
    # =================================================================
    """
    替换 UserStatsService.init_debug_data 的版本。
    使用 tb_user.sql 已有的树形结构,构造一条 SE 链以便完整测试 Honor / HonorHigh / Leadership 三段管道。

    物理树(取自 tb_user.sql):

             5 (root)
             |
             4
             |
             3
            / \
           1   2
          /|    \
         9 13   10

    构造方案(全部为 SE,rank=3):  5,4,3,1,2
    非 SE,纯下单业绩:             9,10,13
    其余 6,7,8,11,12: gpv=0(沉默节点,不影响计算)

    GPV 取值规则(参考 HonorLevelGPUService 内部口径):
    - gpv >= 2000  → gpv_real=1000, gpv_unreal=gpv-1000
    - 1000<=gpv<2000 → gpv_real=gpv, gpv_unreal=0
    - gpv<1000     → gpv_real=0, gpv_unreal=0

    把这段方法整个粘到 UserStatsService 里替换原来的 init_debug_data 即可。
    """
    def init_debug_data(self):
        """
        生产 SE 链,让 HonorLevelGPUService/HighService/LeadershipBonusService 有完整可测的产出。

        SE 链路示意(用户编号 / GPV / rank):
            5 (gpv=4000, rank=3)  ← 顶端 SE
              └─ 4 (gpv=3500, rank=3)
                   └─ 3 (gpv=3000, rank=3)
                        ├─ 1 (gpv=2500, rank=3)
                        │    ├─ 9 (gpv=2500, rank=0) → unreal 1500 给 1, real 1000 越级给 3
                        │    └─ 13(gpv=1500, rank=0) → real 1500 越级给 3(因为 1 是 SE 直推父)
                        └─ 2 (gpv=2200, rank=3)
                             └─ 10(gpv=1300, rank=0) → real 1300 越级给 3
        """
        # 默认沉默节点(无业绩)
        silent_users = ["6", "7", "8", "11", "12"]

        # 形如 user_id -> (gpv, rank, is_elite)
        user_setup = {
            # ---- SE 链 (rank=3, last_elite_calc_id=30) ----
            "5": (4000, 3, True),
            "4": (3500, 3, True),
            "3": (3000, 3, True),
            "1": (2500, 3, True),
            "2": (2200, 3, True),
            # ---- 下单贡献者 (rank=0,业绩供给上方 SE) ----
            "9": (2500, 0, False),  # 给 1 上贡 unreal=1500;real=1000 越级给 3
            "13": (1500, 0, False),  # 1 是 SE 父,real=1500 越级到 grandpa(3)
            "10": (1300, 0, False),  # 2 是 SE 父,real=1300 越级到 grandpa(3)
        }
        for uid in silent_users:
            user_setup[uid] = (0, 0, False)

        print("开始初始化 Redis 调试数据(SE 链版)...")

        for uid, (gpv, rank, is_elite) in user_setup.items():
            UserStats(
                pk=str(uid),
                id=str(uid),
                user_id=uid,
                pv=gpv,  # 单测时把 pv 直接和 gpv 对齐
                gpv=gpv,
                contrib=0,
                is_elite=is_elite,
                rank=rank,
                # 初始化阶段:历史最高与当前 rank 对齐(代表造数时刻就是该用户的历史最高)
                highest_rank=rank,
                qualified_legs=set(),
                virtual_width=0,
            ).save()
            print(f"  user={uid}  gpv={gpv}  rank={rank}  highest_rank={rank}  is_elite={is_elite}")

        Migrator().run()
        print("✅ Redis 调试数据写入完成。")

    def clear_all_redis_data(self):
        """
        核弹清除：清空当前 Redis 数据库中的【所有】键值对。
        注意：仅限纯测试环境使用！
        """
        print("开始清空当前 Redis 数据库...")
        from redis_om import get_redis_connection
        try:
            conn = get_redis_connection(
                host="192.168.18.149",
                port=36378,
                db=0,
                password="123456",
                decode_responses=True
            )
            conn.flushdb()
            print("✅ 当前 Redis 数据库已彻底清空！")
        except Exception as e:
            print(f"❌ 清空数据库时发生错误: {e}")

    def update_elite_performance(self, user_id: str, bv: int):
        print("开始了")

        # region 从redis获取当前用户信息，并记录当前等级和是否为elite
        try:
            current_user = UserStats.get(user_id)
            prev_is_elite = current_user.is_elite
            prev_rank = current_user.rank
        except Exception as e:
            print(f"错误: 找不到用户 {user_id} ({e})")
            return
        # endregion

        # region 计算当前用户的pv和gpv
        current_user.pv = (current_user.pv or 0) + bv
        current_user.gpv = (current_user.gpv or 0) + bv
        # endregion

        # region 判断该用户是否能成为elite，或是elite降级
        is_self_elite = current_user.gpv >= ELITE_MARK
        current_user.is_elite = is_self_elite
        # endregion

        # region 计算虚拟宽度的虚拟下级数量
        if current_user.gpv >= VIRTUAL_MARK:
            current_user.virtual_width = current_user.gpv // ELITE_MARK
        else:
            current_user.virtual_width = 0
        # endregion

        # region 综合评定当前用户的最终 Rank
        total_elite_width = len(current_user.qualified_legs) + current_user.virtual_width
        if total_elite_width >= 3:
            current_user.rank = UserLevel.SUPER_ELITE
            print(f"👑 恭喜！用户 {user_id} 达到 Super Elite (宽度: {total_elite_width})！")
        elif (is_self_elite and total_elite_width >= 1) or (not is_self_elite and total_elite_width >= 2):
            current_user.rank = UserLevel.PRO_ELITE
            print(f"🌟 恭喜！用户 {user_id} 达到 Pro Elite (宽度: {total_elite_width})！")
        elif is_self_elite:
            current_user.rank = UserLevel.ELITE
            print(f"🎉 恭喜！用户 {user_id} GPV达到 {current_user.gpv}，晋升/保持 Elite！")
        else:
            current_user.rank = UserLevel.NOTHING
        # endregion

        # region 高水位维护:只升不降
        self._bump_highest_rank(current_user)
        # endregion

        # region 计算临时贡献度，如果当前gpv小于1000，临时贡献度为当前gpv，否则为0
        new_contrib = current_user.gpv if current_user.gpv < ELITE_MARK else 0
        # endregion

        # region 计算贡献差值：临时贡献度-当前贡献度
        current_contrib = current_user.contrib or 0
        delta_update = new_contrib - current_contrib
        # endregion

        # region 赋值当前贡献度，并保存到redis中
        current_user.contrib = current_contrib + delta_update
        current_user.save()
        # endregion

        # region 当贡献差值为0时，并且 用户的奖衔/Elite资格也没变的情况下，停止向上贡献
        # 注:highest_rank 只在 rank 上升时变化,而 rank 上升必然导致 prev_rank != current_user.rank,
        #    会被下面的 status_changed 捕获,所以无需把 highest_rank 加入终止条件。
        status_changed = (prev_is_elite != current_user.is_elite) or (prev_rank != current_user.rank)
        if delta_update == 0 and not status_changed:
            print(f"用户 {user_id} 的 delta_update 为 0，且资格未变，停止向上贡献。")
            return
        # endregion

        # region 从图谱中获取该用户的所有上级
        client = Client(SCHEDULE_ADDRESS)

        actor = client.get_dataset("graph_actor")
        actor2 = actor.result()
        df_bfs = actor2.get_allparent(user_id).result()
        print("\nBFS Results:")
        print(df_bfs)

        # region 将结果按level的正序排序
        # 一次性将 cuDF(显存) 计算结果转为 Pandas(内存)，
        # 将 Pandas 结果按 level 升序，并提取 descendant 和 predecessor
        pdf = df_bfs.sort_values("level", ascending=True)
        ancestors_info = pdf[["descendant", "predecessor"]].astype(str).to_dict("records")
        # endregion

        # endregion

        # region 计算父级的gpv
        models_to_save = []
        # 建立一个内存缓存字典：存放这轮冒泡中已经处理过的节点，避免重复查 Redis
        processed_nodes = {user_id: current_user}
        for row in ancestors_info:

            # region 从redis中获取用户信息，并记录“等级、直属下线的数量、是否为elite”
            ancestor_id = row["descendant"]
            # leg_id 是 ancestor 的直属下级分支来源
            leg_id = row["predecessor"]
            try:
                ancestor = UserStats.get(ancestor_id)
                prev_anc_is_elite = ancestor.is_elite
                prev_anc_rank = ancestor.rank
                prev_anc_width = len(ancestor.qualified_legs)
            except Exception as e:
                print(f"警告: 无法从 Redis 获取上级用户 {ancestor_id} 的信息 ({e})")
                continue
            # endregion

            # region 计算gpv：当前gpv+下级的贡献差值
            ancestor.gpv = (ancestor.gpv or 0) + delta_update
            # endregion

            # region 判断该用户是否能成为elite，或是elite降级
            is_self_elite = ancestor.gpv >= ELITE_MARK
            ancestor.is_elite = is_self_elite
            # endregion

            # region 计算虚拟宽度的虚拟下级数量
            if ancestor.gpv >= VIRTUAL_MARK:
                ancestor.virtual_width = ancestor.gpv // ELITE_MARK
            else:
                ancestor.virtual_width = 0
            # endregion

            # region 获取直属下级的实体
            leg_node = processed_nodes.get(leg_id)
            if leg_node is None:
                leg_node = UserStats.get(leg_id)
            # endregion

            # region 计算这个直属下级本身拥有的总宽度
            leg_total_width = len(leg_node.qualified_legs) + (leg_node.virtual_width or 0)
            # endregion

            # region 判断直属下级这条线是否合格，这条线合格的条件是：
            # 1. 前驱节点自己是 Elite (rank >= 1)
            # 2. 或者前驱节点自己不是 Elite，但他底下的子孙有 Elite (leg_total_width > 0)
            is_leg_qualified = (leg_node.rank >= UserLevel.ELITE) or (leg_total_width > 0)
            # endregion

            # region 维护当前节点的合格线集合
            if is_leg_qualified:
                ancestor.qualified_legs.add(leg_id)
            else:
                ancestor.qualified_legs.discard(leg_id)
            # endregion

            # region 计算总宽度并评定 Rank
            total_elite_width = len(ancestor.qualified_legs) + (ancestor.virtual_width or 0)

            # 严格应用 Pro Elite 晋升双条件
            if total_elite_width >= 3:
                ancestor.rank = UserLevel.SUPER_ELITE
                print(f"👑 {ancestor_id} 晋升/保持 Super Elite (拥有 {total_elite_width} 个合格宽度)")
            elif (is_self_elite and total_elite_width >= 1) or (not is_self_elite and total_elite_width >= 2):
                ancestor.rank = UserLevel.PRO_ELITE
                print(f"🌟 {ancestor_id} 晋升/保持 Pro Elite (拥有 {total_elite_width} 个合格宽度)")
            elif is_self_elite:
                ancestor.rank = UserLevel.ELITE
                print(f"🎉 {ancestor_id} GPV达标，晋升/保持 Elite")
            else:
                ancestor.rank = UserLevel.NOTHING
                print(f"⚠️ {ancestor_id} 目前无奖衔")

            # region 高水位维护:只升不降,合并自原 EliteHighestService
            self._bump_highest_rank(ancestor)
            # endregion

            # 把计算好的 ancestor 放入内存缓存，供下一次循环(他的更上一级)判定使用
            processed_nodes[ancestor_id] = ancestor
            # endregion

            # region 计算临时贡献度，如果当前gpv小于1000，临时贡献度为当前gpv，否则为0
            ancestor_new_contrib = ancestor.gpv if ancestor.gpv < ELITE_MARK else 0
            # endregion

            # region 计算贡献差值：临时贡献度-当前贡献度
            ancestor_current_contrib = ancestor.contrib or 0
            next_delta_update = ancestor_new_contrib - ancestor_current_contrib
            # endregion

            # region 赋值当前贡献度
            ancestor.contrib = ancestor_current_contrib + next_delta_update
            # 将修改后的对象加入待保存列表
            models_to_save.append(ancestor)
            # endregion

            # region 当贡献差值为0时，且当前节点的资格没有发生任何蝴蝶效应，停止向上贡献
            # 注:highest_rank 只在 rank 上升时变化,会被 prev_anc_rank != ancestor.rank 捕获,
            #    无需单独加入终止条件。
            delta_update = next_delta_update
            anc_status_changed = (prev_anc_is_elite != ancestor.is_elite) or \
                                 (prev_anc_rank != ancestor.rank) or \
                                 (prev_anc_width != len(ancestor.qualified_legs))
            if delta_update == 0 and not anc_status_changed:
                print(f"到达上级用户 {ancestor_id} 时，传导给上级的 delta_update 为 0，且资格状态未变，安全停止向上冒泡。")
                break
            # endregion
        # endregion

        # region 集中批量 I/O 写入
        if models_to_save:
            # 获取当前模型使用的 redis 连接
            db = UserStats.db()
            # 创建一个 Pipeline 管道
            pipe = db.pipeline()

            for model in models_to_save:
                # 传入 pipeline 参数！
                # 此时绝不会产生真实的 Redis 网络请求，而是将写指令暂存在本地管道中
                model.save(pipeline=pipe)

            # 极其关键的一步：一次性将所有组装好的写入指令打包发给 Redis！
            # 无论你有 10 个上级还是 100 个上级，这里只有【1次网络通信】
            pipe.execute()

            print(f"=== 集中写入完成：通过 Pipeline 批量更新了 {len(models_to_save)} 个上级节点的数据 ===")
        else:
            print("=== 没有上级节点需要更新 ===")
        # endregion


def main():
    svc = UserStatsService()
    # svc.update_elite_performance("1", 30)

    # 1. 先清除旧数据
    svc.clear_all_redis_data()

    # 2. 重新预埋初始数据
    svc.init_debug_data()

    # 3. 执行测试逻辑
    print("\n--- 🚀 开始执行 update_elite_performance ---")
    svc.update_elite_performance(user_id="3", bv=50)


if __name__ == "__main__":
    main()
