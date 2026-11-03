"""Explicit noncash recovery processing, borrowing no external payment effects."""
from dataclasses import dataclass


@dataclass(frozen=True)
class StaffRecoveryDispositionCommand:
    case_no: str
    identity: str
    action: str
    amount_ntd: int
    reason: str
    expected_version: int
    key: str
    actor: str


@dataclass(frozen=True)
class StaffRecoveryDispositionItem:
    identity: str
    staff_id: int
    party: str
    original_ntd: int
    remaining_ntd: int
    noncash_ntd: int
    version: int
    status: str
    related_cases: tuple[str,...]


@dataclass(frozen=True)
class StaffRecoveryDispositionEvent:
    identity: str
    target_identity: str
    action: str
    amount_ntd: int
    reason: str
    actor: str
    confirmed_on: str


@dataclass(frozen=True)
class StaffRecoveryDispositionView:
    case_no: str
    items: tuple[StaffRecoveryDispositionItem,...]
    events: tuple[StaffRecoveryDispositionEvent,...]


class StaffRecoveryDispositionApplication:
    def __init__(self,repository,unit_of_work):
        self.repository,self.unit_of_work=repository,unit_of_work

    def query(self,case_no):
        return self.repository.query(case_no)

    def apply(self,command):
        with self.unit_of_work() as work:
            result=self.repository.replay(command)
            if result is None:
                result=self.repository.apply(command)
            work.commit()
            return result
