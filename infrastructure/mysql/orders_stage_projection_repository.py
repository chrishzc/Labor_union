"""
File: orders_stage_projection_repository.py
Description: 以單一 bounded SQL 讀取 Orders 七階段所需跨 owner 根事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from subsystems.orders.stage_projection_query import MAXIMUM_PAGE_SIZE


_PAGE_SQL = """
SELECT o.case_no,
       o.lifecycle_version AS order_version,
       o.updated_at AS order_updated_at,
       import_fact.import_receipt_id,
       import_fact.import_created_at,
       terms_fact.terms_event_id,
       terms_fact.terms_version,
       terms_fact.terms_created_at,
       plan.id AS matching_plan_id,
       plan.version AS matching_plan_version,
       plan.status AS matching_plan_status,
       plan.created_at AS matching_created_at,
       GREATEST(COALESCE(willingness.willingness_count, 0), COALESCE(communication.contact_attempt_count, 0), COALESCE(response_fact.replied_count, 0)) AS willingness_contact_attempt_count,
       GREATEST(COALESCE(willingness.willingness_count, 0), COALESCE(communication.contact_sent_count, 0), COALESCE(response_fact.replied_count, 0)) AS willingness_count,
       GREATEST(COALESCE(willingness.willingness_replied_count, 0), COALESCE(response_fact.replied_count, 0)) AS willingness_replied_count,
       GREATEST(COALESCE(willingness.willingness_accepted_count, 0), COALESCE(response_fact.willing_count, 0)) AS willingness_accepted_count,
       COALESCE(GREATEST(willingness.willingness_contacted_at, communication.contact_sent_at), willingness.willingness_contacted_at, communication.contact_sent_at) AS willingness_contacted_at,
       COALESCE(GREATEST(willingness.willingness_replied_at, response_fact.replied_at), willingness.willingness_replied_at, response_fact.replied_at) AS willingness_replied_at,
       GREATEST(COALESCE(willingness.resume_sent_count, 0), COALESCE(communication.resume_attempt_count, 0)) AS resume_attempt_count,
       GREATEST(COALESCE(willingness.resume_sent_count, 0), COALESCE(communication.resume_sent_count, 0)) AS resume_sent_count,
       COALESCE(GREATEST(willingness.resume_sent_at, communication.resume_sent_at), willingness.resume_sent_at, communication.resume_sent_at) AS resume_sent_at,
       COALESCE(segment_fact.matching_segment_count, 0) AS matching_segment_count,
       COALESCE(signing.staff_contract_sent_count, 0) AS staff_contract_sent_count,
       signing.staff_contract_sent_at,
       COALESCE(signing.staff_contract_signed_count, 0) AS staff_contract_signed_count,
       signing.staff_contract_signed_at,
       COALESCE(signing.client_contract_sent_count, 0) AS client_contract_sent_count,
       signing.client_contract_sent_at,
       COALESCE(signing.client_contract_signed_count, 0) AS client_contract_signed_count,
       signing.client_contract_signed_at,
       contract_fact.contract_event_id,
       contract_fact.contract_created_at,
       finance.aggregate_version AS finance_version,
       COALESCE(deposit_fact.deposit_obligation_count, 0) AS deposit_obligation_count,
       COALESCE(deposit_fact.deposit_open_count, 0) AS deposit_open_count,
       deposit_fact.deposit_updated_at,
       confirmed.id AS confirmed_version_id,
       confirmed.version AS confirmed_version,
       confirmed.confirmed_at_utc AS confirmed_at,
       scheduling.aggregate_version AS scheduling_version,
       COALESCE(assignments.assignment_count, 0) AS assignment_count,
       COALESCE(assignments.assignment_active_count, 0) AS assignment_active_count,
       COALESCE(assignments.assignment_completed_count, 0) AS assignment_completed_count,
       assignments.assignment_updated_at,
       assignments.assignment_first_service_date,
       assignments.assignment_last_service_date,
       TIME_TO_SEC(o.service_start_time) AS service_start_seconds,
       TIME_TO_SEC(o.service_end_time) AS service_end_seconds,
       o.service_end_day_offset,
       service_lock.client_settlement_fingerprint AS service_completion_identity,
       service_lock.created_at AS service_completed_at,
       COALESCE(client_fact.client_obligation_count, 0) AS client_obligation_count,
       COALESCE(client_fact.client_open_count, 0) AS client_open_count,
       client_fact.client_updated_at,
       COALESCE(staff_fact.staff_obligation_count, 0) AS staff_obligation_count,
       COALESCE(staff_fact.staff_open_count, 0) AS staff_open_count,
       staff_fact.staff_updated_at
  FROM orders o FORCE INDEX (PRIMARY)
  LEFT JOIN (
       SELECT case_no, MAX(id) AS import_receipt_id, MAX(created_at) AS import_created_at
         FROM case_import_receipts GROUP BY case_no
  ) import_fact ON import_fact.case_no = o.case_no
  LEFT JOIN (
       SELECT case_no, MAX(id) AS terms_event_id, MAX(resulting_order_version) AS terms_version,
              MAX(created_at) AS terms_created_at
         FROM order_terms_change_events GROUP BY case_no
  ) terms_fact ON terms_fact.case_no = o.case_no
  LEFT JOIN caregiver_matching_plans plan
    ON plan.case_no = o.case_no AND plan.is_active = 1
  LEFT JOIN (
       SELECT case_no, COUNT(*) AS willingness_count,
              SUM(replied_at IS NOT NULL) AS willingness_replied_count,
              SUM(caregiver_accepted = 1) AS willingness_accepted_count,
              MAX(sent_at) AS willingness_contacted_at,
              MAX(replied_at) AS willingness_replied_at,
              SUM(sent_resume_at IS NOT NULL) AS resume_sent_count,
              MAX(sent_resume_at) AS resume_sent_at
         FROM matching_records GROUP BY case_no
  ) willingness ON willingness.case_no = o.case_no
  LEFT JOIN (
       SELECT intent.plan_id,
              COUNT(DISTINCT CASE WHEN intent.notification_kind IN ('caregiver_info_1','caregiver_info_2')
                                        AND intent.projection_status <> 'cancelled'
                                   THEN intent.segment_id END) AS contact_attempt_count,
              COUNT(DISTINCT CASE WHEN intent.notification_kind IN ('caregiver_info_1','caregiver_info_2')
                                        AND delivery.processing_status = 'sent'
                                   THEN intent.segment_id END) AS contact_sent_count,
              MAX(CASE WHEN intent.notification_kind IN ('caregiver_info_1','caregiver_info_2')
                        AND delivery.processing_status = 'sent' THEN delivery.sent_at_utc END) AS contact_sent_at,
              MAX(CASE WHEN intent.notification_kind = 'customer_profiles'
                        AND intent.projection_status <> 'cancelled' THEN 1 ELSE 0 END) AS resume_attempt_count,
              MAX(CASE WHEN intent.notification_kind = 'customer_profiles'
                        AND delivery.processing_status = 'sent' THEN 1 ELSE 0 END) AS resume_sent_count,
              MAX(CASE WHEN intent.notification_kind = 'customer_profiles'
                        AND delivery.processing_status = 'sent' THEN delivery.sent_at_utc END) AS resume_sent_at
         FROM matching_notification_intents intent
         LEFT JOIN line_delivery_tasks delivery ON delivery.id = intent.delivery_task_id
        GROUP BY intent.plan_id
  ) communication ON communication.plan_id = plan.id
  LEFT JOIN (
       SELECT response.plan_id,
              COUNT(DISTINCT response.segment_id) AS replied_count,
              COUNT(DISTINCT CASE WHEN response.response_value = 'willing' THEN response.segment_id END) AS willing_count,
              MAX(response.occurred_at_utc) AS replied_at
         FROM matching_response_events response
        WHERE response.response_type = 'caregiver_willingness'
          AND NOT EXISTS (
              SELECT 1 FROM matching_response_events newer
               WHERE newer.plan_id = response.plan_id
                 AND newer.segment_id = response.segment_id
                 AND newer.response_type = response.response_type
                 AND (newer.occurred_at_utc > response.occurred_at_utc
                      OR (newer.occurred_at_utc = response.occurred_at_utc AND newer.id > response.id))
          )
        GROUP BY response.plan_id
  ) response_fact ON response_fact.plan_id = plan.id
  LEFT JOIN (
       SELECT plan_id, COUNT(*) AS matching_segment_count
         FROM caregiver_matching_plan_segments GROUP BY plan_id
  ) segment_fact ON segment_fact.plan_id = plan.id
  LEFT JOIN (
       SELECT event.matching_plan_id,
              COUNT(DISTINCT CASE WHEN document.document_scope = 'staff_segment'
                                   AND event.event_type = 'sent'
                                  THEN event.matching_segment_id END) AS staff_contract_sent_count,
              MAX(CASE WHEN document.document_scope = 'staff_segment'
                        AND event.event_type = 'sent' THEN event.occurred_at END) AS staff_contract_sent_at,
              COUNT(DISTINCT CASE WHEN document.document_scope = 'staff_segment'
                                   AND event.event_type = 'signed_received'
                                  THEN event.matching_segment_id END) AS staff_contract_signed_count,
              MAX(CASE WHEN document.document_scope = 'staff_segment'
                        AND event.event_type = 'signed_received' THEN event.occurred_at END) AS staff_contract_signed_at,
              MAX(CASE WHEN document.document_scope = 'client_contract'
                        AND event.event_type = 'sent' THEN 1 ELSE 0 END) AS client_contract_sent_count,
              MAX(CASE WHEN document.document_scope = 'client_contract'
                        AND event.event_type = 'sent' THEN event.occurred_at END) AS client_contract_sent_at,
              MAX(CASE WHEN document.document_scope = 'client_contract'
                        AND event.event_type = 'signed_received' THEN 1 ELSE 0 END) AS client_contract_signed_count,
              MAX(CASE WHEN document.document_scope = 'client_contract'
                        AND event.event_type = 'signed_received' THEN event.occurred_at END) AS client_contract_signed_at
         FROM contract_signing_events event
         JOIN contract_document_versions document ON document.id = event.document_version_id
        GROUP BY event.matching_plan_id
  ) signing ON signing.matching_plan_id = plan.id
  LEFT JOIN (
       SELECT case_no, MAX(id) AS contract_event_id, MAX(created_at) AS contract_created_at
         FROM order_contract_flow_events GROUP BY case_no
  ) contract_fact ON contract_fact.case_no = o.case_no
  LEFT JOIN client_finance_accounts finance ON finance.case_no = o.case_no
  LEFT JOIN (
       SELECT case_no,
              SUM(status IN ('open','settled')) AS deposit_obligation_count,
              SUM(status = 'open') AS deposit_open_count,
              MAX(updated_at) AS deposit_updated_at
         FROM client_obligations
        WHERE obligation_type = 'deposit' AND direction = 'receivable_from_client'
        GROUP BY case_no
  ) deposit_fact ON deposit_fact.case_no = o.case_no
  LEFT JOIN confirmed_service_date_versions confirmed
    ON confirmed.case_no = o.case_no AND confirmed.is_current = 1
  LEFT JOIN scheduling_aggregates scheduling ON scheduling.case_no = o.case_no
  LEFT JOIN (
       SELECT assignment.case_no,
              COUNT(DISTINCT CASE WHEN assignment.status NOT IN ('cancelled','replaced') THEN assignment.id END) AS assignment_count,
              COUNT(DISTINCT CASE WHEN assignment.status = 'active' THEN assignment.id END) AS assignment_active_count,
              COUNT(DISTINCT CASE WHEN assignment.status = 'completed' THEN assignment.id END) AS assignment_completed_count,
              MAX(assignment.updated_at) AS assignment_updated_at,
              MIN(CASE WHEN assignment.status NOT IN ('cancelled','replaced') THEN schedule.work_date END) AS assignment_first_service_date,
              MAX(CASE WHEN assignment.status NOT IN ('cancelled','replaced') THEN schedule.work_date END) AS assignment_last_service_date
         FROM case_staff_assignments assignment
         LEFT JOIN staff_schedule schedule
           ON schedule.assignment_id = assignment.id
          AND schedule.effective_marker = 1
          AND schedule.is_work_day = 1
        GROUP BY assignment.case_no
  ) assignments ON assignments.case_no = o.case_no
  LEFT JOIN order_service_data_locks service_lock ON service_lock.case_no = o.case_no
  LEFT JOIN (
       SELECT case_no,
              SUM(status IN ('open','settled')) AS client_obligation_count,
              SUM(status = 'open') AS client_open_count,
              MAX(updated_at) AS client_updated_at
         FROM client_obligations GROUP BY case_no
  ) client_fact ON client_fact.case_no = o.case_no
  LEFT JOIN (
       SELECT case_no,
              SUM(status IN ('open','settled')) AS staff_obligation_count,
              SUM(status = 'open') AS staff_open_count,
              MAX(updated_at) AS staff_updated_at
         FROM staff_obligations GROUP BY case_no
  ) staff_fact ON staff_fact.case_no = o.case_no
 WHERE o.case_no > %s
 ORDER BY o.case_no
 LIMIT %s
"""


class MySqlOrdersStageProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_page(self, *, after_case_no: str | None, page_size: int) -> tuple[Mapping[str, object], ...]:
        cursor_identity = _cursor(after_case_no)
        result_limit = _limit(page_size)
        with self._connection.cursor() as cursor:
            cursor.execute(_PAGE_SQL, (cursor_identity, result_limit))
            return tuple(cursor.fetchall() or ())


def _cursor(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 50:
        raise ValueError("after_case_no must be a canonical case identity")
    return value


def _limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAXIMUM_PAGE_SIZE:
        raise ValueError("page_size is outside the bounded query policy")
    return value + 1


__all__ = ["MySqlOrdersStageProjectionRepository"]
