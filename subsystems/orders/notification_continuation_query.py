"""Orders-owned eligibility for continuing an imported historical case."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class OrderNotificationContinuationFacts:
    historical: bool = False
    formally_arranged: bool = False
    continuation_day: date | None = None

    @property
    def eligible(self) -> bool:
        return not self.historical or self.formally_arranged

    def allows_automatic_payment(self, due_date: date | None) -> bool:
        if not self.eligible:
            return False
        if not self.historical:
            return True
        return bool(self.continuation_day is not None and due_date is not None
                    and due_date >= self.continuation_day)
