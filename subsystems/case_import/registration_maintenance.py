"""Bounded registration maintenance shared by the internal ASGI host and CLI."""
import time


class RegistrationMaintenanceRunner:
    def __init__(self, staging, review, aof, *, monotonic=time.monotonic, after_recovery=None):
        self.staging, self.review, self.aof = staging, review, aof
        self._monotonic = monotonic
        self._next_rewrite = 0.0
        self._after_recovery = after_recovery or (lambda: None)

    def tick(self):
        failures = 0
        # SQL recovery availability must never prevent expiry or AOF cleanup.
        try:
            self.staging.expire_due(limit=200)
        except Exception:
            failures += 1
        try:
            result = self.review.recover(limit=100)
            failures += result.failed
            if result.recovered:
                self._after_recovery()
        except Exception:
            failures += 1
        if self._monotonic() >= self._next_rewrite:
            self._next_rewrite = self._monotonic() + 3600
            try:
                self.aof.run_once()
            except Exception:
                failures += 1
        return failures == 0
