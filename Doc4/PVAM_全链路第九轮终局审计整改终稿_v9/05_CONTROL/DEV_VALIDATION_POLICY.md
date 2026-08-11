# PVAM DEV 验证政策

DEV 证据必须绑定 root baseline、parent commit/tree、parent provenance SHA、trusted registry SHA、WORK commit/tree、patch SHA 与 applied tree。`validate_work_dev.sh` 只编译本 WORK 直接 patch 中的 Python 文件，并在测试后检查零 diff、零 untracked 和 tree 不变。

依赖型 WORK 只有在 canonical registry 对所有前置 WORK 均为 APPROVED 后才能进入门禁。当前注册表已激活，WORK-PVAM-01C、WORK-PVAM-01 已正式批准；依赖型 WORK 仍须逐项满足前置提交、证据和范围门禁。


## B7 前置交付信任根

DEV parent provenance 只接受发布包 canonical registry（SHA-256 `d4ab1ca9303cbf0da11e26ecfc9731ef1e356fd12fe9989c5a6068c9394ff513`）。当前 registry 中 WORK-PVAM-01C、WORK-PVAM-01 为 `APPROVED`，其余条目仍为 `PENDING`；仅满足全部前置关系的 WORK 可进入正式门禁。
