# WORK-PVAM-02 — Cycle 3 / Round 3 — OPUS iterative verification report

| | |
|---|---|
| **Verifier stage** | OPUS (iterative verifier — cannot grant final PASS) |
| **Stage verdict** | **PRECHECK_PASS** |
| **Candidate SHA** | `ae488243e5533778575b94e53935914a36dcae46` |
| **Baseline SHA** | `6281356d77306016cfb96567e84c14a66eefdbbb` |
| **Target branch** | `codex/pvam-work02-uat-candidate-20260813` |
| **Stage input fingerprint** | `12c06bbef7d3f64bbeb3a3b1b28029ec8a94a1bed7dcfd685a6b294af22ca2aa` |
| **Pinned master AGENTS.md SHA-256** | `7ee25f8e4050568ba32857402a95ba1ee29bf8580d1bb3167496843b990f55ed` |
| **UAT action policy SHA-256** | `2397e09f988bc0c4cf829e3c8f04c63c29b5f2c2ab92ce56ebb2c3b73818876f` |
| **UAT period slot** | 12 |
| **Primary `PVAM_BOUND_PERIOD`** | 990023 (calc month 209906) |
| **Secondary `PVAM_BOUND_PERIOD`** | 990024 (calc month 209907) |
| **UAT period pool SHA-256** | `534015fda28c434091ee299a787d6226b8d5e7b8979c41a2178267ff6273be20` |
| **Authorization ID / actor** | `R9-UAT-C3-20260830` / `l343765828` |
| **Cycle scope SHA-256** | `2a7887797013cb5467012374a29137b9f1db2861bc3f05a1c834bb729fcf0b31` |
| **Stage scope SHA-256** | `9c3dfdbfe6cd0f1b2caa3740bb8dbf7cafb73f66368f2ed23193ca9667ebdb18` |
| **Durable UAT execution ID** | `c3-r3-opus-s12-ae488243e553` (unchanged across both attempts) |
| **Authorized actions** | `debug,exec,git-update,restart,test-data-write` |
| **Namespace / resource scope** | `dask-operator` / `deployment/dask-cluster-scheduler,node/node3,pod/dask-cluster-scheduler-*` |
| **Impact scope** | `isolated-uat-only` |
| **Controller evidence** | `.loop-output/controller-evidence/schema-10/cycle-3/round-3/opus/` |
| **GitHub runs** | 33458540982 attempt 1 (BLOCKED, environment) → 33496840220 attempt 1 (this result) |

Every Kubernetes/UAT action went through
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/Redemption/Redemption/.loop-engine/uat-action-proxy.ps1`.
No direct `kubectl`, `git`, `sh -c`, `bash -c` or ad-hoc PowerShell was used. No Superpowers or Ponytail
skill, plugin, instruction file or methodology was read, loaded, invoked or relied on.

---

## 1. Verdict

**PRECHECK_PASS.** This Candidate is stable enough to enter Fable final audit. It is **not** a final PASS.

- All three Round-2 findings (F-01, F-02, F-03) are repaired. Every acceptance criterion has a real,
  non-weakened regression test, and those tests pass **inside the runtime Pod on the exact Candidate SHA**.
- Independent static review of the full `6281356d..ae488243` diff found no new blocking defect.
- The complete governed UAT ran end to end: **11/11 required Kafka scenarios**, **12/12 required
  ConsumerObserve results**, **2/2 controller Redis proofs**, **6/6 mandatory `UatProof` results**, with
  `business_value_proof_ok=true` on every observation.
- Both sides of the F-01 contract are now proven against **live Redis state**, not just unit tests (§4.1).
- The environment was left clean: 234 exact keys requested / 0 remaining, and final Redis `dbsize` 20,
  equal to the pre-UAT baseline of 20.

### Round history

Attempt 1 (run 33458540982) returned **BLOCKED**: the shared Dask `graph_actor` had `dg_sponsor = None`, so
every three-chain dispatch failed at `ELITE_PERFORMANCE`. That was a shared-environment fault in
`User/GraphService.py` / `User/UserService.py`, which are **not** in the WORK-PVAM-02 changed-file set and
**not** in `git_change_allowlist` — so it was correctly reported as an environment blocker rather than a
Candidate defect, and no Codex rework was requested. The operator applied the documented remediation; §6
records the verification that it worked, and §7 records the residual environment note.

---

## 2. Candidate provenance and runtime integrity

### 2.1 Governed `GitAudit`

`action-20260901T024139949Z-3e611473a46a4275bb2d96c7f32d7001.log`

```
worktree_clean=True
local_head=ae488243e5533778575b94e53935914a36dcae46
remote_head=ae488243e5533778575b94e53935914a36dcae46
merge_base=6281356d77306016cfb96567e84c14a66eefdbbb
baseline=6281356d77306016cfb96567e84c14a66eefdbbb
handoff_candidate_sha=ae488243e5533778575b94e53935914a36dcae46
```

Local HEAD == remote branch HEAD == `pushed-sha.txt` == handoff Candidate SHA; merge-base equals the approved
baseline; all 20 changed files pass `git_change_allowlist` and the line-level hunk contract; the handoff
`## CONTROLLER CANDIDATE CONTRACT` file set is byte-identical to `git diff --name-only`. No SQL, `Doc4/`,
Kubernetes manifest or unrelated service file is in the change set.

### 2.2 Governed `GitUpdate` (both attempts)

`action-20260901T102526039Z-a476f097f98c419c9c6df58cdb71f3e1.log` (attempt 2, new Pod)

```
candidate=ae488243e5533778575b94e53935914a36dcae46
remote=ae488243e5533778575b94e53935914a36dcae46
host_repo=/mnt/spark/delta/dask/Redemption/Redemption
pod_repo=/mnt/dask/Redemption/Redemption
```

node3 host HEAD and the scheduler Pod's NFS HEAD both equal the Candidate SHA. Every repo-backed proxy
action independently re-verified the Pod HEAD, so no evidence in this report came from stale NFS code.

### 2.3 Tests in the runtime Pod on the Candidate

| Profile | Result | Evidence |
|---|---|---|
| `PytestFull` (attempt 2, Pod `…-m8bcs`) | **279 passed in 12.78s**, exit 0 | `action-20260901T103440650Z-99c072d889b842929cda9f5e846b5de7.log` |
| `PytestSelected` contract targets (attempt 2) | **105 passed in 0.68s**, exit 0 | `action-20260901T103459352Z-d4dfea6385934166a3e1cf4f5bf09736.log` |
| `PytestSelected` named F-01/F-02/F-03 acceptance node IDs (attempt 1) | **12 passed in 0.08s**, exit 0 | `action-20260901T025333324Z-0bbd43ad59f4488286057ebf813e2560.log` |

Round 2 recorded 269 passed for candidate `7a94f218` on the same profile. The +10 delta matches the
Producer's claim of exactly 10 new regression cases, so nothing was removed or disabled to reach green.
No `skip`, `xfail` or `skipif` exists anywhere in the changed test files.

---

## 3. The three Round-2 findings

### 3.1 F-01 — exception records claimed Redis residue that did not exist → **repaired**

`MessageConsumer/PvEventConsumer.py:500-536` now passes the inferred residue through for the two exception
types that can be raised **before** the delivery boundary, while keeping category `3` /
`PERSISTENT_FAILURE` exactly as the finding required:

```python
if isinstance(exc, (ConsumedOrderConflict, DeliveryIdentityConflict)):
    return FailureDecision(3, failed_stage, True, "PERSISTENT_FAILURE")
if isinstance(exc, (RefundReversalConflict, OriginalOrderNotRefundable)):
    return FailureDecision(3, failed_stage, residue, "PERSISTENT_FAILURE",
                           unclassified=residue is None)
```

Boundary evidence (`_traceback_context:995-1017`, `_infer_residue:1019-1029`) against
`MessageConsumer/PvEventNormalizer.py`:

| Raise site | vs `_prepare_delivery` (`:192`) | Signal | Residue |
|---|---|---|---|
| `get_refundable_order` `:166` | before | `delivery_status` unbound | `False` |
| period conflict `:176` | before | `delivery_status` unbound | `False` |
| amount conflict `:179-182` | before | `delivery_status` unbound | `False` |
| `claim_whole_order` `:202` | after | frame in `_NORMALIZE_RESIDUE_METHODS` **and** `delivery_status` bound | `True` |

Acceptance criteria, all executed in-Pod:

1. `test_refund_validation_conflicts_before_delivery_report_no_residue` (2 params: period-conflict and
   amount-conflict paths) — real normalizer + real `InMemoryConsumedOrderLedger`; asserts
   `reason == "PERSISTENT_FAILURE"`, `has_redis_residue is False`, exact offset commit.
2. `test_original_order_not_refundable_before_delivery_reports_no_residue` — `has_redis_residue is False`.
3. `test_refund_claim_conflict_after_delivery_reports_redis_residue` — `has_redis_residue is True`,
   proving the pre/post paths are distinguished rather than uniformly flipped.
4. `test_permanent_post_delivery_conflict_forwards_with_redis_residue` (2 params) — `ConsumedOrderConflict`
   and `DeliveryIdentityConflict` still assert `True`.
5. Undecidable residue: `test_unraised_refund_conflict_keeps_residue_unknown` pins
   category 3 / `has_redis_residue is None` / `unclassified is True`, matching the O-08 contract.

**Runtime proof is in §4.1** — this is no longer only a unit-test claim.

### 3.2 F-02 — `IndexError` on rebalance during buffered drain → **repaired**

`run()` (`:283-308`) re-checks the deque after the heartbeat poll, and `_poll_and_buffer` (`:715-732`)
captures `poll_epoch = self._assignment_epoch` *before* `consumer.poll(...)` and discards any message
returned after a rebalance callback bumped the epoch. Both halves of the required fix are present.

Acceptance criteria, all executed in-Pod:

1. `test_revoke_during_buffered_drain_does_not_dequeue_an_empty_buffer` drives `on_revoke` from inside
   `poll`, asserts `running_during_revoke == [(True, True)]`, that `run()` returns normally (an `IndexError`
   would fail the test) and `consumer.closed is True`.
2. Same test asserts `coordinator.calls == []` and `consumer.commits == []`;
   `test_revoke_discards_message_returned_by_the_same_heartbeat_poll` proves the message returned by that
   same poll is neither dispatched nor committed.
3. `test_heartbeat_buffered_message_is_polled_during_drain_and_committed_once` is unchanged and still
   asserts `poll_timeouts[1] == 0.0`, the exact three-call coordinator order, and both commits.

The live period-drain path was also exercised for real (§4.2): six partitions boundary-paused, the drain
barrier logged, and the buffered/paused messages replayed after rebind with no crash and no lost message.

### 3.3 F-03 — blocked retry loop emitted no diagnostics → **repaired, and it paid for itself**

`_retry_dispatch` (`:576-657`) emits one classification-bearing warning on entry (`:590-602`) and keeps the
every-10-attempt cadence (`:620-633`); both records carry `event_identity`, `failed_stage`, `reason`,
`exception_class` and `_sanitize_exception_message(str(exc))`.

Acceptance criteria in-Pod: `test_blocked_retry_logs_classification_context_on_entry` asserts exactly one
entry record with all five fields; `test_blocked_retry_periodic_log_is_bounded_and_redacted` uses nine
consecutive transient failures and asserts exactly two records total (entry + `attempts=10`) with
`exception_message=[REDACTED_CONNECTION]` and no password or URI anywhere in `caplog.text`.

**Confirmed live during attempt 1.** The environment fault was diagnosed in seconds *because of this repair*
(`action-20260901T030328717Z-91dc30e614ab4a66b3d7ab4ce6c2dc6a.log`):

```
2026-09-01 03:03:03,521 [WARNING] [pvam-pv-consumer] 分区阻断重试开始:
  topic=pvam-pv-orders partition=0 attempts=1
  event_identity=uat-c3-r3-opus-s12-ae488243e553-order-2
  failed_stage=ELITE_PERFORMANCE reason=RETRY_EXHAUSTED
  exception_class=AttributeError exception_message='NoneType' object has no attribute 'nodes'
```

The identical Round-2 stall produced no error line at all and had to be traced statically. The category-4
bounded budget also terminated correctly instead of looping forever.

---

## 4. Governed UAT results

Runtime host Pod for the successful attempt: `dask-cluster-scheduler-67cbbcb9df-m8bcs` (node5, `scheduler`
container, Ready, 0 restarts), repository `/mnt/dask/Redemption/Redemption` at the Candidate SHA.

### 4.0 Configuration transaction (v21 order)

| Step | Result | Evidence |
|---|---|---|
| `ConsumerLifecycle restore` | `matching_process_count=0` | `action-20260901T102550422Z-09910a85c34541c2b802450812a7a2ca.log` |
| `PVAmountV2Config snapshot` | state `01`, version 1, pointer `1:45e2ee29…` | `action-20260901T102609597Z-958ae38b0bac47cc93c27e5984d6ab23.log` |
| `PVAmountV2Config activate` | state **`11`**, version **2** = original+1, pointer `2:ed298bcb…`, snapshot key `pvam:amount_config:snapshot:2` | `action-20260901T102630829Z-a957209e0a57412ebc0195214f7e849c.log` |
| first `ConsumerLifecycle bind-primary` | after activation, `bound_period=990023`, `matching_process_count=1` | `action-20260901T102653917Z-ed40ea8ddc7c47b5872dcf7a7fc60fd9.log` |

Scheme B admission accepts `00`/`01`/`11` and rejects `10`
(`Redishelper/PVAmountConfigProvider.py:336-343`); the observed original `01` and the activated `11` are
both inside the approved set. The whole UAT ran under state `11`.

### Business-window isolation (deliberate method)

`ConsumerObserve` computes business deltas against the UserStats snapshot taken at
`KafkaScenarioProduce` time. `cross-period-refund` and `future-period`/`future-period-replay` both span the
primary→secondary transition, so with a shared `user_id` their measurement windows overlap and corrupt each
other — Round 2 hit exactly this and worked around it by re-running with fresh identities. This stage gave
each scenario its own business user (`U-UAT-A1`, `U-UAT-DUP`, `U-UAT-PD`, `U-UAT-PP`, `U-UAT-FF`,
`U-UAT-SI`, `U-UAT-CP`, `U-UAT-FP`, `U-UAT-DS`, `U-UAT-EXP`, `U-UAT-PDR`, `U-UAT-P99`), which removes the
race entirely. Every one of those `period + user_id` pairs is controller-derived for exact cleanup.

### 4.1 Scenario matrix — 11/11 produced, 12/12 observed

| Scenario | Bound | Deliveries | Exc | Offset | Key controller assertions |
|---|---|---|---|---|---|
| `order` | primary | 1 | 0 | committed | DISPATCHED + all 3 idempotency namespaces; primary **+1500990000** |
| `refund` | primary | 1 | 0 | committed | primary **-1500990000**, the exact authoritative order amount |
| `duplicate` | primary | 2 | 0 | committed | `duplicate_no_double_ok=True`; 2 deliveries → **one** increment |
| `payload-drift` | primary | 2 | 1 | committed | one increment only; exactly one `EVENT_IDENTITY_CONFLICT` |
| `post-pending-order-conflict` | primary | 1 | 1 | committed | `delivery_status=PENDING`, `post_pending_conflict_ok=True`, **`has_redis_residue=true` asserted on the real exception record**, UserStats unchanged |
| `forbidden-field` | primary | 1 | 1 | committed | `no_redis_side_effects_ok=True`, `D9B_FORBIDDEN_FIELD` |
| `schema-invalid` | primary | 1 | 1 | committed | `no_redis_side_effects_ok=True`, `SCHEMA_VIOLATION` |
| `future-period` | primary | 2 | 0 | **not-committed** | `pause_barrier_ok=True`: future message *and* same-partition guard both uncommitted, zero ledger/idempotency |
| `drain-sentinel` | primary | 6 | 0 | **not-committed** | 6 partitions boundary-paused; `PERIOD DRAIN COMPLETE` log evidence present |
| `cross-period-refund` | produce primary / observe secondary | 2 | 0 | committed | `cross_period_refund_ok=True`; primary **+1500990000**, secondary **-1500990000**; primary refund idempotency absent |
| `future-period-replay` | secondary | 1 | 0 | committed | `future_replay_ok=True`; primary **0**, secondary **+1500990000** |
| `expired-period` | secondary | 1 | 1 | committed | `no_redis_side_effects_ok=True`, `EXPIRED_PERIOD` |

`business_value_proof_ok=true` on **every** observation.

**F-01 proven on live Redis state.** Round 2 caught the Candidate emitting `has_redis_residue: true` for a
**pre-boundary** `RefundReversalConflict` on a drain-sentinel refund. The identical code path ran again here
(`…-ds-refund-3`, three partitions, `failed_stage=NORMALIZE`,
`exception_class=RefundReversalConflict`, `reason=PERSISTENT_FAILURE`), so the actual Redis state could be
read directly — `action-20260901T104534432Z-ebcb9c447bf14864b96e79ed671649a9.log`:

| Key | Type | Meaning |
|---|---|---|
| `…:event_delivery:uat-…-ds-refund-3` | **`none`** | pre-boundary `RefundReversalConflict` left **zero** residue |
| `…:refund_reversal:uat-…-duplicate-3` | **`none`** | the conflicting refund never claimed the original order |
| `…:event_delivery:uat-…-expired-3` | **`none`** | category-1 `EXPIRED_PERIOD` left zero residue |
| `…:event_delivery:uat-…-post-pending-order-conflict-586433` | **`hash`**, `status=PENDING` | post-boundary `ConsumedOrderConflict` residue genuinely exists |

Residue is `true` exactly when a PENDING delivery record exists and `false` exactly when it does not. The
Round-2 false positive is gone, and the `true` side is independently asserted by the
`post-pending-order-conflict` observation against the real `pvam-pv-exceptions` record.

### 4.2 Period switch, observed live

`action-20260901T104213081Z-298402efb04a4482be42caa451f3f027.log`

```
10:37:26,331 [CRITICAL] PERIOD DRAIN COMPLETE: bound=990023 detected=990024, safe to rebind
--- rebind to 990024 ---
10:41:20,103 [INFO]  开始处理用户 U-UAT-FP 的增量 BV: 1500990000 (期数: 990024, 订单: …-future-3)
10:41:21,503 [ERROR] …-future-period-guard-586433  failed_stage=NORMALIZE reason=EXPIRED_PERIOD
10:41:22,107 [INFO]  开始处理用户 U-UAT-CP 的增量 BV: -1500990000 (期数: 990024, 订单: …-cp-refund-3)
10:41:22,458 [ERROR] …-ds-refund-3  failed_stage=NORMALIZE reason=PERSISTENT_FAILURE
                     exception_class=RefundReversalConflict          (x3, one per partition)
10:41:48,268 [ERROR] …-expired-3    failed_stage=NORMALIZE reason=EXPIRED_PERIOD
```

Complete DEC-020 §16 behaviour: drain barrier under the old binding, the previously-paused future message
processed under the new binding, the stale same-partition guard rejected as `EXPIRED_PERIOD`, and the
cross-period refund routed into the secondary period.

### 4.3 Controller Redis proofs — 2/2

- **`duplicate-ledgers`** (`action-20260901T103040119Z-846712773b6343f1842f1f466310af28.log`):
  `order_ledger.amount_units = "1500990000"` — an exact integer string, not a float — and
  `event_delivery.status = DISPATCHED`. Two identical deliveries produced one ledger record.
- **`cross-period-refund-ledgers`** (`action-20260901T104331046Z-9a2c4dcb69794019876bbcc2f3bd1158.log`):
  order recorded in period 990023 at `amount_units=1500990000`; the reversal is keyed by the **original
  order id** with `original_amount_units=1500990000` and `event_identity` bound to the refund's own
  identity; both deliveries `DISPATCHED`; nothing truncated.

Key sets are controller-derived from prior Kafka evidence; the verifier cannot substitute keys.

### 4.4 Mandatory proofs — 6/6

| Proof | Result |
|---|---|
| `cross-period-refund-routing` | primary **+1500990000** / secondary **-1500990000**, primary refund idempotency absent |
| `duplicate-no-double` | `duplicate_delivery_count=2`, business delta = **1500990000** (one increment) |
| `pending-dispatched-recovery` | `crash_window_injected=True`, `idempotency_present_before_restart=True`, `restart_completed=True`, `dispatched_after_restart=True`, `business_unchanged_after_replay=True` |
| `int64-end-to-end` | dtype test passed in-Pod; runtime ledger amount an exact integer; UserStats `pv_type=int`, `amount_encoding_version=2` |
| `pause-rebalance` | pause barrier + 6-partition drain + post-rebind replay, in that order |
| `dispatch-p99` | **p99 = 1455.95 ms** vs 5000 ms policy limit (20 nonce-bound samples, median ≈ 566 ms), far below `MAX_POLL_INTERVAL_MS = 600000` |

`pending-dispatched-recovery` is the strongest of these: the controller drove a real event through all three
chains, injected the persisted ledger back to `PENDING` with all three stage markers still present, replaced
the Consumer process, replayed the same identity, and required `DISPATCHED` again with UserStats unchanged
at the business-field level. A restart inside the PENDING window neither double-counts nor loses PV.

---

## 5. Independent static review

Full read of the candidate at the GitAudit-proven HEAD. Beyond §3:

- **Commit discipline** — `enable.auto.commit=False` and `enable.auto.offset.store=False` (`:1199-1200`);
  every commit is `commit(message=msg, asynchronous=False)` inside the same `try` as `_dispatch`
  (`:407-411`, `:635-638`); the only `finally` is `self.consumer.close()` (`:306-308`) with no commit.
  Boundary-paused partitions are never resumed (`:686`); prefetched same-partition messages are dropped
  without commit (`:331-339`, `:667-685`).
- **`_handle_post_dispatch_commit_failure`** (`:431-481`) retries only the offset commit and never
  re-dispatches; the `dispatch_completed` flag gates both `process_message` and `_retry_dispatch`.
- **Broad `except Exception`** is used only as the classification funnel into `_classify_exception`, not to
  swallow errors. `type(exc) is RuntimeError` (`:561`) is an exact-type check, so the ledger-conflict
  `RuntimeError` subclasses cannot fall through to the category-4 bucket.
- **Secret hygiene** — `_sanitize_exception_message` (`:1060-1063`) strips any URI plus the configured Redis
  password; `main()` (`:1245-1248`) logs only the exception class; `ConsumerSettings.redis_password` uses
  `field(repr=False)`. No credential appears in any proxy request, evidence file or log in this stage.
- **`Common/PeriodResolver.py`** — real SHA-256 over canonical JSON in both repositories (`:113-124`,
  `:170-182`); no fabricated constant. `resolve_current` re-verifies the returned `period_num` (`:91-94`).
  The retained `"DEC-011"` literal is documented as intentional checksum stability (`:112`).
- **`MessageConsumer/PvEventSchema.py`** — `_parse_period_num` rejects `bool` and `< 1`;
  `_parse_amount_units` uses the shared decimal parser with `max_decimals=2`, rejecting JSON numbers,
  exponents, NaN/Infinity and 3-decimal amounts at the raw boundary. The `schema-invalid` scenario exercised
  the JSON-number path live.
- **`Redishelper/PVAmountConfigProvider.py`** — pointer/version/checksum cross-verified (`:289-309`) after
  one atomic Lua read with no GET/HGET fallback.
- **Three-chain idempotency namespaces** are exactly the three the controller asserts:
  `system:idempotency:{period}:` (`User/UserStatsService.py:424,449`),
  `system:idempotency:placement:{period}:` (`User/PlacementIncrementalService.py:331,360`),
  `system:idempotency:elite:{period}:` (`User/EliteBonusService.py:265`).

### Non-blocking observation (considered, deliberately not escalated)

`run()`'s non-buffered branch (`:303`) calls `self.consumer.poll(1.0)` without the `_assignment_epoch` guard
that `_poll_and_buffer` now applies, so a message returned by a poll that also fired `on_revoke` would still
be processed. This is availability-only, not a correctness defect: the deployment contract is one instance
per `group.id` (module docstring `:4-5`), the delivery ledger plus three idempotency namespaces make
reprocessing a no-op (proven live by `duplicate` and `pending-dispatched-recovery`), and the resulting
non-retryable commit failure is handled by `_handle_post_dispatch_commit_failure` without duplicating
business work. It pre-exists this Round and was outside F-02's scope. Fable may wish to form its own view.

---

## 6. AC status

`{NOT_RUN, PASS, FAIL, PENDING_TEST_ENV, BLOCKED}`

| Area | Status | Basis |
|---|---|---|
| Candidate provenance / change-file + hunk scope | PASS | governed `GitAudit` |
| Runtime repo == Candidate (node3 host + Pod NFS) | PASS | governed `GitUpdate`, re-verified per action |
| Full suite on the Candidate, in-Pod | PASS | 279 passed, exit 0 |
| Contract targets in-Pod | PASS | 105 passed, exit 0 |
| **F-01 residue accuracy (D11-a)** | **PASS** | 5 named acceptance tests **+ live pre/post Redis proof** (§4.1) |
| **F-02 rebalance during buffered drain** | **PASS** | 3 named acceptance tests + live 6-partition drain/replay |
| **F-03 blocked-retry observability** | **PASS** | 2 named acceptance tests + live confirmation (§3.3) |
| Scheme B admission `00`/`01`/`11`, reject `10` | PASS | `PVAmountConfigProvider.py:336-343`; live `01` → `11` → `01` |
| Atomic config publish + CAS + read-after-write | PASS | live snapshot / activate / restore, pointer + checksum agreement |
| No implicit record migration | PASS | `PVAmountMigration.py` dry-run-default / exact-record / fail-closed; `require_v2_amount_record` guards |
| int64 units end to end | PASS | `int64-end-to-end` proof; ledger `amount_units="1500990000"`; UserStats `pv_type=int`, version 2 |
| Three-chain idempotency (3 namespaces) | PASS | all namespaces observed per delivery and cleaned exactly |
| Duplicate = single increment | PASS | `duplicate-no-double` proof |
| Payload drift fail-loud | PASS | `payload-drift`: one `EVENT_IDENTITY_CONFLICT`, one increment |
| Cross-period refund routing | PASS | `cross-period-refund-routing` proof, exact ±1500990000 |
| PENDING → DISPATCHED crash recovery | PASS | `pending-dispatched-recovery`, business unchanged |
| Period switch: pause / drain / replay | PASS | `pause-rebalance`; 6-partition drain; ordered replay |
| Pre-dispatch negatives leave no residue | PASS | forbidden-field, schema-invalid, expired-period |
| Post-PENDING conflict residue | PASS | `post-pending-order-conflict`, `has_redis_residue=true`, UserStats unchanged |
| Commit discipline (manual commit, no finally-commit) | PASS | static review §5 + live offset semantics on all 12 observations |
| Dispatch p99 vs `MAX_POLL_INTERVAL_MS` | PASS | 1455.95 ms vs 5000 ms limit |
| Secret hygiene | PASS | no credential in any proxy request, evidence file or log |
| Exception-topic schema (D11-a) at runtime | PASS | correlated records carry identity/topic/partition/offset/payload_hash/reason/residue |

---

## 7. Environment: what happened, and what is left

### 7.1 Attempt-1 blocker and its resolution

Attempt 1 could not dispatch because the Dask worker had lost its in-memory `GraphService` actor while the
scheduler-resident `users_version` dataset survived. `User/GraphService.py:290-293` short-circuits
(`if current_version >= msg_version: return`) whenever that marker is present, so the project's own
bootstrap `python -m User.UserService` recreated an **empty** actor and republished it without building
`dg_sponsor`/`dg_placement`.

Verified fixed on resume: the operator removed the old scheduler Pod, the rollout completed onto the freed
GPU, and the clean scheduler rebuilt the actors.

| Check | Result |
|---|---|
| New Pod `…-67cbbcb9df-m8bcs` | `Running`, `Ready=True`, `scheduler=ready:true,restarts:0`, node5 |
| `DaskListDatasets` | `["graph_actor","userinfo_actor","users_version"]` |
| First dispatch after repair | `order` → DISPATCHED, primary delta **+1500990000** |

Attempt 2's `PVAmountV2Config snapshot` also re-observed the pre-UAT config as exactly `01` / version 1 /
pointer `1:45e2ee29…`, byte-identical to what attempt 1's teardown wrote — independent confirmation that
attempt 1 restored correctly and that no external drift occurred between runs.

### 7.2 Residual environment note (not a Candidate issue)

During attempt 1 I used the granted `restart` token on `deployment/dask-cluster-scheduler` — the only
governed lever that can clear a scheduler-resident dataset. It could not complete at the time because the
scheduler Pod requests `nvidia.com/gpu: 1`, the cluster has one GPU, and the old Pod held it; `delete` and
`scale` are not in this Cycle's grant. That left a `Pending` surge Pod, which the operator's Pod removal
then allowed to schedule — it became the Pod that ran this successful UAT. Pod
`dask-cluster-scheduler-67cbbcb9df-96gjr` remains in the list in phase `Failed` as historical ReplicaSet
residue alongside 15 older `6bd5b9cbd5-*` entries; it is inert and does not affect Pod selection, which
filters on `phase == Running`.

Worth fixing separately, outside this Task-ID: the documented recovery entrypoint cannot recover a lost
in-memory graph while the version marker is still published. A force/rebuild flag on `GraphService.run(...)`,
or unpublishing `users_version` in `loadAllUser` before the build, would remove this whole failure mode.
`User/GraphService.py` and `User/UserService.py` are outside the WORK-PVAM-02 changed-file set and
`git_change_allowlist`, so this Round deliberately did not touch them.

---

## 8. Environment left clean

| Step | Result | Evidence |
|---|---|---|
| Controller-derived exact Redis cleanup | 234 exact keys requested, 188 deleted, 22 discovered via governed scan prefixes, **`remaining_count=0`** | `action-20260901T105145…` |
| `ConsumerLifecycle restore` | `matching_process_count=0`, baseline SHA matches the pre-snapshot restore | `action-20260901T105238447Z-d8494d7b713b4abb8deffe07f588bc7a.log` |
| `PVAmountV2Config restore` | `restored=true`, `snapshot_deleted=true`, back to state `01` / version 1 / pointer `1:45e2ee29…` | `action-20260901T105301798Z-ac46199e4e45450184957c9d36538cbd.log` |
| `RedisDbSize after` (final) | **20**, equal to the `before` baseline of 20 | `action-20260901T105324972Z-cc822035f12d44ae86832bb7d842ca7e.log` |

Cleanup covered every delivered identity's delivery ledger, order ledger, `order_ledger:__period_index__`,
refund reversal, all three idempotency namespaces at the delivery's own period, and the exact UserStats
business record for each controller-delivered `period + user_id`. The 22 discovered keys are the Elite
chain's own `elite_bonus_stats:…` and `eb_source:…` outputs, so the third chain's downstream records were
cleaned too. No pending activation remains, so `.loop-engine/finalize-pvam-v2-uat.ps1` is an idempotent
no-op.

---

## 9. Notes for the final auditor

- This report ends here as the immutable OPUS prefix. Fable appends `## Fable Final Audit` after it.
- `PRECHECK_PASS` means only that this Candidate may enter final audit. It is not a final PASS.
- Fable receives a **separate** final-audit period pair; it must never reuse slot 12 / 990023 / 990024.
- Suggested Fable focus, in order of residual risk:
  1. The `run()` non-buffered `poll` path in §5 — I judged it availability-only; form an independent view.
  2. `has_redis_residue = None` / `unclassified = true` on the genuinely undecidable path. It is unit-tested
     and matches the O-08 contract, but the governed action set has no scenario that produces it at runtime,
     so it remains unit-level only.
  3. Exception-topic consumer-side schema expectations for `has_redis_residue: null` — this project only
     produces to `pvam-pv-exceptions` (DEC-020 D11), so downstream tolerance is out of scope here, but it is
     the natural place for a nasty surprise.
- Two attempt-1 controller records have non-`SUCCESS` outcomes and are retained deliberately rather than
  suppressed: the `DaskListDatasets` scope denial (missing Pod — fail-closed working correctly) and the two
  `ConsumerObserve order` failures carrying the diagnostic traceback. Attempt 1's failed identities
  (`…-order-1`, `…-order-2`) were included in the final cleanup.
- Business-window isolation by `user_id` (§4.0) is the method that made a single clean pass possible. If
  Fable re-runs `cross-period-refund` or `future-period`, it should do the same or those two scenarios will
  corrupt each other's measurement window.
- Controller evidence for this stage: `.loop-output/controller-evidence/schema-10/cycle-3/round-3/opus/`.

---

*OPUS stage verdict: **PRECHECK_PASS**. Written to `.loop-output/opus-result.txt`.
This stage does not and cannot produce a final PASS.*

---

## Fable Final Audit

| | |
|---|---|
| **Verifier stage** | FABLE (independent final auditor) |
| **Final verdict** | **PASS** |
| **Candidate SHA** | `ae488243e5533778575b94e53935914a36dcae46` |
| **Stage input fingerprint** | `3a2c9b8fa83bba5c659f703a9c8011e0c096abf4fda595a818c47c12b7f8c656` |
| **Final-audit period slot** | 13 (fresh; Opus slot 12 not reused) |
| **Primary / secondary `PVAM_BOUND_PERIOD`** | 990025 (calc 209906) / 990026 (calc 209907) |
| **UAT period pool SHA-256** | `534015fda28c434091ee299a787d6226b8d5e7b8979c41a2178267ff6273be20` |
| **Durable UAT execution ID** | `c3-r3-fable-s13-ae488243e553` |
| **Authorization ID / actor** | `R9-UAT-C3-20260830` / `l343765828` |
| **Cycle / stage scope SHA-256** | `2a7887797013cb5467012374a29137b9f1db2861bc3f05a1c834bb729fcf0b31` / `60ff3511fde70bd8db9d2c9f8457e1214ad015fc5399efc20fda4b84d102ab1b` |
| **Pinned master AGENTS.md SHA-256** | `7ee25f8e4050568ba32857402a95ba1ee29bf8580d1bb3167496843b990f55ed` |
| **Controller evidence** | `.loop-output/controller-evidence/schema-10/cycle-3/round-3/fable/` |
| **GitHub run** | 33496840220 attempt 1 |

Every Kubernetes/UAT command went through
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:/Redemption/Redemption/.loop-engine/uat-action-proxy.ps1`.
No direct `kubectl`, `git`, `sh -c`, `bash -c` or ad-hoc mutable PowerShell was used. No Superpowers or
Ponytail skill, plugin, instruction file or methodology was read, loaded, invoked or relied on; the
Producer's skill declarations were treated as non-evidence. The pinned project Skills
(`redemption-file-filter`, `redemption-comment-style`) were read directly from their SKILL.md files and
applied to the review.

### 1. Independent audit scope

1. Re-derived the FABLE mandatory contract from `uat-action-policy.json` (SHA `c98c5f4e…`) and the proxy
   source itself, not from the Opus report.
2. Full independent read of the round-3 rework delta (`MessageConsumer/PvEventConsumer.py`, all 1253 lines,
   plus the test file structure and every new acceptance test) and contract spot-audit of the other 18
   changed files, against a GitAudit-proven clean worktree at the exact candidate SHA.
3. Authenticity audit of the Opus controller evidence (85 records mapped; sampled semantic payloads decoded
   and compared with report claims).
4. Full policy-defined selective revalidation on the fresh slot-13 period pair with a fresh durable
   execution identity — every action below is new schema-10 controller evidence in the Fable tree, not
   reuse of Opus evidence.

### 2. Opus evidence audit result

- All 85 Opus records carry the correct stage binding (execution `c3-r3-opus-s12-ae488243e553`, slot 12,
  990023/990024, authorization and scope SHAs). Sampled semantics decode byte-for-byte as reported:
  `PytestFull` "279 passed in 12.78s" exit 0; activate state `11` version 2 pointer `2:ed298bcb…`; final
  `dbsize` 20; controller-derived cleanup request. Attempt-1 non-SUCCESS records are disclosed, not
  suppressed, and the attempt-1 blocker was correctly classified as environment (files outside the
  change allowlist).
- One immaterial citation drift: report §8 cites the cleanup record as `action-20260901T105145…`; the
  actual file is `action-20260901T105138434Z-5e9612fed028449699062d99c521576f.log` (exists, SUCCESS,
  matching semantics).

### 3. Independent static review result

No new blocking defect in `6281356d..ae488243`. Key independent confirmations: F-01 boundary-aware residue
(`_traceback_context`/`_infer_residue` validated against the real `delivery_status` binding site in the
normalizer); F-02 epoch guard + post-poll re-checks on both the buffered-drain and retry loops, with
overflow stop-for-replay; F-03 bounded, sanitized, context-bearing retry diagnostics; commit discipline
(no auto-commit/store, message-bound synchronous commits inside the dispatch `try`, close-only `finally`,
never-resumed boundary pauses); Scheme B admission rejecting exactly state `10`; bootstrap only able to
publish `01`/`11` under CAS + read-after-write; dry-run-default exact-record migration; strict schema
(bool-period rejection, 2-decimal shared parser); the three exact idempotency namespaces; secret hygiene.

Independent adjudication of the three Opus residual-risk items — all concur, none blocking:

1. `run()` non-buffered poll without the epoch guard: availability-only under the single-instance
   deployment contract; redelivery is idempotent (proven live again this stage by `duplicate`), and a
   stale-epoch commit fails into `_handle_post_dispatch_commit_failure`, which never re-dispatches.
2. `has_redis_residue=None` undecidable path: reachable only through abnormal call topologies outside the
   production stack; correctly flagged `unclassified=true`; two unit tests pin it.
3. Downstream tolerance of `has_redis_residue: null`: out of WORK-PVAM-02 scope (producer-side only per
   DEC-020 D11).

Non-blocking observations recorded: two technical-English region titles in `PVAmountConfigBootstrap.py`
(`Read-after-write verify`, `CLI`) in an otherwise Chinese-titled file — style-level, in hunks accepted by
three prior rounds; and the §2 citation drift above.

### 4. Selective revalidation on the fresh period pair (all SUCCESS, schema-10 Fable evidence)

| Step | Result | Evidence (`action-…`) |
|---|---|---|
| `GitAudit` | clean worktree; local=remote=handoff=pushed `ae488243`; merge-base = baseline; 20 files allowlist+hunk OK | `20260901T111533211Z` |
| `List` pods | unique Running scheduler pod `dask-cluster-scheduler-67cbbcb9df-m8bcs` | `20260901T112300469Z` |
| `GitUpdate` | remote/node3-host/Pod-NFS three-way HEAD = candidate; debug pods UID-cleaned | `20260901T112408960Z` |
| `DaskListDatasets` | `healthy=true`: 3 datasets + GraphService actor with `dg_sponsor` and `dg_placement` loaded | `20260901T112448100Z` |
| `PytestSelected` (both contract targets) | **105 passed in 0.67s**, exit 0, in-Pod on candidate | `20260901T112531218Z` |
| `RedisDbSize before` | **20** | `20260901T112606936Z` |
| `ConsumerLifecycle restore` | `matching_process_count=0` before config mutation | `20260901T112639431Z` |
| `PVAmountV2Config snapshot` | state `01` v1 pointer `1:45e2ee29…` — byte-identical to Opus teardown | `20260901T112654160Z` |
| `PVAmountV2Config activate` | state **`11`** v2 pointer `2:ed298bcb…`, snapshot `pvam:amount_config:snapshot:2` | `20260901T112708917Z` |
| `ConsumerLifecycle bind-primary` | bound 990025 / calc 209906, 1 process, candidate-verified | `20260901T112802620Z` |
| `order` produce + observe | DISPATCHED + 3 namespaces; committed; primary delta **+1500990000** | `20260901T112843301Z`, `20260901T112913923Z` |
| `refund` produce + observe | exact reversal of the delivered order: primary delta **-1500990000** | `20260901T113001099Z`, `20260901T113032453Z` |
| `duplicate` produce + observe | 2 identical deliveries → **one** increment; `duplicate_no_double_ok=true` | `20260901T113119549Z`, `20260901T113153486Z` |
| `payload-drift` produce + observe | original applied once; drifted twin → exactly 1 `EVENT_IDENTITY_CONFLICT` | `20260901T113235619Z`, `20260901T113306560Z` |
| `RedisReadExactKeys` `duplicate-ledgers` | `amount_units="1500990000"` exact integer string; `status=DISPATCHED`; untruncated | `20260901T113351405Z` |
| `UatProof duplicate-no-double` | passed | `20260901T113433626Z` |
| `UatProof int64-end-to-end` | passed: dtype test + integer ledger + UserStats `int`/v2 | `20260901T113524000Z` |
| `UatProof dispatch-p99` | **p99 = 671.63 ms** vs 5000 ms limit (20 nonce-bound three-chain samples) | `20260901T113616969Z` |
| `RedisDeleteExactKeys` (controller-derived) | 140 requested / 140 deleted / **0 remaining**; covers all 24 delivered identities × ledgers + 3 namespaces + UserStats (incl. graph ancestors) + elite/eb_source | `20260901T113659996Z` |
| `ConsumerLifecycle restore` (final) | `matching_process_count=0` | `20260901T113746274Z` |
| `PVAmountV2Config restore` | CAS from this UAT's exact activation; back to `01`/v1/`1:45e2ee29…`; `restored=true`, `snapshot_deleted=true` | `20260901T113803592Z` |
| `RedisDbSize after` | **20 = before** — zero leak | `20260901T113823592Z` |

`business_value_proof_ok=true` on every observation. All v20/v21 ordering gates hold: restore → snapshot →
activate → bind-primary; every observe/proof before the final restore; cleanup before the final restore;
config restore after the consumer restore.

### 5. New findings

None blocking. The two non-blocking observations in §3 are recorded for hygiene only and do not affect
correctness, the governed contract, or the release decision.

### 6. Unresolved risks (carried, non-blocking, outside this Task-ID)

1. The shared-environment GraphService recovery gap (bootstrap cannot rebuild a lost in-memory graph while
   `users_version` stays published) — documented by Opus §7.2; `User/GraphService.py`/`User/UserService.py`
   are outside the WORK-PVAM-02 allowlist. Recommend a separate work item.
2. The 16 Failed historical scheduler pods remain as inert residue; harmless to controller pod selection.

### 7. Final rationale

The candidate's three round-2 findings are repaired with real, non-weakened, in-Pod-passing regression
tests; independent static review of the full diff found no new blocking defect; Opus's evidence is
authentic and its conclusions reproduce; and the complete policy-defined final-audit UAT re-ran green on a
fresh period pair with byte-exact environment restoration (dbsize 20→20, config pointer CAS-restored,
snapshot deleted, zero managed processes). Both F-201 Scheme B invariants held live throughout
(states {01,11} only, v2 records with `amount_encoding_version=2`, exact int64 units end to end).

**FABLE final verdict: PASS** — written to `.loop-output/uat-result.txt`.
