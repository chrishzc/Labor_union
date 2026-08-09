from pathlib import Path
from types import SimpleNamespace

from api.schemas.finance_import import FinanceImportTypedErrorView
from ui.api_clients.finance_import_api_client import FinanceImportApiClient
from ui.api_clients.finance_import_api_client import FinanceImportApiError
from ui.pages.finance_import.panel import _BATCH_APPLY_STATE_KEY, _submit_batch_apply_request


ROOT = Path(__file__).resolve().parents[1]


class _Response:
    ok = True
    status_code = 200

    def json(self):
        return {
            "success": True,
            "message": "ok",
            "data": {
                "batch_identity": "batch:1",
                "batch_version": 4,
                "row_count": 1,
                "preview_fingerprint": "a" * 64,
            },
        }


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return _Response()


def test_historical_reprocess_client_uses_the_typed_preview_endpoint():
    session = _Session()
    client = FinanceImportApiClient(
        base_url="http://api.test",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    selection = [{
        "row_identity": "finance-import-row:1",
        "case_no": "C-1",
        "obligation_identity": "client-obligation:1",
        "reason": "reviewed",
        "evidence_references": ["review:1"],
    }]
    preview = client.preview_historical_reprocess(
        "batch:1", "correlation-1", selection
    )

    assert preview.batch_version == 4
    assert session.calls[0][0] == (
        "POST",
        "http://api.test/api/v1/finance-import/historical-reprocess/preview",
    )
    assert session.calls[0][1]["json"] == {
        "batch_identity": "batch:1",
        "owner_selections": selection,
    }


def test_finance_import_panel_is_not_a_stub_and_exposes_preview_apply_flow():
    source = (ROOT / "ui/pages/finance_import/panel.py").read_text(encoding="utf-8")

    assert "Stub:" not in source
    assert "client.preview_batch" in source
    assert "client.apply_batch" in source
    assert "client.preview_historical_reprocess" in source
    assert "client.apply_historical_reprocess" in source


def test_batch_apply_timeout_retry_reuses_the_same_idempotency_identity():
    preview = SimpleNamespace(
        batch_identity="batch:1",
        preview_fingerprint="a" * 64,
    )
    state = {}
    client = _TimeoutThenAcceptedClient()

    first_job, first_error = _submit_batch_apply_request(
        client, preview, "global retry", state
    )
    second_job, second_error = _submit_batch_apply_request(
        client, preview, "changed UI input is ignored", state
    )

    assert first_job is None
    assert first_error.error.retryable is True
    assert second_error is None
    assert second_job.job_id == "job-1"
    assert len(client.idempotency_keys) == 2
    assert client.idempotency_keys[0] == client.idempotency_keys[1]
    assert state[_BATCH_APPLY_STATE_KEY]["reason"] == "global retry"


class _TimeoutThenAcceptedClient:
    def __init__(self):
        self.idempotency_keys = []

    def apply_batch(self, _preview, **kwargs):
        self.idempotency_keys.append(kwargs["idempotency_key"])
        if len(self.idempotency_keys) == 1:
            raise FinanceImportApiError(
                None,
                FinanceImportTypedErrorView(
                    category="unavailable",
                    code="finance_import_transport_error",
                    message="response lost",
                    correlation_id="client",
                    retryable=True,
                ),
            )
        return SimpleNamespace(job_id="job-1")


def test_batch_apply_ui_shows_pending_before_it_shows_completed(monkeypatch):
    import ui.pages.finance_import.panel as panel

    display = _Display()
    monkeypatch.setattr(panel, "st", display)
    command = {"job_id": "job-1", "terminal": False}
    client = _JobStatusClient("queued")

    panel._refresh_batch_apply_status(client, command)

    assert command["terminal"] is False
    assert display.success_messages == []
    assert display.info_messages == ["正式入帳仍在處理：queued"]

    client.status = "succeeded"
    panel._refresh_batch_apply_status(client, command)

    assert command["terminal"] is True
    assert display.success_messages == ["正式入帳已完成。"]


class _Display:
    def __init__(self):
        self.info_messages = []
        self.success_messages = []

    def info(self, message):
        self.info_messages.append(message)

    def success(self, message):
        self.success_messages.append(message)

    def error(self, _message):
        raise AssertionError("unexpected UI error")

    def spinner(self, _message):
        return _NullContext()

    def json(self, _payload):
        return None


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _JobStatusClient:
    def __init__(self, status):
        self.status = status

    def get_job_status(self, _job_id):
        return SimpleNamespace(
            status=self.status,
            receipt_payload={"receipt": "ok"},
            error_payload=None,
        )
