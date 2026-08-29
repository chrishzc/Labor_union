"""
File: test_line_rich_menu_publication_public_contract.py
Description: 驗證 Rich Menu mutation request/response 為必填、closed 且不洩漏內部發布資料。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from api.routes import line_rich_menus
from api.schemas.line_rich_menus import (
    RichMenuPublicationMutationResult,
    RichMenuPublicationQueueResponse,
    RichMenuPublicationRetryRequest,
    RichMenuPublicationRetryResponse,
    RichMenuPublishRequest,
)
from domains.line.rich_menu import LineRichMenuPublicationStatus
from subsystems.line.rich_menu_contracts import LineRichMenuPublicationQuery


@pytest.mark.parametrize(
    ("model", "payload"),
    (
        (RichMenuPublishRequest, {"preview_id": 7}),
        (
            RichMenuPublishRequest,
            {
                "preview_id": 7,
                "reason": " ",
                "idempotency_key": "publish:7",
                "correlation_id": "correlation:7",
            },
        ),
        (RichMenuPublicationRetryRequest, {}),
        (
            RichMenuPublicationRetryRequest,
            {
                "reason": "重新發布",
                "idempotency_key": "retry:7",
                "correlation_id": "correlation:7",
                "provider_payload": "secret",
            },
        ),
    ),
)
def test_mutation_request_metadata_is_required_and_closed(model, payload) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_mutation_responses_are_typed_closed_safe_projections() -> None:
    result = RichMenuPublicationMutationResult(
        id=41,
        menu_definition_id="default_menu",
        configuration_revision=7,
        status=LineRichMenuPublicationStatus.QUEUED,
    )
    queue_response = RichMenuPublicationQueueResponse(data=result)
    retry_response = RichMenuPublicationRetryResponse(data=result)

    for response in (queue_response, retry_response):
        serialized = json.dumps(response.model_dump(mode="json"), ensure_ascii=False)
        assert set(response.data.model_dump()) == {
            "id",
            "menu_definition_id",
            "configuration_revision",
            "status",
        }
        for forbidden in (
            "provider",
            "raw_error",
            "error_message",
            "fingerprint",
            "idempotency_key",
            "correlation_id",
            "secret",
        ):
            assert forbidden not in serialized


def test_publication_mutation_routes_do_not_expose_generic_dict_models() -> None:
    response_models = {
        route.path: route.response_model
        for route in line_rich_menus.router.routes
        if route.path.endswith("/publish") or route.path.endswith("/retry")
    }

    assert response_models == {
        "/api/v1/line/rich-menus/{menu_id}/publish": RichMenuPublicationQueueResponse,
        "/api/v1/line/rich-menus/publications/{publication_id}/retry": (
            RichMenuPublicationRetryResponse
        ),
    }


def test_publication_query_menu_filter_is_optional_and_canonical() -> None:
    assert (
        LineRichMenuPublicationQuery(menu_definition_id="default_menu").menu_definition_id
        == "default_menu"
    )
    with pytest.raises(ValueError):
        LineRichMenuPublicationQuery(menu_definition_id=" default_menu")
