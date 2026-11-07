"""Query and atomic reconciliation of a selected whole period."""
from dataclasses import dataclass, asdict
from datetime import date
import hashlib
import re
from typing import Protocol, TypedDict, Callable, Literal
from shared_kernel.fingerprints import fingerprint_payload

from domains.government_subsidy.period_reconciliation import (
    PeriodReconciliationConflict, SubsidyPeriod, SubsidyPeriodLine, require_exact_period_receipt, GovernmentPeriodBalance,
    require_government_initial_receipt,
)


@dataclass(frozen=True, slots=True)
class PeriodCoverage:
    receipt_id: int
    period: SubsidyPeriod
    amount_ntd: int
    recovered_advance_ntd: int
    settled: bool = True
    source_label: Literal['人工補登'] | None = None


@dataclass(frozen=True, slots=True)
class SubsidyPeriodView:
    period: SubsidyPeriod
    version: int
    lines: tuple[SubsidyPeriodLine, ...]
    total_ntd: int | None
    coverage: tuple[PeriodCoverage, ...]
    blocked_cases: tuple[str, ...]
    recorded_lines: tuple[SubsidyPeriodLine, ...]
    changed_cases: tuple[str, ...]
    can_reconcile: bool
    balances: tuple[GovernmentPeriodBalance,...] = ()
    amount_controls: tuple['GovernmentAmountItem',...] = ()
    operations: tuple['GovernmentPeriodOperation',...] = ()
    amount_changes: tuple['GovernmentAmountChange',...] = ()


@dataclass(frozen=True)
class GovernmentAmountChange:
    case_no: str
    action: str
    before_ntd: int
    after_ntd: int
    computed_ntd: int
    reason: str
    actor: str
    confirmed_on: str


@dataclass(frozen=True)
class GovernmentAmountItem:
    case_no: str
    mode: str
    computed_ntd: int | None
    effective_ntd: int | None


@dataclass(frozen=True)
class GovernmentPeriodOperation:
    identity: int
    balance_identity: str
    action: str
    amount_ntd: int
    bank_row_id: int | None
    reason: str
    actor: str
    confirmed_on: str


@dataclass(frozen=True)
class GovernmentDifferenceCommand:
    period: SubsidyPeriod
    action: str
    identity: str
    amount_ntd: int | None
    bank_row_id: int | None
    handling: str
    reason: str
    expected_version: int
    key: str
    actor: str


@dataclass(frozen=True)
class ManualInitialPeriodReceipt:
    period: SubsidyPeriod
    amount_ntd: int
    paid_on: date
    handling: str
    reason: str
    expected_version: int
    key: str
    actor: str

    def __post_init__(self):
        if (not isinstance(self.period, SubsidyPeriod) or type(self.period.year) is not int or type(self.period.index) is not int
            or type(self.amount_ntd) is not int or self.amount_ntd <= 0
            or type(self.paid_on) is not date or type(self.expected_version) is not int or self.expected_version < 0
            or self.handling not in {'exact', 'partial', 'refund_excess'}
            or not isinstance(self.reason, str) or self.reason != self.reason.strip() or len(self.reason) > 500
            or not isinstance(self.key, str) or re.fullmatch(r'[a-z0-9][a-z0-9._:-]{0,190}', self.key) is None
            or not isinstance(self.actor, str) or re.fullmatch(r'admin:[1-9][0-9]*', self.actor) is None):
            raise ValueError('subsidy_period_manual_initial_invalid')

    @property
    def payload(self):
        return {'kind': 'government_period_initial_manual_receipt', **asdict(self),
                'paid_on': self.paid_on.isoformat()}

    @property
    def digest(self):
        return fingerprint_payload(self.payload).value

    @property
    def owner_key(self):
        # The original period entry key is bounded to 100 chars; the original
        # command/key and actor remain in the manual source and command receipt.
        return 'government-manual:' + hashlib.sha256(self.key.encode()).hexdigest()


@dataclass(frozen=True)
class ManualInitialPeriodSource:
    row_id: int
    command: ManualInitialPeriodReceipt

    def __post_init__(self):
        if type(self.row_id) is not int or self.row_id <= 0 or not isinstance(self.command, ManualInitialPeriodReceipt):
            raise ValueError('subsidy_period_manual_source_invalid')


@dataclass(frozen=True)
class ManualInitialReceiptProof:
    receipt_id: int
    period: SubsidyPeriod
    amount_ntd: int
    paid_on: date
    source_label: Literal['人工補登']
    key: str


class PeriodBankRow(TypedDict):
    id: int
    paid_on: date | None
    amount_ntd: int


class CasePeriodReceipt(TypedDict):
    receipt_id: int
    label: str
    amount_ntd: int
    recorded_case_amount_ntd: int
    recorded_service_end_date: date
    recovered_advance_ntd: int
    settled: bool
    source_label: str | None


class CasePeriodCoverage(TypedDict):
    case_no: str
    service_end_date: date | None
    amount_ntd: int | None
    coverage: tuple[CasePeriodReceipt, ...]


class PeriodRepository(Protocol):
    def query(self, period: SubsidyPeriod, *, lock: bool = False) -> SubsidyPeriodView: ...
    def find_replay(self, key: str, command: tuple) -> int | None: ...
    def bank_amount(self, bank_row_id: int, *, reversal: bool = False) -> int: ...
    def save(self, view: SubsidyPeriodView, bank_row_id: int, key: str, actor: str) -> int: ...
    def reverse(self, receipt_id: int, bank_row_id: int, key: str, actor: str) -> int: ...
    def bank_rows(self) -> tuple[PeriodBankRow, ...]: ...
    def case_coverage(self, case_no: str) -> CasePeriodCoverage: ...
    def find_manual_initial_replay(self, command: ManualInitialPeriodReceipt) -> int | None: ...
    def append_manual_initial_source(self, command: ManualInitialPeriodReceipt) -> ManualInitialPeriodSource: ...
    def save_manual_initial(self, view: SubsidyPeriodView, source: ManualInitialPeriodSource) -> int: ...
    def save_manual_initial_receipt(self, command: ManualInitialPeriodReceipt, source: ManualInitialPeriodSource, entry_id: int) -> None: ...
    def read_manual_initial_receipt(self, command: ManualInitialPeriodReceipt, entry_id: int) -> ManualInitialReceiptProof: ...


class PeriodReconciliationApplication:
    def __init__(self, repository: PeriodRepository, unit_of_work):
        self.repository = repository
        self.unit_of_work = unit_of_work

    def query(self, period: SubsidyPeriod) -> SubsidyPeriodView:
        return self.repository.query(period)

    def bank_rows(self) -> tuple[PeriodBankRow, ...]:
        return self.repository.bank_rows()

    def case_coverage(self, case_no: str) -> CasePeriodCoverage:
        return self.repository.case_coverage(case_no)

    def reconcile(self, period: SubsidyPeriod, bank_row_id: int, version: int, key: str, actor: str) -> int:
        with self.unit_of_work() as work:
            replay = self.repository.find_replay(key, (period.unit, period.year, period.index, bank_row_id, None))
            if replay is not None:
                work.commit()
                return replay
            current = self.repository.query(period, lock=True)
            if current.version != version:
                raise PeriodReconciliationConflict('subsidy_period_stale')
            if current.coverage:
                raise PeriodReconciliationConflict('subsidy_period_already_covered')
            if current.blocked_cases:
                raise PeriodReconciliationConflict('subsidy_case_already_covered')
            require_exact_period_receipt(current.lines, self.repository.bank_amount(bank_row_id))
            identity = self.repository.save(current, bank_row_id, key, actor)
            work.commit()
            return identity

    def reverse(self, receipt_id: int, bank_row_id: int, key: str, actor: str) -> int:
        with self.unit_of_work() as work:
            result = self.repository.reverse(receipt_id, bank_row_id, key, actor)
            work.commit()
            return result

    def difference(self,command: GovernmentDifferenceCommand):
        with self.unit_of_work() as work:
            result=self.repository.apply_difference(command)
            work.commit()
            return result

    def manual_initial(self, command: ManualInitialPeriodReceipt, *, readback: Callable[[ManualInitialReceiptProof, SubsidyPeriodView], object]):
        """Only the first actual receipt; later cash stays on the bank workflow."""
        with self.unit_of_work() as work:
            identity = self.repository.find_manual_initial_replay(command)
            replayed = identity is not None
            if identity is None:
                current = self.repository.query(command.period, lock=True)
                if current.version != command.expected_version:
                    raise PeriodReconciliationConflict('subsidy_period_stale')
                if current.coverage or current.balances:
                    raise PeriodReconciliationConflict('subsidy_period_already_covered')
                if current.blocked_cases:
                    raise PeriodReconciliationConflict('subsidy_case_already_covered')
                require_government_initial_receipt(current.lines, command.amount_ntd, command.handling)
                source = self.repository.append_manual_initial_source(command)
                identity = self.repository.save_manual_initial(current, source)
                self.repository.save_manual_initial_receipt(command, source, identity)
            # The transport builds its strict typed response before commit.
            view = self.repository.query(command.period)
            original = tuple(item for item in view.coverage if item.receipt_id == identity)
            if (view.period != command.period or (not replayed and len(original) != 1)
                or len(original) > 1 or any(item.period != command.period or item.amount_ntd != command.amount_ntd
                    or item.source_label != '人工補登' for item in original)):
                raise PeriodReconciliationConflict('subsidy_period_manual_readback_invalid')
            # An original receipt remains replayable after an authorized bank
            # reversal removes it from active coverage. find_replay verified
            # that immutable source/entry; current coverage is not rewritten.
            receipt = self.repository.read_manual_initial_receipt(command, identity)
            if (not isinstance(receipt, ManualInitialReceiptProof) or receipt.receipt_id != identity
                or receipt.period != command.period or receipt.amount_ntd != command.amount_ntd
                or receipt.paid_on != command.paid_on or receipt.key != command.key or receipt.source_label != '人工補登'):
                raise PeriodReconciliationConflict('subsidy_period_manual_readback_invalid')
            response = readback(receipt, view)
            work.commit()
            return response
