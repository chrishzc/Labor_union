"""Retired global collection-account API must have no read/write surface."""
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.mark.parametrize(('method', 'suffix'), [('GET', ''), ('POST', '/preview'), ('POST', '/apply')])
def test_retired_payment_destination_api_is_not_registered(method, suffix):
    path = '/api/v1/client-finance/payment-destination' + suffix
    assert path not in app.openapi()['paths']
    client = TestClient(app, raise_server_exceptions=False)
    assert client.request(method, path, json={} if method == 'POST' else None).status_code == 404
