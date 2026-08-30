"""Production assembly for BeClass import review Query, Preview, and Apply."""

from __future__ import annotations

from dataclasses import dataclass
from subsystems.case_import.beclass_import_review_workflow import (
    BeClassImportReviewWorkflow,
)


@dataclass(frozen=True)
class BeClassImportReviewApplication:
    workflow: BeClassImportReviewWorkflow

    def query(self, review_identity, correlation_id):
        return self.workflow.query(review_identity, correlation_id)

    def preview(self, intent, correlation_id):
        return self.workflow.preview(intent, correlation_id)

    def apply(self, command):
        return self.workflow.apply(command)


__all__ = [
    "BeClassImportReviewApplication",
]
