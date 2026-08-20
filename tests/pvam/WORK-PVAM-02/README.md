# WORK-PVAM-02 UAT 消息生产端

`uat_message_producer.py` 按 `MSG-CONTRACT-v1_最简订单退款消息合同.md` 独立构造订单与退款消息，
不复用消费端 schema。它不访问 Redis、不消费 topic、不创建 topic，也不判断 UAT 是否通过。

## 准备

在仓库根目录运行。Kafka 地址必须显式设置；`--dry-run` 也会检查该变量，但不会连接或投递。

```powershell
$env:PVAM_KAFKA_BOOTSTRAP = "kafka.example:9092"
$producer = "tests/pvam/WORK-PVAM-02/uat_message_producer.py"
```

每次真实投递均等待 `acks=all` 的 delivery callback 和 `flush()`。成功后 stdout 每行是一条 JSON
证据，包含 topic、partition、offset、key、原始 payload、payload SHA-256 和 UTC 发送时间。
任一投递失败会写 stderr 并以非零状态退出。

先为任意命令加 `--dry-run` 检查 payload；确认后去掉该参数才会真实写 Kafka。

## 十个场景

正常订单：

```powershell
python $producer order --period 990001 --user-id U-UAT-001 --bv 1500.99 --order-id O-UAT-001 --dry-run
```

正常退款：

```powershell
python $producer refund --period 990002 --user-id U-UAT-001 --original-order-id O-UAT-001 --amount 1500.99 --order-id R-UAT-001 --approved-at 2099-07-01T00:00:00Z --dry-run
```

跨期退款主路径（先发 N 期订单，再发 N+1 期退款）：

```powershell
python $producer cross-period-refund --period 990001 --user-id U-UAT-002 --bv 1500.99 --amount 1500.99 --order-id O-CROSS-001 --refund-order-id R-CROSS-001 --dry-run
```

完全相同消息重发：

```powershell
python $producer duplicate --period 990001 --user-id U-UAT-003 --bv 99.50 --order-id O-DUP-001 --dry-run
```

相同身份、不同金额：

```powershell
python $producer payload-drift --period 990001 --user-id U-UAT-004 --bv 100.00 --drift-bv 100.01 --order-id O-DRIFT-001 --dry-run
```

D9-b 禁止字段。`--forbidden-field` 可重复；不传时一次加入全部三字段，其中
`previous_business_revision` 的值固定为 JSON `null`：

```powershell
python $producer forbidden-field --period 990001 --order-id O-FORBID-ALL --dry-run
python $producer forbidden-field --period 990001 --order-id O-FORBID-ONE --forbidden-field previous_business_revision --dry-run
python $producer forbidden-field --period 990001 --order-id O-FORBID-COMBO --forbidden-field business_revision --forbidden-field previous_amount --dry-run
```

Schema 违规。六种 `--invalid-case` 分别覆盖 JSON number、缺必填字段、零/负/bool 期号和三位小数：

```powershell
python $producer schema-invalid --period 990001 --order-id O-BAD-NUM --invalid-case bv-number --dry-run
python $producer schema-invalid --period 990001 --order-id O-BAD-MISSING --invalid-case missing-required --dry-run
python $producer schema-invalid --period 990001 --order-id O-BAD-ZERO --invalid-case period-zero --dry-run
python $producer schema-invalid --period 990001 --order-id O-BAD-NEG --invalid-case period-negative --dry-run
python $producer schema-invalid --period 990001 --order-id O-BAD-BOOL --invalid-case period-bool --dry-run
python $producer schema-invalid --period 990001 --order-id O-BAD-SCALE --invalid-case amount-scale --dry-run
```

未来期号（期号必须大于当前 Consumer 绑定期）：

```powershell
python $producer future-period --period 990002 --order-id O-FUTURE-001 --dry-run
```

过期期号（期号必须小于当前 Consumer 绑定期）：

```powershell
python $producer expired-period --period 990000 --order-id O-EXPIRED-001 --dry-run
```

排空哨兵会显式向两个 topic 的 0、1、2 分区各发一条，共六条。订单侧固定使用 canonical `"0"`
作为 bv，不采纳该场景的 `--bv` 参数。退款侧必须复用本轮已经确认成功的退款 ID，并传入与该退款
完全相同的 period、user、original order、amount 和 approved_at（若原消息有）；三条退款哨兵因此是
合同定义的同 identity、同 payload 精确重发。该场景禁止再传 `--partition`，因为它必须覆盖全部六个分区：

```powershell
python $producer drain-sentinel --period 990002 --user-id U-UAT-002 --original-order-id O-CROSS-001 --refund-order-id R-CROSS-001 --amount 1500.99 --dry-run
```

普通单消息场景可用 `--partition 0|1|2` 显式指定分区，例如：

```powershell
python $producer order --period 990001 --order-id O-PARTITION-001 --partition 2 --dry-run
```

## 确定性与证据保存

省略 `--order-id` 时使用 `<scenario>-<period>-<seq>`；`--seq` 默认 1，不使用随机数或时间戳。
相同参数会得到相同 order_id 与 payload。`sent_at` 和真实 delivery offset 属运行证据，不参与该确定性保证。

建议把 stdout 原样保存到本轮 UAT 证据目录；不要在命令、输出或文档中加入 Redis 口令。
