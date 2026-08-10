# WORK Approved Commit Registry v2

- canonical path: `05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json`
- schema: `2`
- current SHA-256: `ca9e7c98b59e161871c746163aebe343fe6e2f87598c3fe88036f73a3a22f82f`
- registry status: `ACTIVE`
- authorization status: `APPROVED_FOR_CONSTRUCTION`

## 信任根

活动校验器从自身位置推导发布包根目录，并要求 canonical registry 的路径和 SHA-256 同时匹配根 `DOCUMENT_MANIFEST.json` 与 `VERSION_REFERENCE_MANIFEST.json`。每个 `APPROVED` 条目必须绑定并实读校验 patch、scope result、parent provenance、approval record 四类工件。WORK-PVAM-01C 已由正式 approval record 登记为 `APPROVED`；其余条目保持 `PENDING`。依赖型 WORK 只能引用已批准的前置条目。
