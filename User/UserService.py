from pathlib import Path
import User.GraphService as gsa
import User.UserInfoService as usa
from deltalake import DeltaTable
from Model.Config import DELTA_USER, DELTA_UNSERINFO
from dask.distributed import Client
import sys, importlib, tempfile, os, traceback

SCHEDULE_ADDRESS = "tcp://192.168.18.149:38786"


def add_path(p):
    import sys
    if p not in sys.path:
        sys.path.insert(0, p)
        return True
    return False


def check_env():
    info = {'sys_path': sys.path, 'tempdir': tempfile.gettempdir(), 'cwd': os.getcwd()}
    try:
        m = importlib.import_module('User')
        info['user_file'] = getattr(m, '__file__', None)
        info['import_ok'] = True
    except Exception as e:
        info['import_ok'] = False
        info['import_err'] = traceback.format_exc()
    return info


def loadAllUser():
    client = Client(SCHEDULE_ADDRESS)

    # region 将项目路径添加到sys.path，并测试是否能读取模块
    here = Path(__file__).resolve().parent
    project_root = str(here.parent)
    client.run(add_path, project_root)  # workers
    client.run_on_scheduler(add_path, project_root)  # scheduler（非常关键）
    print("workers:", client.run(check_env))
    try:
        print("scheduler:", client.run_on_scheduler(check_env))
    except Exception as e:
        print("run_on_scheduler failed:", e)
    print("路径添加完成")
    # endregion

    # region 获取delta版本号
    dt = DeltaTable(DELTA_USER)
    version = dt.version()
    # endregion

    # region 创建 actor
    actor_future = client.submit(gsa.GraphService, actor=True)
    actor = actor_future.result()
    # endregion

    # region 构建图
    remote_future = actor.run(msg_version=version, npartitions=1,
                              model_dir=DELTA_USER, renumber_disable=False)
    res = remote_future.result()
    # endregion

    # region 将graph_actor发布到schedule
    ds_name = "graph_actor"
    try:
        # 尝试显式取消已有 dataset（若不存在会抛异常）
        client.unpublish_dataset(ds_name)
        print(f"Unpublished existing dataset: {ds_name}")
    except Exception:
        # 忽略找不到或其它小错误
        pass
    client.publish_dataset(**{ds_name: actor_future})
    print("build res:", res)
    # endregion

    # region 创建 actor
    actor_future_userInfo = client.submit(usa.UserInfoService, actor=True)
    actor_userinfo = actor_future_userInfo.result()
    # endregion

    # region 构建图
    remote_future_userInfo = actor_userinfo.load_userinfo(userinfo_dir=DELTA_UNSERINFO, npartitions=2)
    res = remote_future_userInfo.result()
    # endregion

    # region 将graph_actor发布到schedule
    ds_name = "userinfo_actor"
    try:
        # 尝试显式取消已有 dataset（若不存在会抛异常）
        client.unpublish_dataset(ds_name)
        print(f"Unpublished existing dataset: {ds_name}")
    except Exception:
        # 忽略找不到或其它小错误
        pass
    client.publish_dataset(**{ds_name: actor_future_userInfo})
    print("build res2:", res)
    # endregion

    # 然后显式关闭 dask client（确保 loop 的有序关闭）
    try:
        client.close()
        print("Dask client closed")
    except Exception as e:
        print("Warning: client.close() failed:", e)


if __name__ == "__main__":
    loadAllUser()
