"""Pure candidate ranking for the Scheduling matching recommendation query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class RecommendationFilters:
    region: bool = True
    schedule: bool = True
    babies: bool = True
    time: bool = True


@dataclass(frozen=True, slots=True)
class RecommendationRequest:
    service_dates: tuple[date, ...]
    district: str
    requires_twins: bool
    service_time: str
    filters: RecommendationFilters


@dataclass(frozen=True, slots=True)
class StaffCandidate:
    staff_id: int
    name: str
    phone: str | None
    line_user_id: str | None
    regions: tuple[str, ...]
    maximum_babies: int
    time_slots: tuple[str, ...]
    occupied_dates: frozenset[date]


@dataclass(frozen=True, slots=True)
class StaffRecommendation:
    staff_id: int
    name: str
    phone: str | None
    line_user_id: str | None
    score: int
    reasons: tuple[str, ...]
    reject_reasons: tuple[str, ...]

    def as_legacy_payload(self) -> dict[str, object]:
        status = "🟢 100% 匹配" if self.score >= 90 else "🟡 部分匹配"
        reasons = " | ".join(self.reasons)
        warnings = f" (警示: {', '.join(self.reject_reasons)})" if self.reject_reasons else ""
        return {"staff_id": self.staff_id, "name": self.name, "phone": self.phone, "line_user_id": self.line_user_id, "score": self.score, "display_label": f"{self.name} ({self.phone or ''}) - {status} [{reasons}]{warnings}", "is_perfect": self.score >= 90, "reasons": list(self.reasons), "reject_reasons": list(self.reject_reasons)}


def recommend_staff(request: RecommendationRequest, candidates: tuple[StaffCandidate, ...]) -> tuple[StaffRecommendation, ...]:
    return tuple(sorted((item for candidate in candidates if (item := _recommend(request, candidate)) is not None), key=lambda item: (-item.score, item.staff_id)))


def _recommend(request: RecommendationRequest, candidate: StaffCandidate) -> StaffRecommendation | None:
    region_ok = not request.district or not candidate.regions or any(request.district in region or region in request.district for region in candidate.regions)
    schedule_ok = not bool(set(request.service_dates) & candidate.occupied_dates)
    babies_ok = not request.requires_twins or candidate.maximum_babies >= 2
    time_ok = not request.service_time or request.service_time in candidate.time_slots
    if (request.filters.region and not region_ok) or (request.filters.schedule and not schedule_ok) or (request.filters.babies and not babies_ok) or (request.filters.time and not time_ok):
        return None
    reasons = tuple(label for ok, label in ((region_ok, "符合區域"), (schedule_ok, "檔期無衝突"), (babies_ok, "胎數符合"), (time_ok, "時段符合")) if ok)
    rejected = tuple(label for ok, label in ((region_ok, "區域不符"), (schedule_ok, "檔期衝突"), (babies_ok, "不承接雙胞胎"), (time_ok, "時段不符")) if not ok)
    return StaffRecommendation(candidate.staff_id, candidate.name, candidate.phone, candidate.line_user_id, 100 - 40 * (not region_ok) - 50 * (not schedule_ok) - 30 * (not babies_ok) - 30 * (not time_ok), reasons, rejected)
