"""Fixed private verification transport: the intake network has no Internet/SQL route."""
import os

import requests

from infrastructure.line.liff_token_verifier import LineLoginTokenVerifier


def registration_token_verifier():
    def post(_url, *, data, timeout):
        response = requests.post("http://registration-token-verifier:8081/verify",
                                 json=data, timeout=timeout)
        if response.status_code >= 500:
            raise requests.ConnectionError("registration_verification_relay_unavailable")
        return response
    return LineLoginTokenVerifier(os.environ.get("LINE_LOGIN_CHANNEL_ID", ""), post=post)
