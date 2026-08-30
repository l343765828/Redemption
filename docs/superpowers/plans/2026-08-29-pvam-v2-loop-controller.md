# PVAM V2 Loop Controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Loop Cycle 2 能由 Codex Producer 按方案 B 实施状态 `11`，同时让 Opus/Fable 独立审核，并在隔离 UAT 中由 Controller 审计、恢复临时配置。

**Architecture:** Controller 将角色 Skill 合同作为真实 prompt 组装输入；Candidate 施工范围通过 GitAudit allowlist 扩大但不强制修改全部文件。UAT 新增 Controller-owned `PVAmountV2Config` 三阶段动作，并用证据验证器强制 `snapshot -> activate -> restore`、Consumer 停止边界和 pointer CAS 恢复；工作流 finally 脚本负责异常路径恢复。

**Tech Stack:** PowerShell 5.1、GitHub Actions YAML、Python 3.6+ contract tests、Redis Lua CAS、现有 Loop schema-10 evidence。

**Spec:** `docs/superpowers/specs/2026-08-29-pvam-v2-loop-skill-isolation-design.md`

## Global Constraints

- 只修改主仓库 Loop Controller、prompt、策略、测试和项目 Skill；不修改 Candidate 业务代码。
- 不执行 Kubernetes 变更、Redis 写入、生产迁移或生产配置切换。
- 方案 B 的业务事实为：状态 `11` 正式授权，新记录写入 `amount_encoding_version=2`，已有记录显式迁移。
- 只有 Loop Codex Producer 使用指定 Superpowers 子集和 Ponytail full；Opus/Fable 禁止读取、加载、调用或声称使用二者。
- Candidate 最大文件许可集合严格采用设计文档 §10.1；未列出的文件继续 fail-closed。
- Controller UAT restore 只能在 active pointer 仍等于本次 activate pointer 时恢复原 pointer；漂移返回 `UAT_ENV_BLOCKED`。
- 不新增依赖；复用现有 runtime Python launcher、Redis 客户端、ConsumerLifecycle 和 schema-10 evidence。
- 保留用户现有未跟踪文件；不执行 Git add/commit/push。

---

### Task 1: 真实 Prompt 角色 Skill 合同

**Files:**
- Create: `.loop-engine/agent-skill-contract.ps1`
- Modify: `.github/workflows/loop-round.yml`
- Modify: `.loop-engine/claude-verifier-runner.ps1`
- Modify: `.loop-engine/producer-override.md`
- Modify: `.loop-engine/producer-rework-override.md`
- Modify: `.loop-engine/automated-override.md`
- Test: `tests/loop-engine/test_v21_pvam_v2_loop_contract.py`

**Interfaces:**
- Consumes: `-Role PRODUCER|OPUS|FABLE`。
- Produces: UTF-8 prompt block；Producer block 包含批准的 Skill 顺序，Reviewer block 包含显式禁止合同。

- [ ] **Step 1: 写角色 prompt 的失败测试**

```python
def test_real_role_contract_builder_isolated_skills():
    producer = run_role_contract("PRODUCER")
    opus = run_role_contract("OPUS")
    fable = run_role_contract("FABLE")
    assert "superpowers:systematic-debugging" in producer
    assert "ponytail full" in producer.lower()
    for reviewer in (opus, fable):
        assert "MUST NOT read, load, invoke, or claim" in reviewer
        assert "Producer-only" not in reviewer
```

- [ ] **Step 2: 运行测试并确认因入口不存在而失败**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py::test_real_role_contract_builder_isolated_skills -v`

Expected: FAIL，指出 `.loop-engine/agent-skill-contract.ps1` 不存在。

- [ ] **Step 3: 实现最小角色合同脚本并接入实际组装入口**

```powershell
param([Parameter(Mandatory=$true)][ValidateSet('PRODUCER','OPUS','FABLE')][string]$Role)
if($Role -eq 'PRODUCER') { Write-Output $producerContract; exit 0 }
Write-Output ($reviewerContract.Replace('{ROLE}',$Role))
```

Workflow 在 `$prompt` 数组中加入 `$producerSkillContract`；Claude runner 在 `$freshPrompt` 和 `$resumePrompt` 中加入 `$reviewerSkillContract`。Override 同步记录同一授权事实，但测试以脚本实际输出为准。

- [ ] **Step 4: 运行角色合同测试并确认通过**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py::test_real_role_contract_builder_isolated_skills -v`

Expected: PASS。

---

### Task 2: 方案 B 权威范围与项目注释 Skill 可见性

**Files:**
- Modify: `.loop-engine/uat-action-policy.json`
- Modify: `.loop-engine/producer-override.md`
- Modify: `.loop-engine/producer-rework-override.md`
- Create: `.agents/skills/redemption-comment-style/SKILL.md`
- Create: `.agents/skills/redemption-comment-style/references/comment-patterns.md`
- Modify: `tests/loop-engine/test_v20_review_regressions.py`
- Test: `tests/loop-engine/test_v21_pvam_v2_loop_contract.py`

**Interfaces:**
- Consumes: 设计文档 §10.1 Candidate 最大许可集合。
- Produces: `git_change_allowlist` 的精确文件/测试前缀；空 `git_hunk_allowlist` 表示允许白名单文件内由失败测试证明的任意必要 hunk。

- [ ] **Step 1: 写扩展范围的失败测试**

```python
def test_scheme_b_candidate_scope_is_exact_and_hunk_guards_are_removed():
    current = policy()
    for path in ("Common/AmountModelAdapter.py", "Redishelper/PVAmountConfigProvider.py",
                 "Redishelper/PVAmountConfigBootstrap.py", "Redishelper/PVAmountMigration.py",
                 "User/PlacementIncrementalService.py"):
        assert path in current["git_change_allowlist"]
    assert current["git_hunk_allowlist"] == {}
```

- [ ] **Step 2: 运行测试并确认旧白名单导致失败**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py::test_scheme_b_candidate_scope_is_exact_and_hunk_guards_are_removed -v`

Expected: FAIL，缺少方案 B 文件且仍存在两个历史单行 hunk guard。

- [ ] **Step 3: 最小更新策略、override 与 Skill 文件**

策略允许精确生产文件以及以下测试前缀：`Common/Test/test_amount_*`、`Redishelper/Test/test_pv_amount_*`、`User/Test/test_amount_*`、`MessageConsumer/Test/test_pv_event_consumer.py`。从 `refs/heads/1` 恢复已存在的 comment-style Skill 原文，不重新设计 Skill。

- [ ] **Step 4: 更新 v20 历史回归为向后兼容的子集断言并运行测试**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v20_review_regressions.py tests/loop-engine/test_v21_pvam_v2_loop_contract.py -v`

Expected: PASS。

---

### Task 3: Controller-owned PVAM V2 配置事务

**Files:**
- Modify: `.loop-engine/uat-action-policy.json`
- Modify: `.loop-engine/uat-action-proxy.ps1`
- Modify: `.loop-engine/verify-proxy-period-evidence.ps1`
- Modify: `.loop-engine/claude-verifier-runner.ps1`
- Modify: `.loop-engine/automated-override.md`
- Modify: `.loop-engine/verifier-checkpoint-protocol.md`
- Test: `tests/loop-engine/test_v21_pvam_v2_loop_contract.py`

**Interfaces:**
- Consumes: structured request `{"action":"PVAmountV2Config","operation":"snapshot|activate|restore"}`；activate 不接受 caller pointer/version。
- Produces: `PVAmountV2ConfigResult`，字段包括 `operation`、`original_pointer`、`active_pointer`、`config_version`、`state`、`checksum`、`candidate_sha`、`snapshot_key`、`restored`、`snapshot_deleted`。

- [ ] **Step 1: 写合成 schema-10 evidence 的失败测试**

```python
def test_period_verifier_requires_ordered_pvam_v2_config_transaction(tmp_path):
    evidence = make_evidence_sequence(tmp_path, ["snapshot", "activate", "restore"])
    result = run_period_verifier(evidence)
    assert result.returncode == 0, result.stderr

def test_period_verifier_rejects_unrestored_activation(tmp_path):
    evidence = make_evidence_sequence(tmp_path, ["snapshot", "activate"])
    result = run_period_verifier(evidence, mode="ValidateExistingOnly")
    assert result.returncode != 0
    assert "activation was not restored" in result.stderr
```

- [ ] **Step 2: 运行测试并确认缺少 action/evidence 语义而失败**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py -k pvam_v2_config -v`

Expected: 至少一项 FAIL，因为 verifier 尚未识别 `PVAmountV2ConfigResult`。

- [ ] **Step 3: 实现 snapshot/activate/restore 最小事务**

```powershell
function Invoke-PVAmountV2Config($Request,$Policy) {
    $operation=([string]$Request.operation).Trim().ToLowerInvariant()
    if($operation -notin @('snapshot','activate','restore')) { throw 'UAT_ACTION_POLICY_DENIED: ...' }
    # snapshot 只读；activate 调用 Candidate publish_manual_bootstrap(..., enable_v2=$true)；
    # restore 使用 Controller Lua 比较 activated pointer，恢复 original pointer 并删除精确 UAT snapshot。
}
```

运行期 Python 通过现有 `Invoke-RuntimePythonCommand` 获取 Redis 凭据；请求、stdout 和 semantic evidence 均不得包含凭据。状态 `10` 或 activate 后非 `11` 直接失败。Pointer 漂移必须返回 `UAT_ENV_BLOCKED`，不得覆盖。

- [ ] **Step 4: 强制证据顺序与恢复语义**

Verifier 对正向结果要求 `snapshot < activate < first bind`、最终 `ConsumerLifecycle restore < PVAmountV2Config restore`，且 restore 的 original/activated pointer 与先前证据精确一致。即使 `ValidateExistingOnly`，出现 activate 而未 restore 也失败。

- [ ] **Step 5: 运行新测试并确认通过**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py -k pvam_v2_config -v`

Expected: PASS。

---

### Task 4: 异常路径 Controller Finalizer

**Files:**
- Create: `.loop-engine/finalize-pvam-v2-uat.ps1`
- Modify: `.github/workflows/loop-round.yml`
- Modify: `.loop-engine/uat-action-proxy.ps1`
- Modify: `.loop-engine/protected-evidence-hash.ps1`
- Test: `tests/loop-engine/test_v21_pvam_v2_loop_contract.py`

**Interfaces:**
- Consumes: 当前 stage 的 controller evidence、`VERIFIER_STATE_DIR` 和固定 action proxy。
- Produces: 无 pending activation 时幂等 no-op；有 pending activation 时依次执行 Controller-derived exact cleanup、`ConsumerLifecycle restore`、`PVAmountV2Config restore`。

- [ ] **Step 1: 写 finalizer 决策的失败测试**

```python
def test_finalizer_dry_run_reports_pending_activation(tmp_path):
    write_config_evidence(tmp_path, operations=["snapshot", "activate"])
    result = run_finalizer(tmp_path, dry_run=True)
    assert result.returncode == 0
    assert "RedisDeleteExactKeys -> ConsumerLifecycle restore -> PVAmountV2Config restore" in result.stdout
```

- [ ] **Step 2: 运行测试并确认脚本不存在而失败**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py::test_finalizer_dry_run_reports_pending_activation -v`

Expected: FAIL，指出 finalizer 不存在。

- [ ] **Step 3: 实现 evidence-only dry-run 与真实 finally 路径**

```powershell
param([switch]$DryRun,[string]$EvidenceDir='')
if(-not $pendingActivation){Write-Output 'PVAM_V2_FINALIZER no-op';exit 0}
if($DryRun){Write-Output 'RedisDeleteExactKeys -> ConsumerLifecycle restore -> PVAmountV2Config restore';exit 0}
Invoke-ProxyRequest @{action='RedisDeleteExactKeys';controller_derived=$true}
Invoke-ProxyRequest @{action='ConsumerLifecycle';operation='restore'}
Invoke-ProxyRequest @{action='PVAmountV2Config';operation='restore'}
```

Workflow 在 Opus 与 Fable runner 后各加入 `if: ${{ !cancelled() }}` 的 finalizer step。Proxy 的 controller-derived cleanup 只从本 stage schema-10 成功 delivery evidence 生成精确 ledger、三类幂等和 UserStats keys；不接受 prefix/glob。

- [ ] **Step 4: 运行 finalizer 测试并确认通过**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py::test_finalizer_dry_run_reports_pending_activation -v`

Expected: PASS。

---

### Task 5: 回归验证与交付边界

**Files:**
- Modify: `tests/loop-engine/test_v20_review_regressions.py`（仅当新方案使历史精确值断言失效）
- Verify: `.loop-engine/*.ps1`、`.github/workflows/loop-round.yml`、`tests/loop-engine/*.py`

**Interfaces:**
- Consumes: Tasks 1-4 的最终文件。
- Produces: 新鲜测试输出、精确 Git diff/status；不运行集群动作。

- [ ] **Step 1: 运行目标回归**

Run: `python -m pytest -p no:cacheprovider tests/loop-engine/test_v21_pvam_v2_loop_contract.py tests/loop-engine/test_v20_review_regressions.py tests/loop-engine/test_v19_regressions.py tests/loop-engine/test_r9_scheduler_consumer_runtime.py -v`

Expected: PASS。

- [ ] **Step 2: 运行 PowerShell 静态解析和现有 smoke 子集**

Run: `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$files=@('.loop-engine/agent-skill-contract.ps1','.loop-engine/finalize-pvam-v2-uat.ps1','.loop-engine/uat-action-proxy.ps1','.loop-engine/verify-proxy-period-evidence.ps1'); foreach($file in $files){$null=$tokens=$errors=$null;[Management.Automation.Language.Parser]::ParseFile((Resolve-Path $file),[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){throw ($errors|Out-String)}}"`

Expected: exit 0。

- [ ] **Step 3: 核对实际变更范围**

Run: `git diff --name-only; git status --porcelain=v1 --untracked-files=all`

Expected: 只出现本计划列出的新增/修改文件；用户原有未跟踪文件保持不变。

- [ ] **Step 4: 输出下一步 Loop 参数**

说明本轮未运行集群、未运行 Candidate 方案 B、未 Git commit/push。Controller 文件推送后使用当前 Cycle 的 `run_mode=auto`，不要勾选新 Cycle，action tokens 使用 `none` 以复用已绑定 Cycle 授权。

