"""MySQL persistence for current-plan national-holiday work agreements."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from domains.scheduling.holiday_work_agreement import (
    HolidayWorkAgreementDraft,
    HolidayWorkDecision,
)
from domains.scheduling.matching_communication import MatchingCommunicationConflictError
from infrastructure.mysql.line_repository_support import database_utc
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey


class MySqlMatchingHolidayWorkAgreementRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_current_plan(self, case_no: str, plan_id: int, *, lock: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_PLAN_SQL + suffix, (case_no, plan_id))
            row = cursor.fetchone()
            if not isinstance(row, Mapping):
                return None
            cursor.execute(_SEGMENTS_SQL, (plan_id,))
            segments = tuple(dict(item) for item in (cursor.fetchall() or ()))
        return {"plan": dict(row), "segments": segments}

    def is_holiday(self, holiday_date: date) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(_HOLIDAY_SQL, (holiday_date,))
            return isinstance(cursor.fetchone(), Mapping)

    def find_by_idempotency(
        self,
        key: IdempotencyKey,
        fingerprint: PreviewFingerprint,
    ) -> Mapping[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_BY_KEY_SQL, (key.value,))
            row = cursor.fetchone()
            if not isinstance(row, Mapping):
                return None
            if str(row["preview_fingerprint"]) != fingerprint.value:
                raise MatchingCommunicationConflictError(
                    "holiday-work agreement idempotency key has a different payload"
                )
            cursor.execute(_PARTICIPANTS_SQL, (int(row["id"]),))
            participants = tuple(dict(item) for item in (cursor.fetchall() or ()))
        return {"agreement": dict(row), "participants": participants, "replayed": True}

    def append(
        self,
        draft: HolidayWorkAgreementDraft,
        *,
        idempotency_key: IdempotencyKey,
        fingerprint: PreviewFingerprint,
        occurred_at: datetime,
    ) -> Mapping[str, Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _INSERT_AGREEMENT_SQL,
                (
                    draft.plan_id,
                    draft.holiday_date,
                    draft.plan_version,
                    draft.status.value,
                    draft.actor_id,
                    draft.reason,
                    idempotency_key.value,
                    fingerprint.value,
                    database_utc(occurred_at),
                ),
            )
            agreement_id = int(cursor.lastrowid)
            rows = []
            for item in draft.participant_decisions:
                participant_key = "customer" if item.participant_role == "customer" else f"segment:{item.segment_id}"
                rows.append((
                    agreement_id,
                    item.participant_role,
                    item.segment_id,
                    participant_key,
                    item.decision.value,
                    database_utc(occurred_at),
                ))
            cursor.executemany(_INSERT_PARTICIPANT_SQL, rows)
        return {
            "agreement": {
                "id": agreement_id,
                "plan_id": draft.plan_id,
                "holiday_date": draft.holiday_date,
                "plan_version": draft.plan_version,
                "agreement_status": draft.status.value,
                "actor_id": draft.actor_id,
                "reason": draft.reason,
                "idempotency_key": idempotency_key.value,
                "preview_fingerprint": fingerprint.value,
                "created_at_utc": database_utc(occurred_at),
            },
            "participants": tuple({
                "participant_role": item.participant_role,
                "segment_id": item.segment_id,
                "decision": item.decision.value,
            } for item in draft.participant_decisions),
            "replayed": False,
        }

    def current_accepted_holiday_dates(
        self,
        case_no: str,
        start_date: date,
        end_date: date,
    ) -> tuple[date, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CURRENT_ACCEPTED_DATES_SQL, (case_no, start_date, end_date))
            rows = cursor.fetchall() or ()
        return tuple(row["holiday_date"] for row in rows if isinstance(row, Mapping))


_PLAN_SQL = """SELECT id,case_no,version,status,is_active,start_date,end_date
FROM caregiver_matching_plans WHERE case_no=%s AND id=%s"""
_SEGMENTS_SQL = """SELECT id,staff_id FROM caregiver_matching_plan_segments
WHERE plan_id=%s ORDER BY segment_order,id"""
_HOLIDAY_SQL = "SELECT holiday_date FROM holidays WHERE holiday_date=%s"
_BY_KEY_SQL = "SELECT * FROM matching_holiday_work_agreements WHERE idempotency_key=%s"
_PARTICIPANTS_SQL = """SELECT participant_role,segment_id,decision
FROM matching_holiday_work_agreement_participants WHERE agreement_id=%s
ORDER BY participant_role,segment_id,id"""
_INSERT_AGREEMENT_SQL = """INSERT INTO matching_holiday_work_agreements
(plan_id,holiday_date,plan_version,agreement_status,actor_id,reason,
 idempotency_key,preview_fingerprint,created_at_utc)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
_INSERT_PARTICIPANT_SQL = """INSERT INTO matching_holiday_work_agreement_participants
(agreement_id,participant_role,segment_id,participant_key,decision,created_at_utc)
VALUES (%s,%s,%s,%s,%s,%s)"""
_CURRENT_ACCEPTED_DATES_SQL = """SELECT DISTINCT agreement.holiday_date
FROM matching_holiday_work_agreements agreement
JOIN caregiver_matching_plans plan ON plan.id=agreement.plan_id
JOIN holidays holiday ON holiday.holiday_date=agreement.holiday_date
WHERE plan.case_no=%s
  AND plan.is_active=1
  AND plan.status IN ('proposed', 'accepted')
  AND agreement.plan_version=plan.version
  AND agreement.agreement_status='accepted'
  AND agreement.id = (
      SELECT MAX(latest.id)
      FROM matching_holiday_work_agreements latest
      WHERE latest.plan_id=agreement.plan_id
        AND latest.holiday_date=agreement.holiday_date
        AND latest.plan_version=agreement.plan_version
  )
  AND agreement.holiday_date BETWEEN %s AND %s
  AND EXISTS (
      SELECT 1 FROM matching_holiday_work_agreement_participants customer
      WHERE customer.agreement_id=agreement.id
        AND customer.participant_role='customer'
        AND customer.segment_id IS NULL
        AND customer.decision='accepted'
  )
  AND NOT EXISTS (
      SELECT 1 FROM caregiver_matching_plan_segments segment
      WHERE segment.plan_id=plan.id
        AND NOT EXISTS (
            SELECT 1 FROM matching_holiday_work_agreement_participants caregiver
            WHERE caregiver.agreement_id=agreement.id
              AND caregiver.participant_role='caregiver'
              AND caregiver.segment_id=segment.id
              AND caregiver.decision='accepted'
        )
  )
  AND NOT EXISTS (
      SELECT 1 FROM matching_holiday_work_agreement_participants extra
      LEFT JOIN caregiver_matching_plan_segments segment
        ON segment.id=extra.segment_id AND segment.plan_id=plan.id
      WHERE extra.agreement_id=agreement.id
        AND extra.participant_role='caregiver'
        AND segment.id IS NULL
  )
ORDER BY agreement.holiday_date"""


__all__ = ["MySqlMatchingHolidayWorkAgreementRepository"]
