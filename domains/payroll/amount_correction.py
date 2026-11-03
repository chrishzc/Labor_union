"""Payroll amount mode decisions, independent of bank/payout persistence."""
from dataclasses import dataclass


class PayrollAmountConflict(ValueError):
    pass


@dataclass(frozen=True)
class PayrollAmountDecision:
    mode: str
    effective_ntd: int
    delta_ntd: int


def payroll_amount_decision(mode: str, effective: int, computed: int, action: str, requested: int | None) -> PayrollAmountDecision:
    if action=='manual_amount':
        after=requested
        next_mode='manual'
    elif action=='adopt_calculation':
        after=computed
        next_mode='automatic'
    elif action=='source_update':
        after=effective if mode=='manual' else computed
        next_mode=mode
    else:
        raise PayrollAmountConflict('payroll_amount_action_invalid')
    if not isinstance(after,int) or isinstance(after,bool) or after<0:
        raise PayrollAmountConflict('payroll_amount_invalid')
    return PayrollAmountDecision(next_mode,after,after-effective)
