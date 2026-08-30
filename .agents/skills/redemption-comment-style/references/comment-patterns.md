# Redemption Comment Patterns

Use these patterns as a compact reference for the style established in `User/UserStatsService.py:update_elite_performance`.

## 1. Simple logical paragraph

```python
# region 参数验证
if not order_id:
    raise ValueError("订单增量处理必须传入 order_id 以保证幂等")
# endregion
```

A distinct guard can be a region when it represents an important business/technical stage.

## 2. Initialization paragraph

```python
# region 初始化
period = str(period)
user_id = str(user_id)
done_key = f"system:idempotency:{period}:{order_id}:done"
lock_key = f"system:idempotency:{period}:{order_id}:lock"
# endregion
```

Group related setup; do not create one region per variable.

## 3. Calculation paragraph with semantic inline comments

```python
# region 计算新的贡献度以及贡献差值
old_contrib = current_user.contrib or 0
# 当前节点达到截断条件后，不再继续向上传递普通贡献度。
new_contrib = self._calc_contrib(current_user)
# 差值是本层对上一层的增量输入，而不是新的累计总值。
delta_update = new_contrib - old_contrib
current_user.contrib = new_contrib
# endregion
```

Inline comments should explain the domain meaning of the formula or state transition.

## 4. Branch-policy paragraph

```python
# region 早停: 贡献差值为 0 且自身资格未变 -> 不需要向上传导
if delta_update == 0 and not status_changed:
    ...
    return
# endregion
```

A region title may summarize the actual stop/branch condition when that condition is central to the logic.

## 5. Large-function phase + nested logical paragraphs

```python
# ---------------------------------------------------------
# Step 2: 自底向上处理祖先
# ---------------------------------------------------------
for idx, row in enumerate(ancestors_info):
    # region 获取父级节点的信息
    ...
    # endregion

    # region 判断直属下级这条线是否合格
    ...
    # endregion

    # region 计算贡献差值
    ...
    # endregion
```

Step headings describe major phases. Regions describe the smaller paragraphs within that phase.

## 6. Concurrency/correctness paragraph

```python
# region 落库前最终校验
self._refresh_locks(locks)
self._refresh_order_lock(order_lock)
self._assert_locks_owned(locks)

# 在真正写入前再次校验幂等状态，避免等待锁期间其他实例已完成订单。
if redis_conn.exists(done_key):
    return
# endregion
```

Explain why ordering or repeated checks are needed when concurrency makes the reason non-obvious.

## 7. Region naming style

Prefer short action/intent names:

- 参数验证
- 初始化
- 数据验证
- 幂等验证
- 上订单锁
- 获取关系链
- 收集待锁节点
- 参数初始化
- 获取当前用户状态
- 计算当前等级
- 计算贡献差值
- 判断资格变化
- 重新评定祖先等级
- 判断是否保存父节点
- 链路过长时周期性续约
- 早停: 上传业绩差值=0 且资格状态未改变
- 落库前最终校验

Do not use vague titles such as `处理逻辑`, `业务逻辑`, `其他处理`, or `代码段` when a more precise responsibility is available.

## 8. Density rule

A useful region usually contains one of these:

- a meaningful guard or validation stage
- several related assignments that establish one state
- a business calculation
- a state/rank/qualification transition
- a lock/retry/idempotency stage
- a loop phase or branch policy
- persistence preparation/finalization

Do not wrap trivial syntax solely to satisfy a region count.
