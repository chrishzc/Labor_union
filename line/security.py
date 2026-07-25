"""
================================================================================
檔案名稱: line/security.py
功能說明: LINE Webhook 安全工具，使用 Channel Secret 驗證請求簽章並阻擋偽造事件
================================================================================
"""

import base64
import hashlib
import hmac


def verify_line_signature(raw_body: bytes, signature: str, channel_secret: str) -> bool:
    if not raw_body or not signature or not channel_secret:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)
