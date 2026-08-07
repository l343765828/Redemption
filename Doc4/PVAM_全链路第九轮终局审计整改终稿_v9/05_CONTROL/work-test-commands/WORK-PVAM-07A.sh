#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q MessageConsumer/Test/test_recalc_ack_fail_closed.py --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
