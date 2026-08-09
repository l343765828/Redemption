#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q tests/pvam/WORK-PVAM-01C/test_flag_runtime_contract.py --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
