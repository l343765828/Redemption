# PVAM DEV 验证政策

DEV 证据必须绑定 root baseline、parent commit/tree、parent provenance SHA、trusted registry SHA、WORK commit/tree、patch SHA 与 applied tree。`validate_work_dev.sh` 只编译本 WORK 直接 patch 中的 Python 文件，并在测试后检查零 diff、零 untracked 和 tree 不变。

依赖型 WORK 只有在 canonical registry 对所有前置 WORK 均为 APPROVED 后才能进入门禁。当前注册表为 PENDING，因此真实项目 DEV 仍为 NOT_RUN/GATED。


## B7 前置交付信任根

DEV parent provenance 只接受发布包 canonical registry（SHA-256 `9b4eab9bad7dc52cda3df5396db3f579b7796f241b843389e1822db7dc943bd1`）。当前 registry 全部为 `PENDING`，依赖型真实 WORK 继续 `BLOCKED`。
