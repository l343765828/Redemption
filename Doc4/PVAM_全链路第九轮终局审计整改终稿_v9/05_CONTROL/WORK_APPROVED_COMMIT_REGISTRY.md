# WORK Approved Commit Registry v2

- canonical path: `05_CONTROL/WORK_APPROVED_COMMIT_REGISTRY.json`
- schema: `2`
- current SHA-256: `d4ab1ca9303cbf0da11e26ecfc9731ef1e356fd12fe9989c5a6068c9394ff513`
- registry status: `ACTIVE`
- authorization status: `APPROVED_FOR_CONSTRUCTION`

## 信任根

活动校验器从自身位置推导发布包根目录，并要求 canonical registry 的路径和 SHA-256 同时匹配根 `DOCUMENT_MANIFEST.json` 与 `VERSION_REFERENCE_MANIFEST.json`。每个 `APPROVED` 条目必须绑定并实读校验 patch、scope result、parent provenance、approval record 四类工件。WORK-PVAM-01C、WORK-PVAM-01 已由正式 approval record 登记为 `APPROVED`；其余条目保持 `PENDING`。依赖型 WORK 只能引用已批准的前置条目。

## WORK-PVAM-01 正式批准登记

- commit：`9c1382600fa60e2d488113aef289bcc2331f8f45`
- tree：`8cfa5f0738dc7cb50cf9b739fca9b4a20b609af9`
- approver：`343765828@qq.com`
- role：`技术负责人`
- approved at：`2026-08-10T14:49:08Z`
- approval record：`evidence/WORK-PVAM-01/attempt-20260810-143426/approval/approval_record.json`
- approval record SHA-256：`bf3b1db1c4b6a3da40cde52e609d956b818312f2b8296e47893cf61b1c782136`
