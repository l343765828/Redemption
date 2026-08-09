#!/usr/bin/env bash
set -euo pipefail
: "${PVAM_EVIDENCE_DIR:?set by validate_work_dev.sh}"
mkdir -p "$PVAM_EVIDENCE_DIR"
python -m pytest -q User/Test/test_pv_amount_common.py User/Test/test_amount_model_version.py tests/pvam/WORK-PVAM-01/test_flag_factory_contract.py --junitxml="$PVAM_EVIDENCE_DIR/junit.xml"
