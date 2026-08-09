"""Module tests for LINE configuration and Rich Menu lifecycle rules."""

import pytest

from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationRevisionConflict,
    build_configuration_candidate,
)
from domains.line.identities import LineConfigurationRevision
from domains.line.rich_menu import (
    LineRichMenuPublicationConflict,
    LineRichMenuPublicationStatus,
    transition_rich_menu_publication,
)


def test_configuration_candidate_advances_revision() -> None:
    candidate = build_configuration_candidate(
        kind=LineConfigurationKind.MESSAGE_TEMPLATES,
        current_revision=LineConfigurationRevision(4),
        expected_revision=LineConfigurationRevision(4),
        definition={"templates": [{"id": "welcome"}]},
    )

    assert candidate.resulting_revision == LineConfigurationRevision(5)
    assert candidate.definition_json == '{"templates":[{"id":"welcome"}]}'


def test_configuration_rejects_stale_revision() -> None:
    with pytest.raises(LineConfigurationRevisionConflict):
        build_configuration_candidate(
            kind=LineConfigurationKind.LIFF,
            current_revision=LineConfigurationRevision(4),
            expected_revision=LineConfigurationRevision(3),
            definition={"pages": []},
        )


def test_rich_menu_publication_requires_queue_before_publish() -> None:
    assert transition_rich_menu_publication(
        LineRichMenuPublicationStatus.QUEUED,
        LineRichMenuPublicationStatus.PUBLISHING,
    ) is LineRichMenuPublicationStatus.PUBLISHING

    with pytest.raises(LineRichMenuPublicationConflict):
        transition_rich_menu_publication(
            LineRichMenuPublicationStatus.DRAFT,
            LineRichMenuPublicationStatus.PUBLISHED,
        )


def test_rich_menu_retry_preserves_failed_operation() -> None:
    assert transition_rich_menu_publication(
        LineRichMenuPublicationStatus.ROLLBACK_RETRYABLE_FAILED,
        LineRichMenuPublicationStatus.ROLLBACK_QUEUED,
    ) is LineRichMenuPublicationStatus.ROLLBACK_QUEUED

    with pytest.raises(LineRichMenuPublicationConflict):
        transition_rich_menu_publication(
            LineRichMenuPublicationStatus.ROLLBACK_RETRYABLE_FAILED,
            LineRichMenuPublicationStatus.QUEUED,
        )
