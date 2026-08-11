"""Lease-based Rich Menu publication worker with provider calls outside transactions."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from subsystems.line.ports import LineRichMenuProviderPort, LineUnitOfWorkPort
from subsystems.line.rich_menu_binding import schedule_published_menu_rebindings
from subsystems.line.rich_menu_contracts import (
    ClaimLineRichMenuPublicationsQuery,
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
    LineRichMenuProviderRequest,
    RecordLineRichMenuPublicationCommand,
)


class LineRichMenuWorker:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
        provider: LineRichMenuProviderPort,
        image_materializer: Callable[[str, str | None], str],
        worker_identity: str,
        now: Callable[[], datetime],
        batch_size: int = 5,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._provider = provider
        self._image_materializer = image_materializer
        self._worker_identity = worker_identity
        self._now = now
        self._batch_size = batch_size

    def run_once(self) -> int:
        work_items = self._claim()
        for item in work_items:
            reference, outcome = self._publish(item)
            self._record(item, reference, outcome)
        return len(work_items)

    def _claim(self):
        with self._unit_of_work_factory() as unit_of_work:
            result = unit_of_work.rich_menu_publications.claim(
                ClaimLineRichMenuPublicationsQuery(
                    self._worker_identity,
                    self._now(),
                    self._batch_size,
                )
            )
            unit_of_work.commit()
        return result

    def _publish(self, item):
        reference = item.image_object_reference or "rich_menu/unresolved"
        try:
            reference = self._image_materializer(
                item.definition_json,
                item.image_object_reference,
            )
            outcome = self._provider.publish(
                LineRichMenuProviderRequest(
                    item.publication.publication_id,
                    item.definition_json,
                    reference,
                )
            )
        except (FileNotFoundError, ValueError) as error:
            outcome = LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.REJECTED,
                error_code="line_rich_menu_definition_invalid",
                error_message=str(error)[:500] or "invalid Rich Menu definition",
            )
        except Exception as error:
            outcome = LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.UNAVAILABLE,
                error_code="line_rich_menu_provider_exception",
                error_message=str(error)[:500] or "Rich Menu provider exception",
            )
        return reference, outcome

    def _record(self, item, reference, outcome):
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.rich_menu_publications.record(
                RecordLineRichMenuPublicationCommand(
                    item,
                    outcome,
                    reference,
                    self._now(),
                )
            )
            if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
                schedule_published_menu_rebindings(
                    unit_of_work,
                    item.definition_json,
                    item.publication.publication_id,
                    outcome.provider_menu_id,
                )
            unit_of_work.commit()


__all__ = ["LineRichMenuWorker"]
