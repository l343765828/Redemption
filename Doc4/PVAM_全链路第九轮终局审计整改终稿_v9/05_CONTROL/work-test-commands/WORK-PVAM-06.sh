#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q User/Test/test_settlement_coordinator.py User/Test/test_settlement_guard.py User/Test/test_topology_mutation_wiring.py --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
