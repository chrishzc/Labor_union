"""
File: line_notification_repository.py
Description: 管理 LINE 通知意圖的可取消狀態，確保刪除規則不會讓舊任務穿透至 provider。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from infrastructure.mysql.line_repository_support import aware_utc
from domains.line.delivery import (
    LineDeliveryRequest,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineGroupId
from domains.line.identities import LineDeliveryTaskId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from shared_kernel.validation import require_canonical_text
from subsystems.line.message_configuration import render_message_template
from subsystems.line.notification_policy import NotificationSourceEvent
from subsystems.line.notification_schedule import schedule_notification_occurrences
from subsystems.anomalies.line_notification_anomaly_projector import NotificationDecisionSource
from subsystems.line.ports import LineNotificationCancellationLineage
from subsystems.line.notification_failure_current_fact import (
    LineNotificationFailedSourceFact,
    LineNotificationFailureCurrentFactQuery,
    LineNotificationFailureCurrentFactReadback,
    LineNotificationFailureReason,
    LineNotificationFailureRecheckTarget,
    LineNotificationReplaySuccessorFact,
    evaluate_line_notification_failure_current_fact,
)


class LineNotificationManualReplayValidationError(ValueError):
    """The original source is not presently eligible for a fresh manual replay."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MySqlLineNotificationRepository:
    """Derived notification records only; owning domains retain their source facts."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def cancel_rule(self, rule_id: str, *, reason: str) -> int:
        """Compatibility wrapper returning the count from the intent owner only."""
        return len(self.lock_and_cancel_rule_intents(rule_id, reason=reason).intent_ids)

    def lock_and_cancel_rule_intents(
        self,
        rule_id: str,
        *,
        reason: str,
    ) -> LineNotificationCancellationLineage:
        """Lock and cancel intents; delivery-task state belongs to its own repository."""
        require_canonical_text(rule_id, "LINE notification rule ID", 191)
        require_canonical_text(reason, "LINE notification cancellation reason", 191)
        with self._connection.cursor() as cursor:
            cursor.execute(_LOCK_RULE_INTENTS_SQL, (rule_id,))
            rows = tuple(cursor.fetchall() or ())
            parsed_rows = tuple(_cancellation_row(row) for row in rows)
            intent_ids = tuple(
                sorted(
                    row[0] for row in parsed_rows
                )
            )
            if len(intent_ids) != len(set(intent_ids)):
                raise RuntimeError("line_notification_intent_cancellation_lineage_invalid")
            task_values = tuple(row[1] for row in parsed_rows if row[1] is not None)
            if len(task_values) != len(set(task_values)):
                raise RuntimeError("line_notification_intent_cancellation_lineage_invalid")
            task_ids = tuple(
                sorted(
                    (LineDeliveryTaskId(value) for value in task_values),
                    key=lambda task_id: task_id.value,
                )
            )
            if intent_ids:
                placeholders = ",".join("%s" for _ in intent_ids)
                cursor.execute(
                    _CANCEL_INTENTS_BY_ID_SQL.format(placeholders=placeholders),
                    (reason, *intent_ids),
                )
                if int(cursor.rowcount) != len(intent_ids):
                    raise RuntimeError("line_notification_intent_cancellation_conflict")
        return LineNotificationCancellationLineage(intent_ids, task_ids)

    def mark_delivery_task_provider_accepted(self, delivery_task_id: int) -> None:
        """Keep derived intent state aligned once LINE accepted its linked task."""
        with self._connection.cursor() as cursor:
            cursor.execute(_MARK_PROVIDER_ACCEPTED_SQL, (delivery_task_id,))

    def cancel_service_day_log_reminders(
        self, assignment_id: int, service_date: str
    ) -> int:
        """Stop only unsent reminders for the exact completed assignment and service day."""
        if assignment_id <= 0 or not service_date:
            raise ValueError("service-day notification cancellation target is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CANCEL_SERVICE_DAY_INTENTS_SQL,
                (assignment_id, service_date),
            )
            cancelled = int(cursor.rowcount)
            cursor.execute(
                _CANCEL_SERVICE_DAY_TASKS_SQL,
                (assignment_id, service_date),
            )
        return cancelled

    def cancel_service_day_log_reminders_for_assignments(
        self, assignment_ids: tuple[int, ...]
    ) -> int:
        """Cancel only tasks derived from explicitly superseded Scheduling assignments."""
        normalized = tuple(sorted({int(value) for value in assignment_ids}))
        if not normalized or any(value <= 0 for value in normalized):
            raise ValueError("scheduling notification cancellation target is invalid")
        placeholders = ",".join("%s" for _ in normalized)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _cancel_service_day_assignment_intents_sql(placeholders), normalized
            )
            cancelled = int(cursor.rowcount)
            cursor.execute(
                _cancel_service_day_assignment_tasks_sql(placeholders), normalized
            )
        return cancelled

    def list_case_timeline(self, case_no: str) -> tuple[dict[str, object], ...]:
        """Return deidentified evidence only; notification payload text never crosses this API."""
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_TIMELINE_SQL, (case_no,))
            rows = tuple(cursor.fetchall() or ())
        return tuple(_timeline_row(row) for row in rows if isinstance(row, dict))

    def list_anomaly_sources(self, *, limit: int = 100) -> tuple[NotificationDecisionSource, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_NOTIFICATION_ANOMALY_SOURCES_SQL, (limit,))
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            NotificationDecisionSource(int(row["decision_id"]), str(row["source_event_identity"]),
                str(row["case_no"]), str(row["reason_code"]), int(row["source_version"]))
            for row in rows
            if isinstance(row, dict) and row.get("case_no")
        )

    def current_failure_fact(
        self, query: LineNotificationFailureCurrentFactQuery
    ) -> LineNotificationFailureCurrentFactReadback:
        """Return the complete logical LINE-006 group without writing an aggregate."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                _LINE006_FAILED_SOURCES_SQL,
                (query.case_no, query.notification_reason.value),
            )
            rows = _strict_dict_rows(
                tuple(cursor.fetchall() or ()),
                "line006_failed_source_readback_invalid",
            )
        if not rows:
            return evaluate_line_notification_failure_current_fact(
                query, (), owner_version=0, authoritative_complete=True
            )

        source_rows: dict[int, list[dict[str, object]]] = {}
        for row in rows:
            source_rows.setdefault(int(row["source_event_id"]), []).append(row)
        source_ids = tuple(sorted(source_rows))
        replay_rows = self._line006_replay_rows(source_ids)
        replay_by_original: dict[int, list[LineNotificationReplaySuccessorFact]] = {
            source_id: [] for source_id in source_ids
        }
        maximum_version = max(source_ids)
        for original_id in source_ids:
            successors = _line006_replay_facts(
                original_id,
                source_rows[original_id][0],
                replay_rows,
            )
            replay_by_original[original_id].extend(successors)
            for successor in successors:
                maximum_version = max(maximum_version, successor.source_event_id)

        rule_snapshot = self._current_configuration("notification_rules")
        rules = None if rule_snapshot is None else rule_snapshot[1].get("rules")
        authoritative_complete = isinstance(rules, list)
        if rule_snapshot is not None:
            maximum_version = max(maximum_version, rule_snapshot[0])

        sources: list[LineNotificationFailedSourceFact] = []
        for source_id in source_ids:
            row = source_rows[source_id][0]
            facts = _json_object(row["facts_snapshot"])
            current_rule_applies = False
            if isinstance(rules, list):
                current_rule_applies = any(
                    isinstance(rule, dict)
                    and rule.get("event_code") == row["event_code"]
                    and rule.get("enabled") is True
                    and _predicates_match(rule.get("predicates"), facts)
                    for rule in rules
                )
            sources.append(
                LineNotificationFailedSourceFact(
                    source_event_id=source_id,
                    currently_applicable=bool(row["is_latest_source_version"])
                    and current_rule_applies,
                    applicability_complete=authoritative_complete,
                    replay_successors=tuple(replay_by_original[source_id]),
                )
            )
        return evaluate_line_notification_failure_current_fact(
            query,
            tuple(sources),
            owner_version=maximum_version,
            authoritative_complete=authoritative_complete,
        )

    def line006_recheck_targets_for_source(
        self, source_event_id: int
    ) -> tuple[LineNotificationFailureRecheckTarget, ...]:
        if source_event_id <= 0:
            raise ValueError("notification source event ID is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_LINE006_RECHECK_TARGETS_FOR_SOURCE_SQL, (source_event_id,))
            rows = tuple(cursor.fetchall() or ())
        return _line006_recheck_targets(rows)

    def list_line006_recheck_targets(
        self, *, limit: int = 100
    ) -> tuple[LineNotificationFailureRecheckTarget, ...]:
        if limit <= 0:
            raise ValueError("LINE-006 recheck target limit is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_LINE006_RECHECK_TARGETS_SQL, (limit,))
            rows = tuple(cursor.fetchall() or ())
        return _line006_recheck_targets(rows)

    def line006_recheck_targets_for_delivery_task(
        self, delivery_task_id: int
    ) -> tuple[LineNotificationFailureRecheckTarget, ...]:
        if delivery_task_id <= 0:
            raise ValueError("LINE delivery task ID is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_LINE006_REPLAY_IDENTITY_FOR_TASK_SQL, (delivery_task_id,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return ()
        original_source_id = _manual_replay_original_source_id(
            str(row.get("source_event_identity", ""))
        )
        if original_source_id is None:
            return ()
        return self.line006_recheck_targets_for_source(original_source_id)

    def manual_replay_delivery_validation_failure(
        self, delivery_task_id: int
    ) -> str | None:
        """Freshly validate a replay task immediately before provider delivery."""

        if delivery_task_id <= 0:
            raise ValueError("LINE delivery task ID is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_MANUAL_REPLAY_TASK_VALIDATION_SQL, (delivery_task_id,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        original_source_id = _manual_replay_original_source_id(
            str(row.get("source_event_identity", ""))
        )
        if original_source_id is None:
            return "replay_lineage_ambiguous"
        original = self._source_event(original_source_id)
        if original is None:
            return "replay_lineage_ambiguous"
        replay_facts = _json_object(row["facts_snapshot"])
        if (
            row.get("event_code") != original.event_code
            or row.get("source_aggregate_type") != original.source_aggregate_type
            or row.get("source_aggregate_identity") != original.source_aggregate_identity
            or int(row.get("source_version", -1)) != original.source_version
            or _canonical_json(replay_facts) != _canonical_json(original.facts)
        ):
            return "replay_lineage_ambiguous"
        if self._source_has_newer_version(original):
            return "notification_source_not_currently_applicable"
        rule_snapshot = self._current_configuration("notification_rules")
        template_snapshot = self._current_configuration("message_templates")
        if rule_snapshot is None or template_snapshot is None:
            return "notification_configuration_unavailable"
        rules = rule_snapshot[1].get("rules")
        rule = next(
            (
                item
                for item in rules
                if isinstance(item, dict)
                and item.get("id") == row.get("rule_id")
                and item.get("event_code") == original.event_code
                and item.get("enabled") is True
                and _predicates_match(item.get("predicates"), original.facts)
            ),
            None,
        ) if isinstance(rules, list) else None
        if rule is None:
            return "notification_source_not_currently_applicable"
        recipient = self._resolve_recipient(str(rule.get("recipient_selector")), original.facts)
        if recipient is None:
            return "recipient_unavailable"
        expected_recipient = (
            recipient.recipient_type.value,
            recipient.identity.value,
        )
        if expected_recipient not in {
            (
                str(row.get("recipient_type")),
                str(row.get("recipient_identity")),
            ),
            (
                str(row.get("task_recipient_type")),
                str(row.get("task_recipient_identity")),
            ),
        } or (
            str(row.get("recipient_type")),
            str(row.get("recipient_identity")),
        ) != (
            str(row.get("task_recipient_type")),
            str(row.get("task_recipient_identity")),
        ):
            return "recipient_binding_changed"
        if rule.get("template_id") != row.get("template_id"):
            return "notification_configuration_changed"
        try:
            render_message_template(
                template_snapshot[1],
                str(rule["template_id"]),
                _template_variables(original.facts),
            )
        except (KeyError, ValueError):
            return "template_or_schedule_invalid"
        return None

    def line006_recheck_targets_for_event_codes(
        self, event_codes: tuple[str, ...]
    ) -> tuple[LineNotificationFailureRecheckTarget, ...]:
        normalized = tuple(sorted(set(event_codes)))
        if not normalized:
            return ()
        placeholders = ",".join("%s" for _ in normalized)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _line006_recheck_targets_for_event_codes_sql(placeholders),
                normalized,
            )
            rows = tuple(cursor.fetchall() or ())
        return _line006_recheck_targets(rows)

    def _line006_replay_rows(
        self, original_source_ids: tuple[int, ...]
    ) -> tuple[dict[str, object], ...]:
        if not original_source_ids:
            return ()
        conditions = " OR ".join(
            "replay.source_event_identity LIKE %s" for _ in original_source_ids
        )
        patterns = tuple(f"manual-replay:{source_id}:%" for source_id in original_source_ids)
        with self._connection.cursor() as cursor:
            cursor.execute(_line006_replay_rows_sql(conditions), patterns)
            rows = tuple(cursor.fetchall() or ())
        return _strict_dict_rows(rows, "line006_replay_readback_invalid")

    def list_sources_without_decisions(
        self, *, limit: int = 100
    ) -> tuple[NotificationSourceEvent, ...]:
        """Return only configured source kinds whose committed event has no terminal decision."""
        if limit <= 0:
            raise ValueError("notification reconciliation limit is invalid")
        snapshot = self._current_configuration("notification_rules")
        if snapshot is None:
            return ()
        rules = snapshot[1].get("rules")
        event_codes = tuple(sorted({
            str(rule.get("event_code"))
            for rule in rules
            if isinstance(rule, dict) and isinstance(rule.get("event_code"), str)
        })) if isinstance(rules, list) else ()
        if not event_codes:
            return ()
        placeholders = ",".join("%s" for _ in event_codes)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _sources_without_decisions_sql(placeholders),
                (*event_codes, limit),
            )
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            _source_event_from_row(row)
            for row in rows
            if isinstance(row, dict)
        )

    def preview_manual_replay(self, source_event_id: int) -> dict[str, object]:
        source = self._source_event(source_event_id)
        if source is None:
            raise LookupError("notification source event not found")
        snapshot = self._current_configuration("notification_rules")
        rules = [] if snapshot is None else snapshot[1].get("rules", [])
        matching = sum(
            1 for rule in rules
            if isinstance(rule, dict) and rule.get("event_code") == source.event_code
        ) if isinstance(rules, list) else 0
        return {
            "source_event_id": source_event_id,
            "event_code": source.event_code,
            "historical_silent": source.historical_silent,
            "matching_rule_count": matching,
            "will_create_new_immutable_source": True,
        }

    def manual_replay_source(
        self, source_event_id: int, replay_identity: str, occurred_at: datetime
    ) -> int:
        source = self._source_event(source_event_id)
        if source is None:
            raise LookupError("notification source event not found")
        replay = NotificationSourceEvent(
            identity=replay_identity,
            event_code=source.event_code,
            historical_silent=False,
            facts=source.facts,
            source_domain="manual_replay",
            source_aggregate_type=source.source_aggregate_type,
            source_aggregate_identity=source.source_aggregate_identity,
            source_version=source.source_version,
            occurred_at=occurred_at,
        )
        existing_id = self._existing_source_event_id(replay)
        if existing_id is not None:
            return existing_id
        self._validate_manual_replay(source_event_id, source, occurred_at)
        return self.register_and_project(replay)

    def _existing_source_event_id(
        self, event: NotificationSourceEvent
    ) -> int | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _SOURCE_EVENT_EXISTING_SQL,
                (event.source_domain, event.event_code, event.identity),
            )
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        actual = (
            str(row["source_aggregate_type"]),
            str(row["source_aggregate_identity"]),
            int(row["source_version"]),
            bool(row["historical_silent"]),
            _canonical_json(_json_object(row["facts_snapshot"])),
        )
        expected = (
            event.source_aggregate_type,
            event.source_aggregate_identity,
            event.source_version,
            event.historical_silent,
            _canonical_json(event.facts),
        )
        if actual != expected:
            raise RuntimeError("line_notification_source_event_conflict")
        return int(row["id"])

    def _validate_manual_replay(
        self,
        source_event_id: int,
        source: NotificationSourceEvent,
        occurred_at: datetime,
    ) -> None:
        if source.source_domain == "manual_replay":
            raise LineNotificationManualReplayValidationError(
                "manual_replay_source_must_be_original"
            )
        if self._source_has_newer_version(source):
            raise LineNotificationManualReplayValidationError(
                "notification_source_not_currently_applicable"
            )
        rule_snapshot = self._current_configuration("notification_rules")
        template_snapshot = self._current_configuration("message_templates")
        if rule_snapshot is None or template_snapshot is None:
            raise LineNotificationManualReplayValidationError(
                "notification_configuration_unavailable"
            )
        rules = rule_snapshot[1].get("rules")
        templates = template_snapshot[1]
        matching = tuple(
            rule
            for rule in rules
            if isinstance(rule, dict)
            and rule.get("event_code") == source.event_code
            and rule.get("enabled") is True
            and _predicates_match(rule.get("predicates"), source.facts)
        ) if isinstance(rules, list) else ()
        if not matching:
            raise LineNotificationManualReplayValidationError(
                "notification_source_not_currently_applicable"
            )
        for rule in matching:
            selector = rule.get("recipient_selector")
            recipient = self._resolve_recipient(str(selector), source.facts)
            if recipient is None:
                raise LineNotificationManualReplayValidationError(
                    "recipient_unavailable"
                )
            try:
                render_message_template(
                    templates, str(rule["template_id"]), _template_variables(source.facts)
                )
                occurrences = schedule_notification_occurrences(
                    occurred_at=occurred_at,
                    schedule=_object(rule.get("schedule")),
                    frequency=_object(rule.get("frequency"), default={"kind": "once"}),
                )
            except (KeyError, ValueError) as error:
                raise LineNotificationManualReplayValidationError(
                    "template_or_schedule_invalid"
                ) from error
            if not occurrences:
                raise LineNotificationManualReplayValidationError(
                    "template_or_schedule_invalid"
                )

    def _source_has_newer_version(self, source: NotificationSourceEvent) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _SOURCE_HAS_NEWER_VERSION_SQL,
                (
                    source.source_domain,
                    source.event_code,
                    source.source_aggregate_type,
                    source.source_aggregate_identity,
                    source.source_version,
                ),
            )
            return cursor.fetchone() is not None

    def _source_event(self, source_event_id: int) -> NotificationSourceEvent | None:
        if source_event_id <= 0:
            raise ValueError("notification source event ID is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(_SOURCE_EVENT_BY_ID_SQL, (source_event_id,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        return _source_event_from_row(row)

    def register_source_event(self, event: NotificationSourceEvent) -> int:
        """Persist an immutable owner-event copy; exact replay returns its prior ID."""
        if event.occurred_at is None:
            raise ValueError("notification source event requires occurred_at")
        facts_json = _canonical_json(event.facts)
        with self._connection.cursor() as cursor:
            cursor.execute(
                _SOURCE_EVENT_INSERT_SQL,
                (
                    event.source_domain,
                    event.event_code,
                    event.identity,
                    event.source_aggregate_type,
                    event.source_aggregate_identity,
                    event.source_version,
                    event.historical_silent,
                    facts_json,
                    event.occurred_at,
                ),
            )
            if cursor.rowcount == 1:
                return int(cursor.lastrowid)
            cursor.execute(
                _SOURCE_EVENT_EXISTING_SQL,
                (event.source_domain, event.event_code, event.identity),
            )
            row = cursor.fetchone()
        if not isinstance(row, dict):
            raise RuntimeError("line_notification_source_event_duplicate_missing")
        actual = (
            str(row["source_aggregate_type"]),
            str(row["source_aggregate_identity"]),
            int(row["source_version"]),
            bool(row["historical_silent"]),
            _canonical_json(_json_object(row["facts_snapshot"])),
        )
        expected = (
            event.source_aggregate_type,
            event.source_aggregate_identity,
            event.source_version,
            event.historical_silent,
            facts_json,
        )
        if actual != expected:
            raise RuntimeError("line_notification_source_event_conflict")
        return int(row["id"])

    def register_and_project(self, event: NotificationSourceEvent) -> int:
        """Persist then atomically create only the tasks allowed by the active rule revision."""
        source_event_id = self.register_source_event(event)
        rule_snapshot = self._current_configuration("notification_rules")
        template_snapshot = self._current_configuration("message_templates")
        if rule_snapshot is None or template_snapshot is None:
            return source_event_id
        rule_revision_id, definition = rule_snapshot
        _, templates = template_snapshot
        rules = definition.get("rules")
        if not isinstance(rules, list):
            return source_event_id
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("event_code") != event.event_code:
                continue
            self._project_rule(
                source_event_id, event, rule_revision_id, rule, templates, template_snapshot[0]
            )
        return source_event_id

    def _project_rule(
        self,
        source_event_id: int,
        event: NotificationSourceEvent,
        rule_revision_id: int,
        rule: dict[str, object],
        templates: dict[str, object],
        template_revision_id: int,
    ) -> None:
        rule_id = rule.get("id")
        selector = rule.get("recipient_selector")
        if not isinstance(rule_id, str) or not isinstance(selector, str):
            return
        if event.historical_silent:
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "historical_source_silent", event)
            return
        if rule.get("enabled", False) is not True:
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "rule_shadow_mode", event)
            return
        if not _predicates_match(rule.get("predicates"), event.facts):
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "prerequisite_not_satisfied", event)
            return
        recipient = self._resolve_recipient(selector, event.facts)
        if recipient is None:
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, None, "suppressed", "recipient_unavailable", event)
            return
        try:
            rendered = render_message_template(
                templates, str(rule["template_id"]), _template_variables(event.facts)
            )
            occurrences = schedule_notification_occurrences(
                occurred_at=event.occurred_at,
                schedule=_object(rule.get("schedule")),
                frequency=_object(rule.get("frequency"), default={"kind": "once"}),
            )
        except (KeyError, ValueError):
            self._record_decision(source_event_id, rule_revision_id, rule_id, selector, recipient, "suppressed", "template_or_schedule_invalid", event)
            return
        decision_id = self._record_decision(
            source_event_id, rule_revision_id, rule_id, selector, recipient, "intent_created", "rule_matched", event
        )
        for occurrence in occurrences:
            self._create_intent_if_absent(
                decision_id, occurrence.number, occurrence.scheduled_at, template_revision_id,
                str(rule["template_id"]), rendered, recipient, event,
            )

    def _current_configuration(self, kind: str) -> tuple[int, dict[str, object]] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_CURRENT_CONFIGURATION_SQL, (kind,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            return None
        definition = _json_object(row["definition_snapshot"])
        return int(row["revision_id"]), definition

    def _resolve_recipient(self, selector: str, facts: Any):
        if selector != "case_group" or not isinstance(facts, dict):
            return None
        case_no = facts.get("case_no")
        if not isinstance(case_no, str) or not case_no:
            return None
        with self._connection.cursor() as cursor:
            cursor.execute(_ACTIVE_CASE_GROUP_SQL, (case_no,))
            row = cursor.fetchone()
        if not isinstance(row, dict) or not isinstance(row.get("group_id"), str):
            return None
        return LineRecipient(LineRecipientType.GROUP, LineGroupId(row["group_id"]))

    def _record_decision(self, source_event_id, revision_id, rule_id, selector, recipient, status, reason, event) -> int:
        recipient_type = None if recipient is None else recipient.recipient_type.value
        recipient_identity = "" if recipient is None else recipient.identity.value
        snapshot = _canonical_json({"event_code": event.event_code, "facts": event.facts, "reason_code": reason})
        with self._connection.cursor() as cursor:
            cursor.execute(_DECISION_INSERT_SQL, (source_event_id, revision_id, rule_id, selector, recipient_type, recipient_identity, status, reason, snapshot))
            return int(cursor.lastrowid)

    def _create_intent_if_absent(self, decision_id, occurrence_number, scheduled_at, template_revision_id, template_id, rendered, recipient, event) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_INTENT_INSERT_SQL, (decision_id, occurrence_number, template_revision_id, template_id, rendered.payload_json, rendered.payload_json, scheduled_at))
            if cursor.rowcount != 1:
                return
            intent_id = int(cursor.lastrowid)
        from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository

        delivery = MySqlLineDeliveryTaskRepository(self._connection).enqueue(
            LineDeliveryRequest(recipient, rendered.message_kind, rendered.payload_json, scheduled_at,
                IdempotencyKey(f"line-notification:{decision_id}:{occurrence_number}"),
                CorrelationId(f"line-notification:{event.identity}"), event.source_aggregate_type, event.source_aggregate_identity)
        )
        with self._connection.cursor() as cursor:
            cursor.execute(_INTENT_TASK_LINK_SQL, (delivery.task_id.value, intent_id))
            if cursor.rowcount != 1:
                raise RuntimeError("line_notification_intent_task_link_conflict")


_LOCK_RULE_INTENTS_SQL = (
    "SELECT intent.id AS intent_id,intent.delivery_task_id "
    "FROM line_notification_decisions AS decision "
    "JOIN line_notification_intents AS intent ON intent.decision_id=decision.id "
    "WHERE decision.rule_id=%s AND intent.intent_status='scheduled' "
    "ORDER BY intent.id FOR UPDATE"
)
_CANCEL_INTENTS_BY_ID_SQL = (
    "UPDATE line_notification_intents SET intent_status='cancelled',"
    "cancellation_reason=%s,cancelled_at_utc=UTC_TIMESTAMP(6) "
    "WHERE id IN ({placeholders}) AND intent_status='scheduled'"
)
_MARK_PROVIDER_ACCEPTED_SQL = (
    "UPDATE line_notification_intents SET intent_status='provider_accepted' "
    "WHERE delivery_task_id=%s AND intent_status='scheduled'"
)
_CANCEL_SERVICE_DAY_INTENTS_SQL = (
    "UPDATE line_notification_intents intent "
    "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
    "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
    "SET intent.intent_status='cancelled',intent.cancellation_reason='service_day_log_completed',"
    "intent.cancelled_at_utc=UTC_TIMESTAMP(6) "
    "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='scheduled' "
    "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED)=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.service_date'))=%s"
)
_CANCEL_SERVICE_DAY_TASKS_SQL = (
    "UPDATE line_delivery_tasks task "
    "JOIN line_notification_intents intent ON intent.delivery_task_id=task.id "
    "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
    "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
    "SET task.processing_status='cancelled',task.error_code='service_day_log_completed',"
    "task.error_message='service day log completed',task.lease_owner=NULL,"
    "task.lease_acquired_at_utc=NULL,task.lease_expires_at_utc=NULL "
    "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='cancelled' "
    "AND task.processing_status IN ('pending','retryable_failed','processing') "
    "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED)=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.service_date'))=%s"
)


def _cancel_service_day_assignment_intents_sql(placeholders: str) -> str:
    return (
        "UPDATE line_notification_intents intent "
        "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
        "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
        "SET intent.intent_status='cancelled',intent.cancellation_reason='assignment_replaced',"
        "intent.cancelled_at_utc=UTC_TIMESTAMP(6) "
        "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='scheduled' "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED) "
        f"IN ({placeholders})"
    )


def _cancel_service_day_assignment_tasks_sql(placeholders: str) -> str:
    return (
        "UPDATE line_delivery_tasks task "
        "JOIN line_notification_intents intent ON intent.delivery_task_id=task.id "
        "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
        "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
        "SET task.processing_status='cancelled',task.error_code='assignment_replaced',"
        "task.error_message='service assignment replaced',task.lease_owner=NULL,"
        "task.lease_acquired_at_utc=NULL,task.lease_expires_at_utc=NULL "
        "WHERE source.event_code='service_time_checkpoint' AND intent.intent_status='cancelled' "
        "AND task.processing_status IN ('pending','retryable_failed','processing') "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.assignment_id')) AS UNSIGNED) "
        f"IN ({placeholders})"
    )

_SOURCE_EVENT_INSERT_SQL = (
    "INSERT INTO line_notification_source_events (source_domain,event_code,"
    "source_event_identity,source_aggregate_type,source_aggregate_identity,"
    "source_version,historical_silent,facts_snapshot,occurred_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)"
)
_SOURCE_EVENT_EXISTING_SQL = (
    "SELECT id,source_aggregate_type,source_aggregate_identity,source_version,"
    "historical_silent,facts_snapshot FROM line_notification_source_events "
    "WHERE source_domain=%s AND event_code=%s AND source_event_identity=%s"
)
_SOURCE_EVENT_BY_ID_SQL = (
    "SELECT source_domain,event_code,source_event_identity,source_aggregate_type,"
    "source_aggregate_identity,source_version,historical_silent,facts_snapshot,occurred_at_utc "
    "FROM line_notification_source_events WHERE id=%s FOR UPDATE"
)
_CURRENT_CONFIGURATION_SQL = (
    "SELECT config_current.revision_id,revision.definition_snapshot "
    "FROM line_configuration_current config_current JOIN line_configuration_revisions revision "
    "ON revision.id=config_current.revision_id WHERE config_current.configuration_kind=%s"
)
_ACTIVE_CASE_GROUP_SQL = (
    "SELECT binding.group_id FROM line_order_group_bindings binding "
    "WHERE binding.case_no=%s AND binding.binding_status='active' AND binding.group_id IS NOT NULL "
    "AND EXISTS (SELECT 1 FROM line_order_group_participants customer "
    "WHERE customer.case_no=binding.case_no AND customer.participant_type='customer' AND customer.invitation_status='joined') "
    "AND EXISTS (SELECT 1 FROM line_order_group_participants staff "
    "WHERE staff.case_no=binding.case_no AND staff.participant_type='staff' AND staff.invitation_status='joined') "
    "FOR UPDATE"
)
_DECISION_INSERT_SQL = (
    "INSERT INTO line_notification_decisions (source_event_id,rule_revision_id,rule_id,recipient_selector,recipient_type,recipient_identity,decision_status,reason_code,decision_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)"
)
_INTENT_INSERT_SQL = (
    "INSERT IGNORE INTO line_notification_intents (decision_id,occurrence_number,template_revision_id,template_id,payload_snapshot,payload_fingerprint,scheduled_at_utc) "
    "VALUES (%s,%s,%s,%s,%s,SHA2(%s,256),%s)"
)
_INTENT_TASK_LINK_SQL = (
    "UPDATE line_notification_intents SET delivery_task_id=%s WHERE id=%s AND delivery_task_id IS NULL"
)
_CASE_TIMELINE_SQL = (
    "SELECT source.id AS source_event_id,source.event_code,source.occurred_at_utc,source.historical_silent,"
    "decision.rule_id,decision.decision_status,decision.reason_code,decision.recipient_type,decision.recipient_identity,"
    "intent.occurrence_number,intent.intent_status,intent.scheduled_at_utc,intent.delivery_task_id,task.processing_status "
    "FROM line_notification_source_events source "
    "LEFT JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
    "LEFT JOIN line_notification_intents intent ON intent.decision_id=decision.id "
    "LEFT JOIN line_delivery_tasks task ON task.id=intent.delivery_task_id "
    "WHERE JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no'))=%s "
    "ORDER BY source.occurred_at_utc DESC,source.id DESC,decision.id DESC,intent.occurrence_number ASC"
)
_NOTIFICATION_ANOMALY_SOURCES_SQL = (
    "SELECT decision.id AS decision_id,source.source_event_identity,"
    "JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no')) AS case_no,"
    "decision.reason_code,source.source_version "
    "FROM line_notification_decisions decision JOIN line_notification_source_events source "
    "ON source.id=decision.source_event_id "
    "WHERE decision.reason_code IN ('recipient_unavailable','template_or_schedule_invalid') "
    "ORDER BY decision.id LIMIT %s"
)

_LINE006_FAILED_SOURCES_SQL = (
    "SELECT source.id AS source_event_id,source.source_domain,source.event_code,"
    "source.source_event_identity,source.source_aggregate_type,"
    "source.source_aggregate_identity,source.source_version,source.facts_snapshot,"
    "decision.rule_id,decision.reason_code,"
    "NOT EXISTS (SELECT 1 FROM line_notification_source_events newer "
    "WHERE newer.source_domain=source.source_domain AND newer.event_code=source.event_code "
    "AND newer.source_aggregate_type=source.source_aggregate_type "
    "AND newer.source_aggregate_identity=source.source_aggregate_identity "
    "AND newer.source_domain<>'manual_replay' AND newer.source_version>source.source_version) "
    "AS is_latest_source_version "
    "FROM line_notification_source_events source "
    "JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
    "WHERE source.source_domain<>'manual_replay' "
    "AND JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no'))=%s "
    "AND decision.reason_code=%s ORDER BY source.id,decision.id"
)

_LINE006_RECHECK_TARGETS_FOR_SOURCE_SQL = (
    "SELECT DISTINCT JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no')) AS case_no,"
    "decision.reason_code FROM line_notification_source_events source "
    "JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
    "WHERE source.id=%s AND source.source_domain<>'manual_replay' "
    "AND decision.reason_code IN ('recipient_unavailable','template_or_schedule_invalid') "
    "ORDER BY case_no,decision.reason_code"
)

_LINE006_RECHECK_TARGETS_SQL = (
    "SELECT DISTINCT JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no')) AS case_no,"
    "decision.reason_code FROM line_notification_source_events source "
    "JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
    "WHERE source.source_domain<>'manual_replay' "
    "AND decision.reason_code IN ('recipient_unavailable','template_or_schedule_invalid') "
    "ORDER BY case_no,decision.reason_code LIMIT %s"
)

_LINE006_REPLAY_IDENTITY_FOR_TASK_SQL = (
    "SELECT source.source_event_identity FROM line_delivery_tasks task "
    "JOIN line_notification_intents intent ON intent.delivery_task_id=task.id "
    "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
    "JOIN line_notification_source_events source ON source.id=decision.source_event_id "
    "WHERE task.id=%s AND source.source_domain='manual_replay'"
)

_MANUAL_REPLAY_TASK_VALIDATION_SQL = (
    "SELECT replay.source_event_identity,replay.event_code,replay.source_aggregate_type,"
    "replay.source_aggregate_identity,replay.source_version,replay.facts_snapshot,"
    "decision.rule_id,decision.recipient_type,decision.recipient_identity,"
    "intent.template_id,task.recipient_type AS task_recipient_type,"
    "task.recipient_identity AS task_recipient_identity "
    "FROM line_delivery_tasks task "
    "JOIN line_notification_intents intent ON intent.delivery_task_id=task.id "
    "JOIN line_notification_decisions decision ON decision.id=intent.decision_id "
    "JOIN line_notification_source_events replay ON replay.id=decision.source_event_id "
    "WHERE task.id=%s AND replay.source_domain='manual_replay'"
)

_SOURCE_HAS_NEWER_VERSION_SQL = (
    "SELECT id FROM line_notification_source_events WHERE source_domain=%s AND event_code=%s "
    "AND source_aggregate_type=%s AND source_aggregate_identity=%s "
    "AND source_domain<>'manual_replay' AND source_version>%s LIMIT 1"
)


def _sources_without_decisions_sql(placeholders: str) -> str:
    return (
        "SELECT source.source_domain,source.event_code,source.source_event_identity,"
        "source.source_aggregate_type,source.source_aggregate_identity,source.source_version,"
        "source.historical_silent,source.facts_snapshot,source.occurred_at_utc "
        "FROM line_notification_source_events source "
        "LEFT JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
        f"WHERE source.event_code IN ({placeholders}) AND decision.id IS NULL "
        "ORDER BY source.id LIMIT %s"
    )


def _line006_replay_rows_sql(conditions: str) -> str:
    return (
        "SELECT replay.id AS replay_source_event_id,replay.source_event_identity,"
        "replay.event_code,replay.source_aggregate_type,replay.source_aggregate_identity,"
        "replay.source_version,replay.facts_snapshot,decision.id AS decision_id,"
        "decision.decision_status,decision.reason_code,intent.id AS intent_id,"
        "task.processing_status AS delivery_status,task.id AS delivery_task_id "
        "FROM line_notification_source_events replay "
        "LEFT JOIN line_notification_decisions decision ON decision.source_event_id=replay.id "
        "LEFT JOIN line_notification_intents intent ON intent.decision_id=decision.id "
        "LEFT JOIN line_delivery_tasks task ON task.id=intent.delivery_task_id "
        "WHERE replay.source_domain='manual_replay' AND (" + conditions + ") "
        "ORDER BY replay.id,decision.id,intent.id"
    )


def _line006_recheck_targets_for_event_codes_sql(placeholders: str) -> str:
    return (
        "SELECT DISTINCT JSON_UNQUOTE(JSON_EXTRACT(source.facts_snapshot,'$.case_no')) AS case_no,"
        "decision.reason_code FROM line_notification_source_events source "
        "JOIN line_notification_decisions decision ON decision.source_event_id=source.id "
        "WHERE source.source_domain<>'manual_replay' "
        f"AND source.event_code IN ({placeholders}) "
        "AND decision.reason_code IN ('recipient_unavailable','template_or_schedule_invalid') "
        "ORDER BY case_no,decision.reason_code"
    )


def _canonical_json(value: object) -> str:
    if not isinstance(value, dict):
        value = dict(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise RuntimeError("line_notification_source_event_facts_invalid")
    return parsed


def _source_event_from_row(row: dict[str, object]) -> NotificationSourceEvent:
    return NotificationSourceEvent(
        identity=str(row["source_event_identity"]),
        event_code=str(row["event_code"]),
        historical_silent=bool(row["historical_silent"]),
        facts=_json_object(row["facts_snapshot"]),
        source_domain=str(row["source_domain"]),
        source_aggregate_type=str(row["source_aggregate_type"]),
        source_aggregate_identity=str(row["source_aggregate_identity"]),
        source_version=int(row["source_version"]),
        occurred_at=aware_utc(row["occurred_at_utc"]),
    )


def _line006_replay_facts(
    original_source_id: int,
    original: dict[str, object],
    rows: tuple[dict[str, object], ...],
) -> tuple[LineNotificationReplaySuccessorFact, ...]:
    grouped: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        if _manual_replay_original_source_id(
            str(row.get("source_event_identity", ""))
        ) == original_source_id:
            grouped.setdefault(int(row["replay_source_event_id"]), []).append(row)
    result: list[LineNotificationReplaySuccessorFact] = []
    for replay_source_id, replay_rows in sorted(grouped.items()):
        first = replay_rows[0]
        exact_lineage = (
            first.get("event_code") == original.get("event_code")
            and first.get("source_aggregate_type") == original.get("source_aggregate_type")
            and first.get("source_aggregate_identity") == original.get("source_aggregate_identity")
            and int(first.get("source_version", -1)) == int(original.get("source_version", -2))
            and _canonical_json(_json_object(first["facts_snapshot"]))
            == _canonical_json(_json_object(original["facts_snapshot"]))
        )
        failed_validation = any(
            row.get("reason_code")
            in {"recipient_unavailable", "template_or_schedule_invalid"}
            for row in replay_rows
        )
        created_rows = tuple(
            row for row in replay_rows if row.get("decision_status") == "intent_created"
        )
        fresh_validation_valid: bool | None
        if failed_validation:
            fresh_validation_valid = False
        elif not created_rows:
            fresh_validation_valid = None
        else:
            fresh_validation_valid = all(
                row.get("intent_id") is not None
                and row.get("delivery_task_id") is not None
                for row in created_rows
            )
        statuses = tuple(
            sorted(
                str(row["delivery_status"])
                for row in created_rows
                if row.get("delivery_status") is not None
            )
        )
        result.append(
            LineNotificationReplaySuccessorFact(
                replay_source_id,
                exact_lineage,
                fresh_validation_valid,
                statuses,
            )
        )
    return tuple(result)


def _manual_replay_original_source_id(identity: str) -> int | None:
    prefix = "manual-replay:"
    if not identity.startswith(prefix):
        return None
    source_id, separator, idempotency_key = identity[len(prefix):].partition(":")
    if not separator or not idempotency_key or not source_id.isdigit():
        return None
    value = int(source_id)
    return value if value > 0 else None


def _line006_recheck_targets(
    rows: tuple[object, ...],
) -> tuple[LineNotificationFailureRecheckTarget, ...]:
    targets: set[LineNotificationFailureRecheckTarget] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_no"), str):
            raise RuntimeError("line006_recheck_target_readback_invalid")
        try:
            reason = LineNotificationFailureReason(str(row.get("reason_code")))
        except ValueError as error:
            raise RuntimeError("line006_recheck_target_readback_invalid") from error
        targets.add(LineNotificationFailureRecheckTarget(row["case_no"], reason))
    return tuple(
        sorted(targets, key=lambda item: (item.case_no, item.notification_reason.value))
    )


def _strict_dict_rows(
    rows: tuple[object, ...], error_code: str
) -> tuple[dict[str, object], ...]:
    if not all(isinstance(row, dict) for row in rows):
        raise RuntimeError(error_code)
    return tuple(rows)  # type: ignore[return-value]


def _object(value: object, *, default: dict[str, object] | None = None) -> dict[str, object]:
    if value is None and default is not None:
        return default
    if not isinstance(value, dict):
        raise ValueError("notification rule object is invalid")
    return value


def _predicates_match(predicates: object, facts: object) -> bool:
    if not isinstance(predicates, list) or not isinstance(facts, dict):
        return False
    checks = {
        "requires_cooking_true": facts.get("requires_cooking") is True,
        "baby_log_missing": facts.get("baby_log_completed") is False,
        "beclass_missing": facts.get("beclass_completed") is False,
    }
    return all(checks.get(item, False) for item in predicates)


def _template_variables(facts: object) -> dict[str, object]:
    if not isinstance(facts, dict):
        return {}
    service_date = facts.get("service_date")
    return {"service_date": service_date} if isinstance(service_date, str) else {}


def _timeline_row(row: dict[str, object]) -> dict[str, object]:
    recipient = row.get("recipient_identity")
    return {
        "source_event_id": int(row["source_event_id"]),
        "event_code": str(row["event_code"]),
        "occurred_at_utc": str(row["occurred_at_utc"]),
        "historical_silent": bool(row["historical_silent"]),
        "rule_id": row.get("rule_id"),
        "decision_status": row.get("decision_status"),
        "reason_code": row.get("reason_code"),
        "recipient_type": row.get("recipient_type"),
        "recipient_masked": _mask_recipient(recipient),
        "occurrence_number": row.get("occurrence_number"),
        "intent_status": row.get("intent_status"),
        "scheduled_at_utc": None if row.get("scheduled_at_utc") is None else str(row["scheduled_at_utc"]),
        "delivery_status": row.get("processing_status"),
        "delivery_task_id": row.get("delivery_task_id"),
    }


def _mask_recipient(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return "***" + value[-4:]


def _cancellation_row(row: object) -> tuple[int, int | None]:
    if not isinstance(row, dict) or frozenset(row) != {"intent_id", "delivery_task_id"}:
        raise RuntimeError("line_notification_intent_cancellation_lineage_invalid")
    intent_id = row["intent_id"]
    task_id = row["delivery_task_id"]
    if not isinstance(intent_id, int) or isinstance(intent_id, bool) or intent_id < 1:
        raise RuntimeError("line_notification_intent_cancellation_lineage_invalid")
    if task_id is not None and (
        not isinstance(task_id, int) or isinstance(task_id, bool) or task_id < 1
    ):
        raise RuntimeError("line_notification_intent_cancellation_lineage_invalid")
    return intent_id, task_id

__all__ = [
    "LineNotificationManualReplayValidationError",
    "MySqlLineNotificationRepository",
]
