#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q User/Test/test_pv_event_normalizer.py User/Test/test_period_resolver.py User/Test/test_amount_dtype_migration.py --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
