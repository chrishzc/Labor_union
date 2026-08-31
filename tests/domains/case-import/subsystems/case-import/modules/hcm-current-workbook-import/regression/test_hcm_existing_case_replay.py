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
