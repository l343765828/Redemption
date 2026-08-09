# WORK Approved Commit Registry v2

- canonical path: `05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json`
- schema: `2`
- current SHA-256: `6c286713ee421777acc4d76177be6afbb6f16aad57565158d1f25de8fa3a1c68`
- registry status: `PENDING_ORGANIZATIONAL_APPROVAL`
- authorization status: `PENDING_ORGANIZATIONAL_APPROVAL`

## 信任根

活动校验器从自身位置推导发布包根目录，并要求 canonical registry 的路径和 SHA-256 同时匹配根 `DOCUMENT_MANIFEST.json` 与 `VERSION_REFERENCE_MANIFEST.json`。每个 `APPROVED` 条目必须绑定并实读校验 patch、scope result、parent provenance、approval record 四类工件。当前十个条目全部为 `PENDING`，不能作为依赖 WORK 的开工依据。
