from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
import datetime
import time

# 1. 定义测试间隔时间（例如：每 3 秒触发一次）
CHECK_INTERVAL_SECONDS = 3


# 2. 编写一个 Mock 的微批处理函数来代替实际业务逻辑
def run_micro_batch():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 🚀 触发微批处理测试...")

    # 你可以取消下面两行的注释，测试 max_instances=1 的防并发机制
    # print("   (模拟耗时 5 秒的操作...)")
    # time.sleep(5)

    print(f"[{now}] ✅ 微批处理完成！\n")


def start_scheduler():
    """
    使用 APScheduler 启动常驻调度器 (测试版)
    """
    print(f"🛠️ Honor 结算微批处理守护进程已启动 (测试模式)")
    print(f"⏱️ 调度策略: 每 {CHECK_INTERVAL_SECONDS} 秒固定触发一次\n")
    print("👉 提示: 按 Ctrl+C 可以测试优雅退出机制\n" + "-" * 50)
    # 每个线程执行一个任务，N个任务对应N个线程
    executors = {
        'default': ThreadPoolExecutor(20)
    }
    scheduler = BlockingScheduler(executors)

    # 添加定时任务
    scheduler.add_job(
        run_micro_batch,
        'interval',
        seconds=CHECK_INTERVAL_SECONDS,
        max_instances=1,  # 🛡️ 安全锁：防止前一个任务没跑完就启动下一个
        id='gpu_honor_recalc_job'  # 给任务命名，方便后续日志追踪
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        # 优雅退出的处理
        print("\n🛑 接收到退出信号，守护进程已安全关闭。")


if __name__ == "__main__":
    start_scheduler()