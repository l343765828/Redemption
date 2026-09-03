# WORK-PVAM-02 Cycle 3 Round 3 — IMPLEMENTATION HANDOFF

## Identity

- Task-ID: WORK-PVAM-02
- Cycle / Round: 3 / 3
- Findings-Source: OPUS
- Baseline-SHA: `6281356d77306016cfb96567e84c14a66eefdbbb`
- Candidate-HEAD-before-rework: `7a94f2183b70f7a54dfe71bc92e7f42c7724e142`
- Candidate-HEAD-tree-before-rework: `1a589e5ac60e2d34f941a210381dc71c49c42792`
- Candidate-HEAD-parent: `170d6696daace0cf2f18b866ca88a7547347b5a8`
- Local-Commit-HEAD-SHA: N/A（按契约由 workflow 提交）
- Producer-Status: READY_FOR_UAT

## Opening verification and authoritative inputs

- Branch: `codex/pvam-work02-uat-candidate-20260813`.
- Initial independent `git status --porcelain=v1 --untracked-files=all`: no entries; only the local global-ignore permission warning was printed.
- Initial independent `git diff --stat --` and `git diff --name-only --`: no output.
- The first combined PowerShell command did not provide valid tree/status evidence: unquoted `HEAD^{tree}` was interpreted by the shell and injected `-encodedCommand dAByAGUAZQA=` into later git arguments. It was discarded. Final independent `git cat-file -p HEAD` proved tree `1a589e5ac60e2d34f941a210381dc71c49c42792` and parent `170d6696daace0cf2f18b866ca88a7547347b5a8`.
- Read the complete Controller-supplied OPUS findings in the prompt before editing.
- Read the two construction instructions from the main repository, DEC-020 through §17, MSG-CONTRACT-v1, and the authoritative Scheme B design. The pinned main `AGENTS.md` content was supplied by the Controller; `D:\Redemption\Redemption\AGENTS.md` SHA-256 was independently verified as `7ee25f8e4050568ba32857402a95ba1ee29bf8580d1bb3167496843b990f55ed`.
- Controller-staged comment Skill SHA-256 matched `0c860127b1180ae2032898e4d19a8450434d1b0b646f58979bc569a30f1f8158`; its reference matched `2dabd35a40b0a01e6ac58ce63f66edcef85a092b4f741040b858be8d1d4db3ee`.

## Independently confirmed findings and repairs

### F-01 — residue accuracy

Confirmed in `PvEventConsumer._classify_exception`: the function calculated `residue` from traceback/boundary state, then discarded it by hardcoding `True` for `RefundReversalConflict` and `OriginalOrderNotRefundable`.

Repair:

- `ConsumedOrderConflict` and `DeliveryIdentityConflict` remain category 3 with residue `True`.
- `RefundReversalConflict` and `OriginalOrderNotRefundable` remain category 3 / `PERSISTENT_FAILURE`, but now retain the inferred `False`, `True`, or `None` residue.
- When residue is genuinely undecidable, the decision now carries `has_redis_residue=None` and `unclassified=True`.
- Real normalizer/coordinator tests cover period conflict, amount conflict, `get_refundable_order` rejection, and post-PENDING `claim_whole_order` conflict; commit discipline is asserted.

### F-02 — rebalance during buffered drain

Confirmed in `PvEventConsumer.run`: `consumer.poll()` can synchronously invoke `on_revoke`, which clears `_buffered_messages`; the subsequent unconditional `popleft()` raised `IndexError`. A message returned by that same poll could also be re-added after the assignment epoch changed.

Repair:

- `run()` rechecks deque emptiness after heartbeat polling before dequeueing.
- `_poll_and_buffer()` captures the existing `_assignment_epoch` and discards a message returned after a rebalance callback changes the epoch.
- Regression tests prove the empty-deque path returns normally, the revoke callback itself leaves `running` unchanged, and neither a prebuffered nor same-poll revoked message is dispatched or committed.
- The existing ordinary buffered-drain test remains unchanged and passes, including `poll_timeouts[1] == 0.0`, coordinator ordering, and exactly-once commit.

### F-03 — blocked retry diagnostics

Confirmed in `PvEventConsumer._retry_dispatch`: entry attempts 1–9 emitted no diagnostic, while the periodic warning contained only topic/partition/attempt count. Category 2 can loop indefinitely.

Repair:

- One warning is emitted on entering the blocked retry loop.
- Existing every-10-attempt cadence is preserved and enriched; there is still no per-attempt log.
- Entry and periodic records include `event_identity`, `failed_stage`, `reason`, `exception_class`, and sanitized `exception_message` plus existing partition context.
- Both paths reuse `_sanitize_exception_message`; tests prove the synthetic Redis credential/URI is absent.

## Changed files

- `MessageConsumer/PvEventConsumer.py`
  - Boundary-aware refund residue classification.
  - Assignment-epoch guard and empty-buffer recheck during drain.
  - Sanitized, bounded blocked-retry diagnostics.
- `MessageConsumer/Test/test_pv_event_consumer.py`
  - Added 10 collected regression cases (nine new cases plus one new parameter instance) covering all OPUS acceptance paths.
  - No skip/xfail or weakened assertion was added.

Final diff stat:

```text
 MessageConsumer/PvEventConsumer.py             |  47 ++++-
 MessageConsumer/Test/test_pv_event_consumer.py | 267 ++++++++++++++++++++++++-
 2 files changed, 300 insertions(+), 14 deletions(-)
```

Final changed-file scope:

```text
MessageConsumer/PvEventConsumer.py
MessageConsumer/Test/test_pv_event_consumer.py
```

Both files are inside the authoritative maximum production/test permission set. No SQL, Doc4, Kubernetes, production configuration, Provider/Bootstrap/Migration, or three service file was modified.

## Producer Skills actually read and used

1. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\using-superpowers\SKILL.md`
2. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\using-superpowers\references\codex-tools.md`
3. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\receiving-code-review\SKILL.md`
4. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\systematic-debugging\SKILL.md`
5. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\test-driven-development\SKILL.md`
6. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\test-driven-development\writing-good-tests.md`
7. `C:\Users\Administrator\.codex\plugins\cache\ponytail\ponytail\4.9.0\skills\ponytail\SKILL.md` (full)
8. `D:\actions-runner\_work\_temp\loop-engine-producer\run-33458540982-attempt-1-cycle-3-round-3\skills\redemption-comment-style\SKILL.md`
9. `D:\actions-runner\_work\_temp\loop-engine-producer\run-33458540982-attempt-1-cycle-3-round-3\skills\redemption-comment-style\references\comment-patterns.md`
10. `D:\Redemption\Worktrees\pvam-work02-m2-float64-test\.claude\skills\redemption-file-filter\SKILL.md`
11. `C:\Users\Administrator\.codex\plugins\cache\openai-curated-remote\superpowers\6.3.0\skills\verification-before-completion\SKILL.md`

No brainstorming, writing-plans, executing-plans, multi-agent, or reviewer-side Skill was used.

Comment Style influence: the new concurrency comments are concise Chinese intent/invariant comments inside the existing main-loop and buffering regions. No noisy per-line comments or unrelated region churn was added.

Ponytail full influence: reused `_infer_residue`, `_assignment_epoch`, `_sanitize_exception_message`, the existing retry cadence, fake consumer hook, real normalizer/coordinator, and in-memory ledgers. Avoided a second residue classifier, per-message epoch wrapper, new logging abstraction/configuration, new dependency, service edits, and speculative Consumer migration behavior.

## TDD RED evidence

The initial PATH interpreter command did not enter pytest and is not counted as RED:

```text
python -m pytest ...
Exit code: 1
程序“python.exe”无法运行: 系统无法访问此文件。
```

Valid RED command before production edits:

```powershell
& 'D:\Redemption\Redemption\.venv\Scripts\python.exe' -m pytest -q MessageConsumer/Test/test_pv_event_consumer.py -k "revoke_during_buffered_drain or revoke_discards_message_returned or refund_validation_conflicts_before_delivery or original_order_not_refundable_before_delivery or refund_claim_conflict_after_delivery or blocked_retry_logs_classification or blocked_retry_periodic_log"
```

Result / exit 1:

```text
7 failed, 1 passed, 69 deselected in 0.55s
```

Expected failures included the exact `IndexError: pop from an empty deque`, revoked message dispatch, three `True is False` residue mismatches, zero entry retry logs, and a periodic log lacking the required second contextual record.

Additional undecidable-residue RED command before production edits:

```powershell
& 'D:\Redemption\Redemption\.venv\Scripts\python.exe' -m pytest -q MessageConsumer/Test/test_pv_event_consumer.py::test_unraised_refund_conflict_keeps_residue_unknown
```

Result / exit 1:

```text
1 failed in 0.27s
AssertionError: assert True is None
```

## GREEN and final verification evidence

First focused GREEN command after the minimal production repair:

```powershell
& 'D:\Redemption\Redemption\.venv\Scripts\python.exe' -m pytest -q MessageConsumer/Test/test_pv_event_consumer.py -k "revoke_during_buffered_drain or revoke_discards_message_returned or refund_validation_conflicts_before_delivery or original_order_not_refundable_before_delivery or refund_claim_conflict_after_delivery or blocked_retry_logs_classification or blocked_retry_periodic_log or unraised_refund_conflict"
```

Result / exit 0:

```text
9 passed, 69 deselected in 0.08s
```

Fresh final target command (`PYTHONDONTWRITEBYTECODE=1`) / exit 0:

```powershell
& 'D:\Redemption\Redemption\.venv\Scripts\python.exe' -m pytest -q MessageConsumer/Test/test_pv_event_consumer.py User/Test/test_pv_event_normalizer.py
```

```text
147 passed in 1.17s
```

Fresh final locally collectible suite command (`PYTHONDONTWRITEBYTECODE=1`) / exit 0:

```powershell
& 'D:\Redemption\Redemption\.venv\Scripts\python.exe' -m pytest -q --ignore=User/Test/test_amount_dtype_migration.py --ignore=User/Test/test_bonus_config.py --ignore=User/Test/test_team_bonus_tb.py --ignore=User/test_bonus_pipeline_auto_check.py --ignore=User/test_userstatsservice_elite_report.py
```

```text
228 passed, 85 subtests passed in 3.31s
```

Other checks:

- `python -m py_compile MessageConsumer/PvEventConsumer.py MessageConsumer/Test/test_pv_event_consumer.py` — exit 0, no output.
- `pytest --collect-only -q MessageConsumer/Test/test_pv_event_consumer.py User/Test/test_pv_event_normalizer.py` — exit 0, `147 tests collected in 0.09s`.
- `git diff --check` — exit 0, no output.
- Final `git status --porcelain=v1 --untracked-files=all` — only the two modified allowed files; the global-ignore permission warning is an environment warning.
- No git add/commit/push/checkout/reset/clean operation was executed.

## Full-suite boundary and checks not passed

An unfiltered local `pytest -q` was actually attempted and stopped during collection (exit 1) with five existing environment/import errors:

- `User/Test/test_amount_dtype_migration.py`: `ModuleNotFoundError: pandas`
- `User/Test/test_bonus_config.py`: `ModuleNotFoundError: pandas`
- `User/Test/test_team_bonus_tb.py`: `ModuleNotFoundError: pandas`
- `User/test_bonus_pipeline_auto_check.py`: `ModuleNotFoundError: cudf`
- `User/test_userstatsservice_elite_report.py`: `ModuleNotFoundError: UserStatsService`

Therefore this handoff does not claim an unfiltered local full-suite pass. The prior governed OPUS report states 269 + 133 tests passed in the Pod for Candidate `7a94f218...`; Producer did not rerun that Pod suite after this rework.

`black --check` was attempted, but this local virtual environment has no `black` module. No lint/format pass is claimed. No dependency was installed.

Producer did not run Kubernetes, Dask, Kafka, Redis, GPU, Consumer rebalance integration, or live exception-topic UAT. These remain Verifier activities.

## Notes-For-Verifier

1. Material conflict/assumption: the original construction instruction §6.7 contains the historical blanket wording that the four ledger-conflict exception types are category 3 with residue `true`. DEC-020 §13.1 says classification/residue truth depends on the PENDING boundary, and current OPUS F-01 plus the user rework contract explicitly require pre/post paths to be distinguished while preserving category 3. This rework follows the higher-priority current instruction: category/reason remain unchanged, only `has_redis_residue` follows the already-computed boundary evidence; unknown evidence is JSON null/unclassified.
2. The same-poll rebalance test models confluent-kafka invoking `on_revoke` inside `poll()` and returning a message afterward. Candidate now rejects that return when the assignment epoch changed. Live librdkafka rebalance behavior was not exercised locally and should remain part of UAT.
3. Entry retry logging adds one bounded warning per blocked episode; periodic cadence remains once every ten attempts. Secret redaction was verified with a synthetic URI/password only.
4. The test/compile run created untracked bytecode caches. After validating every path came from `git status` and remained inside the worktree, 53 generated `.pyc` files were deleted and empty cache directories removed. Final tests used `PYTHONDONTWRITEBYTECODE=1`; final status has no generated artifact.
5. No Scheme B Provider/Bootstrap/Migration/service behavior was reopened because all three OPUS findings were confined to `PvEventConsumer.py`, and the previous governed report already marked those Scheme B ACs PASS.

## UAT focus

- Re-run the governed target/full Pod suites on the workflow-created Candidate SHA.
- Exercise a real group rebalance while heartbeat buffering is non-empty; assert process survival, no revoked-message dispatch/commit, and replay under the new assignment.
- Tail exception-topic output for pre-boundary refund period/amount/not-refundable cases and post-boundary claim conflict; verify exact `has_redis_residue` false/true values.
- Force a long category-2 block and verify one entry warning plus one contextual warning per ten attempts, with real configured credential material absent from logs.

## CONTROLLER CANDIDATE CONTRACT
Candidate SHA: ae488243e5533778575b94e53935914a36dcae46
Baseline SHA: 6281356d77306016cfb96567e84c14a66eefdbbb
Target branch: codex/pvam-work02-uat-candidate-20260813
Changed files:
- `Common/PeriodResolver.py`
- `MessageConsumer/PvEventConsumer.py`
- `MessageConsumer/PvEventNormalizer.py`
- `MessageConsumer/PvEventSchema.py`
- `MessageConsumer/Test/test_pv_event_consumer.py`
- `Model/Config.py`
- `Model/Order/NormalizedPvEvent.py`
- `Redishelper/BaseRedisModel.py`
- `Redishelper/PVAmountConfigBootstrap.py`
- `Redishelper/PVAmountConfigProvider.py`
- `Redishelper/PVAmountMigration.py`
- `User/EliteBonusService.py`
- `User/PlacementIncrementalService.py`
- `User/Test/test_period_resolver.py`
- `User/Test/test_pv_event_normalizer.py`
- `User/UserStatsService.py`
- `tests/pvam/WORK-PVAM-01/test_flag_factory_contract.py`
- `tests/pvam/WORK-PVAM-01C/test_flag_runtime_contract.py`
- `tests/pvam/WORK-PVAM-02/test_amount_migration.py`
- `tests/pvam/WORK-PVAM-02/test_three_chain_scheme_b.py`
