from ui.api_clients.accounts_payable_export_client import (
    AccountsPayableExportApiClient,
)


class _Response:
    headers = {"Content-Disposition": 'attachment; filename="payables.xlsx"'}
    content = b"xlsx"

    def raise_for_status(self):
        return None

    def json(self):
        return {"success": True, "data": {"rows": []}}


class _Session:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Response()


def test_client_uses_the_canonical_finance_reports_routes(monkeypatch):
    monkeypatch.setattr(
        "ui.api_clients.accounts_payable_export_client.resolve_api_base_url",
        lambda: "http://api.test",
    )
    monkeypatch.setattr(
        "ui.api_clients.accounts_payable_export_client.build_admin_headers",
        lambda: {"X-Admin": "test"},
    )
    session = _Session()
    client = AccountsPayableExportApiClient(session=session)

    client.query("2026-03")
    client.export("2026-03")
    client.query_archive(2026)

    assert [item[1] for item in session.calls] == [
        "http://api.test/api/v1/finance-reports/accounts-payable?target_month=2026-03",
        "http://api.test/api/v1/finance-reports/accounts-payable/export?target_month=2026-03",
        "http://api.test/api/v1/finance-reports/accounts-payable/archive?year=2026",
    ]
