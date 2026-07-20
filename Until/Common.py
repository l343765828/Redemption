from deltalake import DeltaTable
import dask_cudf


# 读取delta文件
def read_delta_snapshot_files(delta_path, cols=None, npartitions=None):
    dt = DeltaTable(delta_path)

    # delta-rs 的 API 名称有 file_uris() / files()，视版本而定
    uris = dt.file_uris()  # list[str]
    # normalize paths (remove file:// if present)
    file_paths = [u.replace("file://", "") for u in uris]

    kwargs = {}
    if cols:
        kwargs["columns"] = cols
    if npartitions:
        kwargs["npartitions"] = npartitions

    # dask_cudf 能接受 file_paths 列表
    ddf = dask_cudf.read_parquet(file_paths, **kwargs)
    return ddf, dt.version()
