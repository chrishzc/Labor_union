"""Composition root for canonical LINE identity and review applications."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

from infrastructure.line.liff_token_verifier import LineLoginTokenVerifier
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from subsystems.line.identity_application import LineIdentityApplication
from subsystems.line.identity_review_application import LineIdentityReviewApplication


@lru_cache(maxsize=1)
def get_line_identity_application() -> LineIdentityApplication:
    return LineIdentityApplication(open_line_unit_of_work, _utc_now)


@lru_cache(maxsize=1)
def get_line_identity_review_application() -> LineIdentityReviewApplication:
    return LineIdentityReviewApplication(open_line_unit_of_work, _utc_now)


@lru_cache(maxsize=1)
def get_liff_token_verifier() -> LineLoginTokenVerifier:
    channel_id = os.getenv("LINE_LOGIN_CHANNEL_ID", "").strip()
    return LineLoginTokenVerifier(channel_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "get_liff_token_verifier",
    "get_line_identity_application",
    "get_line_identity_review_application",
]
