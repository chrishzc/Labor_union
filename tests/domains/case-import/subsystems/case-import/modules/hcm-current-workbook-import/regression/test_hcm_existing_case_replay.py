"""Regression coverage for HCM existing-case exact replay."""

from types import SimpleNamespace

from scripts.imports import import_client_hcm
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId


def test_matching_source_receipt_replays_without_rebuilding_transient_command(
    monkeypatch,
) -> None:
    source_fingerprint = PreviewFingerprint("a" * 64)
    receipt = SimpleNamespace(
        source_fingerprint=source_fingerprint,
        preview_fingerprint=PreviewFingerprint("b" * 64),
    )

    class Application:
        def find_receipt(self, _key):
            return SimpleNamespace(receipt=receipt)

        def apply_in_current_uow(self, _command):
            raise AssertionError(
                "exact replay must not rebuild a command from a transient upload filename"
            )

    reconciliation_calls = []
    monkeypatch.setattr(
        import_client_hcm,
        "fingerprint_case_import_source",
        lambda _intent: source_fingerprint,
    )
    monkeypatch.setattr(
        import_client_hcm,
        "_reconcile_without_rolling_back_hcm",
        lambda connection, case_no, *, in_current_uow=False: reconciliation_calls.append(
            (connection, case_no, in_current_uow)
        ),
    )

    connection = object()
    outcome = import_client_hcm._replay_existing_hcm_case(
        Application(),
        SimpleNamespace(case_no="115000001"),
        CorrelationId("corr-replay"),
        "different-random-upload-name.xlsx",
        connection,
        "c" * 64,
        "資料",
        2,
        {},
        current_uow=True,
    )

    assert outcome == "exact_replay"
    assert reconciliation_calls == [(connection, "115000001", True)]


def test_existing_case_with_different_source_is_skipped_without_review_or_write(monkeypatch) -> None:
    class Application:
        def find_receipt(self, _key):
            return None

    monkeypatch.setattr(
        import_client_hcm,
        "_persist_hcm_review",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ordinary existing-case skip must not create a review")
        ),
    )
    monkeypatch.setattr(
        import_client_hcm,
        "_reconcile_without_rolling_back_hcm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("a skipped row must not trigger reconciliation")
        ),
    )

    outcome = import_client_hcm._replay_existing_hcm_case(
        Application(),
        SimpleNamespace(case_no="115000001"),
        CorrelationId("corr-skip"),
        "changed-source.xlsx",
        object(),
        "c" * 64,
        "資料",
        2,
        {"行動電話": "0912345678"},
        current_uow=True,
    )

    assert outcome == "skipped_existing"


def test_non_citizen_new_hcm_row_is_reviewed_before_case_writer(monkeypatch):
    import pandas as pd
    from domains.case_import.case_import import HcmIdentityResolution
    record = {"case_no": "A115002", "identity_status": "非市民"}
    monkeypatch.setattr(import_client_hcm, "_normalized_record", lambda _: record)
    monkeypatch.setattr(import_client_hcm, "validate_hcm_row", lambda _: {})
    monkeypatch.setattr(import_client_hcm, "_persist_hcm_review", lambda *args: "synthetic-review")
    class Application:
        def resolve_hcm_identity(self, *args):
            return next(item for item in HcmIdentityResolution if item is not HcmIdentityResolution.EXISTING_MATCH)
        def preview(self, *args):
            raise AssertionError("HCM must not create a non-citizen case")
    outcome = import_client_hcm._import_row(pd.Series({}), 2, None, Application(), "synthetic.xlsx", detailed=True)
    assert outcome["outcome"] == "review_required"
    assert outcome["problem_fields"] == ["身分資格"]
    assert outcome["issue_codes"] == ["hcm_field_invalid:身分資格"]
