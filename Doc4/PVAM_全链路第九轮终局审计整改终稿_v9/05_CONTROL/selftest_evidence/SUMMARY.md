# 第九轮终局控制自测证据摘要

| 自测 | 退出码 | 结果 |
|---|---:|---|
| `selftest_all_controls.sh` | 0 | Traceability、治理、Version、patch、DEV 与 registry 信任根正负例全部通过；终局输出 `ALL_CONTROL_SELFTESTS_PASS` |
| `selftest_traceability_v3.sh` | 0 | 20 类负例被阻断；新增 false REPORT-CHK edge、错误 R→TASK 路由、错误 TASK→WORK 配对三类跨层权威负例 |
| `selftest_document_governance.sh` | 0 | 100 条 AC 三元组、AC-06 专节、WORK §4.1 索引与 Version 负例通过；陈旧 WORK-08 索引被阻断 |
| `selftest_dev_parent_tree.sh` | 0 | canonical registry 正例通过；伪造路径、缺失工件、摘要篡改、registry/evidence/目录符号链接负例被阻断 |

证据文件保留 stdout、stderr 和 exit code。所有 Git commit、patch、Registry 与 DEV 结果均为控制脚本的合成自测对象，不是 Redemption 项目真实 WORK 交付，也不得把代码审计、真实 DEV/UAT 或 Gate C 状态升格。
