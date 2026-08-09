# WORK-PVAM-07A Recalc Consumer ACK 紧急 fail-closed 修复施工任务书

> 文档定位：来源于待组织批准的 `TASK-PVAM-07A`，在取得组织授权后转化为可执行施工说明。本文件不重新决定业务规则；实际结果只能写入执行记录与验证交付报告。

## 0. 填写与执行规则

1. 上游修改任务与本 v1.3 施工套件当前均为 `DRAFT`；没有组织授权前，本任务保持 `BLOCKED`，不得启动代码施工或部署。
2. 只实施 `R-012A`（parent=`R-012`，紧急子集） 中已 `ACCEPTED` 或由来源 TASK 明确批准的条件代码事项。任何 `REJECTED / NEEDS_DECISION / DEFERRED / 未获 TASK 授权的 UAT_VERIFY` 只允许登记、验证或阻断，不得扩展代码范围。
3. 基线必须精确等于 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；发现漂移立即登记 `BLOCK-PVAM-07A-BASELINE`。
4. 所有新文件/符号已在变更表标为“新增”；其余锚点均来自固定基线。
5. DEV替身不能冒充真实Kafka/Redis/Dask/GPU/MySQL UAT验证。

## 1. 文档信息与追溯关系

| 字段 | 内容 |
|---|---|
| 施工任务编号 | `WORK-PVAM-07A` |
| 施工任务名称 | Recalc Consumer ACK 紧急 fail-closed 修复 |
| 所属施工总方案 | `WORK-PLAN-PVAM_v1.3` |
| 来源修改任务 | `TASK-PVAM-07A@MODPLAN-PVAM_v1.2`（authorization=PENDING_ORGANIZATIONAL_APPROVAL） |
| 来源问题 | `R-012A`（parent=`R-012`，紧急子集） |
| 复核闭环追踪号 | `REM-012A / W-012A / V-012A`（R-012 紧急子集） |
| 来源检查项 | `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003` |
| 关联决策 | `DEC-010` |
| 代码基线 | `l343765828/Redemption@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2` |
| SQL基线 | `sql_uat/*@3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，仅有效SQL |
| 文档版本 | `v1.3` |
| 负责人 | `待指派 / 实施工程师` |
| 复核人 | `待指派 / 架构与QA` |
| 当前状态 | `BLOCKED` |
| 文档治理状态 | `DRAFT`（`PENDING_ORGANIZATIONAL_APPROVAL`） |
| 前置任务 | 无金额域依赖；可与WORK-01并行 |
| 功能开关 | `RECALC_ACK_FAIL_CLOSED_V1` |

### 1.1 一对一追溯摘要

```text
CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003
  └─ R-012A（parent=R-012，紧急子集）
       └─ DEC-010
            └─ TASK-PVAM-07A (DRAFT / PENDING_ORGANIZATIONAL_APPROVAL)
                 └─ WORK-PVAM-07A
                      ├─ STEP-PVAM-07A-01 / STEP-PVAM-07A-02 / STEP-PVAM-07A-03 / STEP-PVAM-07A-04
                      ├─ TC-PVAM-07A-01 / TC-PVAM-07A-02 / TC-PVAM-07A-03 / TC-PVAM-07A-04 / TC-PVAM-07A-05 / TC-PVAM-07A-06 / TC-PVAM-07A-07
                      └─ EV-PVAM-07A-01...
```

## 2. 施工任务生成依据

### 2.1 上游输入

| 输入 | 编号/版本 | 本任务使用的结论 | 状态 |
|---|---|---|---|
| 复核报告 | `Redemption_PV_Amount_Migration_d74_复核报告_v1.5` | R-012A（parent=R-012，紧急子集） 的代码事实与严重级别 | CONFIRMED |
| 修改任务书 | `TASK-PVAM-07A` | 采用方案、范围、排除项、AC | DRAFT（待组织授权） |
| 检查方案 | `PLAN-PVAM-v1.15` | CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003 | CONTROLLED |
| 正式决策 | DEC-010 | 只执行已关闭裁决；开放项阻断 | CLOSED / 按上游登记 |
| 代码/SQL快照 | 3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2 | 唯一施工对象 | FROZEN |
| 施工模板 | 总方案模板/专项模板 | 章节、状态、证据纪律 | CONTROLLED |

### 2.2 开工条件

- [ ] 当前 HEAD 精确为 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`，工作树无未登记变更。
- [ ] `TASK-PVAM-07A` 的人工批准记录已归档；本 `WORK` 已由施工负责人和复核人签署。
- [ ] 前置关系满足：无金额域依赖；可与WORK-01并行。
- [ ] 本任务涉及的接口、单位、精度、兼容和回滚边界已由上游任务固定。
- [ ] DEV测试依赖已安装；UAT项具备WORK-08生成的环境/数据/schema manifest。
- [ ] 功能开关默认关闭，回滚路径已演练。

未满足任一关键项时，本任务状态为 `BLOCKED`；不得用假设替代。

## 3. 问题事实与施工目标

### 3.1 已确认问题

| 项目 | 内容 |
|---|---|
| 预期行为 | 在不修改producer/envelope/retention的前提下，把ACK改为显式结果驱动：只有handler完成、已批准audited no-op或DLQ写成功才ACK；其余保留PEL或进入IN_DOUBT。 |
| 当前行为 | `RecalcStreamConsumer.process_event` 对空payload返回True，调用方随后ACK。；JSON解析后直接 `e.get`，合法JSON array/null/string/number不在受控异常边界。；`_dispatch_business` 的已知分支仅print/pass，未知事件也自然返回成功。；`_reclaim_stale` 遇到empty fields/ghost entry直接加入ack_ids。；DLQ写失败的处置没有独立结果类型，normal read与reclaim逻辑分散。 |
| 差异 | 当前实现缺少本任务批准的唯一合同、门禁或原子边界。 |
| 影响 | 金额/PV单位、奖金、并发一致性、发布或可恢复性，具体见来源问题。 |
| 严重级别 | P0 |
| 证据位置 | 固定代码基线 `3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`；来源 `TASK-PVAM-07A`；检查项 `CHK-ARCH-002、CHK-EVT-006、CHK-EVT-007、CHK-TEST-001、CHK-TEST-003` |

### 3.2 已确认代码事实

- `RecalcStreamConsumer.process_event` 对空payload返回True，调用方随后ACK。
- JSON解析后直接 `e.get`，合法JSON array/null/string/number不在受控异常边界。
- `_dispatch_business` 的已知分支仅print/pass，未知事件也自然返回成功。
- `_reclaim_stale` 遇到empty fields/ghost entry直接加入ack_ids。
- DLQ写失败的处置没有独立结果类型，normal read与reclaim逻辑分散。

### 3.3 本任务目标

在不修改producer/envelope/retention的前提下，把ACK改为显式结果驱动：只有handler完成、已批准audited no-op或DLQ写成功才ACK；其余保留PEL或进入IN_DOUBT。

### 3.4 完成定义

- [ ] 所有 CHG 和 STEP 在批准范围内完成，未触碰排除项。
- [ ] DEV 静态、单元、契约和 mutation 测试全部通过并生成原始证据。
- [ ] UAT 所属用例已执行并回传，或保持 `PENDING_TEST_ENV/BLOCKED`，绝不预标通过。
- [ ] 受影响调用者回归通过，重复执行和失败恢复满足本任务断言。
- [ ] 回滚开关与 `git revert` 路径均可用，回滚后关键读写验证通过。

告警数值未定不阻断fail-closed代码与DEV/UAT；生产切换窗口另由总方案发布门控制。

### 3.5 明确非目标

- 不修改来源 TASK 未批准的业务比例、资格、分母、Country、period、舍入或发布职责。
- 不使用 `_bak`、`_final`、copy、废弃SQL或 `GraphService.run_bfs` 作为施工依据。
- 不把 UAT_VERIFY 风险转化为代码修复；只做验证、证据或阻断。
- 不建设 PB/SFB/GPB/CRB 算法或 Team Bonus units-int 生产服务。

## 4. 修改前调用链与数据流

### 4.1 入口与调用链

| 顺序 | 调用方/入口 | 文件与符号 | 输入契约 | 输出/副作用 | 错误形成点 |
|---|---|---|---|---|---|
| 1 | 新消息读取 | `RecalcStreamConsumer.start_consuming` | Stream entry | process_event True→XACK | 假成功 |
| 2 | payload解析 | `process_event` | payload string | 空直接True；JSON后e.get | 非object异常逃逸 |
| 3 | 分发 | `_dispatch_business` | event_type/dict | print/pass/unknown无错误 | 未处理仍ACK |
| 4 | reclaim | `_reclaim_stale` | XAUTOCLAIM entry | empty fields直接ACK | payload不可恢复 |

### 4.2 当前错误形成点

当前链路在上述入口缺少本任务目标合同，导致已确认问题在写入、计算、路由或发布边界形成并传播。修改必须落在表中稳定符号或明确标记为“新增”的边界；不得通过外围日志掩盖。

### 4.3 受影响消费者

| 消费者 | 依赖内容 | 预期影响 | 是否同步修改 | 对应步骤/测试 |
|---|---|---|---|---|
| start_consuming | 处理结果 | 改用统一process_entry结果 | 是 | STEP-07A-03/TC-027 |
| _reclaim_stale | 同一结果 | 不再独立决定ACK | 是 | STEP-07A-03/TC-028 |
| DLQ stream | 永久无效消息 | DLQ成功后ACK | 是 | STEP-07A-02 |
| producer | 现有payload | 不修改 | 否 | 回滚独立 |

## 5. 施工设计

### 5.1 采用方案

- 新增 `MessageConsumer/RecalcProcessResult.py`，枚举 `HANDLED_ACK`、`DLQ_WRITTEN_ACK`、`RETRY_KEEP_PEL`、`UNHANDLED_KEEP_PEL`、`GHOST_IN_DOUBT`。
- 重构为 `process_entry(message_id, fields) -> RecalcProcessResult`；normal/reclaim只根据结果决定XACK。
- 空 payload 固定返回 `UNHANDLED_KEEP_PEL`，不写 DLQ、不 ACK；非空 payload 的非法 JSON 或合法非 object JSON 才尝试写 DLQ，只有 XADD 成功返回 `DLQ_WRITTEN_ACK`。
- 现有print/pass分支全部视为UNHANDLED_KEEP_PEL，直到WORK-07B提供正式handler；不得虚构audited noop。
- ghost entry不ACK，记录高优先级告警并保留恢复证据。

选择理由：

- 与有效SQL、已关闭DEC及来源TASK目标一致。
- 采用 additive-first、显式version/manifest/feature flag，支持独立合入和回滚。
- 将纯函数、I/O适配、业务计算、权威提交和证据采集分层，便于DEV替身与UAT真实验证分别取证。

### 5.2 被否决方案

| 方案 | 不采用原因 | 来源 |
|---|---|---|
| 未知事件直接ACK | 永久丢失 | R-012 |
| empty fields ACK | deleted-ID不可恢复 | CHK-EVT-007 |
| catch-all后ACK | 掩盖处理失败 | CHK-EVT-006 |
| 本hotfix改producer/schema | 破坏独立回滚 | TASK-07A |
| 把pass当noop | 无批准依据 | TASK-07A |

### 5.3 修改后调用链与数据契约

| 边界 | 输入 | 处理 | 输出 | 断言/错误行为 | 责任符号 |
|---|---|---|---|---|---|
| 施工入口 | 固定commit + 批准TASK + RECALC_ACK_FAIL_CLOSED_V1 | 先执行基线/前置检查 | 受控diff | 任一前置失败即BLOCK | `RecalcProcessResult.py` |
| 核心处理 | strict version/type/period/run合同 | 按STEP顺序执行 | 可测试状态/事件/金额 | 非法类型、状态或proof fail-loud | 见CHG表 |
| 证据出口 | 命令、输入、输出、状态前后 | WORK-08 schema封装 | EV包+SHA-256 | 缺原始证据不得PASS | `uat/scripts/*` |

## 6. 文件与符号级变更清单

| 变更编号 | 文件 | 类/函数/字段/表 | 类型 | 修改前行为 | 要求的修改 | 修改后行为 | 禁止行为 |
|---|---|---|---|---|---|---|---|
| CHG-01 | `MessageConsumer/RecalcProcessResult.py` | 结果枚举 | 新增 | 不存在 | 定义ACK/PEL/IN_DOUBT语义 | 可审计 | 不得用bool |
| CHG-02 | `MessageConsumer/RecalcStreamConsumer.py` | `process_event`→`process_entry` | 修改 | bool结果/空payload成功 | dict校验、结果枚举、DLQ成功门禁 | fail-closed | 不得吞异常 |
| CHG-03 | 同文件 | `start_consuming` | 修改 | True即ACK | 仅两种ACK结果进入ack_ids | 未处理保PEL | 不得批量ACK其他结果 |
| CHG-04 | 同文件 | `_reclaim_stale` | 修改 | ghost直接ACK | 统一process_entry；ghost IN_DOUBT | normal/reclaim一致 | 不得删除PEL占位 |
| CHG-05 | `MessageConsumer/Test/test_recalc_ack_fail_closed.py` | pytest | 新增 | 不存在 | payload/JSON/unknown/pass/DLQ/ghost矩阵 | hotfix可独立验证 | 不得依赖WORK-07B |

### 6.1 固定基线锚点复验

`MessageConsumer/RecalcStreamConsumer.py`当前存在四个确定的假ACK入口：

1. `_reclaim_stale`遇到空`fields`直接加入`ack_ids`；
2. `process_event`遇到空payload返回True；
3. `json.loads`返回array/null/string/number后，`e.get`在统一异常边界之外；
4. `_dispatch_business`对已列事件仅print/pass，unknown也落空，随后返回True。

### 6.2 五态结果与ACK函数

> 规范合同：新增文件、枚举类名、类型标注和测试导入统一使用 `MessageConsumer.RecalcProcessResult.RecalcProcessResult`。以下代码块是该新增文件的规范参考实现，包含 §5.1、CHG-01、STEP-01 与 §9.2.1 共同要求的只读 `should_ack` 属性。

```python
from enum import Enum


class RecalcProcessResult(str, Enum):
    HANDLED_ACK = "HANDLED_ACK"
    DLQ_WRITTEN_ACK = "DLQ_WRITTEN_ACK"
    RETRY_KEEP_PEL = "RETRY_KEEP_PEL"
    UNHANDLED_KEEP_PEL = "UNHANDLED_KEEP_PEL"
    GHOST_IN_DOUBT = "GHOST_IN_DOUBT"

    @property
    def should_ack(self) -> bool:
        """只有业务处理完成或 DLQ 已可靠写入时才允许 XACK。"""
        return self in (
            RecalcProcessResult.HANDLED_ACK,
            RecalcProcessResult.DLQ_WRITTEN_ACK,
        )


ACKABLE = frozenset(
    {
        RecalcProcessResult.HANDLED_ACK,
        RecalcProcessResult.DLQ_WRITTEN_ACK,
    }
)
```

> **补丁性质：`DESIGN_FRAGMENT`（非逐字可应用补丁）。真实patch须在实施commit后按§12.A生成并校验。**

```diff
--- a/MessageConsumer/RecalcStreamConsumer.py
+++ b/MessageConsumer/RecalcStreamConsumer.py
@@
             for message_id, fields in claimed:
                 # region 幽灵消息 消息如果在原 Stream 中被删了，但还在 PEL 里，清掉占位
                 if not fields:
-                    ack_ids.append(message_id)
+                    self._record_ghost_in_doubt(message_id)
                     continue
@@
         # region 验证
         if not payload_str:
-            return True
+            return RecalcProcessResult.UNHANDLED_KEEP_PEL
         # endregion
 
         # region 处理消息 如有异常 加入死信队列 (格式级别毒丸)
         try:
             e = json.loads(payload_str)
         except json.JSONDecodeError as err:
             logger.error(f"解析 JSON 失败: {err}, 扔进死信队列 (DLQ)")
-            self.r.xadd(DLQ_STREAM_KEY, {"original_id": message_id, "raw_payload": payload_str, "error": str(err),
-                                         "type": "JSON_ERROR"})
-            return True
+            return self._write_dlq_or_keep_pel(
+                message_id,
+                payload_str,
+                "JSON_ERROR",
+                error=str(err),
+            )
         # endregion
 
+        if not isinstance(e, dict):
+            return self._write_dlq_or_keep_pel(
+                message_id,
+                payload_str,
+                "NON_OBJECT_JSON",
+            )
+
         et = e.get("event_type")
```

主循环和reclaim必须调用同一个`process_entry`，并且只在 `result.should_ack is True` 时执行 XACK；`ACKABLE` 仅作为等价审计集合，不得形成第二套判定。DLQ XADD异常返回`RETRY_KEEP_PEL`；没有真实handler的现有print/pass分支返回`UNHANDLED_KEEP_PEL`，不得编造副作用。

### 6.3 发布纪律

告警阈值、观察窗和运维容量不是核心代码开工前置；它们只影响生产切换批准。07A的DEV/UAT必须先证明“未完成业务绝不ACK”，不能因阈值未定而延后P0修复。

> **DEV 执行口径：** `05_CONTROL/check_baseline_preflight.sh` 与 `05_CONTROL/validate_work_dev.sh` 是唯一强制门禁。STEP 中列出的 `py_compile`、`compileall` 或 `pytest` 命令仅是附加局部检查，不得替代 parent-tree、scope、patch、tree-hash 与专属测试门禁。

## 7. 可执行施工步骤

### STEP-PVAM-07A-01：定义处理结果

- 目的：定义处理结果，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：无
- 修改文件：`RecalcProcessResult.py`
- 目标符号：Enum
- 精确操作：
1. 实现五个结果和`should_ack`只读属性
2. 只两类返回true。
- 必须保持：不加入事件业务语义
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcProcessResult.py`
- 本步单元验证：`TC-PVAM-07A-01`
- 完成证据：`EV-PVAM-07A-01`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：仍用bool则不合并

### STEP-PVAM-07A-02：重构payload/DLQ边界

- 目的：重构payload/DLQ边界，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：STEP-07A-01
- 修改文件：`MessageConsumer/RecalcStreamConsumer.py::process_entry`（`NEW_SYMBOL`，基线仅有`process_event`）
- 目标符号：处理函数
- 精确操作：
1. fields 缺失/ghost 进入 `GHOST_IN_DOUBT`；空 payload 返回 `UNHANDLED_KEEP_PEL`，不写 DLQ。
2. 非空非法 JSON/非 object JSON 尝试写 DLQ，只有写入成功才可 ACK。
3. unknown/print/pass/handler失败均保留 PEL；DLQ失败返回 `RETRY_KEEP_PEL`。
- 必须保持：unknown/pass不成功
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcStreamConsumer.py`
- 本步单元验证：`TC-PVAM-07A-02~04`
- 完成证据：`EV-PVAM-07A-02`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：任一未处理返回ACK即停工

### STEP-PVAM-07A-03：统一normal/reclaim ACK决策

- 目的：统一normal/reclaim ACK决策，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：STEP-07A-02
- 修改文件：`start_consuming`、`_reclaim_stale`
- 目标符号：ACK路由
- 精确操作：
1. 两路径均调用process_entry，按should_ack收集ID
2. ghost告警/IN_DOUBT。
- 必须保持：不改group/key/config
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m py_compile MessageConsumer/RecalcStreamConsumer.py`
- 本步单元验证：`TC-PVAM-07A-05/06`
- 完成证据：`EV-PVAM-07A-03`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：行为不一致不得合并

### STEP-PVAM-07A-04：补齐mutation与回归

- 目的：补齐mutation与回归，落实 `TASK-PVAM-07A` 的已批准目标。
- 前置条件：STEP-07A-01~03
- 修改文件：新增测试
- 目标符号：pytest
- 精确操作：
1. 覆盖空/非法/非object/unknown/pass/handler失败/DLQ失败/ghost及reclaim。
- 必须保持：测试不依赖正式handler
- 禁止实现：不得引入未批准业务规则、默认值、异常白名单或不可逆数据操作。
- 本步静态检查：`python -m pytest -q MessageConsumer/Test/test_recalc_ack_fail_closed.py`
- 本步单元验证：`TC-PVAM-07A-01~07`
- 完成证据：`EV-PVAM-07A-04`（diff、命令、exit code、stdout/stderr、SHA-256）
- 失败时停止点：mutation存活不得发布

## 8. 数据迁移、兼容与重跑

### 8.1 数据变化

| 对象 | 旧格式/状态 | 新格式/状态 | 转换位置 | 版本识别 | 异常数据策略 |
|---|---|---|---|---|---|
| PEL/ACK处置 | bool成功 | 显式 `RecalcProcessResult` | consumer两路径 | message_id/result | 未处理保PEL |

### 8.2 迁移步骤

| 顺序 | 操作 | 批次/范围 | 幂等键或判定 | 校验 | 失败处理 |
|---|---|---|---|---|---|
| 1 | 只读扫描/dry-run | 专用period/fixture或全量key清单 | run_id + 对象唯一键 | 数量、版本、金额/事件汇总 | 不写入并生成BLOCK |
| 2 | 启用shadow/read验证 | 单个隔离run | event/run/generation或feature flag | 新旧输出逐字段比较 | 关闭flag |
| 3 | 受控新写/切换 | 批准的UAT范围 | idempotency key/CAS | 重复执行结果不变 | 停止consumer/回滚代码 |
| 4 | 保留审计与兼容窗口 | 直到Gate关闭 | manifest checksum | 无新旧混读 | 不删除新字段/证据 |

### 8.3 兼容矩阵

| 读取方 | 旧数据 | 新数据 | 混合数据 | 预期行为 |
|---|---|---|---|---|
| 旧代码 | 原合同内支持 | 默认不保证 | 禁止 | 回滚前必须停止新写；不得让旧代码读取v2数据 |
| 新代码 | 仅隔离adapter/审计 | 支持 | 普通计算阻断 | 不能静默换算 |
| 证据/迁移工具 | 只读支持 | 只读支持 | 分类报告 | 不参与奖金计算 |

### 8.4 幂等与重跑断言

- 第一次执行：产生一个可追踪 run/attempt 及确定结果。
- 相同输入重复执行：以本任务定义的 event/run/generation/idempotency 键 no-op 或得到完全相同结果。
- 中断后续跑：从权威状态判断旧/新完整状态，不把半状态当成功。
- 部分旧/部分新：普通计算阻断，输出精确异常对象与证据；不得自动洗白。

## 9. 测试设计

### 9.1 测试用例总表

| 测试编号 | 层级 | 场景 | 固定输入 | 精确预期 | 对应步骤 | 环境 | 状态 |
|---|---|---|---|---|---|---|---|
| TC-PVAM-07A-01 | 单元 | ACK结果矩阵 | 五种enum | 仅HANDLED_ACK/DLQ_WRITTEN_ACK should_ack=True | STEP-07A-01 | DEV | NOT_RUN |
| TC-PVAM-07A-02 | 单元 | 空payload | None/empty | UNHANDLED_KEEP_PEL，不XACK | STEP-07A-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-03 | 单元 | JSON非object | `[]`,`null`,`"x"`,`1` | 写DLQ成功后ACK；DLQ失败KEEP_PEL | STEP-07A-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-04 | 单元 | 未知/pass事件 | unknown/现有pass分支 | UNHANDLED_KEEP_PEL | STEP-07A-02 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-05 | 集成 | normal/reclaim一致 | 同一entry分别投递 | 结果与ACK决定一致 | STEP-07A-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-06 | 集成 | ghost entry | XAUTOCLAIM empty fields | GHOST_IN_DOUBT、告警、无ACK | STEP-07A-03 | DEV+UAT | NOT_RUN |
| TC-PVAM-07A-07 | mutation | 反转fail-closed | unknown→ACK/ghost→ACK/DLQ失败→ACK | 测试全部失败 | STEP-07A-04 | DEV | NOT_RUN |

受控检查方案用例映射：`TC-027, TC-028, TC-031`。`TC-000` 为 RETIRED，不执行、不计完成率。

### 9.2 开发环境自动验证

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set the implementation commit for WORK-PVAM-07A}"
: "${PARENT_COMMIT_SHA:?set the controlled parent commit; root WORK uses BASE_SHA}"
: "${PARENT_TREE_SHA:?set the tree of PARENT_COMMIT_SHA}"
: "${PARENT_PROVENANCE_JSON:?set schema-v2 parent provenance JSON}"
: "${APPROVED_COMMIT_REGISTRY_JSON:?set canonical WORK_APPROVED_COMMIT_REGISTRY.json}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to the released 05_CONTROL directory}"

# Phase A：只验证固定基线和既有锚点，不要求 Common/Settlement/Ops 等未来目录存在。
bash "$CONTROL_ROOT/check_baseline_preflight.sh" \
  --repo "$REPO_ROOT" --base "$BASE_SHA" --work-id "WORK-PVAM-07A"

# Phase B：在由 parent provenance 证明来源的干净 PARENT_COMMIT worktree 应用当前 WORK 的直接 patch，
# 校验 per-WORK scope、applied tree hash，随后只编译本 WORK 实际变更的 Python 文件并执行专属测试命令。
bash "$CONTROL_ROOT/validate_work_dev.sh" \
  --repo "$REPO_ROOT" \
  --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" \
  --work-id "WORK-PVAM-07A" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --test-command-file "$CONTROL_ROOT/work-test-commands/WORK-PVAM-07A.sh" \
  --out "evidence/WORK-PVAM-07A/dev"
```

#### 9.2.1 必须落地的关键 `assert` 契约

以下断言骨架必须进入本任务列出的 pytest 文件；fixture 由测试文件实现，不得用复制生产公式的替身替代被测符号。

```python
from MessageConsumer.RecalcProcessResult import RecalcProcessResult


def test_ack_result_contract() -> None:
    assert RecalcProcessResult.HANDLED_ACK.should_ack is True
    assert RecalcProcessResult.DLQ_WRITTEN_ACK.should_ack is True
    assert RecalcProcessResult.RETRY_KEEP_PEL.should_ack is False
    assert RecalcProcessResult.UNHANDLED_KEEP_PEL.should_ack is False
    assert RecalcProcessResult.GHOST_IN_DOUBT.should_ack is False
```

通过标准：所有命令 exit code 0；pytest 无未解释 skip；证据schema校验通过。GPU/Dask/真实Redis/Kafka/MySQL未在DEV执行时必须标注 `NOT_RUN/PENDING_TEST_ENV`。

### 9.3 测试环境手工执行包

#### ENV-TC-PVAM-07A-01：ACK/PEL/DLQ/ghost hotfix

- 对应受控测试：`TC-027、TC-028、TC-031`
- 环境版本：由 `uat/environment_manifest.yaml` 固定 Python/CUDA/RAPIDS/Dask/Redis/Kafka/DB/镜像/commit。
- 前置服务与数据：隔离Redis Stream/group；不启用WORK-07B schema
- 清理/隔离：必须使用专用 topic/group、Redis前缀、period/run_id；禁止复用生产数据。
- 执行命令：

```bash
RUN_ID=work07a-$(date +%Y%m%d%H%M%S)
bash uat/scripts/run_work_uat.sh --work WORK-PVAM-07A --run-id "$RUN_ID" --tc TC-027,TC-028,TC-031
```

- SQL/数据库证据命令（仅在专用 UAT schema 和 WORK-08 manifest 校验通过后执行；N/A 项只保留说明）：

```bash
# N/A：本任务验证 Redis Stream PEL/ACK/DLQ，不执行 SQL。
```

- 执行步骤：
1. 发布空/非法/non-object/unknown/handler失败消息；分别记录 PEL 与 DLQ 变化
2. 模拟DLQ写失败
3. 制造pending后删除stream entry并XAUTOCLAIM
4. 查询XPENDING/XRANGE/DLQ
- 精确预期：
- 未处理消息留PEL
- 空 payload 固定留在 PEL 且不写 DLQ；非法 JSON/非 object JSON 仅在 DLQ 成功后 ACK
- ghost不ACK并有IN_DOUBT告警
- 必须回传：完整命令、exit code、stdout/stderr、JUnit/JSON、输入fixture SHA-256、代码commit、镜像、环境版本、执行起止时间、Redis/DB/Kafka/Dask前后证据。
- 失败停止与清理：停止专用consumer/job；保留PEL/状态和证据；禁止在未分析前清理失败现场；按第11节回滚。

### 9.4 SQL 对账样例

| 样例 | SQL输入/来源 | SQL预期 | Python预期 | 比较口径 | 允许差异 |
|---|---|---|---|---|---|
| N/A | 事件ACK不涉及业务SQL | N/A | N/A | Redis Stream状态 | N/A |

## 10. 验收标准映射

| 验收编号 | 来源TASK验收项 | 实现步骤 | 测试用例 | 所需证据 | 环境 | 通过条件 |
|---|---|---|---|---|---|---|
| AC-01 | 空 payload 不返回成功，不在无处置证据时 ACK | STEP-PVAM-07A-02/04 | TC-027 | EV-PVAM-07A-01 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-02 | 非法 JSON 与合法非 object JSON 均进入统一异常边界，不中断 reclaim 批次 | STEP-PVAM-07A-02/04 | TC-027 | EV-PVAM-07A-02 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-03 | 未知事件、缺 handler、现有 print/pass 分支不得落空成功 | STEP-PVAM-07A-02/04 | TC-027 | EV-PVAM-07A-03 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-04 | handler 失败或后置条件未知时不 ACK，保留 PEL 等待重试/后续合同 | STEP-PVAM-07A-02/03/04 | TC-027 | EV-PVAM-07A-04 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-05 | 永久非法消息只有在 DLQ 写成功后 ACK；DLQ 失败保留 PEL | STEP-PVAM-07A-02/04 | TC-027、TC-028 | EV-PVAM-07A-05 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-06 | normal read 与 xautoclaim 使用同一处理函数，对同一 entry 行为一致 | STEP-PVAM-07A-03/04 | TC-027、TC-028 | EV-PVAM-07A-06 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-07 | deleted-ID/empty fields 不直接 ACK；至少告警并阻断该批恢复链 | STEP-PVAM-07A-03/04 | TC-028 | EV-PVAM-07A-07 | DEV+UAT | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-08 | 本 hotfix 不要求 producer/envelope 变更，能够独立启停和回滚 | STEP-PVAM-07A-01/03/04 | TC-031 | EV-PVAM-07A-08 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |
| AC-09 | mutation 将 unknown 重新设为成功、ghost 直接 ACK、DLQ 失败仍 ACK 时，测试必失败 | STEP-PVAM-07A-04 | TC-031 | EV-PVAM-07A-09 | DEV | 来源AC全部断言满足；命令exit code 0；原始证据与SHA-256齐全 |

### 10.1 AC-01 实施细化

来源 AC 原文保持为“空 payload 不返回成功，不在无处置证据时 ACK”。本 WORK 的唯一实施细化为：空 payload 返回 `UNHANDLED_KEEP_PEL`，不写 DLQ、不调用 `XACK`；该细化不得反向改写来源 TASK 的 AC 文本。

没有 STEP、TC 或 EV 映射的AC不得标记完成。任何含UAT的AC在未回传真实环境证据时只能为 `PENDING_TEST_ENV/BLOCKED`。

## 11. 风险、停工与回滚

### 11.1 风险清单

| 风险 | 触发条件 | 影响 | 预防措施 | 监测/证据 | 处置 |
|---|---|---|---|---|---|
| PEL增长 | pass/unknown不再ACK | 积压 | 告警/容量临时提升/WORK-07B尽快接handler | XPENDING | 不回退假ACK |
| ghost不可保留payload | 原stream已trim | 恢复困难 | IN_DOUBT和证据 | ghost指标 | WORK-07B恢复 |
| 下游依赖旧假ACK | 积压暴露 | 运维压力 | 灰度flag | group lag | 停消费者但不ACK |

### 11.2 本任务强制停工条件

- HEAD、SQL blob、模型schema或上游TASK与受控基线不一致。
- 实施必须改变未批准的业务规则、精度、资格、分母、Country或发布职责才能继续。
- 需要修改排除文件/模块或扩大异常白名单才能通过测试。
- 关键mutation存活、SQL黄金样例出现未批准差异、幂等/原子/回滚断言失败。
- UAT权限、schema、数据或隔离条件不足；此时保持 `validation_status=BLOCKED` 或 `validation_status=PENDING_TEST_ENV`。

### 11.3 部署面与数据面回滚门禁

**当前可执行性：`BLOCKED_EXTERNAL_EVIDENCE`。** 当前材料没有给出真实部署系统、workload/release、镜像、配置对象和健康检查命令，因此不得以本地`export`或通用`git revert`冒充部署回滚。

部署前必须提供并签署`evidence/WORK-PVAM-07A/rollback/ROLLBACK-MANIFEST-PVAM-v1.json`，至少包含：

- `deployment_system`、`environment`、`workload_id`、`release_before/after`、`image_before/after`；
- 精确的停止、回滚、恢复、健康检查和重新放量命令；
- Redis/Stream/ledger/run/manifest的备份或快照位置及SHA-256；
- 执行人、复核人、批准时间、允许的数据恢复范围；
- 命令dry-run/隔离演练的退出码和原始日志。

本任务数据面处置：停止consumer；导出XPENDING和DLQ；恢复旧镜像前证明回滚窗口内没有未处理消息被ACK；保留PEL并由批准的恢复步骤重新消费。

统一执行顺序：

1. 停止新写并完成本任务定义的drain/freeze；
2. 导出任务相关Redis/Stream/ledger/run状态及checksum；
3. 由已签署manifest执行真实部署系统回滚，禁止仅修改当前shell环境变量；
4. 执行数据恢复/重放门禁；
5. 运行健康检查与幂等复验；
6. 保存命令、退出码、stdout/stderr和SHA-256。

缺少manifest、隔离演练或数据恢复证明时，只允许停止工作负载和保留证据，不得执行生产切换或声称“可独立回滚”。

### 11.4 不可逆部分

本任务计划不包含不可逆生产数据删除。若实施中出现清库、物理删除、无法恢复的trim或数据库DDL需求，立即停工并回上游方案审批。

## 12. 交付物与完成证据

| 编号 | 交付物/证据 | 生成步骤 | 位置/格式 | 验收人 | artifact_status |
|---|---|---|---|---|---|
| EV-PVAM-07A-01 | AC-01验收证据：空 payload 固定返回 UNHANDLED_KEEP_PEL，不写 DLQ且不 ACK | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-01/ | 待指派QA | PENDING |
| EV-PVAM-07A-02 | AC-02验收证据：非法 JSON 与合法非 object JSON 均进入统一异常边界，不中断 reclaim 批次 | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-02/ | 待指派QA | PENDING |
| EV-PVAM-07A-03 | AC-03验收证据：未知事件、缺 handler、现有 print/pass 分支不得落空成功 | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-03/ | 待指派QA | PENDING |
| EV-PVAM-07A-04 | AC-04验收证据：handler 失败或后置条件未知时不 ACK，保留 PEL 等待重试/后续合同 | STEP-PVAM-07A-02/03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-04/ | 待指派QA | PENDING |
| EV-PVAM-07A-05 | AC-05验收证据：永久非法消息只有在 DLQ 写成功后 ACK；DLQ 失败保留 PEL | STEP-PVAM-07A-02/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-05/ | 待指派QA | PENDING |
| EV-PVAM-07A-06 | AC-06验收证据：normal read 与 xautoclaim 使用同一处理函数，对同一 entry 行为一致 | STEP-PVAM-07A-03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-06/ | 待指派QA | PENDING |
| EV-PVAM-07A-07 | AC-07验收证据：deleted-ID/empty fields 不直接 ACK；至少告警并阻断该批恢复链 | STEP-PVAM-07A-03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-07/ | 待指派QA | PENDING |
| EV-PVAM-07A-08 | AC-08验收证据：本 hotfix 不要求 producer/envelope 变更，能够独立启停和回滚 | STEP-PVAM-07A-01/03/04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-08/ | 待指派QA | PENDING |
| EV-PVAM-07A-09 | AC-09验收证据：mutation 将 unknown 重新设为成功、ghost 直接 ACK、DLQ 失败仍 ACK 时，测试必失败 | STEP-PVAM-07A-04 | evidence/WORK-PVAM-07A/attempt-*/ac/AC-09/ | 待指派QA | PENDING |
| EV-PVAM-07A-P01 | 处理结果枚举与consumer diff | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07A-P02 | DEV fail-closed/mutation测试 | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07A-P03 | UAT PEL/DLQ/ghost证据 | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |
| EV-PVAM-07A-P04 | 运行告警和回滚说明 | 对应STEP/TC | evidence/WORK-PVAM-07A/attempt-*/package/ | 待指派QA | PENDING |

> 第 12 节交付物表中的 `PENDING` 属于 `artifact_status`，只表示工件尚未生成；环境验证状态必须使用 `validation_status ∈ {NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}`。

### 12.A 标准补丁与实施 commit 门禁

文档中的 `diff` 均为 `DESIGN_FRAGMENT`，不是预生成补丁。真实代码完成后必须执行受控脚本；不得手工省略 scope、worktree、tree hash 或测试绑定：

```bash
set -euo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2"
: "${WORK_COMMIT_SHA:?set implementation commit}"
CONTROL_ROOT="${PVAM_CONTROL_ROOT:?point to released 05_CONTROL}"

bash "$CONTROL_ROOT/validate_work_patch.sh" \
  --repo "$REPO_ROOT" \
  --base "$BASE_SHA" \
  --parent-commit "$PARENT_COMMIT_SHA" \
  --parent-tree "$PARENT_TREE_SHA" \
  --parent-provenance "$PARENT_PROVENANCE_JSON" \
  --approved-registry "$APPROVED_COMMIT_REGISTRY_JSON" \
  --work-commit "$WORK_COMMIT_SHA" \
  --work-id "WORK-PVAM-07A" \
  --scope "$CONTROL_ROOT/WORK_SCOPE_ALLOWLIST.json" \
  --out "evidence/WORK-PVAM-07A/patch"
```

门禁必须证明：

1. `BASE_SHA` 是 `WORK_COMMIT_SHA` 的祖先；
2. 全部新增、修改、删除和 rename 的旧/新路径均落在 `WORK-PVAM-07A` 批准 allowlist；
3. patch 非空，由 `git diff --full-index --binary BASE WORK_COMMIT` 生成；
4. 在干净 BASE worktree 上 `git apply --check --index` 与实际 apply 均成功；
5. apply 后 tree hash 与 `WORK_COMMIT_SHA^{tree}` 完全一致；
6. 证据记录 base、work commit、patch SHA-256、applied tree hash、changed paths、命令、退出码和日志；
7. DEV 结果必须在该 applied tree 上重跑，不能用 `HEAD==BASE_SHA` 的预检查冒充实施验证。

无代码变更的 WORK 必须提交受控 `NO_CODE_CHANGE` 裁决，不得生成空 patch 冒充通过。

## 13. 执行记录（实施后填写）

### 13.1 实际修改

| 步骤 | 实际修改文件/符号 | commit | 执行人 | 时间 | 结果 |
|---|---|---|---|---|---|
| STEP-PVAM-07A-01 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07A-02 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07A-03 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |
| STEP-PVAM-07A-04 | 待执行 | 待生成 | 待指派 | 待执行 | NOT_RUN |

### 13.2 实际验证

| 测试 | 环境 | 命令/版本 | 结果 | 证据 | 执行时间 |
|---|---|---|---|---|---|
| TC-PVAM-07A-01 | DEV | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-02 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-03 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-04 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-05 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-06 | DEV+UAT | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |
| TC-PVAM-07A-07 | DEV | 待执行 | NOT_RUN | EV-PVAM-07A-* | 待执行 |

### 13.3 未完成项

| 项目 | 原因 | 风险 | 后续动作 | 责任人 | 截止时间 |
|---|---|---|---|---|---|
| UAT/外部材料 | 当前计划阶段未执行 | 不能关闭P0/P1 | 由WORK-08准入后执行 | 待指派 | 待批准 |

## 14. 偏离、发现项与上游回流

| 编号 | 类型 | 发现事实 | 是否影响业务/范围 | 临时动作 | 需要更新 | 最终裁决 |
|---|---|---|---|---|---|---|
| `DEV-PVAM-07A-001` | `预留` | 待执行 | 待判断 | 停工/隔离 | WORK/TASK/DEC/REVIEW | 待裁决 |

任何新增缺陷必须回复核报告登记新的 `R-*`；任何业务/架构歧义必须新增或重开 `DEC-*`。

## 15. 任务结论

本任务结论：`BLOCKED`

说明：本项是**执行/验证结论**，不是文档审批结论。本 v1.3 任务书治理状态为 `DRAFT`、执行状态为 `BLOCKED`；未取得组织授权和实施/DEV/UAT/rollback 证据前不得转为 `READY`。

### 15.1 签署

| 角色 | 姓名 | 结论 | 时间 | 备注 |
|---|---|---|---|---|
| 实施 | 待指派 | 待签署 | 待补充 |  |
| 代码复核 | 待指派 | 待签署 | 待补充 |  |
| 测试环境执行 | 待指派 | 待签署 | 待补充 |  |
| 最终验收 | 待指派 | 待签署 | 待补充 |  |

## 16. 版本记录

| 版本 | 日期 | 变更内容 | 变更原因/来源 | 编制人 | 批准状态 |
|---|---|---|---|---|---|
| v1.0 | 2026-08-04 | 初版施工任务书 | `TASK-PVAM-07A` + `PLAN-PVAM-v1.15` + 固定代码基线 | AI Agent（编制） | DRAFT |
| v1.1 | 2026-08-05 | 依据二轮核验报告完成定点修订并补齐治理追溯 | F-A/F-B/F-H/F-I/F-J/F-K/F-F/F-E/F-L/F-M/F-N 中适用项 | AI Agent（编制） | DRAFT |
| v1.2 | 2026-08-05 | 闭合 G-1：§6.2 统一使用 `RecalcProcessResult`，补齐只读 `should_ack`，同步 diff、ACK 判定与测试合同；不改变五态语义、CHK/DEC/TASK/WORK 范围 | 历史会话声明（未形成可独立验证组织授权，现由 v1.3 取代） | AI Agent（编制） | SUPERSEDED |
| v1.3 | 2026-08-05 | 第四轮关闭 F3-01～F3-10：治理回退 DRAFT、Traceability v3、patch/DEV 双阶段、状态枚举及设计边界 | 三轮审查报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r6 | 2026-08-06 | 五轮 F5 定点修订：规范 v3 追溯、parent provenance/DEV CLI、控制状态字段及单一事实源 | 五轮审计报告 + 当前文档修订指令 | AI Agent（编制） | DRAFT |
| v1.3-r7 | 2026-08-06 | 六轮 S6：信任 registry 初版、归档哈希、临时目录与 Decimal finite 防护 | 六轮终局审计报告 | AI Agent（编制） | DRAFT |
| v1.3-r8 | 2026-08-06 | 七轮 B7：registry 发布信任根、四工件摘要、AC 来源保真及当前轮次引用 | 七轮终局审计报告 + B7 处置 | AI Agent（编制） | DRAFT |
