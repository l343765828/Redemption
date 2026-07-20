from typing import List


# 将List转换成kafka消息内容
def json_list_to_array_bytes(rows: List[str], encoding: str = "utf-8") -> bytes:
    # 这里直接假设 rows 已经是一整个 list，可以用 len(rows), rows[0] 等
    if not rows:
        return b"[]"
    # 保持此前逻辑
    json_array = "[" + ",".join(rows) + "]"
    return json_array.encode(encoding)
