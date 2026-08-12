from types import SimpleNamespace

from ui.pages.order import contract_match_panel


def test_document_snapshot_reuses_key_until_file_or_stale_changes(monkeypatch):
    session_state = {}
    monkeypatch.setattr(contract_match_panel.st, "session_state", session_state)
    document = SimpleNamespace(name="signed.pdf", size=12)

    first = contract_match_panel._document_version_snapshot("client", document, 9)
    replay = contract_match_panel._document_version_snapshot("client", document, 10)

    assert replay == first
    assert replay["document_version_id"] == 9

    replacement = contract_match_panel._document_version_snapshot(
        "client", SimpleNamespace(name="replacement.pdf", size=12), 10,
    )

    assert replacement["document_version_id"] == 10
    assert replacement["idempotency_key"] != first["idempotency_key"]

    contract_match_panel._clear_stale_document_snapshot(
        "client", "contract_document_version_stale",
    )

    refreshed = contract_match_panel._document_version_snapshot("client", document, 11)

    assert refreshed["document_version_id"] == 11
    assert refreshed["idempotency_key"] != replacement["idempotency_key"]
