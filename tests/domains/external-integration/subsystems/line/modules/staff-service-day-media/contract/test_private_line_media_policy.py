"""The public transport must not expose malformed peer errors or use other credentials."""
import pytest
import httpx

from infrastructure.http.line_media_client import LineMediaClient, LineMediaError


@pytest.mark.parametrize('url', [
    'http://management-api', 'https://user:password@management-api',
    'https://management-api/path', 'https://management-api:invalid',
])
def test_private_photo_configuration_rejects_unsafe_destination(url):
    with pytest.raises((LineMediaError, ValueError)):
        LineMediaClient(url, 'token-file', 'ca-file')


@pytest.mark.parametrize('body', [
    [], {'detail': {'error': None}}, {'detail': {'error': []}},
    {'detail': {'code': '/private/path-must-not-be-relayed'}},
])
def test_malformed_peer_error_becomes_closed_unavailable(body):
    with pytest.raises(LineMediaError) as error:
        LineMediaClient._decode(httpx.Response(422, json=body))
    assert error.value.status_code == 503
    assert str(error.value) == 'line_media_unavailable'


def test_private_photo_does_not_fall_back_to_worker_configuration(monkeypatch):
    for key in ('LINE_MEDIA_API_BASE_URL', 'LINE_MEDIA_SERVICE_TOKEN_FILE', 'LINE_MEDIA_API_CA_FILE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('INTERNAL_API_BASE_URL', 'https://worker-api')
    monkeypatch.setenv('INTERNAL_SERVICE_TOKEN_FILE', 'worker-token-file')
    monkeypatch.setenv('INTERNAL_SERVICE_SHARED_KEY', 'worker-test-key')
    with pytest.raises(LineMediaError, match='configuration_unavailable'):
        LineMediaClient.from_environment()
