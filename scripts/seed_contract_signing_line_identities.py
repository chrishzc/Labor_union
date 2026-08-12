"""Create validation LINE platform roots, then bind them through identity flows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_STAFF_SOURCE = Path("validation/external_inputs/contract_signing_staff_master_v1.json")
_CASE_SOURCE = Path("validation/datasets/dataset_v1_foundation.json")


def seed(arguments) -> dict[str, object]:
    _configure_database(arguments)
    staff, customer = _identity_subjects(arguments.staff_source, arguments.case_source)
    namespace = _line_namespace(arguments.line_namespace)
    _register_platform_users(namespace)
    return _bind_subjects(
        staff,
        customer,
        namespace,
        reuse_staff_binding=getattr(arguments, "reuse_staff_binding", False),
    )


def _configure_database(arguments) -> None:
    if not arguments.database.startswith("lu_test_dataset_"):
        raise ValueError("database must be a disposable validation dataset")
    if arguments.confirm_database != arguments.database:
        raise ValueError("confirmation must exactly match database")
    settings = {"DB_HOST": arguments.host, "DB_PORT": str(arguments.port), "DB_USER": arguments.user, "DB_PASSWORD": arguments.password, "DB_DATABASE": arguments.database}
    os.environ.update(settings)
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    DB_CONFIG.update({"host": arguments.host, "port": arguments.port, "user": arguments.user, "password": arguments.password, "database": arguments.database})


def _identity_subjects(staff_path: Path, case_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    staff = json.loads(staff_path.read_text(encoding="utf-8"))["staff"]
    customer = json.loads(case_path.read_text(encoding="utf-8"))["root_case"]["client_attributes"]
    return staff, customer


def _register_platform_users(namespace: str) -> None:
    from domains.line.identities import LineUserId, LineWebhookEventId
    from domains.line.platform_user import LineFriendEvent, LineFriendEventType
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
    users = (
        ("U-validation-staff-1", f"validation-follow-staff-{namespace}"),
        (f"U-validation-client-{namespace}", f"validation-follow-client-{namespace}"),
    )
    for user, event in users:
        with open_line_unit_of_work() as unit:
            unit.platform_users.apply_friend_event(LineFriendEvent(LineUserId(user), LineWebhookEventId(event), LineFriendEventType.FOLLOW, datetime(2026, 7, 1, tzinfo=timezone.utc)))
            unit.commit()


def _bind_subjects(
    staff: dict[str, object],
    customer: dict[str, object],
    namespace: str,
    *,
    reuse_staff_binding: bool,
) -> dict[str, object]:
    from api.dependencies.line_identity import get_line_identity_application
    from domains.line.identities import LineUserId
    from domains.line.identity_flow import LineIdentityFlowPurpose
    from shared_kernel.identities import CorrelationId, IdempotencyKey
    from subsystems.line.identity_contracts import CustomerIdentityProof, StaffIdentityProof
    get_line_identity_application.cache_clear()
    application = get_line_identity_application()
    staff_result = None if reuse_staff_binding else _bind(application, LineIdentityFlowPurpose.STAFF_VERIFICATION, LineUserId("U-validation-staff-1"), StaffIdentityProof(str(staff["name"]), str(staff["identity_card"]), datetime.fromisoformat(str(staff["birthday"])).date()), f"staff-{namespace}")
    client_result = _bind(application, LineIdentityFlowPurpose.CUSTOMER_BINDING, LineUserId(f"U-validation-client-{namespace}"), CustomerIdentityProof(str(customer["name"]), str(customer["phone"])), f"client-{namespace}")
    staff_status = "reused" if staff_result is None else _approve_staff_review_if_needed(staff_result, namespace)
    return {"staff": staff_status, "customer": client_result.status.value}


def _line_namespace(value: object) -> str:
    text = str(value or "default").strip().lower()
    if not text or not text.replace("-", "").isalnum():
        raise ValueError("line namespace must be alphanumeric or hyphen")
    return text


def _approve_staff_review_if_needed(result, namespace: str) -> str:
    if result.status.value != "pending_review":
        return result.status.value
    from api.dependencies.line_identity import get_line_identity_review_application
    from domains.line.review import LineReviewDecision
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from subsystems.line.review_contracts import DecideLineReviewCommand
    application = get_line_identity_review_application()
    snapshot = application.get(result.review_request_id)
    approved = application.decide(DecideLineReviewCommand(snapshot.request_id, LineReviewDecision.APPROVE, snapshot.version, ActorContext("validation-dataset-seed", ("line.identity.review",)), "approve synthetic staff identity evidence", IdempotencyKey(f"validation-contract-staff-review-approve-{namespace}"), CorrelationId(f"validation-contract-staff-review-approve-{namespace}")))
    return approved.snapshot.status.value


def _bind(application, purpose, user, proof, suffix):
    from shared_kernel.identities import CorrelationId, IdempotencyKey

    flow = application.open_flow(purpose, user, IdempotencyKey(f"validation-contract-flow-{suffix}"), CorrelationId(f"validation-contract-flow-{suffix}"))
    if purpose.value == "staff_verification":
        return application.apply_staff(flow.flow_id, user, proof, CorrelationId(f"validation-contract-apply-{suffix}"))
    return application.apply_customer(flow.flow_id, user, proof, CorrelationId(f"validation-contract-apply-{suffix}"))


def main() -> int:
    values = dotenv_values(".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=values.get("DB_HOST") or "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(values.get("DB_PORT") or 3306))
    parser.add_argument("--user", default=values.get("DB_USER") or "root")
    parser.add_argument("--password", default=values.get("DB_PASSWORD") or "1234")
    parser.add_argument("--database", required=True)
    parser.add_argument("--confirm-database", required=True)
    parser.add_argument("--staff-source", type=Path, default=_STAFF_SOURCE)
    parser.add_argument("--case-source", type=Path, default=_CASE_SOURCE)
    parser.add_argument("--line-namespace", default="default")
    parser.add_argument("--reuse-staff-binding", action="store_true")
    print(json.dumps(seed(parser.parse_args()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
