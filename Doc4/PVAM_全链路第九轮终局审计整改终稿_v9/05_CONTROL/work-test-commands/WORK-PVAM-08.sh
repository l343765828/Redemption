#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q User/Test MessageConsumer/Test uat/Test --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
