"""
File: rich_menu_api_adapter.py
Description: 提供 LINE Rich Menu 分步發布與個人選單讀回。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import json
import re
from typing import Any

import requests

from domains.line.identities import LineUserId
from infrastructure.line.http_outcomes import response_failure, response_request_id
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
    LineRichMenuProviderRequest,
)
from subsystems.line.rich_menu_definition import (
    rich_menu_is_default,
    rich_menu_provider_definition,
)

_API_ROOT = "https://api.line.me/v2/bot"
_DATA_ROOT = "https://api-data.line.me/v2/bot"


class LineRichMenuApiAdapter:
    def __init__(
        self,
        channel_access_token: str,
        image_loader: Callable[[str], tuple[bytes, str]],
        *,
        session: Any | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        normalized = channel_access_token.strip()
        if not normalized:
            raise ValueError("LINE channel access token is required")
        self._access_token = normalized
        self._image_loader = image_loader
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds

    def publish(
        self,
        request: LineRichMenuProviderRequest,
    ) -> LineRichMenuProviderOutcome:
        created = self.create(request)
        if created.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            return created
        provider_menu_id = created.provider_menu_id
        uploaded = self.upload(request, provider_menu_id)
        if uploaded.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            self.delete(provider_menu_id)
            return uploaded
        linked = self.upsert_alias(request, provider_menu_id)
        if linked.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            self.delete(provider_menu_id)
            return linked
        switched = self.switch_default(request, provider_menu_id)
        if switched.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            self.delete(provider_menu_id)
            return switched
        return switched

    def create(
        self,
        request: LineRichMenuProviderRequest,
    ) -> LineRichMenuProviderOutcome:
        created = self._create(
            rich_menu_provider_definition(request.definition_json),
        )
        if isinstance(created, str):
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS,
                provider_menu_id=created,
            )
        return created

    def upload(
        self,
        request: LineRichMenuProviderRequest,
        provider_menu_id: str,
    ) -> LineRichMenuProviderOutcome:
        image_bytes, content_type = self._image_loader(request.image_object_reference)
        return self._upload(
            provider_menu_id,
            image_bytes,
            content_type,
        ) or LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id=provider_menu_id,
        )

    def upsert_alias(
        self,
        request: LineRichMenuProviderRequest,
        provider_menu_id: str,
    ) -> LineRichMenuProviderOutcome:
        result = self._set_alias(
            _rich_menu_alias_id(request.definition_json),
            provider_menu_id,
        )
        return result or LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id=provider_menu_id,
        )

    def switch_default(
        self,
        request: LineRichMenuProviderRequest,
        provider_menu_id: str,
    ) -> LineRichMenuProviderOutcome:
        if not rich_menu_is_default(request.definition_json):
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS,
                provider_menu_id=provider_menu_id,
            )
        return self.set_default(provider_menu_id)

    def delete(self, provider_menu_id: str) -> LineRichMenuProviderOutcome:
        outcome = self._empty_success_operation(
            "delete",
            f"{_API_ROOT}/richmenu/{provider_menu_id}",
            provider_menu_id,
        )
        if outcome.error_code == "line_http_404":
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS, provider_menu_id=provider_menu_id,
            )
        return outcome

    def link_to_user(
        self,
        provider_menu_id: str,
        line_user_id: LineUserId,
    ) -> LineRichMenuProviderOutcome:
        response = self._request(
            "post",
            f"{_API_ROOT}/user/{line_user_id.value}/richmenu/{provider_menu_id}",
        )
        if _successful(response):
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS, provider_menu_id=provider_menu_id,
            )
        if response.status_code == 404:
            return _personal_menu_failure(response, "link", "line_rich_menu_link_menu_missing")
        if response.status_code == 400:
            # LINE documents both invalid user IDs and missing menu images for link 400.
            current = self.get_user_rich_menu(line_user_id)
            if current.error_code == "line_rich_menu_readback_user_invalid":
                return _personal_menu_failure(response, "link", "line_rich_menu_readback_user_invalid")
            if current.provider_menu_id is not None or current.error_code == "line_http_404":
                image = self._request("get", f"{_DATA_ROOT}/richmenu/{provider_menu_id}/content", stream=True)
                if not isinstance(image, _SyntheticFailure):
                    image.close()
                if image.status_code == 404:
                    return _personal_menu_failure(response, "link", "line_rich_menu_image_unavailable")
        return _personal_menu_failure(response, "link")

    def get_user_rich_menu(self, line_user_id: LineUserId) -> LineRichMenuProviderOutcome:
        response = self._request("get", f"{_API_ROOT}/user/{line_user_id.value}/richmenu")
        if response.status_code == 400:
            return _personal_menu_failure(response, "readback", "line_rich_menu_readback_user_invalid")
        if not _successful(response):
            return _personal_menu_failure(response, "readback")
        try:
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS,
                provider_menu_id=response.json()["richMenuId"],
            )
        except (KeyError, TypeError, ValueError):
            return _adapter_failure("line_rich_menu_readback_invalid")

    def unlink_from_user(
        self,
        line_user_id: LineUserId,
    ) -> LineRichMenuProviderOutcome:
        """Remove a user's Rich Menu through the canonical provider boundary."""
        return self._empty_success_operation(
            "delete",
            f"{_API_ROOT}/user/{line_user_id.value}/richmenu",
            line_user_id.value,
        )

    def restore_default_for_user(self, line_user_id: LineUserId) -> LineRichMenuProviderOutcome:
        default = self._request("get", f"{_API_ROOT}/user/all/richmenu")
        if not _successful(default):
            return _rich_menu_failure(default)
        try:
            menu_id = default.json()["richMenuId"]
        except (KeyError, TypeError, ValueError):
            return _adapter_failure("line_rich_menu_default_response_invalid")
        if not isinstance(menu_id, str) or not menu_id or menu_id != menu_id.strip() or len(menu_id) > 191:
            return _adapter_failure("line_rich_menu_default_response_invalid")

        outcome = self.unlink_from_user(line_user_id)
        if outcome.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            return outcome
        personal = self._request("get", f"{_API_ROOT}/user/{line_user_id.value}/richmenu")
        if personal.status_code == 404:
            return LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS,
                provider_menu_id=menu_id,
            )
        if _successful(personal):
            return _adapter_failure("line_rich_menu_personal_link_still_present")
        return _rich_menu_failure(personal)

    def set_default(self, provider_menu_id: str) -> LineRichMenuProviderOutcome:
        return self._empty_success_operation(
            "post",
            f"{_API_ROOT}/user/all/richmenu/{provider_menu_id}",
            provider_menu_id,
        )

    def _set_alias(
        self,
        alias_id: str | None,
        provider_menu_id: str,
    ):
        if not alias_id:
            return None
        payload = json.dumps(
            {"richMenuAliasId": alias_id, "richMenuId": provider_menu_id},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        response = self._request(
            "post",
            f"{_API_ROOT}/richmenu/alias",
            data=payload,
            content_type="application/json",
        )
        if _successful(response):
            return None
        if response.status_code not in (400, 409):
            return _rich_menu_failure(response)
        lookup = self._request(
            "get",
            f"{_API_ROOT}/richmenu/alias/{alias_id}",
        )
        if lookup.status_code == 404:
            return _rich_menu_failure(response)
        if not _successful(lookup):
            return _rich_menu_failure(lookup)
        try:
            current_provider_menu_id = lookup.json()["richMenuId"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return _adapter_failure("line_rich_menu_alias_response_invalid")
        if current_provider_menu_id == provider_menu_id:
            return None
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.REJECTED,
            error_code="line_rich_menu_alias_target_conflict",
            error_message="LINE Rich Menu alias points to a different provider menu",
        )

    def _create(self, definition_json: str):
        response = self._request(
            "post",
            f"{_API_ROOT}/richmenu",
            data=definition_json,
            content_type="application/json",
        )
        if not _successful(response):
            return _rich_menu_failure(response)
        try:
            provider_menu_id = response.json()["richMenuId"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return _adapter_failure("line_rich_menu_response_invalid")
        if not isinstance(provider_menu_id, str) or not provider_menu_id.strip():
            return _adapter_failure("line_rich_menu_response_invalid")
        return provider_menu_id

    def _upload(self, menu_id, image_bytes, content_type):
        response = self._request(
            "post",
            f"{_DATA_ROOT}/richmenu/{menu_id}/content",
            data=image_bytes,
            content_type=content_type,
        )
        if _successful(response):
            return None
        if response.status_code == 400:
            current = self._request("get", f"{_DATA_ROOT}/richmenu/{menu_id}/content")
            if _successful(current) and current.content == image_bytes:
                return None
        return _rich_menu_failure(response)

    def _empty_success_operation(self, method, url, provider_menu_id):
        response = self._request(method, url)
        if not _successful(response):
            return _rich_menu_failure(response)
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id=provider_menu_id,
        )

    def _request(self, method, url, *, data=None, content_type=None, stream=False):
        headers = {"Authorization": f"Bearer {self._access_token}"}
        if content_type is not None:
            headers["Content-Type"] = content_type
        try:
            return self._session.request(
                method,
                url,
                headers=headers,
                data=data,
                timeout=self._timeout_seconds,
                **({"stream": True} if stream else {}),
            )
        except requests.Timeout:
            return _SyntheticFailure("timeout")
        except requests.RequestException:
            return _SyntheticFailure("unavailable")


class _SyntheticFailure:
    def __init__(self, category: str) -> None:
        self.category = category
        self.status_code = 599
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, str]:
        return {"message": f"LINE Rich Menu provider {self.category}"}


def _successful(response: object) -> bool:
    return 200 <= int(getattr(response, "status_code")) < 300


def _rich_menu_alias_id(definition_json: str) -> str | None:
    try:
        definition = json.loads(definition_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    alias_id = definition.get("rich_menu_alias_id")
    if isinstance(alias_id, str) and alias_id.strip():
        return alias_id.strip()
    return None


def _rich_menu_failure(response: object) -> LineRichMenuProviderOutcome:
    if isinstance(response, _SyntheticFailure):
        outcome_type = {
            "timeout": LineRichMenuProviderOutcomeType.TIMEOUT,
            "unavailable": LineRichMenuProviderOutcomeType.UNAVAILABLE,
        }[response.category]
        return LineRichMenuProviderOutcome(
            outcome_type,
            error_code=f"line_rich_menu_{response.category}",
            error_message=f"LINE Rich Menu provider {response.category}",
        )
    failure = response_failure(response, retry_after_on_unavailable=True)
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType(failure.category),
        error_code=failure.code,
        error_message=failure.message,
        retry_after_seconds=failure.retry_after_seconds,
    )


def _adapter_failure(code: str) -> LineRichMenuProviderOutcome:
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType.UNAVAILABLE,
        error_code=code,
        error_message=code.replace("_", " "),
    )


def _personal_menu_failure(response, operation, code=None):
    outcome = _rich_menu_failure(response)
    if isinstance(response, _SyntheticFailure):
        return outcome
    request_id = response_request_id(response)
    trace = (
        f" (x-line-request-id: {request_id})"
        if request_id and re.fullmatch(r"[a-zA-Z0-9-]{1,64}", request_id)
        else ""
    )
    return replace(
        outcome,
        error_code=code or outcome.error_code,
        error_message=f"LINE rich menu {operation} HTTP {response.status_code}{trace}",
    )


__all__ = ["LineRichMenuApiAdapter"]
