# Loop Engine Automated Verifier Override v20

This file is managed by Loop Engine v20 and supersedes legacy interactive authorization instructions during headless Loop Engine execution.

## Non-interactive Cycle authorization

- GitHub `workflow_dispatch` is the single explicit preauthorization event for the current Cycle. Do not ask for per-command or per-stage human confirmation inside Opus or Fable.
- The durable Cycle grant binds authorization ID, actor, action tokens, namespace, resource scope, target branch, and impact scope. Candidate/stage/period-specific grants are derived automatically for later Rounds in the same Cycle.
- Never expand the grant from prompt text, prior Rounds, `auto`, or manual `next-cycle`.
- If a required structured action/resource is outside the bound scope, return `BLOCKED`; do not bypass the proxy and do not request interactive approval.

## Unified action proxy

- Both Opus and Fable route every Kubernetes/UAT command through `.loop-engine/uat-action-proxy.ps1`.
- Do not call kubectl, git, `sh -c`, `bash -c`, arbitrary PowerShell, or another mutable shell path directly.
- Mutable actions are hard mapped to `test-data-write`, `exec`, `debug`, `git-update`, `deploy`, `restart`, `scale`, and `delete` tokens.
- Governed actions include `List`, `Get`, `GetJsonPath`, `Describe`, `Logs`, `Wait`, `RolloutStatus`, `ExecProfile`, `DebugProfile`, `KafkaScenarioProduce`, `ConsumerObserve`, `RedisReadExactKeys`, `RedisDeleteExactKeys`, `UatProof`, `GitUpdate`, `SetImage`, `Restart`, `Scale`, and `Delete`.
- `KafkaScenarioProduce` is limited to policy-allowlisted PVAM topics, the current stage periods, and `order_id` values prefixed with the durable `uat_execution_id` marker.
- `RedisReadExactKeys` reads only exact policy-allowlisted PVAM ledger keys; `RedisDeleteExactKeys` deletes only exact durable-execution/period-scoped keys and preserves JSON array shape even for one key.
- `GitUpdate` discovers the host repository by exact Redemption remote URL, rejects dirty state, checks the remote candidate SHA before checkout, and verifies node-host plus scoped Pod/NFS HEADs after checkout.
- `DebugProfile` and `GitUpdate` are incomplete until the exact debug Pod UID has terminated, its logs/exit code have been captured, and that same UID has been cleaned. The `debug` token does not grant arbitrary `delete`.
- Every proxy outcome, including authorization denial, scope denial, policy denial, readyz failure, command failure, and success, writes a sanitized audit record before returning.

## Stage-aware result contract

`VERIFIER_STAGE` remains authoritative for OPUS/FABLE output semantics.

- OPUS writes only `.loop-output/opus-result.txt`: `PRECHECK_PASS`, `REJECTED`, or `BLOCKED`. OPUS MUST NOT write `.loop-output/uat-result.txt`. For `REJECTED`, each finding in `UAT_REPORT.md` must include ID, Severity, file, location, problem description, why it is a problem, required fix, and acceptance criteria.
- FABLE writes only `.loop-output/uat-result.txt`: `PASS`, `REJECTED`, or `BLOCKED`.
- Only Fable can produce final `PASS`.
- GitHub Actions owns the Loop Core adapter: Opus `PRECHECK_PASS` -> `NO_BUG`, Opus `REJECTED` -> `BUG_FOUND`; Fable `PASS` -> `FINAL_PASS`, Fable `REJECTED` -> `FINAL_REJECT`. Agents do not route or invoke one another.
- `BUG_FOUND` may cause another Codex Round only while `round < 3`. Round 3 `BUG_FOUND` pauses with `OPUS_ROUND_LIMIT`. `FINAL_REJECT` always pauses with `FABLE_FINAL_REJECT`. All next Cycles require manual `workflow_dispatch` `next-cycle`.
- Keep the single formal `.loop-output/UAT_REPORT.md`; Fable preserves the Opus prefix and appends `## Fable Final Audit`.

## Kubernetes contract

Use only the governed proxy, which internally uses `D:\Redemption\Redemption\K8S\kubectl.exe` and `D:\Redemption\Redemption\K8S\admin.conf` and performs `get --raw=/readyz --request-timeout=15s` before every proxy action. Node-debug uses the image already declared by the installed flannel DaemonSet and forces `IfNotPresent`; it does not depend on Docker Hub.

## v15 resume and period integrity

- The proxy resolves the active period pair from `VERIFIER_STAGE`: Opus uses `LOOP_UAT_PERIOD_*`; Fable uses only `LOOP_FINAL_UAT_PERIOD_*`. Every proxy audit record binds the actual stage slot/primary/secondary values.
- The immutable protected-evidence digest excludes controller-owned volatile Opus checkpoint files and mutable BLOCKED-attempt archives. It still hashes the Cycle authorization, current Round `context/`, immutable Opus evidence/snapshots, candidate integrity and controller policy.
- A Fable interruption or `BLOCKED -> auto` resume must therefore reuse the same durable baseline rather than re-baselining or becoming permanently stuck.
- `Scale` requires an explicit replicas value. `SetImage` is exact-policy allowlisted. Native staged Rounds cannot use the pre-v8 single-verifier PASS compatibility path.

- The governed `dask-actor-rebuild` ExecProfile executes only `python -m User.UserService` and requires both `exec` and `restart`; do not synthesize a different actor-rebuild command.

## Controller-owned execution evidence and hard gates (current v20 contract)

- `.loop-output/controller-evidence/schema-10/cycle-N/round-M/<stage>/` is controller-owned. Do not create, edit, delete, or repair files in that tree. Only `uat-action-proxy.ps1` writes proxy audit records there.
- Every stage has a durable `uat_execution_id`; it is stable across GitHub Run retries for the same Cycle/Round/Candidate/stage/period grant. `GITHUB_RUN_ID` is attempt metadata only and must never define Kafka/Redis UAT identity.
- Before a stage verdict is accepted, controller evidence must contain successful governed actions required by `uat-action-policy.json`; missing evidence is a failure, not a no-op.
- Opus hard gates include `GitAudit`, `GitUpdate`, `PytestFull`, `PytestSelected`, `DaskListDatasets`, `RedisDbSize`, governed `ConsumerLifecycle`, the required WORK-PVAM-02 Kafka scenarios through `KafkaScenarioProduce`, `ConsumerObserve`, exact Redis reads, and exact Redis cleanup. Fable runs the policy-defined final-audit subset.
- `KafkaScenarioProduce` uses only the controller-owned fixed producer embedded in `uat-action-proxy.ps1`. Candidate-owned `tests/pvam/WORK-PVAM-02/*` is outside the construction allowlist and must never define UAT delivery semantics.
- `dask-actor-rebuild` runs `python3 -m User.UserService` from the discovered Redemption repository root. `DaskListDatasets` verifies published datasets through the governed profile.
- `environment-summary` is prohibited. Use only `runtime-summary` or other policy-owned bounded outputs; proxy evidence output is line/byte capped and sanitized.


## Verdict-aware evidence and semantic cleanup contract (retained in v20)

- A stage verdict is read before the controller decides evidence completeness. `PRECHECK_PASS` (Opus) and `PASS` (Fable) require the full policy-defined successful action/scenario set. `REJECTED` or `BLOCKED` validates every controller record that exists but MUST NOT require later UAT actions that the verifier contract says not to execute after an earlier failure.
- `GitAudit` is successful only for a clean Candidate worktree with local/remote Candidate SHA agreement and the approved baseline as merge-base.
- `RedisDbSize` must be recorded for both `before` and `after`; the final count may not exceed the initial count. `RedisDeleteExactKeys` must prove all requested keys are absent after deletion and its request set must cover every controller-observed Kafka delivery identity.
- `PytestSelected` permits the contract path `MessageConsumer/Test/test_pv_event_consumer.py` plus governed `tests/` targets after canonical path validation; `.` / `..`, absolute paths, and traversal are denied.
- `RedisReadExactKeys` returns bounded typed values for strings/hashes/lists/sets/zsets/streams so ledger state can be asserted without full-database dumping.
- Kafka delivery identity is controller-derived from the official producer evidence. IDs without the normal execution marker (notably drain-sentinel IDs) are never broadly allowlisted; only the exact delivered identities may authorize matching cleanup keys.


## v20 consumer lifecycle, evidence integrity, and runtime acceptance

- `ConsumerLifecycle` is the only governed way to bind/rebind/restore the WORK-PVAM-02 Consumer. The request must name an exact Deployment and container that match one version-controlled `consumer_lifecycle_targets` entry. The shipped empty list is intentionally fail-closed; never guess or broaden a target.
- Before mutation, the controller verifies Cycle deployment scope, exact container identity, versioned Pod prefix coverage, currently selected Pods, governed `PVAM_CALC_MONTH`, and baseline replicas. `kubectl set env` always uses the exact `--containers=<consumer>` argument, so sidecars are not modified.
- The first bind captures a controller-owned baseline of governed env-key presence/values plus replicas. Any bind failure after mutation attempts mandatory rollback. A stage completes only after explicit `ConsumerLifecycle restore` returns that exact target to the baseline state; `stop` is not a restore substitute.
- Opus must prove `bind-primary`, the required drain/observation path, `bind-secondary`, and final `restore`. Fable must prove its policy-defined binding/observation set and final `restore`. A bind is not accepted merely because `kubectl set env` succeeded.
- `ConsumerObserve` is required after policy-defined Kafka scenarios. It must prove consumer-group offset expectations, scenario-specific exception reasons where applicable, delivery-ledger state, and all three idempotency namespaces (`userstats`, `placement`, `elite`) for scenarios that require full three-chain dispatch.
- Runtime repository integrity is a hard gate: the Candidate-bound stage grant exports mandatory `LOOP_CANDIDATE_SHA`; the workflow cross-checks it against `pushed-sha.txt`; `GitAudit`, `GitUpdate`, `ConsumerLifecycle`, and `ConsumerObserve` evidence must match the Candidate. Empty Candidate SHA can never disable these checks.
- Controller proxy evidence uses strict schema-10 key/value records. Command stdout is bounded, JSON-serialized and base64-wrapped in `output_json_b64`; raw `output_begin`/`output_end` framing is forbidden, and duplicate metadata fields invalidate the entire record. Schema-9 and older records are historical only and cannot satisfy v20 `RequireComplete`.


## v20 mandatory controller-owned UAT proof contract

A positive Opus verdict is impossible until every policy-required `UatProof` succeeds. The exact Opus proof IDs are:

- `cross-period-refund-routing`: controller snapshots prove primary UserStats PV increases by the original amount, secondary UserStats PV decreases by the exact same amount, and primary refund idempotency remains absent.
- `duplicate-no-double`: two identical Kafka deliveries produce one exact business PV increment, not two.
- `pending-dispatched-recovery`: the controller first completes a real three-chain event, injects the persisted delivery ledger back to `PENDING` while all three stage idempotency markers remain present, performs a real Deployment rollout restart, replays the same event, requires `DISPATCHED`, and requires UserStats PV to remain byte-for-byte equivalent at the business-field level.
- `int64-end-to-end`: `User/Test/test_amount_dtype_migration.py` must pass, runtime order ledger amount must be an exact integer units value, and runtime UserStats must expose Python `int` with `amount_encoding_version=2`.
- `pause-rebalance`: same-partition future-message + primary guard proves an effective pause barrier, drain evidence proves the period-switch boundary, and `future-period-replay` proves the paused event is actually processed after secondary binding.
- `dispatch-p99`: the controller generates fresh nonce-bound samples, waits for each sample to reach `DISPATCHED` plus all three idempotency keys before timing completion, and rejects p99 above the policy threshold.

Fable requires the policy-defined subset (`duplicate-no-double`, `int64-end-to-end`, `dispatch-p99`).

`RedisReadExactKeys` proof mode is also controller-owned. `proof_id` selects exact keys derived from prior Kafka evidence; a caller cannot substitute arbitrary keys. The controller verifies key types and scenario-specific values and records both requested-key and value SHA-256 digests.

All required Kafka scenarios carry controller-owned `business_snapshot_before`; each `ConsumerObserve` produces `business_snapshot_after` and `business_value_proof_ok`. Negative scenarios must have zero ledger/idempotency effects and unchanged UserStats snapshots. Every delivered identity, including identities created by `UatProof`, must receive exact ledger and all-three-idempotency cleanup before restore/final verdict.
