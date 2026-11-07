"""One application-owned transaction for the existing manual supplement command."""
from collections.abc import Callable
from typing import Protocol

from shared_kernel.ports import UnitOfWork
from subsystems.finance_import.accounting_workspace import CaseAccounting
from subsystems.finance_import.case_manual_supplement import ManualSupplementResult


class CaseManualSupplementCommandPort(Protocol):
    def execute(self, case_no: str, bank: str, direction: str, target_item: str, amount_ntd: int,
                transaction_date: str, reason: str | None, idempotency_key: str, actor: str,
                allow_overage_disposition: bool = False) -> ManualSupplementResult: ...


class CaseManualSupplementApplication:
    def __init__(self, commands: CaseManualSupplementCommandPort, query: Callable[[str], CaseAccounting],
                 unit_of_work_factory: Callable[[], UnitOfWork]):
        self._commands = commands
        self._query = query
        self._unit_of_work_factory = unit_of_work_factory

    def execute(self, *, case_no: str, bank: str, direction: str, target_item: str, amount_ntd: int,
                transaction_date: str, reason: str | None, idempotency_key: str, actor: str,
                allow_overage_disposition: bool = False, readback: Callable[[CaseAccounting], object]):
        with self._unit_of_work_factory() as work:
            self._commands.execute(case_no=case_no, bank=bank, direction=direction, target_item=target_item,
                amount_ntd=amount_ntd, transaction_date=transaction_date, reason=reason,
                idempotency_key=idempotency_key, actor=actor, allow_overage_disposition=allow_overage_disposition)
            # The fixed transport callback constructs its strict view here.
            # Writer/query/schema failure therefore exits the original UoW
            # without committing, including unexpected exceptions.
            response = readback(self._query(case_no))
            work.commit()
            return response
