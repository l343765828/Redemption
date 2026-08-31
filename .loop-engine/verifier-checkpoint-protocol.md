# Loop Engine Verifier Checkpoint Protocol v20

This is the automation control contract for the staged Claude verifier. It does not replace business rules in the base verifier prompt.

## 1. Staged verifier model

v15 retains two verifier stages for the same logical Round and Candidate:

- `OPUS`: iterative verifier. Broad code review + real UAT. Allowed stage verdicts: `PRECHECK_PASS`, `REJECTED`, `BLOCKED`. Opus can never grant final PASS.
- `FABLE`: independent final auditor. Runs only after Opus `PRECHECK_PASS`. Allowed final verdicts: `PASS`, `REJECTED`, `BLOCKED`. Fable is the only stage allowed to grant final PASS.

The workflow sets `VERIFIER_STAGE` and gives each stage a separate durable checkpoint/session directory:

- `.loop-output/verifier-state/opus/`
- `.loop-output/verifier-state/fable/`

The progress ledger is more authoritative than Claude conversation memory. Only the MAIN verifier/coordinator may edit its stage ledger; subagents must not edit it concurrently.

## 2. Single formal report contract

There is exactly one formal report file for the Round:

- `.loop-output/UAT_REPORT.md`

Opus creates and maintains the verification/UAT body. When Fable starts, the workflow pins the exact Opus report as `.loop-output/verifier-state/opus/UAT_REPORT.pre-fable.md`.

Fable MUST preserve that exact content as an unchanged prefix and append a section titled:

`## Fable Final Audit`

Fable must not rename the report, delete Opus evidence, rewrite the Opus prefix, or create a competing formal final report.

Stage result files are intentionally different:

- Opus: `.loop-output/opus-result.txt` = `PRECHECK_PASS|REJECTED|BLOCKED`
- Fable/final Round: `.loop-output/uat-result.txt` = `PASS|REJECTED|BLOCKED`

## 3. Fingerprint boundary

The workflow validates candidate SHA and stage fingerprint before Claude starts. The fingerprint includes:

- verifier stage
- candidate SHA
- stage-specific UAT period allocation
- UAT period pool SHA-256
- pinned local master AGENTS SHA-256
- prompt / override / protocol / effective settings hashes
- Claude model + effort

Do not change `candidate_sha`, `input_fingerprint`, or `verifier_stage` in the ledger. Evidence reused on resume must match all of them.

## 4. Immutable UAT period allocation

Opus receives the Round pair:

- `LOOP_UAT_PERIOD_SLOT`
- `LOOP_UAT_PERIOD_PRIMARY`
- `LOOP_UAT_PERIOD_SECONDARY`
- `LOOP_UAT_PERIOD_POOL_SHA256`

Fable receives a separate fresh final-audit pair allocated only after Opus `PRECHECK_PASS`:

- `LOOP_FINAL_UAT_PERIOD_SLOT`
- `LOOP_FINAL_UAT_PERIOD_PRIMARY`
- `LOOP_FINAL_UAT_PERIOD_SECONDARY`
- `LOOP_FINAL_UAT_PERIOD_POOL_SHA256`

The active stage UAT period allocation is part of that stage fingerprint and **must not change on resume**. Opus and Fable must never reuse the same slot. A resumed stage reuses its exact existing pair; it never allocates a new one.

Hardcoded `PVAM_BOUND_PERIOD=990001/990002` literals in the base verifier prompt are superseded by the active stage mapping supplied by the runner. If the exact durable pair cannot be used safely, return `BLOCKED`.

Every period-bound evidence file and `UAT_REPORT.md` must record stage, slot, primary/secondary periods, and pool SHA-256.

## 5. Immutable local master AGENTS.md snapshot

Each logical Round pins one local master `AGENTS.md` before Codex or verifier work begins:

- `LOOP_MASTER_AGENTS_SNAPSHOT`
- `LOOP_MASTER_AGENTS_SHA256`

The master AGENTS.md snapshot **must not change on resume**. Codex, Opus, and Fable all receive the exact same pinned Round snapshot. An operator edit to local master `AGENTS.md` applies only at the next logical Round boundary.

## 6. Build a stable task plan before execution

Read the base verifier prompt and current stage ledger first. If `tasks` is empty:

1. Convert the stage responsibilities plus base verifier contract into an ordered list of atomic review/deploy/UAT/finalization tasks.
2. Reuse explicit task IDs when present; otherwise assign deterministic IDs.
3. Persist the whole task list before executing tasks.
4. Task IDs/order are immutable for the stage fingerprint.

Each task contains at least `id`, `title`, `kind`, `status`, `attempts`, timestamps, evidence path, and summary.

Allowed task states:

- `PENDING`
- `RUNNING`
- `RETRY_REQUIRED`
- `DONE`
- `BLOCKED`
- `FAILED`

Normal transition: `PENDING -> RUNNING -> DONE`.

Interrupted `RUNNING`, `BLOCKED`, or execution `FAILED` tasks are converted by the prepare script to `RETRY_REQUIRED` before resume so side effects are checked before repetition.

## 7. Mandatory checkpoint sequence

For every task:

1. Skip `DONE` tasks.
2. For `RETRY_REQUIRED`, inspect durable evidence and observable target state before repeating side effects.
3. Emit `PROGRESS_START <TASK_ID> | <concise rationale>`.
4. Persist `RUNNING` before deployment/UAT/database/Redis/Kafka side effects.
5. Execute only the task work and write durable evidence.
6. Evidence must contain candidate SHA, stage fingerprint, verifier stage, master AGENTS SHA, active UAT period allocation when relevant, timestamps, commands/actions, relevant outputs/findings, result, and final literal `EVIDENCE_COMPLETE`.
7. Persist terminal task state immediately.
8. Emit `PROGRESS_DONE`, `PROGRESS_BLOCKED`, or `PROGRESS_FAILED`.

Subagents may assist independent tasks but never edit the main stage ledger.

## 8. Opus finalization

Opus must not finalize while required tasks remain `PENDING`, `RUNNING`, or `RETRY_REQUIRED`.

When its work is complete:

1. Build/update `.loop-output/UAT_REPORT.md` from durable Opus evidence.
2. Write exactly one of `PRECHECK_PASS`, `REJECTED`, `BLOCKED` to `.loop-output/opus-result.txt`.
3. Set stage ledger `final_verdict` to the same value.
4. `PRECHECK_PASS` or `REJECTED` => stage ledger `status=COMPLETE`; `BLOCKED` => `status=BLOCKED`.
5. Opus MUST NOT create final PASS and MUST NOT write `.loop-output/uat-result.txt`.
6. Emit `PROGRESS_FINAL | <Opus verdict and concise reason>`.

`PRECHECK_PASS` means only that the Candidate may enter Fable final audit.

## 9. Fable finalization

Fable runs only after a durable Opus `PRECHECK_PASS`.

Loop Core result normalization is Controller-owned: Opus `PRECHECK_PASS` -> `NO_BUG`, Opus `REJECTED` -> `BUG_FOUND`; Fable `PASS` -> `FINAL_PASS`, Fable `REJECTED` -> `FINAL_REJECT`. The legacy stage files remain verification-layer evidence, while GitHub Actions routes only on normalized results.

Fable must independently audit the Candidate and Opus evidence, search for coverage gaps/shared blind spots, and selectively rerun critical/suspicious UAT using its fresh final-audit period allocation.

When complete:

1. Preserve the exact pinned Opus `UAT_REPORT.md` prefix.
2. Append `## Fable Final Audit` with independent audit scope, evidence reviewed, selective revalidation, new findings, unresolved risks, and final rationale.
3. Write exactly one of `PASS`, `REJECTED`, `BLOCKED` to `.loop-output/uat-result.txt`.
4. Set Fable ledger `final_verdict` to the same value.
5. `PASS` or `REJECTED` => `status=COMPLETE`; `BLOCKED` => `status=BLOCKED`.
6. Emit `PROGRESS_FINAL | <final verdict and concise reason>`.

A Fable `REJECTED` is a final-review rejection. GitHub Actions maps it to Loop Core `FINAL_REJECT`, persists `PAUSED_AWAITING_USER` with `FABLE_FINAL_REJECT`, and stops. It MUST NOT invoke Codex automatically. If the user later dispatches `next-cycle`, Codex receives the original WORK plus the Fable findings and current Candidate SHA; every resulting code change must then pass Opus again before Fable can run.

## 10. Interruption and quota recovery

If either Claude stage stops because of session/usage limit, process exit, runner failure, auth/network error, or other technical interruption before stage finalization:

- do not fabricate the stage result;
- preserve the latest durable checkpoint/session;
- rerun `loop-engine.yml` with `run_mode=auto`;
- do not use GitHub `Re-run failed jobs`;
- do not rerun Codex merely because Claude stopped;
- do not allocate another UAT pair for the same stage.

Session reuse is an optimization. A saved session may fall back to a fresh session only when the saved session itself is proven invalid/unavailable. Quota/auth/network/session-limit failures must not trigger a fresh-session fallback.

## v11 stage isolation and runtime contracts

- `VERIFIER_STAGE` is authoritative for result file semantics. OPUS writes only `opus-result.txt`; FABLE writes final `uat-result.txt`. Legacy single-stage output instructions are superseded.
- Kubernetes access uses `D:\\Redemption\\Redemption\\K8S\\kubectl.exe` with `D:\\Redemption\\Redemption\\K8S\\admin.conf`; the first Kubernetes API operation is the read-only `get --raw=/readyz --request-timeout=15s` probe.
- A new logical producer Round must fail closed if any stale active Opus/Fable verifier/runtime/result/report path cannot be removed before `Save-State`.
- Fable does not inherit local verifier shell allow rules. Its effective mutation allowlist is rebuilt from scratch, and its Claude invocation excludes user/project/local setting sources. Managed policy remains the administrator boundary.
- Fable mutable Kubernetes/UAT actions use only the fixed `.loop-engine/uat-action-proxy.ps1`; arbitrary mutable shell commands and Agent fan-out are not part of the final-audit allowlist.
- Fable is launched with the PowerShell-5.1-safe single argv token `--setting-sources=`; never pass the empty source list as a separate empty argument.
- A completed `BLOCKED` Round reopened with `auto` clears only the prior `final_audit_evidence_verified*` acceptance marker so the same candidate/period can later bind PASS or REJECTED after the blocker is fixed.
- Canonical/reconcile acceptance recomputes `protected_round_contract_sha256` from the current durable Round before accepting any Fable final result.
- Native kubectl stderr is captured with a scoped `ErrorActionPreference=Continue`, preserving the real exit code and evidence for negative UATs/warnings.
- Before Fable, the exact Opus report SHA-256 and byte length are bound to the durable Round ledger. The final report must preserve that exact byte prefix and append `## Fable Final Audit`.
- The workflow also pins a SHA-256 digest of the entire protected evidence/control surface through a GitHub step output and requires the same digest after Fable. This includes the full Opus evidence tree, Loop ledger/cycle archive, candidate provenance/cleanliness, and controller/instruction files.

## v12 explicit UAT write authorization contract

- `run_mode=auto` or manual `next-cycle` is never itself permission to mutate the UAT environment.
- Before a verifier stage performs any mutable action, Loop Engine must have a durable stage grant bound to the exact Cycle, Round, Candidate SHA, verifier stage, stage UAT period pair, authorization ID, actor, and canonical allowed-action list.
- Allowed mutable action tokens are `test-data-write`, `exec`, `debug`, `git-update`, `deploy`, `restart`, `scale`, and `delete`.
- A required mutable action absent from the bound list is a human-authorization blocker: record the need and return `BLOCKED` before the action.
- The grant scope SHA-256 is part of the verifier fingerprint and protected Round contract. Changing the explicit scope archives/rebuilds the affected verifier checkpoint and invalidates any previous final-audit acceptance marker/baseline.
- A durable grant may be reused only for the same Candidate/stage/period allocation. A new Round or new Candidate requires a new binding.
- Both verifier stages are enforced by `.loop-engine/uat-action-proxy.ps1`; ungranted tokens are rejected before kubectl runs.


## v16 non-interactive Cycle authorization

The durable Cycle authorization is authoritative for headless Loop execution. Do not create an interactive approval checkpoint. Every stage checkpoint records the Cycle authorization SHA and the derived stage authorization SHA. Kubernetes/UAT execution uses only `.loop-engine/uat-action-proxy.ps1`; out-of-scope actions become `BLOCKED`.

`DebugProfile` and `GitUpdate` are incomplete until the exact node-debugger Pod UID has terminated, logs/container exit code are captured, and that same UID is deleted in `finally`. A cleanup failure is `RETRY_REQUIRED`/`BLOCKED` evidence, never DONE.


## v16 structured action notes

`List` performs resource-scope-filtered discovery. `KafkaScenarioProduce` is restricted to allowlisted PVAM topics/current stage periods/durable-execution-bound order IDs and uses the controller-owned fixed producer embedded in the proxy. `RedisReadExactKeys` permits only exact allowlisted ledger reads; `RedisDeleteExactKeys` permits only exact durable-execution/period-scoped ledger keys or the exact UserStats business key derived from successful Kafka `period + user_id` evidence, and serializes even a singleton as a JSON array. `GitUpdate` rejects dirty host worktrees and requires remote, node-host, and scoped Pod/NFS HEAD agreement with the candidate SHA. All proxy outcomes write sanitized audit evidence.

## v16 actual-period and resumable evidence contract

- The action proxy derives period context from `VERIFIER_STAGE`. OPUS may use only the Round pair; FABLE may use only the separately allocated final-audit pair. Proxy audit evidence records the actual slot/primary/secondary and the workflow verifies it against the durable stage allocation.
- The protected-evidence digest hashes immutable Opus evidence/snapshots, the Cycle authorization, current Round `context/`, controller/policy files and candidate integrity. It intentionally excludes volatile Opus checkpoint/session files and mutable Round archive output produced by a legitimate `BLOCKED` attempt.
- `verifier-progress.json`, `resume-context.md`, `claude-session.txt`, and BLOCKED-attempt archive copies must never be used to force a new protected baseline on resume. The already-bound durable digest remains authoritative.
- `Scale` requires explicit replicas; `SetImage` requires an exact policy tuple; native staged rounds may not reconcile through the legacy single-verifier PASS path; stale active verdict/report cleanup is fail-closed.

- WORK-PVAM-02 actor recovery uses the versioned `dask-actor-rebuild` profile (`python3 -m User.UserService` from the discovered repo root, `exec+restart`) followed by actor inventory evidence.


## v16 controller-owned proxy evidence

- Verifier task ledgers/evidence remain writable in `verifier-state/<stage>`, but proxy execution evidence is not. The proxy alone writes `.loop-output/controller-evidence/schema-10/cycle-N/round-M/<stage>/action-*.log`. Both verifier effective settings explicitly deny editing `controller-evidence/**`.
- Each proxy record binds the raw structured request (base64 + SHA-256), stage scope SHA, durable `uat_execution_id`, actual stage period slot/pair/pool SHA, required tokens, outcome, and exit code.
- `verify-proxy-period-evidence.ps1` fails closed if the controller evidence directory/logs are missing, rejects request/hash/scope/execution/period mismatches, requires `SUCCESS` + exit code 0, and enforces the policy-defined minimum action/scenario set.
- Opus controller evidence is included in the pre-Fable protected digest. Fable controller evidence is written separately and verified after Fable.
- Same-stage technical resume reuses the exact durable `uat_execution_id`; GitHub Run ID/attempt are audit metadata only.
- Protected evidence uses the pinned Round `context/master-AGENTS.md`; the live master working-tree `AGENTS.md` is deliberately excluded so an edit intended for the next Round cannot invalidate the current Round resume.


## v17 verdict-aware controller evidence

The controller reads the stage verdict before enforcing evidence completeness. Opus `PRECHECK_PASS` and Fable `PASS` require the full policy-defined action/scenario set. `REJECTED` and `BLOCKED` use `ValidateExistingOnly`: zero proxy evidence is valid when no proxy action was reached, while every record that exists must still pass request hash, authorization scope, execution ID, period/pool, token, outcome and semantic-integrity checks.

Successful hard-gate actions carry controller-created semantic metadata. `GitAudit` binds clean status, local/remote Candidate HEAD and merge-base. `RedisDbSize` is phase-labelled (`before`/`after`). `RedisDeleteExactKeys` records requested/deleted/remaining counts and exact keys, and cleanup completeness is checked against Kafka delivery identities and controller-derived period/user UserStats business records. `KafkaScenarioProduce` records scenario plus actual topic/key/partition/offset deliveries from the repository-owned producer.

Selected pytest targets are canonicalized before execution. The exact contract path `MessageConsumer/Test/test_pv_event_consumer.py` is approved. Directory traversal, absolute paths and `.`/`..` segments are denied before the Pod command is built.


## v20 consumer lifecycle, three-chain, and evidence-schema contract

- Verifier fingerprint/checkpoint schema is `8`. Controller execution evidence is independently versioned as `schema-10`; schema-9 and older proxy logs are historical and cannot become active evidence after a checkpoint migration.
- Active proxy evidence lives only at `.loop-output/controller-evidence/schema-10/cycle-N/round-M/<stage>/`; verifier-writable state never owns this tree.
- Every Candidate-bound stage grant must export a valid 40-hex `LOOP_CANDIDATE_SHA`. The workflow cross-checks that SHA with `pushed-sha.txt` before verifier execution, and the controller verifier performs Candidate comparisons unconditionally for GitAudit/GitUpdate/ConsumerLifecycle/ConsumerObserve evidence.
- Controller evidence is strict key/value metadata. Command output is represented only as bounded JSON encoded into `output_json_b64`; raw sentinel framing is forbidden and duplicate metadata keys are fatal.
- The Consumer is a governed runtime component. `ConsumerLifecycle` requires the exact version-controlled `consumer_runtime_target`: scheduler-Pod temporary-process mode, namespace, host Deployment/container, Pod prefix, NFS repository, module, Kafka bootstrap, and role-specific calc months. Missing or mismatched configuration is fail-closed; Cycle resource scope remains an additional boundary.
- Before any bind mutation, the controller validates the exact scheduler container, unique Running+Ready Pod and UID, Pod prefix/scope, Candidate SHA, role period, and governed calc month. It starts or replaces only the execution-owned `MessageConsumer.PvEventConsumer` process and never mutates scheduler Deployment env, replicas, or rollout state.
- All Kafka/Redis/observation/proof helpers resolve that same scheduler Pod and exact NFS repository from policy. Dask and non-secret Redis endpoints are pinned by `consumer_runtime_target`; the inner Python launcher fails closed unless Candidate `Model.Config` has exactly the same endpoint values. Only the Redis credential is loaded from `Model.Config` inside the Pod, so secrets never cross the proxy request/evidence boundary. Dask exec profiles receive the policy-pinned scheduler address from the proxy and do not import Candidate configuration.
- The first bind captures a controller-owned baseline (governed env presence/values plus replicas). A failed bind rolls back automatically; rollback failure is a distinct fail-closed error. Positive stage completion requires final `ConsumerLifecycle restore`; `stop` cannot satisfy restoration.
- Opus requires the policy lifecycle sequence for primary and secondary binding plus final restore; the period-switch UAT cannot be satisfied by assigning two period numbers only in controller state. Fable likewise requires its policy-defined bind/observe contract plus restore.
- The three incremental idempotency namespaces are independent acceptance surfaces: `system:idempotency:{period}:...`, `system:idempotency:placement:{period}:...`, and `system:idempotency:elite:{period}:...`. Full positive-path acceptance requires observation and exact cleanup for every required namespace and delivered identity.
- `ConsumerObserve` turns producer evidence into end-to-end evidence. It checks fixed consumer-group offset semantics, policy-declared delivery state, three-chain done keys, scenario-specific exception reasons and `has_redis_residue`, and period-drain log evidence before the stage may claim the corresponding scenario complete. `post-pending-order-conflict` is the controlled exception: it must prove PENDING exists before the seeded order-ledger conflict is finalized, the exception reports `has_redis_residue=true`, and no UserStats business value changed.
- `GitAudit` binds HANDOFF Candidate SHA and the controller-owned changed-file allowlist. `GitUpdate` and all repo-backed runtime actions bind the Pod/NFS Candidate SHA, preventing stale NFS code from producing accepted evidence.
- `REJECTED` / `BLOCKED` remain verdict-aware: only evidence already produced must be authentic/consistent. `PRECHECK_PASS` / final `PASS` require the full v20 policy action, lifecycle, observation, cleanup, restore, evidence-integrity and runtime-SHA contract.


## v20 hard-proof completion sequence

`UatProof` is a governed controller action and `RequireComplete` must observe every proof required by `mandatory_uat_proofs_by_stage`. Opus requires, by exact ID:

1. `cross-period-refund-routing`
2. `duplicate-no-double`
3. `pending-dispatched-recovery`
4. `int64-end-to-end`
5. `pause-rebalance`
6. `dispatch-p99`

Fable requires the policy-defined subset. These proofs are not prose checklist items: each produces schema-10 controller evidence and is revalidated by `verify-proxy-period-evidence.ps1`.

- Cross-period and duplicate proofs include UserStats before/after snapshots and exact business deltas.
- PENDING recovery injects the persisted crash-window state only after a real event completed all three stages, preserves all three idempotency markers, performs rollout restart, replays the same identity, and requires no business-PV change.
- Int64 proof binds the mandatory amount-dtype test to runtime integer ledger/UserStats evidence.
- Pause/rebalance proof binds future pause barrier, drain, secondary rebind, and future replay ordering.
- Dispatch p99 uses fresh controller nonce-bound identities and records per-sample completion timestamps.

`RedisReadExactKeys` with `proof_id` derives the exact key set from controller Kafka evidence and rejects caller-supplied substitutions. Required Redis proof IDs are stage-specific and must report `expectations_satisfied=true` plus request/value SHA-256 digests.

For all required ConsumerObserve scenarios, `business_value_proof_ok=true` is mandatory. Policy-listed pre-dispatch negative scenarios additionally require unchanged UserStats snapshots and zero delivery/order/refund/idempotency residue. The governed post-PENDING conflict scenario requires unchanged UserStats plus the exact PENDING and seeded order-ledger residue declared by policy. Final cleanup must explicitly cover every known ledger key and all three idempotency namespaces for every delivery identity, plus the exact UserStats business key for each controller-delivered period/user pair, before `ConsumerLifecycle restore`.

## v21 PVAM v2 configuration transaction

Each Opus/Fable stage owns one ordered configuration transaction in schema-10 Controller evidence:

1. `ConsumerLifecycle restore` proves zero managed processes.
2. `PVAmountV2Config snapshot` records the original pointer, state, version, checksum, and Candidate SHA.
3. `PVAmountV2Config activate` publishes state `11` through the Candidate Bootstrap; caller-supplied pointer/version/checksum fields are forbidden.
4. The first `ConsumerLifecycle bind-*` occurs only after activation.
5. Exact Redis cleanup completes before the final Consumer restore.
6. `PVAmountV2Config restore` occurs after final Consumer restore, restores the exact original pointer by Controller-only CAS, deletes the exact UAT snapshot, and proves `restored=true` plus `snapshot_deleted=true`.

`ValidateExistingOnly` still rejects an activation without a later successful restore. On abnormal verifier exit, `.loop-engine/finalize-pvam-v2-uat.ps1` derives cleanup keys only from successful Controller evidence and executes cleanup -> Consumer restore -> config restore. Pointer drift is fail-closed and requires operator intervention; the finalizer never overwrites an external config update.
