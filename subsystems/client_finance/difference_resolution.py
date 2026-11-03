"""One Client Finance transaction per human-confirmed difference command."""
from dataclasses import dataclass
from typing import Protocol
from domains.client_finance.difference_resolution import ClientDifferenceConflict


@dataclass(frozen=True)
class ClientDifferenceCommand:
    case_no: str
    identity: str
    action: str
    amount_ntd: int | None
    reason: str
    expected_version: int
    key: str
    actor: str


@dataclass(frozen=True)
class ClientDifferenceItem:
    identity: str
    label: str
    kind: str
    direction: str
    expected_ntd: int
    actual_ntd: int
    remaining_ntd: int
    noncash_ntd: int
    mode: str
    computed_ntd: int
    effective_ntd: int
    status: str
    options: tuple[str, ...]
    service_reduction_ntd: int = 0
    effective_charge_ntd: int | None = None


@dataclass(frozen=True)
class ClientDifferenceEvent:
    identity: str
    target_identity: str
    action: str
    amount_ntd: int
    reason: str
    actor: str
    confirmed_on: str
    before_ntd: int | None = None
    after_ntd: int | None = None
    computed_ntd: int | None = None


@dataclass(frozen=True)
class ClientDifferenceView:
    case_no: str
    version: int
    items: tuple[ClientDifferenceItem, ...]
    events: tuple[ClientDifferenceEvent, ...]


class ClientDifferencePort(Protocol):
    def query(self, case_no: str): ...
    def replay(self, command: ClientDifferenceCommand): ...
    def apply(self, command: ClientDifferenceCommand): ...


class ClientDifferenceApplication:
    def __init__(self, repository: ClientDifferencePort, unit_of_work):
        self.repository, self.unit_of_work = repository, unit_of_work

    def query(self, case_no):
        return self.repository.query(case_no)

    def apply(self, command: ClientDifferenceCommand):
        if not command.key.strip() or not command.actor.strip():
            raise ClientDifferenceConflict('client_difference_command_invalid')
        with self.unit_of_work() as work:
            previous = self.repository.replay(command)
            if previous is not None:
                work.commit()
                return previous
            result = self.repository.apply(command)
            work.commit()
            return result
