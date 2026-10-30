"""Purpose-bound, opaque image links; no case or recipient data enters URLs."""
import base64
import hashlib
import json
import os
from datetime import timedelta
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from subsystems.line.table_image_contracts import TableImageUnavailable

_PURPOSE = b'line-table-image-v1'
_INTERNAL_KEY = hashlib.sha256(b'labor-union-internal-line-table-image-key-v1').digest()


def _cipher():
    configured = (
        os.getenv('LINE_CHANNEL_SECRET', '').strip()
        or os.getenv('MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET', '').strip()
    )
    if configured and not configured.startswith('replace_with_'):
        return AESGCM(hashlib.sha256(_PURPOSE + configured.encode('utf-8')).digest())
    return AESGCM(_INTERNAL_KEY)


def image_url(key, index, now):
    base = (os.getenv('LINE_PUBLIC_BASE_URL', '').strip() or os.getenv('BASE_URL', '').strip()).rstrip('/')
    try:
        parsed = urlsplit(base)
        parsed.port
    except ValueError:
        raise TableImageUnavailable('圖片服務尚未設定安全網址。') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(char.isspace() for char in base)):
        raise TableImageUnavailable('圖片服務尚未設定安全網址。')
    nonce = os.urandom(12)
    claim = json.dumps({'key': key, 'index': index, 'exp': int((now + timedelta(days=7)).timestamp())}, separators=(',', ':')).encode()
    token = base64.urlsafe_b64encode(nonce + _cipher().encrypt(nonce, claim, _PURPOSE)).decode().rstrip('=')
    return f'{base}/api/v1/line/table-images/lti_{token}'


def image_claim(token, now):
    if not isinstance(token, str) or not token.startswith('lti_') or len(token) > 1500:
        raise ValueError('table image link is invalid')
    try:
        raw = base64.urlsafe_b64decode(token[4:] + '=' * (-len(token[4:]) % 4))
        value = json.loads(_cipher().decrypt(raw[:12], raw[12:], _PURPOSE))
    except TableImageUnavailable:
        raise
    except Exception as error:
        raise ValueError('table image link is invalid') from error
    if (not isinstance(value, dict) or set(value) != {'key', 'index', 'exp'} or not isinstance(value['key'], str)
            or not 1 <= len(value['key']) <= 191 or type(value['index']) is not int
            or not 0 <= value['index'] <= 2 or type(value['exp']) is not int or now.timestamp() >= value['exp']):
        raise ValueError('table image link is invalid or expired')
    return value
