"""
File: run_task96_rpre_browser_scenario.py
Description: 以正式 no-auth API 建立停在 stage 04 的 fresh RPRE Browser 驗收案件。
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path
import re
import sys

from fastapi.testclient import TestClient
import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_task96_hob_route_a as route_a
from api.dependencies.matching_coordination import get_matching_coordination_composition
from domains.scheduling.matching_coordination import (
    MatchingPackage,
    MatchingPackageMode,
    MatchingPackageState,
    MatchingSegment,
    build_manual_matching_package,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.scheduling.matching_coordination_application import (
    MatchingCoordinationApplication,
)
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyCustomerMatchingDecision,
    PreviewMatchingPackage,
)


DEFAULT_CASE_NO = "115960402"
DEFAULT_SERVICE_DATES = (
    "2026-09-14",
    "2026-09-15",
    "2026-09-16",
    "2026-09-17",
    "2026-09-18",
)
SCENARIO = "R-02"


def _configured_database() -> str:
    database = os.getenv("DB_DATABASE", "").strip()
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", database):
        raise RuntimeError("task96_rpre_browser_database_must_be_lu_test")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise RuntimeError("task96_rpre_browser_requires_development_validation_profile")
    return database


def _configured_service_dates() -> tuple[str, ...]:
    raw = os.getenv("TASK96_RPRE_SERVICE_DATES", "").strip()
    values = tuple(item.strip() for item in raw.split(",") if item.strip()) or DEFAULT_SERVICE_DATES
    if len(values) != len(set(values)) or tuple(sorted(values)) != values:
        raise RuntimeError("task96_rpre_service_dates_must_be_unique_and_sorted")
    return values


def _ensure_order_matching_preferences(client: TestClient) -> dict[str, object]:
    path = f"/api/v1/orders/{route_a.CASE_NO}/terms"
    current = route_a._require_success(client.get(path), "order_terms_query")
    terms = dict(current["terms"])
    if terms.get("requires_cooking") is not None:
        return current
    terms["requires_cooking"] = False
    preview = route_a._require_success(
        client.post(
            f"{path}/preview",
            headers={
                "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:terms-preview"
            },
            json={"proposed_terms": terms},
        ),
        "order_terms_preview",
    )
    return route_a._require_success(
        client.post(
            f"{path}/apply",
            headers={
                "Idempotency-Key": f"task96:rpre:{route_a.CASE_NO}:terms-apply",
                "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:terms-apply",
            },
            json={
                "proposed_terms": terms,
                "expected_order_version": preview["order_version"],
                "expected_scheduling_version": preview["scheduling_version"],
                "expected_client_finance_version": preview[
                    "client_finance_version"
                ],
                "expected_payroll_version": preview["payroll_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 RPRE synthetic matching preference",
            },
        ),
        "order_terms_apply",
    )


def _configure_route() -> None:
    global SCENARIO
    database = _configured_database()
    scenario = os.getenv("TASK96_RPRE_SCENARIO", "R-02").strip()
    if scenario not in {"R-01", "R-02", "R-03", "R-04", "R-07"}:
        raise RuntimeError("task96_rpre_fixture_scenario_not_supported")
    SCENARIO = scenario
    case_no = os.getenv("TASK96_RPRE_CASE_NO", DEFAULT_CASE_NO).strip()
    if not case_no or len(case_no) > 50:
        raise RuntimeError("task96_rpre_case_no_invalid")
    route_a.DATABASE = database
    route_a.CASE_NO = case_no
    route_a.SERVICE_DATES = _configured_service_dates()
    route_a.SCENARIO_ID = f"TASK96-RPRE-{scenario}-{case_no}"
    route_a.SOURCE_REVISION = f"TASK96-RPRE-{scenario}-{case_no}-r1"


class _PackageFixtureFactsReader:
    """Inject one previewed package while retaining fresh owner-fact reads."""

    def __init__(self, delegate: object, package: object) -> None:
        self._delegate = delegate
        self._package = package

    def load(self, case_no: str):
        return replace(self._delegate.load(case_no), package=self._package)

    def load_fresh(self, case_no: str, *, for_update: bool):
        return replace(
            self._delegate.load_fresh(case_no, for_update=for_update),
            package=self._package,
        )


def _seed_canonical_matching_package(
    *,
    staff_id: int,
) -> dict[str, object]:
    """Create a canonical M3 package through production workflow/repository code.

    M3 currently exposes package Preview but no package Apply endpoint.  This
    validation-only fixture injects that preview into the production Apply
    orchestration so RPRE can be tested against real canonical lineage rather
    than fabricated table rows.
    """

    dependency = get_matching_coordination_composition()
    composition = next(dependency)
    try:
        application = composition.application
        facts = application._facts_reader.load(route_a.CASE_NO)
        service_dates = tuple(date.fromisoformat(value) for value in route_a.SERVICE_DATES)
        preview = application.preview(
            PreviewMatchingPackage(
                case_no=route_a.CASE_NO,
                actor=ActorContext("system:local_bypass"),
                reason="Task 96 RPRE canonical browser fixture",
                correlation_id=CorrelationId(
                    f"task96:rpre:{route_a.CASE_NO}:package-preview"
                ),
                idempotency_key=IdempotencyKey(
                    f"task96:rpre:{route_a.CASE_NO}:package-preview"
                ),
                expected_source_versions=facts.source_versions,
                criteria_snapshot_id=facts.snapshot.snapshot_id,
                required_service_dates=service_dates,
                segments=(MatchingSegment(staff_id, service_dates, 1),),
            )
        )
        candidates = tuple(
            item for item in facts.candidates if item.staff_id == staff_id
        )
        if len(candidates) != 1:
            raise RuntimeError("task96_rpre_matching_candidate_not_unique")
        candidate = candidates[0]
        package = build_manual_matching_package(
            package_id=preview.package_id,
            version=preview.version,
            segments=(MatchingSegment(staff_id, service_dates, 1),),
            required_service_dates=service_dates,
            candidate_results=facts.candidates,
            criteria_snapshot_id=facts.snapshot.snapshot_id,
            source_versions=facts.source_versions,
        )
        if package.fingerprint != preview.fingerprint:
            raise RuntimeError("task96_rpre_matching_preview_domain_drift")
        seeded = MatchingCoordinationApplication(
            _PackageFixtureFactsReader(application._facts_reader, package),
            application._repository,
            application._unit_of_work_factory,
            workflow=application._workflow,
            clock=application._clock,
        )
        receipt = seeded.apply(
            ApplyCustomerMatchingDecision(
                case_no=route_a.CASE_NO,
                actor=ActorContext("system:local_bypass"),
                reason="Task 96 RPRE canonical browser fixture",
                correlation_id=CorrelationId(
                    f"task96:rpre:{route_a.CASE_NO}:customer-decision"
                ),
                idempotency_key=IdempotencyKey(
                    f"task96:rpre:{route_a.CASE_NO}:customer-decision"
                ),
                expected_source_versions=facts.source_versions,
                criteria_snapshot_id=facts.snapshot.snapshot_id,
                package_id=package.package_id,
                package_version=package.version,
                candidate_id=candidate.candidate_id,
                decision="accepted",
                preview_fingerprint=package.fingerprint,
            )
        )
        return {
            "criteria_snapshot_id": facts.snapshot.snapshot_id,
            "package_id": package.package_id,
            "package_version": package.version,
            "package_fingerprint": package.fingerprint.value,
            "candidate_id": candidate.candidate_id,
            "customer_decision_receipt_id": receipt.receipt_id,
            "source_versions": {
                "items": [
                    {
                        "source_kind": item.source_kind,
                        "source_id": item.source_id,
                        "version": item.version,
                        "fingerprint": item.fingerprint,
                    }
                    for item in facts.source_versions
                ]
            },
        }
    finally:
        try:
            next(dependency)
        except StopIteration:
            pass


def _ensure_candidate_contact_pool(
    client: TestClient,
    *,
    staff_id: int,
    target_willingness: str = "willing",
) -> int:
    if target_willingness not in {"willing", "unwilling"}:
        raise ValueError("task96_rpre_candidate_willingness_invalid")
    pool = route_a._require_success(
        client.get(
            f"/api/v1/orders/{route_a.CASE_NO}/candidate-contact-pool"
        ),
        "candidate_contact_pool_query",
    )
    matching_candidates = [
        item for item in pool.get("candidates", ()) if item.get("staff_id") == staff_id
    ]
    if not matching_candidates:
        added = route_a._require_success(
            client.post(
                f"/api/v1/orders/{route_a.CASE_NO}/candidate-contact-pool/candidates",
                json={
                    "actor": route_a.ACTOR,
                    "event_key": f"task96-rpre-{route_a.CASE_NO}-candidate-add",
                    "candidates": [
                        {
                            "staff_id": staff_id,
                            "start_date": route_a.SERVICE_DATES[0],
                            "end_date": route_a.SERVICE_DATES[-1],
                        }
                    ],
                },
            ),
            "candidate_contact_pool_add",
        )
        candidate_id = int(added["candidate_ids"][0])
        candidate_willingness = "pending"
    elif len(matching_candidates) == 1:
        candidate_id = int(matching_candidates[0]["id"])
        candidate_willingness = matching_candidates[0]["willingness"]
    else:
        raise RuntimeError("task96_rpre_candidate_contact_identity_not_unique")
    if candidate_willingness != target_willingness:
        route_a._require_success(
            client.put(
                f"/api/v1/orders/{route_a.CASE_NO}/candidate-contact-pool/candidates/{candidate_id}/willingness",
                json={
                    "actor": route_a.ACTOR,
                    "event_key": (
                        f"task96-rpre-{route_a.CASE_NO}-candidate-"
                        f"{target_willingness}"
                    ),
                    "willingness": target_willingness,
                    "reason": (
                        "service_date_conflict"
                        if target_willingness == "unwilling"
                        else "Task 96 RPRE canonical browser fixture"
                    ),
                },
            ),
            "candidate_contact_pool_willingness",
        )
    return candidate_id


def _ensure_r03_line_identity_bindings(client: TestClient) -> dict[str, object]:
    bindings = (
        (
            "customer",
            "customer_binding",
            f"task96-rpre-customer-{route_a.CASE_NO}",
            {"name": route_a.CLIENT_NAME, "phone": route_a.CLIENT_PHONE},
        ),
        (
            "staff",
            "staff_verification",
            f"task96-rpre-staff-{route_a.CASE_NO}",
            {
                "name": route_a.STAFF_NAME,
                "identity_card": route_a.STAFF_IDENTITY,
                "birthday": "1990-01-02",
            },
        ),
    )
    receipts: dict[str, object] = {}
    for kind, purpose, line_user_id, proof in bindings:
        existing = _read_r03_line_identity_binding(
            line_user_id=line_user_id,
            subject_type="customer" if kind == "customer" else "staff",
        )
        if existing is not None:
            receipts[kind] = {"status": "bound", "existing": existing}
            continue
        flow = route_a._require_success(
            client.post(
                "/api/v1/line/identity/flow/open",
                json={
                    "purpose": purpose,
                    "idempotency_key": f"task96:rpre:{route_a.CASE_NO}:line:{kind}:flow",
                    "development_line_user_id": line_user_id,
                },
            ),
            f"rpre_r03_line_{kind}_flow",
        )
        request = {
            "flow_id": flow["flow_id"],
            "development_line_user_id": line_user_id,
            **proof,
        }
        preview = route_a._require_success(
            client.post(
                f"/api/v1/line/identity/{kind}/preview",
                json=request,
            ),
            f"rpre_r03_line_{kind}_preview",
        )
        applied = route_a._require_success(
            client.post(
                f"/api/v1/line/identity/{kind}/apply",
                json={
                    **request,
                    "expected_version": preview["expected_version"],
                    "preview_fingerprint": preview["preview_fingerprint"],
                },
            ),
            f"rpre_r03_line_{kind}_apply",
        )
        review = None
        if applied["status"] == "pending_review":
            review_request_id = applied.get("review_request_id")
            if not isinstance(review_request_id, int):
                raise RuntimeError("task96_rpre_line_review_identity_missing")
            review_reason = "Task 96 RPRE canonical browser fixture"
            review_snapshot = route_a._require_success(
                client.get(f"/api/v1/line/identity/reviews/{review_request_id}"),
                f"rpre_r03_line_{kind}_review_detail",
            )
            review_preview = route_a._require_success(
                client.post(
                    f"/api/v1/line/identity/reviews/{review_request_id}/approve/preview",
                    json={
                        "expected_version": review_snapshot["version"],
                        "reason": review_reason,
                    },
                ),
                f"rpre_r03_line_{kind}_review_preview",
            )
            review = route_a._require_success(
                client.post(
                    f"/api/v1/line/identity/reviews/{review_request_id}/approve/apply",
                    json={
                        "expected_version": review_preview["expected_version"],
                        "reason": review_reason,
                        "idempotency_key": (
                            f"task96:rpre:{route_a.CASE_NO}:line:{kind}:review"
                        ),
                        "preview_fingerprint": review_preview["preview_fingerprint"],
                    },
                ),
                f"rpre_r03_line_{kind}_review_apply",
            )
            if review["status"] != "approved":
                raise RuntimeError("task96_rpre_line_review_not_approved")
        receipts[kind] = {
            "status": applied["status"],
            "receipt_identity": applied["receipt_identity"],
            "review": review,
        }
    return receipts


def _read_r03_line_identity_binding(
    *,
    line_user_id: str,
    subject_type: str,
) -> dict[str, object] | None:
    connection = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        database=route_a.DATABASE,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT line_user_id,binding_status,subject_type,subject_reference,"
                "aggregate_version FROM line_identity_bindings WHERE line_user_id=%s",
                (line_user_id,),
            )
            rows = tuple(cursor.fetchall() or ())
    finally:
        connection.close()
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError("task96_rpre_line_binding_identity_not_unique")
    row = rows[0]
    if (
        row.get("binding_status") != "bound"
        or row.get("subject_type") != subject_type
        or not str(row.get("subject_reference") or "").strip()
    ):
        raise RuntimeError("task96_rpre_line_binding_existing_state_invalid")
    return {
        "subject_type": row["subject_type"],
        "subject_reference": str(row["subject_reference"]),
        "aggregate_version": int(row["aggregate_version"]),
    }


def _acquire_r03_waiting_lock(
    client: TestClient,
    *,
    plan_id: int,
) -> dict[str, object]:
    route_a._ensure_deposit_root(client)
    schedule = route_a._confirm_matching_schedule(client, plan_id)
    existing = _read_r03_waiting_lock(plan_id=plan_id)
    if existing is not None:
        return {
            **existing,
            "schedule_snapshot_id": schedule["snapshot_id"],
            "existing": True,
        }
    lock_path = (
        f"/api/v1/orders/{route_a.CASE_NO}/matching-plans/{plan_id}/"
        "waiting-deposit-lock/acquire"
    )
    preview = route_a._require_success(
        client.post(f"{lock_path}/preview"),
        "rpre_r03_waiting_lock_preview",
    )
    if not preview.get("apply_allowed"):
        raise RuntimeError("task96_rpre_r03_waiting_lock_not_allowed")
    identity = f"{route_a.SCENARIO_ID}:waiting-lock:v1"
    lock = route_a._require_success(
        client.post(
            f"{lock_path}/apply",
            json={"preview_fingerprint": preview["preview_fingerprint"]},
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "rpre_r03_waiting_lock_apply",
    )
    return {
        "lock_id": lock["lock_id"],
        "schedule_snapshot_id": schedule["snapshot_id"],
    }


def _read_r03_waiting_lock(*, plan_id: int) -> dict[str, object] | None:
    connection = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        database=route_a.DATABASE,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,status,is_active FROM caregiver_availability_locks "
                "WHERE plan_id=%s ORDER BY id",
                (plan_id,),
            )
            locks = tuple(cursor.fetchall() or ())
            if not locks:
                return None
            if len(locks) != 1:
                raise RuntimeError("task96_rpre_waiting_lock_identity_not_unique")
            lock = locks[0]
            if lock.get("status") != "active" or lock.get("is_active") != 1:
                raise RuntimeError("task96_rpre_waiting_lock_existing_state_invalid")
            cursor.execute(
                "SELECT staff_id,lock_date,active_marker FROM "
                "caregiver_availability_lock_days WHERE lock_id=%s "
                "ORDER BY lock_date,staff_id,id",
                (lock["id"],),
            )
            days = tuple(cursor.fetchall() or ())
    finally:
        connection.close()
    observed_dates = tuple(str(row["lock_date"]) for row in days)
    if (
        observed_dates != tuple(route_a.SERVICE_DATES)
        or any(row.get("active_marker") != 1 for row in days)
    ):
        raise RuntimeError("task96_rpre_waiting_lock_existing_days_invalid")
    return {"lock_id": int(lock["id"]), "locked_dates": observed_dates}


def _apply_initial_matching_criteria(client: TestClient) -> dict[str, object]:
    preview = route_a._require_success(
        client.post(
            f"/api/v1/matching-coordination/{route_a.CASE_NO}/preview/initial-criteria",
            headers={
                "X-Correlation-ID":
                    f"task96:rpre:{route_a.CASE_NO}:criteria-preview"
            },
            json={"reason": "Task 96 RPRE canonical browser fixture"},
        ),
        "matching_initial_criteria_preview",
    )
    raw_source_versions = preview["source_versions"]
    source_versions = (
        {"items": raw_source_versions}
        if isinstance(raw_source_versions, list)
        else raw_source_versions
    )
    return route_a._require_success(
        client.post(
            f"/api/v1/matching-coordination/{route_a.CASE_NO}/apply/initial-criteria",
            headers={
                "Idempotency-Key":
                    f"task96:rpre:{route_a.CASE_NO}:initial-criteria",
                "X-Correlation-ID":
                    f"task96:rpre:{route_a.CASE_NO}:criteria-apply",
            },
            json={
                "reason": "Task 96 RPRE canonical browser fixture",
                "expected_source_versions": source_versions,
                "preview_fingerprint": preview["fingerprint"],
            },
        ),
        "matching_initial_criteria_apply",
    )


def _seed_open_matching_parent(*, staff_id: int) -> dict[str, object]:
    dependency = get_matching_coordination_composition()
    composition = next(dependency)
    try:
        application = composition.application
        facts = application._facts_reader.load(route_a.CASE_NO)
        candidates = tuple(
            item for item in facts.candidates if item.staff_id == staff_id
        )
        if len(candidates) != 1 or candidates[0].willingness != "unwilling":
            raise RuntimeError("task96_rpre_unavailable_candidate_not_unique")
        candidate = candidates[0]
        package = MatchingPackage(
            package_id=(
                f"matching:{route_a.CASE_NO}:package:open:"
                f"{facts.snapshot.fingerprint.value[:16]}"
            ),
            version=1,
            mode=MatchingPackageMode.SINGLE,
            segments=(),
            required_service_dates=tuple(
                date.fromisoformat(value) for value in route_a.SERVICE_DATES
            ),
            candidate_results=(),
            criteria_snapshot_id=facts.snapshot.snapshot_id,
            source_versions=facts.source_versions,
            state=MatchingPackageState.CANDIDATE_POOL_OPEN,
        )
        seeded = MatchingCoordinationApplication(
            _PackageFixtureFactsReader(application._facts_reader, package),
            application._repository,
            application._unit_of_work_factory,
            workflow=application._workflow,
            clock=application._clock,
        )
        receipt = seeded.apply(
            ApplyCustomerMatchingDecision(
                case_no=route_a.CASE_NO,
                actor=ActorContext("system:local_bypass"),
                reason="Task 96 RPRE candidate unavailable fixture",
                correlation_id=CorrelationId(
                    f"task96:rpre:{route_a.CASE_NO}:open-parent"
                ),
                idempotency_key=IdempotencyKey(
                    f"task96:rpre:{route_a.CASE_NO}:open-parent"
                ),
                expected_source_versions=facts.source_versions,
                criteria_snapshot_id=facts.snapshot.snapshot_id,
                package_id=package.package_id,
                package_version=package.version,
                candidate_id=candidate.candidate_id,
                decision="rejected",
                preview_fingerprint=package.fingerprint,
            )
        )
        return {
            "criteria_snapshot_id": facts.snapshot.snapshot_id,
            "package_id": package.package_id,
            "package_version": package.version,
            "package_state": package.state.value,
            "candidate_id": candidate.candidate_id,
            "customer_decision_receipt_id": receipt.receipt_id,
        }
    finally:
        try:
            next(dependency)
        except StopIteration:
            pass


def _establish_r01_matching_lineage(
    client: TestClient,
    *,
    staff_id: int,
) -> dict[str, object]:
    initial = _apply_initial_matching_criteria(client)
    package = _seed_open_matching_parent(staff_id=staff_id)
    return {**package, "initial_criteria_receipt_id": initial["receipt_id"]}


def _confirm_r07_zero_candidate(
    client: TestClient,
    lineage: dict[str, object],
) -> dict[str, object]:
    query = route_a._require_success(
        client.post(
            f"/api/v1/matching-coordination/{route_a.CASE_NO}/query",
            json={},
            headers={
                "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:r07-query"
            },
        ),
        "matching_r07_query",
    )
    package = query.get("package")
    if not isinstance(package, dict) or package.get("state") != "candidate_pool_open":
        raise RuntimeError("task96_rpre_r07_open_package_unavailable")
    body = {
        "reason": "Task 96 R-07 fresh pool has no eligible willing candidate",
        "evidence": [f"task96:rpre:{route_a.CASE_NO}:fresh-pool-empty"],
        "expected_source_versions": query["source_versions"],
        "criteria_snapshot_id": query["snapshot"]["snapshot_id"],
        "package_id": package["package_id"],
        "package_version": package["version"],
    }
    preview = route_a._require_success(
        client.post(
            f"/api/v1/matching-coordination/{route_a.CASE_NO}/preview/confirm-zero-candidate",
            headers={
                "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:r07-preview"
            },
            json=body,
        ),
        "matching_r07_zero_candidate_preview",
    )
    applied = route_a._require_success(
        client.post(
            f"/api/v1/matching-coordination/{route_a.CASE_NO}/apply/confirm-zero-candidate",
            headers={
                "Idempotency-Key": f"task96:rpre:{route_a.CASE_NO}:r07-confirm",
                "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:r07-apply",
            },
            json={**body, "preview_fingerprint": preview["fingerprint"]},
        ),
        "matching_r07_zero_candidate_apply",
    )
    if (
        applied.get("result_state") != "zero_candidate_confirmed"
        or applied.get("resulting_package", {}).get("state") != "no_candidate"
    ):
        raise RuntimeError("task96_rpre_r07_zero_candidate_readback_drift")
    return {
        **lineage,
        "zero_candidate_preview": preview,
        "zero_candidate_apply": applied,
    }


def _establish_matching_lineage(client: TestClient, *, staff_id: int) -> dict[str, object]:
    existing_response = client.post(
        f"/api/v1/matching-coordination/{route_a.CASE_NO}/query",
        json={},
        headers={
            "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:lineage-query"
        },
    )
    if existing_response.status_code == 200:
        existing = route_a._require_success(
            existing_response,
            "matching_existing_lineage_query",
        )
        package = existing.get("package")
        if package is not None:
            return {
                "package_id": package["package_id"],
                "existing": True,
                "snapshot_id": existing["snapshot"]["snapshot_id"],
            }
    pool = route_a._require_success(
        client.get(
            f"/api/v1/orders/{route_a.CASE_NO}/candidate-contact-pool"
        ),
        "candidate_contact_pool_query_before_matching",
    )
    matching_candidates = [
        item
        for item in pool.get("candidates", ())
        if item.get("staff_id") == staff_id and item.get("willingness") == "willing"
    ]
    if len(matching_candidates) != 1:
        raise RuntimeError("task96_rpre_willing_candidate_not_unique")
    initial_apply = _apply_initial_matching_criteria(client)
    package = _seed_canonical_matching_package(staff_id=staff_id)
    return {
        **package,
        "initial_criteria_receipt_id": initial_apply["receipt_id"],
    }


def _replacement_row_counts() -> dict[str, int]:
    tables = (
        "scheduling_service_before_replacement_events",
        "scheduling_service_before_replacement_roots",
        "scheduling_service_before_replacement_successors",
        "scheduling_service_before_replacement_receipts",
        "scheduling_service_before_replacement_outbox",
    )
    connection = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        database=route_a.DATABASE,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            result: dict[str, int] = {}
            for table in tables:
                cursor.execute(
                    f"SELECT COUNT(*) FROM `{table}` WHERE case_no = %s",
                    (route_a.CASE_NO,),
                )
                result[table] = int(cursor.fetchone()[0])
            return result
    finally:
        connection.close()


def _run_actual_service_referral(
    client: TestClient,
    *,
    query: dict[str, object],
) -> dict[str, object]:
    if query.get("outcome") != "substitution_referral":
        raise RuntimeError("task96_rpre_referral_query_outcome_invalid")
    reason = "已有實際服務，轉介請假代班流程"
    evidence = [f"task96:rpre:{route_a.CASE_NO}:actual-service-proof"]
    before = _replacement_row_counts()
    preview = route_a._require_success(
        client.post(
            f"/api/v1/orders/{route_a.CASE_NO}/service-before-replacement/preview",
            headers={"X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:referral-preview"},
            json={"scenario": SCENARIO, "reason": reason, "evidence": evidence},
        ),
        "rpre_actual_service_referral_preview",
    )
    apply_response = client.post(
        f"/api/v1/orders/{route_a.CASE_NO}/service-before-replacement/apply",
        headers={
            "Idempotency-Key": f"task96:rpre:{route_a.CASE_NO}:referral-apply",
            "X-Correlation-ID": f"task96:rpre:{route_a.CASE_NO}:referral-apply",
        },
        json={
            "scenario": SCENARIO,
            "reason": reason,
            "evidence": evidence,
            "expected_generation_version": preview["expected_generation_version"],
            "expected_event_version": preview["expected_event_version"],
            "expected_aggregate_version": preview["expected_aggregate_version"],
            "prior_generation_identity": preview["prior_generation_identity"],
            "prior_event_identity": preview["prior_event_identity"],
            "prior_aggregate_identity": preview["prior_aggregate_identity"],
            "preview_fingerprint": preview["preview_fingerprint"],
        },
    )
    apply_payload = apply_response.json()
    apply_error = apply_payload.get("error") or apply_payload.get("detail", {}).get("error")
    if (
        apply_response.status_code != 409
        or not isinstance(apply_error, dict)
        or apply_error.get("code") != "replacement_actual_service_exists"
    ):
        raise RuntimeError(
            f"task96_rpre_referral_apply_not_blocked:{apply_response.status_code}:{apply_payload}"
        )
    after = _replacement_row_counts()
    if after != before:
        raise RuntimeError("task96_rpre_referral_wrote_replacement_rows")
    return {
        "preview": preview,
        "forced_apply_status": apply_response.status_code,
        "forced_apply_error": apply_error,
        "replacement_row_counts_before": before,
        "replacement_row_counts_after": after,
    }


def run_scenario() -> dict[str, object]:
    _configure_route()
    route_a._require_safe_environment()
    from api.main import app

    with TestClient(app) as client:
        if os.getenv("TASK96_RPRE_REFERRAL_ONLY", "").strip().lower() == "true":
            query = route_a._require_success(
                client.get(
                    f"/api/v1/orders/{route_a.CASE_NO}/service-before-replacement",
                    params={"scenario": SCENARIO},
                ),
                "rpre_query",
            )
            return {
                "scenario_id": route_a.SCENARIO_ID,
                "database": route_a.DATABASE,
                "case_no": route_a.CASE_NO,
                "rpre_query": query,
                "actual_service_referral": _run_actual_service_referral(
                    client,
                    query=query,
                ),
            }
        hcm_preview, hcm_apply = route_a._preview_apply_workbook(
            client,
            name="hcm",
            content=route_a._hcm_workbook(),
            preview_path="/api/v1/case-import/hcm/workbooks/preview",
            apply_path="/api/v1/case-import/hcm/workbooks/apply",
        )
        staff_preview, staff_apply = route_a._preview_apply_workbook(
            client,
            name="staff",
            content=route_a._staff_workbook(),
            preview_path="/api/v1/case-import/staff-historical/workbooks/preview",
            apply_path="/api/v1/case-import/staff-historical/workbooks/apply",
            form={"source_revision": route_a.SOURCE_REVISION},
            command_version=3,
        )
        client_preview, client_apply = route_a._preview_apply_client_beclass(client)
        _, service_dates_apply = route_a._confirm_service_dates(client)
        order = route_a._require_success(
            client.get(f"/api/v1/orders/{route_a.CASE_NO}"),
            "order_readback",
        )
        staff_page = route_a._require_success(
            client.get("/api/v1/staff/summaries", params={"page_size": 200}),
            "staff_readback",
        )
        selected_staff = [
            item for item in staff_page.get("items", ())
            if item.get("name") == route_a.STAFF_NAME
        ]
        if len(selected_staff) != 1:
            raise RuntimeError("task96_rpre_staff_identity_not_unique")
        staff_id = int(selected_staff[0]["id"])
        route_a._ensure_client_region(client, int(order["client_id"]))
        route_a._ensure_staff_preferences(client, staff_id)
        _ensure_order_matching_preferences(client)
        line_identities = None
        waiting_lock = None
        assignment = None
        commitment = None
        if SCENARIO in {"R-01", "R-07"}:
            candidate_id = _ensure_candidate_contact_pool(
                client,
                staff_id=staff_id,
                target_willingness="unwilling",
            )
            matching = {
                "stage": "candidate-pool-open",
                "candidate_id": candidate_id,
                "willingness": "unwilling",
            }
            matching_coordination = _establish_r01_matching_lineage(
                client,
                staff_id=staff_id,
            )
            if SCENARIO == "R-07":
                matching_coordination = _confirm_r07_zero_candidate(
                    client,
                    matching_coordination,
                )
        else:
            _ensure_candidate_contact_pool(client, staff_id=staff_id)
            matching = route_a._run_stage_02(client, staff_id)
            commitment = route_a._run_stage_03(client, int(matching["plan_id"]))
            if SCENARIO == "R-03":
                line_identities = _ensure_r03_line_identity_bindings(client)
                waiting_lock = _acquire_r03_waiting_lock(
                    client,
                    plan_id=int(matching["plan_id"]),
                )
            else:
                assignment = route_a._run_stage_04(
                    client,
                    int(matching["plan_id"]),
                    staff_id,
                )
            matching_coordination = _establish_matching_lineage(
                client,
                staff_id=staff_id,
            )
        query = route_a._require_success(
            client.get(
                f"/api/v1/orders/{route_a.CASE_NO}/service-before-replacement",
                params={"scenario": SCENARIO},
            ),
            "rpre_query",
        )
        referral = (
            _run_actual_service_referral(client, query=query)
            if query.get("outcome") == "substitution_referral"
            else None
        )
    fixture_stage = {
        "R-01": "candidate-pool-open-rpre-ready",
        "R-07": "matching-no-candidate-rpre-ready",
        "R-03": "stage-03-waiting-lock-rpre-ready",
    }.get(SCENARIO, "stage-04-zero-service-rpre-ready")
    return {
        "scenario_id": route_a.SCENARIO_ID,
        "database": route_a.DATABASE,
        "stage": fixture_stage,
        "case_no": route_a.CASE_NO,
        "staff_id": staff_id,
        "service_dates": service_dates_apply.get("service_dates")
        or service_dates_apply.get("current_dates"),
        "hcm": {"ready_count": hcm_preview.get("ready_count"), "inserted_count": hcm_apply.get("inserted_count")},
        "staff": {"created_count": staff_preview.get("created_count"), "applied_created_count": staff_apply.get("created_count")},
        "client_beclass": {"create_count": client_preview.get("create_count"), "created_count": client_apply.get("created_count")},
        "matching": matching,
        "commitment": commitment,
        "assignment": assignment,
        "line_identities": line_identities,
        "waiting_lock": waiting_lock,
        "matching_coordination": matching_coordination,
        "rpre_query": query,
        "actual_service_referral": referral,
    }


if __name__ == "__main__":
    print(json.dumps(run_scenario(), ensure_ascii=False, sort_keys=True))
