"""Preview/adopt a unique original BeClass refund account through the existing correction writer.

Default is read-only preview. Applying a real-data correction requires a separate
explicitly authorized invocation with the original version, preview and operation key.
"""
from __future__ import annotations

import argparse
import json
import os

from domains.case_import.refund_account import mask_refund_values
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.case_import.beclass_correction_workflow import BeClassCorrectionWorkflow


def prepare(repository, case_no):
    account = repository.original_refund_account(case_no)
    if account is None:
        raise ValueError("beclass_refund_source_incomplete")
    return {"refund_bank_code": account.bank_code, "refund_account_no": account.account_no}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-no", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-version", type=int)
    parser.add_argument("--preview-fingerprint")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--actor")
    args = parser.parse_args()
    if args.apply and any(value is None for value in (args.expected_version, args.preview_fingerprint, args.idempotency_key, args.actor)):
        parser.error("Apply requires the reviewed version, preview fingerprint, operation key and actor.")
    from infrastructure.mysql.mysql_adapter import _database_config_from_environment, get_connection
    from infrastructure.mysql.beclass_correction_repository import MySqlBeClassCorrectionRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    config = _database_config_from_environment()
    if os.getenv("APP_ENV", "development") != "development" or config["host"] not in {"127.0.0.1", "localhost"}:
        parser.error("This bounded maintenance tool is limited to local development.")
    if config["database"] != "union_db" and not config["database"].startswith("lu_test_"):
        parser.error("Unexpected local maintenance database.")
    connection = get_connection()
    try:
        repository = MySqlBeClassCorrectionRepository(connection)
        workflow = BeClassCorrectionWorkflow(repository, lambda: MySqlUnitOfWork(connection))
        changes = prepare(repository, args.case_no)
        if args.apply:
            receipt = workflow.apply(args.case_no, changes, ExpectedVersion(args.expected_version),
                PreviewFingerprint(args.preview_fingerprint), IdempotencyKey(args.idempotency_key),
                ActorContext(args.actor), "依唯一原始問卷補齊正式退款帳戶",
                CorrelationId("registration-refund-account-repair"))
            result = {"case_no": receipt.case_no, "resulting_version": receipt.resulting_version,
                      "changed_fields": receipt.changed_fields, "replayed": receipt.replayed}
        else:
            snapshot = workflow.query(args.case_no)
            if any(snapshot.effective.get(field) for field in changes):
                raise ValueError("beclass_refund_account_already_present")
            preview = workflow.preview(args.case_no, changes, ExpectedVersion(snapshot.version))
            result = {"case_no": args.case_no, "mode": "preview_only", "current_version": preview.current_version,
                      "preview_fingerprint": preview.preview_fingerprint.value,
                      "before": mask_refund_values(preview.before), "after": mask_refund_values(preview.after)}
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # Do not print SQL errors, raw account inputs or generic exception representations.
        print(json.dumps({"case_no": args.case_no, "status": "not_applied", "code": "refund_account_repair_incomplete"}))
        return 1
    finally:
        connection.rollback()
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
