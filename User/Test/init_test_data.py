import time
from Model.User.UserStats import UserStats
import Model.User.UserLevel as UserLevel
from redis_om import get_redis_connection

# 连接测试环境 Redis
redis_conn = UserStats.db()

def init_redis_from_sql():
    print("开始清理并初始化测试数据...")
    # 清理旧数据 (生产环境慎用)
    redis_conn.flushall()

    # 根据 tb_user.txt 整理的关系 (id, parent)
    # 结构: 13,9 -> 1 -> 3;  10 -> 2 -> 3;  3 -> 4 -> 5;  7 -> 8
    user_relations = {
        '1': '3', '10': '2', '11': '0', '12': '0', '13': '1',
        '2': '3', '3': '4', '4': '5', '5': '0', '6': '0',
        '7': '8', '8': '0', '9': '1'
    }

    # 设定初始 PV (为了测试 Elite 截断和 GPV 冒泡)
    # 节点 13 和 10 设为 Elite (1000 PV)
    # 节点 9 设为 500 PV (贡献给上级)
    pv_map = {'13': 1000, '10': 1000, '9': 500}

    nodes = {}
    
    # 1. 第一遍：创建基础实体
    for uid in user_relations.keys():
        pv = pv_map.get(uid, 0)
        is_elite = pv >= 1000
        nodes[uid] = UserStats(
            pk=uid, id=uid, user_id=uid,
            pv=pv, gpv=pv, 
            is_elite=is_elite,
            rank=UserLevel.ELITE if is_elite else UserLevel.NOTHING,
            highest_rank=UserLevel.ELITE if is_elite else UserLevel.NOTHING,
            contrib=0 if is_elite else pv, # 已达标则贡献为0，未达标则贡献全部GPV
            qualified_legs=set()
        )

    # 2. 第二遍：模拟初始 GPV 冒泡 (简单模拟，仅为测试 TopologyMutationService 之前的初态)
    # 注意：这里只是为了让 Redis 里有数据，真正的重算会由 Service 完成
    nodes['1'].gpv = nodes['13'].contrib + nodes['9'].contrib # 0 + 500 = 500
    nodes['1'].contrib = 500
    nodes['2'].gpv = nodes['10'].contrib # 0
    nodes['2'].contrib = 0
    nodes['3'].gpv = nodes['1'].contrib + nodes['2'].contrib # 500
    nodes['3'].contrib = 500
    nodes['4'].gpv = nodes['3'].contrib # 500
    nodes['4'].contrib = 500
    nodes['5'].gpv = nodes['4'].contrib # 500

    # 3. 批量保存到 Redis
    for node in nodes.values():
        node.save()
    
    print("数据初始化完成。")
    print(f"当前节点 4 (旧父) 的 GPV: {nodes['4'].gpv}")
    print(f"当前节点 8 (新父) 的 GPV: {nodes['8'].gpv}")

if __name__ == "__main__":
    init_redis_from_sql()