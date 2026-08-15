"""HTTP adapter for LINE Rich Menu create, upload, link, and delete operations."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

import requests

from domains.line.identities import LineUserId
from infrastructure.line.http_outcomes import response_failure
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
        created = self._create(rich_menu_provider_definition(request.definition_json))
        if not isinstance(created, str):
            return created
        image_bytes, content_type = self._image_loader(request.image_object_reference)
        uploaded = self._upload(created, image_bytes, content_type)
        if uploaded is not None:
            self.delete(created)
            return uploaded
        if rich_menu_is_default(request.definition_json):
            selected = self.set_default(created)
            if selected.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
                self.delete(created)
                return selected
        aliased = self._set_alias(_rich_menu_alias_id(request.definition_json), created)
        if aliased is not None:
            self.delete(created)
            return aliased
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id=created,
        )

    def delete(self, provider_menu_id: str) -> LineRichMenuProviderOutcome:
        return self._empty_success_operation(
            "delete",
            f"{_API_ROOT}/richmenu/{provider_menu_id}",
            provider_menu_id,
        )

    def link_to_user(
        self,
        provider_menu_id: str,
        line_user_id: LineUserId,
    ) -> LineRichMenuProviderOutcome:
        return self._empty_success_operation(
            "post",
            f"{_API_ROOT}/user/{line_user_id.value}/richmenu/{provider_menu_id}",
            provider_menu_id,
        )

    def set_default(self, provider_menu_id: str) -> LineRichMenuProviderOutcome:
        return self._empty_success_operation(
            "post",
            f"{_API_ROOT}/user/all/richmenu/{provider_menu_id}",
            provider_menu_id,
        )

    def _set_alias(self, alias_id: str | None, provider_menu_id: str):
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
        if int(getattr(response, "status_code")) != 409:
            return _rich_menu_failure(response)
        update_payload = json.dumps(
            {"richMenuId": provider_menu_id},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        update = self._request(
            "post",
            f"{_API_ROOT}/richmenu/alias/{alias_id}",
            data=update_payload,
            content_type="application/json",
        )
        return None if _successful(update) else _rich_menu_failure(update)

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
        return None if _successful(response) else _rich_menu_failure(response)

    def _empty_success_operation(self, method, url, provider_menu_id):
        response = self._request(method, url)
        if not _successful(response):
            return _rich_menu_failure(response)
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.SUCCESS,
            provider_menu_id=provider_menu_id,
        )

    def _request(self, method, url, *, data=None, content_type=None):
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
    failure = response_failure(response)
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType(failure.category),
        error_code=failure.code,
        error_message=failure.message,
    )


def _adapter_failure(code: str) -> LineRichMenuProviderOutcome:
    return LineRichMenuProviderOutcome(
        LineRichMenuProviderOutcomeType.UNAVAILABLE,
        error_code=code,
        error_message=code.replace("_", " "),
    )


__all__ = ["LineRichMenuApiAdapter"]
