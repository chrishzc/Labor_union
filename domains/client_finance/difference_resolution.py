"""Client Finance noncash dispositions and amount corrections; no bank writes."""
from dataclasses import dataclass
from enum import StrEnum


class ClientDifferenceConflict(ValueError):
    pass


class ClientDifferenceAction(StrEnum):
    LOSS = 'loss'
    REDUCE = 'reduce_service_fee'
    FEE = 'union_bank_fee'
    ABSORB = 'absorb_overpayment'
    CLOSE_REFUND = 'close_refund'
    MANUAL = 'manual_amount'
    AUTO = 'adopt_calculation'


@dataclass(frozen=True)
class ClientDifferenceTarget:
    identity: str
    kind: str
    direction: str
    expected_ntd: int
    actual_ntd: int
    remaining_ntd: int
    noncash_ntd: int = 0


def client_difference_options(target: ClientDifferenceTarget) -> tuple[str, ...]:
    options = [ClientDifferenceAction.MANUAL.value, ClientDifferenceAction.AUTO.value]
    if target.remaining_ntd <= 0:
        return tuple(options)
    if target.kind in ('over_refund_recovery','over_refund_correction'):
        options += ['loss', 'absorb_overpayment']
    elif target.direction == 'receivable_from_client':
        options += ['loss']
        if target.kind in ('deposit', 'first', 'second', 'adjustment'):
            options += ['reduce_service_fee', 'union_bank_fee']
    elif target.kind in ('refund', 'subsidy_return'):
        options += ['close_refund']
    return tuple(options)


def require_client_disposition(target: ClientDifferenceTarget, action: str, amount: int, reason: str) -> int:
    if action not in client_difference_options(target) or action in ('manual_amount', 'adopt_calculation'):
        raise ClientDifferenceConflict('client_difference_action_not_allowed')
    if not isinstance(amount, int) or isinstance(amount, bool) or not 0 < amount <= target.remaining_ntd:
        raise ClientDifferenceConflict('client_difference_amount_invalid')
    if action == 'close_refund':
        if amount != target.remaining_ntd:
            raise ClientDifferenceConflict('client_refund_close_requires_remaining')
    elif not reason.strip():
        raise ClientDifferenceConflict('client_difference_reason_required')
    return target.remaining_ntd - amount


@dataclass(frozen=True)
class ClientAmountChange:
    effective_ntd: int
    remaining_ntd: int
    separate_direction: str | None
    separate_amount_ntd: int


def plan_client_amount_change(target: ClientDifferenceTarget, effective_ntd: int, *, frozen: bool) -> ClientAmountChange:
    if not isinstance(effective_ntd, int) or isinstance(effective_ntd, bool) or effective_ntd < 0:
        raise ClientDifferenceConflict('client_amount_invalid')
    # A previously settled source is evidence. Corrections become independent debts.
    if frozen:
        delta = effective_ntd - target.expected_ntd
        direction = target.direction if delta > 0 else (
            'payable_to_client' if target.direction == 'receivable_from_client' else 'receivable_from_client')
        return ClientAmountChange(effective_ntd, target.remaining_ntd, direction if delta else None, abs(delta))
    available = effective_ntd - target.actual_ntd - target.noncash_ntd
    opposite = 'payable_to_client' if target.direction == 'receivable_from_client' else 'receivable_from_client'
    return ClientAmountChange(effective_ntd, max(0, available), opposite if available < 0 else None, max(0, -available))


CLIENT_DIFFERENCE_LABELS = {
    'loss': '已作損失處理', 'reduce_service_fee': '已減收結清',
    'union_bank_fee': '工會已負擔手續費', 'absorb_overpayment': '工會已承擔超付款',
    'close_refund': '已確認不用再退款',
}
