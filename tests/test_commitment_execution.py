from datetime import date

import pytest

from domains.scheduling.commitment_execution import (
    CommitmentExecutionMismatch,
    CommitmentServiceDay,
    ExecutionServiceDay,
    require_exact_commitment_execution,
)


def test_exact_commitment_execution_requires_the_same_plan_staff_and_dates():
    service_date = date(2026, 8, 1)

    require_exact_commitment_execution(
        7,
        (7,),
        (CommitmentServiceDay(3, service_date),),
        (ExecutionServiceDay(3, service_date),),
    )


@pytest.mark.parametrize(
    ("lock_plan_ids", "execution_days"),
    [
        ((8,), (ExecutionServiceDay(3, date(2026, 8, 1)),)),
        ((7,), (ExecutionServiceDay(4, date(2026, 8, 1)),)),
        ((7,), (ExecutionServiceDay(3, date(2026, 8, 2)),)),
    ],
)
def test_exact_commitment_execution_rejects_any_mapping_difference(
    lock_plan_ids,
    execution_days,
):
    with pytest.raises(CommitmentExecutionMismatch):
        require_exact_commitment_execution(
            7,
            lock_plan_ids,
            (CommitmentServiceDay(3, date(2026, 8, 1)),),
            execution_days,
        )
