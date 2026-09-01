"""驗證取消流程對已生效取消狀態維持 typed fail-closed。"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.errors import ErrorCategory
from subsystems.orders.cancellation_workflow import (
    CancellationWorkflowError,
    OrderCancellationWorkflow,
)


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.preview_loads = 0

    def load_for_preview(self, case_no, requested_staff_ids):
        self.preview_loads += 1
        return self.facts


def _facts(*, status=OrderLifecycleStatus.CANCELLED, cancellation_effective=True):
    return SimpleNamespace(
        lifecycle=SimpleNamespace(
            current_status=status,
            cancellation_effective=cancellation_effective,
        )
    )


@pytest.mark.parametrize(
    "facts",
    (
        _facts(),
        _facts(status=OrderLifecycleStatus.IN_SERVICE, cancellation_effective=True),
    ),
)
def test_preview_rejects_an_already_effective_cancellation_without_rebuilding_candidate(
    facts,
):
    repository = _Repository(facts)
    workflow = OrderCancellationWorkflow(
        repository,
        lambda: pytest.fail("preview must not open a write unit of work"),
        FixedBusinessClock(datetime(2026, 9, 1, 12, tzinfo=TAIPEI_TIME_ZONE)),
    )

    with pytest.raises(CancellationWorkflowError) as error:
        workflow.preview("OPS96-CANCEL-B-20260901", ())

    assert error.value.error.category is ErrorCategory.CONFLICT
    assert error.value.error.code == "order_version_conflict"
    assert repository.preview_loads == 1
