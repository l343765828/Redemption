import logging
from User.TopologyMutationService import TopologyMutationService
from Model.User.UserStats import UserStats
from Model.User.ChangeUserMsg import ChangeUserMsg
import time

logging.basicConfig(level=logging.INFO)

def run_test():
    target_id = "3"
    old_parent = "4"
    new_parent = "8"
    
    # 构造 CDC 变更消息
    # 将节点 3 的 parent 改为 8
    change_msg = ChangeUserMsg(
        id=target_id,
        user=target_id,
        parent=new_parent,
        op="u", # Update
        updatetime=int(time.time())
    )
    
    service = TopologyMutationService()
    
    print(f"\n>>> 开始执行拓扑变更事务: 节点 {target_id} 从 {old_parent} 转移到 {new_parent}")
    
    # 执行编排器 (内部包含：提取旧链 -> 更新图 -> 提取新链 -> 全量重算)
    service.orchestrate_topology_mutation(
        target_node_id=target_id,
        cdc_version=20260511001, # 模拟一个单调递增的 CDC 版本
        change_list=[change_msg]
    )

    print("\n>>> 变更执行完成，开始验证 Redis 数据...")
    
    # 验证受影响的节点
    # 1. 检查旧链路：4 和 5 应该失去了 3 的贡献，GPV 归零
    anc_old_4 = UserStats.get("4")
    anc_old_5 = UserStats.get("5")
    
    # 2. 检查新链路：8 应该获得了 3 的贡献，GPV 增加
    anc_new_8 = UserStats.get("8")
    
    # 3. 检查 Target 本身：GPV 应保持不变 (500)
    target = UserStats.get(target_id)

    print("-" * 30)
    print(f"节点 {target_id} (Target) GPV: {target.gpv} (预期: 500)")
    print(f"节点 4 (旧父) GPV: {anc_old_4.gpv} (预期: 0)")
    print(f"节点 5 (旧爷) GPV: {anc_old_5.gpv} (预期: 0)")
    print(f"节点 8 (新父) GPV: {anc_new_8.gpv} (预期: 500)")
    
    if anc_new_8.gpv == 500 and anc_old_4.gpv == 0:
        print("\n🎉 验证成功：业绩已准确从旧链路转移至新链路！")
    else:
        print("\n❌ 验证失败：业绩计算结果不符合预期。")

if __name__ == "__main__":
    run_test()