"""
File: test_wp77_import_contracts.py
Description: 驗證 Staff 來源時間覆寫、HCM review及警示中心人工修正入口契約。
"""

from __future__ import annotations

import importlib
import pytest
from pathlib import Path
from types import SimpleNamespace

from domains.case_import.hcm_import_review import build_hcm_import_review_root, opened_anomaly_snapshot
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from domains.case_import.case_import import (
    HcmIdentityFacts,
    HcmIdentityResolution,
    resolve_hcm_identity,
)
from domains.case_import.staff_historical_adoption import plan_staff_scalar_merge
from scripts.imports import import_client_hcm
from scripts.imports import import_client_beclass, import_staff_beclass
from scripts import rebuild_beclass_import_anomalies
from scripts import audit_staff_historical_adoption
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId
from subsystems.anomalies import hcm_import_review_outbox_consumer as hcm_outbox
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest
from domains.anomalies.registry import (
    AlertWorkflowStatus,
    DesiredAlertState,
    default_anomaly_registry,
)
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_beclass_missing_requests,
    build_hcm_missing_requests,
)
from subsystems.case_import import hcm_beclass_reconciliation as reconciliation
from subsystems.case_import import staff_historical_adoption as staff_adoption
from subsystems.case_import import staff_historical_workbook_adoption as staff_workbook_adoption
from subsystems.case_import.staff_historical_workbook import StaffHistoricalWorkbookRow
from subsystems.case_import import beclass_review_intake


@pytest.mark.parametrize(
    ("facts", "expected"),
    (
        (HcmIdentityFacts((), (), False), HcmIdentityResolution.NEW),
        (HcmIdentityFacts((7,), (7,), True), HcmIdentityResolution.EXISTING_MATCH),
        (HcmIdentityFacts((), (7,), False), HcmIdentityResolution.UNIQUE_CANDIDATE),
        (HcmIdentityFacts((7,), (), True), HcmIdentityResolution.CONFLICT),
        (HcmIdentityFacts((), (7, 8), False), HcmIdentityResolution.AMBIGUOUS),
    ),
)
def test_hcm_identity_blocks_case_or_same_ip_name_duplicate(facts, expected):
    assert resolve_hcm_identity(facts) is expected


def test_hcm_identity_allows_shared_ip_when_name_does_not_match():
    facts = HcmIdentityFacts((), (), False)

    assert resolve_hcm_identity(facts) is HcmIdentityResolution.NEW


def test_hcm_duplicate_application_issue_is_preserved_for_alert_projection():
    issue_codes = import_client_hcm._hcm_review_issue_codes(
        {"hcm_identity": "hcm_duplicate_application"}
    )

    assert issue_codes == ("hcm_identity:hcm_duplicate_application",)


def test_staff_historical_merge_fills_blank_scalars_when_source_time_is_not_newer():
    existing = {
        "name": "既有姓名",
        "phone": None,
        "email": "current@example.test",
        "status": "active",
        "line_user_id": "current-line-binding",
    }
    historical = {
        "name": "既有姓名",
        "phone": "0912345678",
        "email": "historical@example.test",
        "status": "inactive",
        "line_user_id": "historical-line-binding",
    }

    result = plan_staff_scalar_merge(existing, historical)

    assert result.patch == {"phone": "0912345678"}
    assert result.conflict_fields == ("email",)


def test_staff_historical_merge_newer_source_overwrites_mutable_scalars():
    existing = {
        "registered_at": "2026-08-01 09:00:00",
        "name": "既有姓名",
        "phone": "0911000000",
        "email": "current@example.test",
        "status": "active",
        "line_user_id": "current-line-binding",
    }
    historical = {
        "registered_at": "2026-08-02 09:00:00",
        "name": "既有姓名",
        "phone": "0922000000",
        "email": "historical@example.test",
        "status": "inactive",
        "line_user_id": "historical-line-binding",
    }

    result = plan_staff_scalar_merge(existing, historical)

    assert result.patch == {
        "email": "historical@example.test",
        "phone": "0922000000",
        "registered_at": "2026-08-02 09:00:00",
    }
    assert result.conflict_fields == ()


def test_staff_historical_merge_newer_source_updates_name_for_traceable_change():
    existing = {
        "registered_at": "2026-08-01 09:00:00",
        "name": "舊姓名",
    }
    historical = {
        "registered_at": "2026-08-02 09:00:00",
        "name": "新姓名",
    }

    result = plan_staff_scalar_merge(existing, historical)

    assert result.source_is_newer is True
    assert result.patch == {
        "name": "新姓名",
        "registered_at": "2026-08-02 09:00:00",
    }
    assert result.conflict_fields == ()


def test_staff_workbook_preview_treats_newer_name_change_as_adoption(monkeypatch):
    existing = {
        "registered_at": "2026-08-01 09:00:00",
        "name": "舊姓名",
    }
    row = StaffHistoricalWorkbookRow(
        source_row=2,
        record={
            "identity_card": "A123456789",
            "registered_at": "2026-08-02 09:00:00",
            "name": "新姓名",
        },
        errors=(),
        bank_accounts=(),
        relations={},
    )
    repository = SimpleNamespace(load_staff=lambda identity, for_update: [existing])
    monkeypatch.setattr(
        staff_workbook_adoption,
        "MySqlStaffHistoricalAdoptionRepository",
        lambda connection: repository,
    )
    service = staff_workbook_adoption.StaffHistoricalWorkbookService(None, None)

    outcome, reviewed = service._preview_row(row)

    assert outcome == "adopted_existing"
    assert reviewed is True


def test_hcm_review_identity_replays_exact_source_and_never_contains_raw_case_number():
    arguments = {
        "source_content_digest": "a" * 64,
        "source_sheet": "任意資料頁",
        "source_row": 7,
        "case_identity": "HCM-PRIVATE-1234",
        "issue_codes": ("hcm_field_invalid:服務時間",),
        "evidence_snapshot": {"invalid_field_count": 1, "has_case_identity": True},
    }

    first = build_hcm_import_review_root(**arguments)
    replay = build_hcm_import_review_root(**arguments)

    assert replay == first
    assert "HCM-PRIVATE" not in first.review_identity
    assert first.masked_case_identity == "hcm-***-1234"
    assert opened_anomaly_snapshot(first)["definition_code"] == "IMPORT-004"


def test_hcm_review_rejects_nested_or_raw_evidence():
    with pytest.raises(ValueError, match="bounded scalar"):
        build_hcm_import_review_root(
            source_content_digest="a" * 64,
            source_sheet="資料",
            source_row=1,
            case_identity="HCM-1",
            issue_codes=("invalid",),
            evidence_snapshot={"raw_row": {"姓名": "不應保存"}},
        )

    with pytest.raises(ValueError, match="numeric or boolean"):
        build_hcm_import_review_root(
            source_content_digest="a" * 64,
            source_sheet="資料",
            source_row=1,
            case_identity="HCM-1",
            issue_codes=("invalid",),
            evidence_snapshot={"operator_note": "完整姓名不應保存"},
        )


def test_counterpart_anomalies_are_symmetric_and_auto_resolvable():
    as_of = __import__("datetime").date(2026, 8, 13)
    hcm_waiting = build_beclass_missing_requests(
        [{"case_no": "115000001", "beclass_id": None}], as_of=as_of
    )[0]
    beclass_waiting = build_hcm_missing_requests(
        [{"query_no": "115000002", "beclass_id": 7, "hcm_case_no": None}],
        as_of=as_of,
    )[0]
    reconciled = build_hcm_missing_requests(
        [{"query_no": "115000002", "beclass_id": 7, "hcm_case_no": "115000002"}],
        as_of=as_of,
    )[0]

    assert hcm_waiting.desired.definition_code == "BECLASS-001"
    assert hcm_waiting.desired.active is True
    assert beclass_waiting.desired.definition_code == "IMPORT-003"
    assert beclass_waiting.desired.active is True
    assert beclass_waiting.display_snapshot["error_codes"] == (
        "beclass_hcm_mismatch",
    )
    assert reconciled.desired.active is False


def test_import_adapters_use_owned_review_outboxes_instead_of_legacy_alert_writes():
    hcm_source = Path("scripts/imports/import_client_hcm.py").read_text(encoding="utf-8")
    staff_source = Path("scripts/imports/import_staff_beclass.py").read_text(encoding="utf-8")

    assert "record_invalid_beclass_row" not in hcm_source
    assert "BeClassImportSourceKind.HCM" not in hcm_source
    assert "get_anomaly_application" not in hcm_source
    assert "upsert_system_alert" not in staff_source
    assert "delete_system_alert" not in staff_source


def test_hcm_outbox_result_counts_terminal_delivery_attempts(monkeypatch):
    outcomes = iter((True, False, None))
    monkeypatch.setattr(hcm_outbox, "_consume_next", lambda connection: next(outcomes))

    result = hcm_outbox.consume_hcm_import_review_events(object(), maximum_events=3)

    assert result.delivered_count == 1
    assert result.failed_count == 1


def test_hcm_outbox_projection_contains_only_masked_review_evidence():
    request = hcm_outbox._project_request(
        {"id": 9},
        {
            "review_identity": "hcm-review:" + "a" * 64,
            "source_version": 1,
            "active": True,
            "source_row": 4,
            "masked_case_identity": "hcm-***-0004",
            "issue_codes": ["hcm_field_invalid:服務日期"],
        },
    )

    assert request.desired.definition_code == "IMPORT-004"
    assert request.desired.fingerprint_values == {"case_no": "hcm-***-0004"}
    assert request.display_snapshot["masked_case_identity"] == "hcm-***-0004"
    assert "raw_row" not in request.display_snapshot


def test_wp77_schema_is_additive_and_keeps_receipt_and_review_roots_immutable():
    sql = Path("db/schema_parts/193_staff_historical_adoption_hcm_review.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS staff_historical_adoption_receipts" in sql
    assert "CREATE TABLE IF NOT EXISTS case_import_hcm_review_rows" in sql
    assert "CREATE TABLE IF NOT EXISTS case_import_hcm_review_outbox" in sql
    assert "staff_historical_adoption_receipts records cannot be updated" in sql
    assert "case_import_hcm_review_rows records cannot be deleted" in sql
    assert "ALTER TABLE staff" not in sql
    assert "DROP TABLE" not in sql


def test_hcm_existing_case_is_exact_replay_only_when_source_fingerprint_matches(monkeypatch):
    source_fingerprint = PreviewFingerprint("a" * 64)
    preview_fingerprint = PreviewFingerprint("b" * 64)
    receipt = SimpleNamespace(
        source_fingerprint=source_fingerprint,
        preview_fingerprint=preview_fingerprint,
    )

    class Application:
        applied = None

        def find_receipt(self, key):
            return SimpleNamespace(receipt=receipt)

        def apply(self, command):
            self.applied = command

    application = Application()
    monkeypatch.setattr(
        import_client_hcm,
        "fingerprint_case_import_source",
        lambda intent: source_fingerprint,
    )
    monkeypatch.setattr(import_client_hcm, "_reconcile_without_rolling_back_hcm", lambda *_: "reconciled")

    outcome = import_client_hcm._replay_existing_hcm_case(
        application,
        SimpleNamespace(case_no="115000001"),
        CorrelationId("corr-1"),
        "hcm.xlsx",
        object(),
        "c" * 64,
        "資料",
        1,
        {},
    )

    assert outcome == "exact_replay"
    assert application.applied.preview_fingerprint == preview_fingerprint


def test_hcm_existing_case_without_matching_receipt_becomes_hcm_review(monkeypatch):
    captured = []
    application = SimpleNamespace(find_receipt=lambda key: None)
    monkeypatch.setattr(import_client_hcm, "_persist_hcm_review", lambda *args: captured.append(args))

    outcome = import_client_hcm._replay_existing_hcm_case(
        application,
        SimpleNamespace(case_no="115000001"),
        CorrelationId("corr-2"),
        "hcm.xlsx",
        object(),
        "d" * 64,
        "資料",
        2,
        {},
    )

    assert outcome == "review_required"
    assert captured


def test_unique_pair_with_ambiguous_cooking_creates_review_without_changing_order(monkeypatch):
    review_calls = []
    monkeypatch.setattr(
        reconciliation,
        "_load_pair_facts",
        lambda *_: {
            "hcm_count": 1,
            "beclass_count": 1,
            "beclass_id": 9,
            "survey_details": {},
            "requires_cooking": None,
        },
    )
    monkeypatch.setattr(reconciliation, "_record_cooking_review", lambda *args: review_calls.append(args))
    monkeypatch.setattr(
        reconciliation,
        "_apply_cooking_terms",
        lambda *_: pytest.fail("ambiguous cooking must not update Orders"),
    )

    result = reconciliation.reconcile_hcm_beclass_cooking(object(), "115000009")

    assert result.status == "cooking_review_required"
    assert review_calls


@pytest.mark.parametrize(
    ("stored_outcome", "is_exact_replay"),
    (("created", True), ("adopted_existing", True), ("blocked_identity", False)),
)
def test_staff_exact_replay_requires_a_successful_receipt(
    monkeypatch, stored_outcome, is_exact_replay
):
    class Repository:
        def __init__(self, connection):
            pass

        def claim(self, key, command_fingerprint, source_identity):
            return False

        def find_receipt(self, key):
            return {
                "command_fingerprint": expected_fingerprint,
                "outcome": stored_outcome,
                "staff_id": 7 if is_exact_replay else None,
            }

        def load_staff(self, identity_card, *, for_update):
            return [{"id": 7, "name": "測試"}]

    historical_record = {"identity_card": "A123456789", "name": "測試"}
    source_identity = f"staff-workbook:{'e' * 64}:row:2"
    expected_fingerprint = staff_adoption.fingerprint_payload(
        {
            "source_identity": source_identity,
            "source_fingerprint": staff_adoption.fingerprint_payload(historical_record).value,
        }
    ).value
    monkeypatch.setattr(staff_adoption, "MySqlStaffHistoricalAdoptionRepository", Repository)

    replayed = staff_adoption.record_staff_adoption_outcome(
        object(),
        source_content_digest="e" * 64,
        source_row=2,
        staff_id=None,
        historical_record=historical_record,
        review_identity=None,
        outcome="blocked_identity",
    )

    assert replayed is is_exact_replay


def test_staff_successful_receipt_requires_fresh_matching_root(monkeypatch):
    historical_record = {"identity_card": "A123456789", "name": "測試"}
    source_identity = f"staff-workbook:{'e' * 64}:row:2"
    expected_fingerprint = staff_adoption.fingerprint_payload(
        {
            "source_identity": source_identity,
            "source_fingerprint": staff_adoption.fingerprint_payload(historical_record).value,
        }
    ).value

    class Repository:
        def __init__(self, connection):
            pass

        def claim(self, key, command_fingerprint, aggregate_identity):
            return False

        def find_receipt(self, key):
            return {
                "command_fingerprint": expected_fingerprint,
                "outcome": "created",
                "staff_id": 9,
            }

        def load_staff(self, identity_card, *, for_update):
            assert identity_card == "A123456789"
            assert for_update is True
            return []

    monkeypatch.setattr(staff_adoption, "MySqlStaffHistoricalAdoptionRepository", Repository)

    with pytest.raises(RuntimeError, match="staff_historical_adoption_replay_root_drift"):
        staff_adoption.record_staff_adoption_outcome(
            object(),
            source_content_digest="e" * 64,
            source_row=2,
            staff_id=None,
            historical_record=historical_record,
            review_identity=None,
            outcome="blocked_identity",
        )


def test_anomaly_checkpoint_does_not_hide_a_missing_current_projection():
    desired = DesiredAlertState(
        "IMPORT-001",
        "beclass-review:" + "a" * 64,
        0,
        True,
        {"entity_kind": "staff", "review_item_id": "beclass-review:" + "a" * 64},
    )
    request = ProjectAlertRequest(desired, "review-rescan:event", "consumer", "partition", {})

    class Repository:
        def __init__(self):
            self.saved = None

        def checkpoint_matches(self, request):
            return True

        def load_current(self, fingerprint, *, for_update):
            return None

        def save_projection(self, definition, previous, resulting, display_snapshot):
            self.saved = resulting

        def append_projector_event(self, previous, resulting, request):
            pass

        def save_checkpoint(self, request):
            pass

    class UnitOfWork:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def commit(self):
            pass

    repository = Repository()
    application = AnomalyApplication(default_anomaly_registry(), repository, UnitOfWork)

    resulting = application.project(request)

    assert resulting is repository.saved
    assert resulting.workflow_status is AlertWorkflowStatus.OPEN


def test_beclass_anomaly_rebuild_cli_returns_a_typed_projection_count(monkeypatch):
    connection = SimpleNamespace(close=lambda: None)
    page = SimpleNamespace(projected_count=14, next_review_row_id=None)
    monkeypatch.setattr(rebuild_beclass_import_anomalies, "get_connection", lambda: connection)
    monkeypatch.setattr(
        rebuild_beclass_import_anomalies,
        "project_beclass_import_review_page",
        lambda received, **kwargs: page,
    )

    result = rebuild_beclass_import_anomalies.rebuild_beclass_import_anomalies()

    assert result == {
        "status": "projected",
        "projected_count": 14,
        "next_review_row_id": None,
    }


@pytest.mark.parametrize(
    ("receipt", "identity_card", "name", "expected_reason"),
    (
        (None, "A123456789", "月嫂", "receipt_missing"),
        (
            {
                "outcome": "created",
                "staff_id": 1,
                "live_staff_id": None,
                "live_identity_card": None,
                "live_name": None,
            },
            "A123456789",
            "月嫂",
            "staff_root_missing",
        ),
    ),
)
def test_staff_historical_audit_reports_each_non_replay_reason(
    receipt, identity_card, name, expected_reason
):
    assert audit_staff_historical_adoption._replay_reason(receipt, identity_card, name) == expected_reason


def test_staff_historical_audit_reports_shared_staff_roots_by_source_row():
    result = audit_staff_historical_adoption._summarize_root_mappings(
        (
            {"source_row": 2, "reason": "exact_replay_verified", "staff_id": 8},
            {"source_row": 3, "reason": "exact_replay_verified", "staff_id": 8},
            {"source_row": 4, "reason": "exact_replay_verified", "staff_id": 9},
            {"source_row": 5, "reason": "staff_root_missing", "staff_id": 10},
        ),
        {
            2: {"identity_card": {"group": "identity-1"}, "name": {"group": "name-1"}},
            3: {"identity_card": {"group": "identity-1"}, "name": {"group": "name-1"}},
            4: {"identity_card": {"group": "identity-2"}, "name": {"group": "name-2"}},
            5: {"identity_card": {"group": "identity-3"}, "name": {"group": "name-3"}},
        },
    )

    assert result == {
        "verified_replay_rows": 3,
        "distinct_verified_staff_roots": 2,
        "shared_staff_roots": (
            {
                "staff_id": 8,
                "source_rows": [2, 3],
                "identity_card_groups": ["identity-1", "identity-1"],
                "name_groups": ["name-1", "name-1"],
                "same_normalized_identity_card": True,
                "same_normalized_name": True,
            },
        ),
    }


def test_staff_historical_audit_groups_source_values_without_exposing_them():
    labels = audit_staff_historical_adoption._private_group_labels(
        ("A123456789", "A123456789", "B123456789", ""), "identity"
    )

    result = audit_staff_historical_adoption._value_evidence(
        " A123456789 ", "A123456789", labels
    )

    assert result == {
        "normalized_value": "A123456789",
        "group": "identity-01",
        "raw_type": "str",
        "blank": False,
        "trimmed": True,
    }


def test_beclass_review_payloads_keep_personal_values_out_of_durable_evidence():
    client = import_client_beclass._privacy_safe_client_review_payload(
        {
            "query_no": "115000001",
            "name": "完整姓名",
            "phone": "0912345678",
            "address": "完整地址",
        }
    )
    staff = import_staff_beclass._privacy_safe_staff_review_payload(
        {
            "identity_card": "A123456789",
            "name": "完整姓名",
            "phone": "0912345678",
            "address": "完整地址",
        }
    )

    serialized = repr({"client": client, "staff": staff})
    assert "完整姓名" not in serialized
    assert "0912345678" not in serialized
    assert "A123456789" not in serialized
    assert "完整地址" not in serialized


def test_beclass_review_privacy_upgrade_replays_only_the_same_source_issue():
    coordinates = {
        "source_kind": BeClassImportSourceKind.STAFF,
        "source_event_identity": "beclass-workbook:" + "f" * 64 + ":row:2",
        "source_sheet": "資料",
        "source_row": 2,
        "masked_identifier": "staff-***-6789",
        "issue_codes": ("身分證字號",),
    }
    existing = SimpleNamespace(**coordinates, source_payload={"identity_card": "A123456789"})
    privacy_safe = SimpleNamespace(**coordinates, source_payload={"has_identity_card": True})
    different_issue = SimpleNamespace(
        **{**coordinates, "issue_codes": ("identity_name_mismatch",)},
        source_payload={"has_identity_card": True},
    )

    assert beclass_review_intake._same_source_issue(existing, privacy_safe) is True
    assert beclass_review_intake._same_source_issue(existing, different_issue) is False


def test_alert_workspace_navigates_beclass_reviews_without_loading_correction_panel(monkeypatch):
    alerts_page = importlib.import_module("ui.pages.06_finance_alerts")
    captured = {}
    monkeypatch.setattr(
        alerts_page,
        "st",
        SimpleNamespace(caption=lambda *_args, **_kwargs: None, button=lambda *_args, **_kwargs: True),
    )
    monkeypatch.setattr("ui.nav_helper.navigate_to", lambda title: captured.update(title=title))
    all_items = (
        SimpleNamespace(definition_code="IMPORT-001", source_identity="beclass-review:" + "a" * 64),
        SimpleNamespace(definition_code="IMPORT-003", source_identity="beclass-review:" + "b" * 64),
        SimpleNamespace(definition_code="IMPORT-004", source_identity="hcm-review:" + "c" * 64),
    )
    items = alerts_page._beclass_review_items(all_items)

    alerts_page._render_beclass_review_navigation(items)

    assert captured == {"title": "📥 資料匯入中心"}
    assert "render_beclass_import_review_panel" not in Path(
        "ui/pages/06_finance_alerts.py"
    ).read_text(encoding="utf-8")


def test_alert_center_does_not_render_finance_recovery_workspace():
    source = Path("ui/pages/06_finance_alerts.py").read_text(encoding="utf-8")

    assert "_render_finance_tab(items, registry_client, recovery_client)" not in source


def test_review_panel_disables_empty_identity_load(monkeypatch):
    review_panel = importlib.import_module("ui.pages.anomalies.beclass_import_review_panel")
    button_calls = []
    fake_streamlit = SimpleNamespace(
        session_state={},
        subheader=lambda *args, **kwargs: None,
        caption=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        text_input=lambda *args, **kwargs: "",
        button=lambda *args, **kwargs: button_calls.append(kwargs) or False,
    )
    monkeypatch.setattr(review_panel, "st", fake_streamlit)

    review_panel.render_beclass_import_review_panel(object())

    assert button_calls == [{"key": "beclass_review_load", "disabled": True}]
