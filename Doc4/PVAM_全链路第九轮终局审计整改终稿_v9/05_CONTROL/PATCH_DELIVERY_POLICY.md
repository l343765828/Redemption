# PVAM 标准 Patch 交付门禁（受信任前置注册表版）

固定根基线：`3891f4b9c1f33df056e1334ed30e0ec3f2be1ad2`。每个 WORK 的 patch 只允许表示 `PARENT_COMMIT → WORK_COMMIT` 的直接差异。

强制条件：
1. parent provenance schema v2 必须绑定 `approved_commit_registry_sha256`；
2. 依赖型 WORK 的每个 included prerequisite 必须与 canonical `WORK_APPROVED_COMMIT_REGISTRY.json` 中 APPROVED entry 的 commit/tree 一致；
3. registry entry 还必须绑定 patch、scope、parent provenance 与批准记录 SHA-256，以及批准人身份、角色和时间；
4. `validate_work_patch.sh` 执行 scope、rename 双路径、`git apply --check --index` 与 applied tree 对账；
5. 当前规范注册表为 PENDING，不能据此声称任何真实 WORK 已批准。


## B7 发布信任根门禁

- `--approved-registry` 只为 CLI 兼容保留；其解析结果必须精确等于运行中控制包的 canonical registry。
- registry SHA-256 必须同时匹配根 `DOCUMENT_MANIFEST.json` 和 `VERSION_REFERENCE_MANIFEST.json`。
- 每个前置 `APPROVED` WORK 的 patch、scope result、parent provenance、approval record 四类工件必须存在并通过实文件 SHA-256 比对。
- 调用方自带 registry、缺失工件、摘要错配或符号链接均非 0 退出。
