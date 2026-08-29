"""
File: test_line_configuration_public_query.py
Description: 驗證 LINE Configuration 安全查詢的型別、去敏、失敗關閉與零寫入契約。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from domains.line.configuration import LineConfigurationKind, LineConfigurationSnapshot
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import ActorContext
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.configuration_contracts import (
    GetLineConfigurationSafeQuery,
    LineConfigurationQueryContractError,
    LineConfigurationQueryUnavailableError,
    LineConfigurationSafeState,
)


class _ConfigurationRepository:
    def __init__(self, result: object) -> None:
        self.result = result
        self.get_count = 0
        self.apply_count = 0

    def get(self, _kind: LineConfigurationKind) -> object:
        self.get_count += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def apply(self, _command: object) -> None:
        self.apply_count += 1
        raise AssertionError("safe query must not apply a configuration")


class _WriteSink:
    def __init__(self) -> None:
        self.count = 0

    def append(self, _item: object) -> None:
        self.count += 1
        raise AssertionError("safe query must not append durable state")

    def enqueue(self, _item: object) -> None:
        self.count += 1
        raise AssertionError("safe query must not enqueue work")


class _UnitOfWork:
    def __init__(self, result: object) -> None:
        self.configurations = _ConfigurationRepository(result)
        self.audit = _WriteSink()
        self.receipts = _WriteSink()
        self.outbox = _WriteSink()
        self.commit_count = 0

    def __enter__(self) -> _UnitOfWork:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def commit(self) -> None:
        self.commit_count += 1
        raise AssertionError("safe query must not commit")


def _snapshot(
    kind: LineConfigurationKind,
    revision: int,
    definition: dict[str, object],
) -> LineConfigurationSnapshot:
    return LineConfigurationSnapshot(
        kind,
        LineConfigurationRevision(revision),
        json.dumps(
            definition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _query(
    result: object,
    kind: LineConfigurationKind = LineConfigurationKind.RICH_MENUS,
):
    unit_of_work = _UnitOfWork(result)
    application = LineConfigurationApplication(lambda: unit_of_work)
    view = application.get_safe(
        GetLineConfigurationSafeQuery(kind),
        ActorContext("admin:configuration-query", ("line.config.read",)),
    )
    return view, unit_of_work


@pytest.mark.parametrize("kind", tuple(LineConfigurationKind))
def test_safe_query_returns_only_typed_root_facts_for_every_known_kind(
    kind: LineConfigurationKind,
) -> None:
    view, unit_of_work = _query(
        _snapshot(
            kind,
            7,
            {
                "definition": "raw-definition-sentinel",
                "uri": "https://secret.invalid/menu",
                "data": "postback-secret",
                "image": "private/image.png",
                "provider_id": "provider-secret",
                "payload": {"token": "credential-secret"},
                "correlation_id": "correlation-secret",
            },
        ),
        kind,
    )

    assert view.kind is kind
    assert view.revision == 7
    assert view.state is LineConfigurationSafeState.CONFIGURED
    assert "secret" not in repr(view).lower()
    assert unit_of_work.configurations.get_count == 1
    assert unit_of_work.configurations.apply_count == 0
    assert unit_of_work.commit_count == 0
    assert unit_of_work.audit.count == 0
    assert unit_of_work.receipts.count == 0
    assert unit_of_work.outbox.count == 0


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        ({}, LineConfigurationSafeState.EMPTY),
        ({"menus": []}, LineConfigurationSafeState.CONFIGURED),
    ],
)
def test_safe_query_treats_only_exact_canonical_empty_object_as_empty(
    definition: dict[str, object],
    expected: LineConfigurationSafeState,
) -> None:
    view, _unit_of_work = _query(
        _snapshot(LineConfigurationKind.RICH_MENUS, 0, definition)
    )

    assert view.state is expected


@pytest.mark.parametrize(
    "malformed",
    [
        {"kind": "rich_menus", "revision": 3, "definition": {}},
        SimpleNamespace(
            kind=LineConfigurationKind.RICH_MENUS,
            revision=LineConfigurationRevision(3),
            definition_json="{}",
        ),
        LineConfigurationSnapshot(
            LineConfigurationKind.LIFF,
            LineConfigurationRevision(3),
            "{}",
        ),
        LineConfigurationSnapshot(
            LineConfigurationKind.RICH_MENUS,
            3,  # type: ignore[arg-type]
            "{}",
        ),
    ],
)
def test_safe_query_fails_closed_for_malformed_or_mismatched_repository_shape(
    malformed: object,
) -> None:
    with pytest.raises(LineConfigurationQueryContractError):
        _query(malformed)


def test_safe_query_maps_repository_failure_without_leaking_exception() -> None:
    with pytest.raises(LineConfigurationQueryUnavailableError) as captured:
        _query(RuntimeError("provider-token-secret"))

    assert "provider-token-secret" not in str(captured.value)
