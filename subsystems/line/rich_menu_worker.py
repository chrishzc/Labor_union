"""
File: rich_menu_worker.py
Description: 執行 LINE Rich Menu 分步 saga 與 published cleanup-only crash redrive。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from subsystems.line.ports import (
    LineRichMenuCleanupAnomaly,
    LineRichMenuCleanupWorkItem,
    LineRichMenuPublicationStep,
    LineRichMenuProviderPort,
    LineRichMenuStepAttemptEvent,
    LineRichMenuStepAttemptOutcome,
    LineRichMenuStepReceipt,
    LineUnitOfWorkPort,
)
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
            self._process(item)
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

    def _process(self, item) -> None:
        if isinstance(item, LineRichMenuCleanupWorkItem):
            self._process_cleanup_only(item)
            return
        reference = item.image_object_reference or "rich_menu/unresolved"
        previous_provider_menu_id = None
        receipts = {}
        attempts = {}
        receipts, attempts, previous_provider_menu_id = self._load_state(item)
        if LineRichMenuPublicationStep.UPLOAD not in receipts:
            try:
                reference = self._image_materializer(
                    item.definition_json,
                    item.image_object_reference,
                )
            except (FileNotFoundError, ValueError) as error:
                self._record(
                    item,
                    reference,
                    LineRichMenuProviderOutcome(
                        LineRichMenuProviderOutcomeType.REJECTED,
                        error_code="line_rich_menu_definition_invalid",
                        error_message=str(error)[:500]
                        or "invalid Rich Menu definition",
                    ),
                    previous_provider_menu_id,
                )
                return
            except Exception:
                self._record(
                    item,
                    reference,
                    self._retryable_unknown_outcome(
                        "line_rich_menu_image_materialization_unavailable",
                        "Rich Menu image materialization was unavailable",
                    ),
                    previous_provider_menu_id,
                )
                return
        outcome, provider_menu_id = self._advance(
            item,
            reference,
            receipts,
            attempts,
        )
        self._record(
            item,
            reference,
            outcome,
            previous_provider_menu_id,
        )
        if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
            self._cleanup(
                item,
                reference,
                provider_menu_id,
                previous_provider_menu_id,
                receipts,
                attempts,
            )

    def _process_cleanup_only(self, item: LineRichMenuCleanupWorkItem) -> None:
        reference = item.image_object_reference
        if reference is None:
            raise RuntimeError("line_rich_menu_cleanup_image_reference_missing")
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.rich_menu_publications
            receipts = {}
            for receipt in repository.list_step_receipts(
                item.publication.publication_id
            ):
                if receipt.step in receipts:
                    raise RuntimeError("line_rich_menu_step_receipt_collision")
                receipts[receipt.step] = receipt
            attempts = {
                LineRichMenuPublicationStep.CLEANUP: list(
                    repository.list_step_attempt_events(
                        item.publication.publication_id,
                        LineRichMenuPublicationStep.CLEANUP,
                    )
                )
            }
        self._cleanup(
            item,
            reference,
            item.published_provider_menu_id,
            item.previous_provider_menu_id,
            receipts,
            attempts,
        )

    def _load_state(self, item):
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.rich_menu_publications
            list_receipts = getattr(repository, "list_step_receipts", None)
            if not callable(list_receipts):
                raise RuntimeError("line_rich_menu_step_receipt_store_unavailable")
            receipts = {}
            for receipt in list_receipts(item.publication.publication_id):
                if receipt.step in receipts:
                    raise RuntimeError("line_rich_menu_step_receipt_collision")
                receipts[receipt.step] = receipt
            list_attempts = getattr(repository, "list_step_attempt_events", None)
            if not callable(list_attempts):
                raise RuntimeError("line_rich_menu_step_attempt_store_unavailable")
            attempts = {}
            for event in list_attempts(item.publication.publication_id):
                attempts.setdefault(event.step, []).append(event)
            previous_provider_menu_id = repository.published_provider_menu_id(
                item.publication.menu_definition_id
            )
        return receipts, attempts, previous_provider_menu_id

    def _advance(self, item, reference, receipts, attempts):
        request = LineRichMenuProviderRequest(
            item.publication.publication_id,
            item.definition_json,
            reference,
        )
        provider_menu_id = self._receipt_provider_id(
            item,
            request,
            receipts,
            LineRichMenuPublicationStep.CREATE,
            None,
        )
        if provider_menu_id is None:
            outcome, provider_menu_id = self._run_step(
                item,
                request,
                receipts,
                attempts,
                LineRichMenuPublicationStep.CREATE,
                lambda: self._provider.create(request),
                None,
            )
            if outcome.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
                return outcome, None

        for step, call in (
            (
                LineRichMenuPublicationStep.UPLOAD,
                lambda: self._provider.upload(request, provider_menu_id),
            ),
            (
                LineRichMenuPublicationStep.LINK,
                lambda: self._provider.upsert_alias(request, provider_menu_id),
            ),
            (
                LineRichMenuPublicationStep.SWITCH,
                lambda: self._provider.switch_default(request, provider_menu_id),
            ),
        ):
            outcome, step_provider_id = self._run_step(
                item,
                request,
                receipts,
                attempts,
                step,
                call,
                provider_menu_id,
            )
            if outcome.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
                return outcome, provider_menu_id
            provider_menu_id = step_provider_id or provider_menu_id
        return (
            LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.SUCCESS,
                provider_menu_id=provider_menu_id,
            ),
            provider_menu_id,
        )

    def _run_step(
        self,
        item,
        request,
        receipts,
        attempts,
        step,
        call,
        provider_menu_id,
    ):
        self._validate_attempt_history(
            item,
            request,
            attempts,
            step,
            provider_menu_id,
        )
        existing = self._receipt_provider_id(
            item,
            request,
            receipts,
            step,
            provider_menu_id,
        )
        if existing is not None:
            return (
                LineRichMenuProviderOutcome(
                    LineRichMenuProviderOutcomeType.SUCCESS,
                    provider_menu_id=existing,
                ),
                existing,
            )
        attempt_number = self._next_attempt_number(attempts, step)
        try:
            outcome = call()
        except (FileNotFoundError, ValueError) as error:
            outcome = LineRichMenuProviderOutcome(
                LineRichMenuProviderOutcomeType.REJECTED,
                error_code="line_rich_menu_definition_invalid",
                error_message=str(error)[:500] or "invalid Rich Menu definition",
            )
        except Exception:
            outcome = self._retryable_unknown_outcome(
                "line_rich_menu_provider_exception",
                "LINE Rich Menu provider outcome was not acknowledged",
            )
            self._append_step_attempt(
                item,
                request,
                attempts,
                step,
                attempt_number,
                LineRichMenuStepAttemptOutcome.LOST_ACK,
                provider_menu_id,
                outcome.error_code,
            )
            return outcome, provider_menu_id
        acknowledged_provider_id = outcome.provider_menu_id or provider_menu_id
        attempt_outcome = LineRichMenuStepAttemptOutcome(outcome.outcome_type.value)
        if (
            outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
            and acknowledged_provider_id is None
        ):
            missing_id = self._retryable_unknown_outcome(
                "line_rich_menu_provider_id_missing",
                "LINE Rich Menu provider success acknowledgement was incomplete",
            )
            self._append_step_attempt(
                item,
                request,
                attempts,
                step,
                attempt_number,
                LineRichMenuStepAttemptOutcome.LOST_ACK,
                provider_menu_id,
                missing_id.error_code,
            )
            return missing_id, provider_menu_id
        acknowledged_ids = {
            event.provider_menu_id
            for event in attempts.get(step, ())
            if event.outcome is LineRichMenuStepAttemptOutcome.SUCCESS
        }
        if (
            outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
            and acknowledged_ids
            and acknowledged_ids != {acknowledged_provider_id}
        ):
            raise RuntimeError("line_rich_menu_step_attempt_provider_id_conflict")
        self._append_step_attempt(
            item,
            request,
            attempts,
            step,
            attempt_number,
            attempt_outcome,
            provider_menu_id,
            outcome.error_code,
            acknowledged_provider_id=acknowledged_provider_id,
        )
        if outcome.outcome_type is not LineRichMenuProviderOutcomeType.SUCCESS:
            return outcome, provider_menu_id
        self._append_step_receipt(
            item,
            request,
            step,
            acknowledged_provider_id,
            fingerprint_provider_id=provider_menu_id,
        )
        receipts[step] = LineRichMenuStepReceipt(
            item.publication.publication_id,
            step,
            self._step_fingerprint(request, step, provider_menu_id),
            IdempotencyKey(self._step_key(item, step)),
            self._now(),
            acknowledged_provider_id,
        )
        return outcome, acknowledged_provider_id

    def _next_attempt_number(self, attempts, step):
        return max(
            (event.attempt_number for event in attempts.get(step, ())),
            default=0,
        ) + 1

    def _validate_attempt_history(
        self,
        item,
        request,
        attempts,
        step,
        provider_menu_id,
    ) -> None:
        expected_fingerprint = self._step_fingerprint(
            request,
            step,
            provider_menu_id,
        )
        seen_attempt_numbers = set()
        for event in attempts.get(step, ()):
            if event.attempt_number in seen_attempt_numbers:
                raise RuntimeError("line_rich_menu_step_attempt_collision")
            seen_attempt_numbers.add(event.attempt_number)
            if event.publication_id != item.publication.publication_id:
                raise RuntimeError("line_rich_menu_step_attempt_publication_conflict")
            if event.request_fingerprint != expected_fingerprint:
                raise RuntimeError("line_rich_menu_step_attempt_fingerprint_conflict")
            if event.idempotency_key != IdempotencyKey(
                self._attempt_key(item, step, event.attempt_number)
            ):
                raise RuntimeError("line_rich_menu_step_attempt_idempotency_conflict")
            if event.correlation_id != item.correlation_id:
                raise RuntimeError("line_rich_menu_step_attempt_correlation_conflict")

    def _append_step_attempt(
        self,
        item,
        request,
        attempts,
        step,
        attempt_number,
        outcome,
        fingerprint_provider_id,
        error_code,
        *,
        acknowledged_provider_id=None,
    ):
        event = LineRichMenuStepAttemptEvent(
            item.publication.publication_id,
            step,
            attempt_number,
            self._step_fingerprint(request, step, fingerprint_provider_id),
            IdempotencyKey(self._attempt_key(item, step, attempt_number)),
            outcome,
            self._now(),
            item.correlation_id,
            acknowledged_provider_id
            if outcome is LineRichMenuStepAttemptOutcome.SUCCESS
            else None,
            None
            if outcome is LineRichMenuStepAttemptOutcome.SUCCESS
            else error_code or "line_rich_menu_provider_failure",
        )
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.rich_menu_publications
            append_attempt = getattr(repository, "append_step_attempt_event", None)
            if not callable(append_attempt):
                raise RuntimeError("line_rich_menu_step_attempt_store_unavailable")
            append_attempt(event)
            unit_of_work.commit()
        attempts.setdefault(step, []).append(event)

    def _receipt_provider_id(self, item, request, receipts, step, provider_menu_id):
        receipt = receipts.get(step)
        if receipt is None:
            return None
        if receipt.idempotency_key != IdempotencyKey(self._step_key(item, step)):
            raise RuntimeError("line_rich_menu_step_receipt_idempotency_conflict")
        if receipt.request_fingerprint != self._step_fingerprint(
            request,
            step,
            provider_menu_id,
        ):
            raise RuntimeError("line_rich_menu_step_receipt_fingerprint_conflict")
        if receipt.provider_menu_id is None:
            raise RuntimeError("line_rich_menu_step_receipt_provider_id_missing")
        return receipt.provider_menu_id

    def _append_step_receipt(
        self,
        item,
        request,
        step,
        provider_menu_id,
        *,
        fingerprint_provider_id,
    ):
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.rich_menu_publications
            append_receipt = getattr(repository, "append_step_receipt", None)
            if not callable(append_receipt):
                raise RuntimeError("line_rich_menu_step_receipt_store_unavailable")
            append_receipt(
                LineRichMenuStepReceipt(
                    item.publication.publication_id,
                    step,
                    self._step_fingerprint(
                        request,
                        step,
                        fingerprint_provider_id,
                    ),
                    IdempotencyKey(self._step_key(item, step)),
                    self._now(),
                    provider_menu_id,
                )
            )
            unit_of_work.commit()

    def _cleanup(
        self,
        item,
        reference,
        provider_menu_id,
        previous_provider_menu_id,
        receipts,
        attempts,
    ):
        request = LineRichMenuProviderRequest(
            item.publication.publication_id,
            item.definition_json,
            reference,
        )
        cleanup_target = previous_provider_menu_id or provider_menu_id
        self._validate_attempt_history(
            item,
            request,
            attempts,
            LineRichMenuPublicationStep.CLEANUP,
            cleanup_target,
        )
        acknowledged_cleanup_target = self._receipt_provider_id(
            item,
            request,
            receipts,
            LineRichMenuPublicationStep.CLEANUP,
            cleanup_target,
        )
        if acknowledged_cleanup_target is not None:
            if acknowledged_cleanup_target != cleanup_target:
                raise RuntimeError(
                    "line_rich_menu_cleanup_receipt_provider_id_conflict"
                )
            return
        if not previous_provider_menu_id or previous_provider_menu_id == provider_menu_id:
            self._append_step_receipt(
                item,
                request,
                LineRichMenuPublicationStep.CLEANUP,
                provider_menu_id,
                fingerprint_provider_id=provider_menu_id,
            )
            return
        attempt_number = self._next_attempt_number(
            attempts,
            LineRichMenuPublicationStep.CLEANUP,
        )
        try:
            outcome = self._provider.delete(previous_provider_menu_id)
        except Exception:
            outcome = self._manual_recovery(
                "line_rich_menu_cleanup_exception",
                "LINE Rich Menu cleanup outcome was not acknowledged",
            )
            attempt_outcome = LineRichMenuStepAttemptOutcome.LOST_ACK
        else:
            attempt_outcome = LineRichMenuStepAttemptOutcome(outcome.outcome_type.value)
        self._append_step_attempt(
            item,
            request,
            attempts,
            LineRichMenuPublicationStep.CLEANUP,
            attempt_number,
            attempt_outcome,
            previous_provider_menu_id,
            outcome.error_code,
            acknowledged_provider_id=previous_provider_menu_id,
        )
        if outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS:
            self._append_step_receipt(
                item,
                request,
                LineRichMenuPublicationStep.CLEANUP,
                previous_provider_menu_id,
                fingerprint_provider_id=previous_provider_menu_id,
            )
            return
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.rich_menu_publications
            append_anomaly = getattr(repository, "append_cleanup_anomaly", None)
            if not callable(append_anomaly):
                raise RuntimeError("line_rich_menu_cleanup_anomaly_store_unavailable")
            append_anomaly(
                LineRichMenuCleanupAnomaly(
                    item.publication.publication_id,
                    outcome.error_code or "line_rich_menu_cleanup_failed",
                    self._now(),
                )
            )
            unit_of_work.commit()

    def _manual_recovery(self, error_code, error_message):
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.REJECTED,
            error_code=error_code,
            error_message=error_message,
        )

    def _retryable_unknown_outcome(self, error_code, error_message):
        return LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.UNAVAILABLE,
            error_code=error_code,
            error_message=error_message,
        )

    def _step_fingerprint(self, request, step, provider_menu_id):
        return fingerprint_payload(
            {
                "publication_id": request.publication_id.value,
                "step": step.value,
                "definition_json": request.definition_json,
                "image_object_reference": request.image_object_reference,
                "provider_menu_id": provider_menu_id,
            }
        )

    def _step_key(self, item, step):
        return f"line-rich-menu:{item.publication.publication_id.value}:{step.value}"

    def _attempt_key(self, item, step, attempt_number):
        return (
            f"{self._step_key(item, step)}:attempt:{attempt_number}"
        )

    def _record(
        self,
        item,
        reference,
        outcome,
        previous_provider_menu_id,
    ):
        with self._unit_of_work_factory() as unit_of_work:
            if (
                outcome.outcome_type is LineRichMenuProviderOutcomeType.SUCCESS
                and previous_provider_menu_id is not None
            ):
                unit_of_work.rich_menu_publications.persist_cleanup_target(
                    item.publication.publication_id,
                    item.lease_owner,
                    previous_provider_menu_id,
                )
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
