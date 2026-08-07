#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q User/Test/test_elite_atomic_commit.py User/Test/test_elite_publish_batch.py --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
