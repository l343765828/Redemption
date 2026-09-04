# WORK-PVAM-02 收尾归档

本目录是 WORK-PVAM-02 的长期、可校验收尾证据。W2 已完成；第一版不可变基线为 `ae488243e5533778575b94e53935914a36dcae46`，对应 tree 为 `b7a0d19a9b89c469ff0fa921b144a2c1426d3de9`，长期分支为 `codex/work2`。

## 权威边界

- `WORK_CLOSURE_ARCHIVE.json` 是本归档的机器可读 closure manifest。
- `evidence/` 保存最终 UAT、状态、各审查结果、候选 SHA 和 handoff 的原始副本。
- `historical-governance/WORK_APPROVED_COMMIT_REGISTRY.json` 是旧治理注册表的逐字节副本，仅用于历史追溯。
- `historical-governance/HISTORICAL_ONLY.json` 明确规定旧注册表为 `HISTORICAL_ONLY`、`authoritative=false`、`consumed_by_new_engine=false`。
- 新架构不得迁移或恢复旧 schema 4 state，也不得在运行时读取旧注册表。以后重新审核 W2 时，应针对明确指定的历史 commit 创建全新的 schema 5 execution 和新证据。

## 分支保护

`codex/work2` 由 GitHub ruleset `Protect codex/work2 via PR`（ID `22201355`）精确保护：只能通过 PR 更新，禁止删除和 force-push，无 bypass actor。该结论来自规则配置检查，未通过实际破坏性操作测试。

## 完整性验证

`SHA256SUMS.txt` 覆盖本目录中除其自身外的全部归档文件。可在本目录使用 PowerShell 验证：

```powershell
Get-Content -LiteralPath .\SHA256SUMS.txt | ForEach-Object {
    $expected, $relativePath = $_ -split '  ', 2
    $path = Join-Path -Path $PWD -ChildPath ($relativePath -replace '/', '\\')
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "SHA-256 mismatch: $relativePath" }
}
```

本归档不得原位覆盖。未来如需再次审核或修正 W2，应新增日期化归档版本，保留本版本及其校验值不变。
