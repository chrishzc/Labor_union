"""Framework-neutral ports for matching communication persistence and projection."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from domains.scheduling.matching_communication import MatchingPlanReference
from shared_kernel.identities import IdempotencyKey
from shared_kernel.ports import UnitOfWork
from subsystems.scheduling.matching_notification_contracts import (
    MatchingNotificationAudience,
    MatchingNotificationResult,
    MatchingResponseResult,
    RecordCaregiverLineResponseCommand,
    RecordCustomerLineDecisionCommand,
    RecordManualMatchingResponseCommand,
    RequestCaregiverInformationCommand,
    RequestCustomerProfilesCommand,
)


class MatchingNotificationRepositoryPort(Protocol):
    def request_caregiver_information(
        self,
        command: RequestCaregiverInformationCommand,
    ) -> MatchingNotificationResult: ...

    def request_customer_profiles(
        self,
        command: RequestCustomerProfilesCommand,
    ) -> MatchingNotificationResult: ...

    def record_caregiver_line_response(
        self,
        command: RecordCaregiverLineResponseCommand,
    ) -> MatchingResponseResult: ...

    def record_customer_line_decision(
        self,
        command: RecordCustomerLineDecisionCommand,
    ) -> MatchingResponseResult: ...

    def record_manual_response(
        self,
        command: RecordManualMatchingResponseCommand,
    ) -> MatchingResponseResult: ...

    def next_projection_due_at(self) -> datetime | None: ...


class MatchingAudienceQueryPort(Protocol):
    def caregiver_for_segment(
        self,
        plan: MatchingPlanReference,
        segment_id: int,
    ) -> MatchingNotificationAudience | None: ...

    def customer_for_plan(
        self,
        plan: MatchingPlanReference,
    ) -> MatchingNotificationAudience | None: ...


class MatchingNotificationReceiptPort(Protocol):
    def result_for(self, key: IdempotencyKey) -> MatchingNotificationResult | None: ...


class MatchingNotificationUnitOfWorkPort(UnitOfWork, Protocol):
    matching_notifications: MatchingNotificationRepositoryPort
    matching_audiences: MatchingAudienceQueryPort
    matching_receipts: MatchingNotificationReceiptPort


__all__ = [
    "MatchingAudienceQueryPort",
    "MatchingNotificationReceiptPort",
    "MatchingNotificationRepositoryPort",
    "MatchingNotificationUnitOfWorkPort",
]
