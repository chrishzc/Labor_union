from datetime import datetime

import pytest

from infrastructure.mysql.background_job_repository import JobIdempotencyConflict
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.orders.auto_completion_job_dispatch import (
    AutoCompletionJobDispatcher,
    DueOrderAutoCompletion,
)


class DueOrderReader:
    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def find_due_orders(self, evaluation_at, after_case_no, limit):
        self.calls.append((evaluation_at, after_case_no, limit))
        return self._pages.get(after_case_no, ())


class CommandEnqueuer:
    def __init__(self, duplicate_case_numbers=()):
        self._duplicate_case_numbers = set(duplicate_case_numbers)
        self.commands = []

    def enqueue_command(self, command):
        case_no = command.payload["case_no"]
        if case_no in self._duplicate_case_numbers:
            raise JobIdempotencyConflict("existing-" + case_no)
        self.commands.append(command)
        return command.job_id


def _due(case_no, version=0):
    return DueOrderAutoCompletion(
        case_no,
        version,
        datetime(2026, 8, 4, 17, tzinfo=TAIPEI_TIME_ZONE),
    )


def test_dispatcher_pages_due_orders_and_uses_the_due_instant_as_command_time():
    reader = DueOrderReader({None: (_due("CASE-A", 2), _due("CASE-B", 3)), "CASE-B": ()})
    enqueuer = CommandEnqueuer()

    receipt = AutoCompletionJobDispatcher(reader, enqueuer).dispatch_due_orders(
        datetime(2026, 8, 4, 21, tzinfo=TAIPEI_TIME_ZONE),
        page_size=2,
    )

    assert receipt.scanned_count == 2
    assert receipt.enqueued_count == 2
    assert receipt.duplicate_count == 0
    assert [command.payload["evaluation_at"] for command in enqueuer.commands] == [
        "2026-08-04T17:00:00+08:00",
        "2026-08-04T17:00:00+08:00",
    ]
    assert [command.command_identity for command in enqueuer.commands] == [
        "orders-auto-completion:CASE-A:v2:20260804T170000+0800",
        "orders-auto-completion:CASE-B:v3:20260804T170000+0800",
    ]
    assert reader.calls[1][1] == "CASE-B"


def test_dispatcher_records_an_existing_durable_command_as_a_duplicate_not_success():
    reader = DueOrderReader({None: (_due("CASE-A"),), "CASE-A": ()})
    enqueuer = CommandEnqueuer(("CASE-A",))

    receipt = AutoCompletionJobDispatcher(reader, enqueuer).dispatch_due_orders(
        datetime(2026, 8, 4, 17, tzinfo=TAIPEI_TIME_ZONE),
    )

    assert receipt.scanned_count == 1
    assert receipt.enqueued_count == 0
    assert receipt.duplicate_count == 1
    assert enqueuer.commands == []


def test_dispatcher_rejects_a_non_advancing_or_unsorted_reader_page():
    reader = DueOrderReader({None: (_due("CASE-B"), _due("CASE-A"))})

    with pytest.raises(ValueError, match="sorted unique"):
        AutoCompletionJobDispatcher(reader, CommandEnqueuer()).dispatch_due_orders(
            datetime(2026, 8, 4, 17, tzinfo=TAIPEI_TIME_ZONE),
        )


@pytest.mark.parametrize("page_size", [0, 201])
def test_dispatcher_bounds_discovery_pages(page_size):
    with pytest.raises(ValueError, match="page_size"):
        AutoCompletionJobDispatcher(DueOrderReader({}), CommandEnqueuer()).dispatch_due_orders(
            datetime(2026, 8, 4, 17, tzinfo=TAIPEI_TIME_ZONE),
            page_size=page_size,
        )
