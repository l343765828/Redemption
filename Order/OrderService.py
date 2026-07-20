from Model.Order.OrderPayload import OrderPayload
from dask.distributed import Client


def main():
    client = Client("tcp://127.0.0.1:8786")

    actor = client.get_dataset("graph_actor")
    actor2 = actor.result()
    orders = [OrderPayload("ORD-001", 1, 199.9)]
    # bfs_result = actor2.run_bfs(orders).result()
    bfs_result = actor2.descendant_counts_via_bfs(5).result()
    # 选项 A: 在 driver 计算成 cudf.DataFrame（如果数据量适中）
    print("\nBFS Results:")
    print(bfs_result)
    # 然后显式关闭 dask client（确保 loop 的有序关闭）
    try:
        client.close()
        print("Dask client closed")
    except Exception as e:
        print("Warning: client.close() failed:", e)


if __name__ == "__main__":
    main()
