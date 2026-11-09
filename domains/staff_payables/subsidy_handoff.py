"""HANDOFF-01..06: subsidy purpose never creates or rewrites a financial obligation."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SubsidyHandoffFacts:
    manual_scheme: str | None
    historical_scheme: str
    historical_conflict: bool
    order_status: str
    total_ntd: int | None
    subsidy_ntd: int | None
    customer_amount_ntd: int | None
    customer_paid_ntd: int | None
    staff_paid_ntd: int | None
    staff_subsidy_paid_ntd: int | None
    customer_subsidy_paid_ntd: int | None
    government_received_ntd: int | None
    has_customer_subsidy_payable: bool
    full_subsidy_order: bool = False
    funding_conflict: bool = False


@dataclass(frozen=True, slots=True)
class SubsidyPayableHandoff:
    scheme: str
    manual: bool
    service_completed: bool
    subsidy_ntd: int | None
    full_subsidy: bool
    requires_manual_plan: bool = False
    staff_subsidy_reason: str | None = None
    client_subsidy_reason: str | None = None


def decide_subsidy_handoff(facts: SubsidyHandoffFacts) -> SubsidyPayableHandoff:
    manual = facts.manual_scheme in {'split', 'advance', 'direct'}
    historical = facts.order_status.startswith('歷史')
    completed = facts.order_status in {'訂單完成', '訂單取消', '歷史訂單－服務完成', '歷史訂單－帳務完成'}
    automatic_full = not manual and not historical and facts.full_subsidy_order
    scheme = facts.manual_scheme if manual else facts.historical_scheme if historical else 'split' if automatic_full else 'unknown'
    full = facts.full_subsidy_order or (facts.customer_amount_ntd == 0 and facts.total_ntd is not None and facts.total_ntd == facts.subsidy_ntd)
    staff_reason = client_reason = None
    if not manual and not automatic_full:
        if not historical:
            staff_reason = client_reason = '補助退款方案尚未人工保存，請先確認補助歸屬。'
        elif facts.historical_conflict:
            staff_reason = client_reason = '歷史補助方案或金額來源互相衝突，請由原帳務流程核對。'
    elif automatic_full and facts.historical_conflict:
        staff_reason = client_reason = '正式補助方案或金額來源互相衝突，請由原帳務流程核對。'
    elif not completed:
        staff_reason = client_reason = '服務尚未正式結束，補助款尚未交接應付流程。'
    elif facts.total_ntd is None or facts.subsidy_ntd is None or (automatic_full and facts.total_ntd <= 0):
        staff_reason = client_reason = '案件總額或正式補助金額來源待確認。'
    elif not 0 <= facts.subsidy_ntd <= facts.total_ntd:
        staff_reason = client_reason = '正式補助金額與案件總額矛盾，請由原帳務流程核對。'
    elif facts.funding_conflict:
        staff_reason = client_reason = '正式客戶計價與月嫂應收來源互相矛盾，請由原帳務流程核對。'
    elif facts.full_subsidy_order and (facts.customer_amount_ntd != 0 or (facts.customer_paid_ntd or 0) > 0 or facts.subsidy_ntd != facts.total_ntd):
        staff_reason = client_reason = '免自備正式來源與既有客戶款項矛盾，保留原證據並待確認。'
    elif full and scheme != 'split':
        staff_reason = client_reason = '免自備正式款項與人工補助歸屬矛盾，保留原金額並待確認。'
    elif scheme == 'split':
        if (facts.staff_subsidy_paid_ntd or 0) > facts.subsidy_ntd:
            staff_reason = '已轉交月嫂的補助超出本案正式補助，請由原帳務流程核對。'
        elif facts.has_customer_subsidy_payable or (facts.customer_subsidy_paid_ntd or 0) > 0:
            staff_reason = '補助轉交月嫂與既有客戶補助退款矛盾，保留原款項並待確認。'
        elif facts.customer_amount_ntd != facts.total_ntd - facts.subsidy_ntd or (facts.customer_paid_ntd is not None and facts.customer_paid_ntd > facts.total_ntd - facts.subsidy_ntd):
            staff_reason = '客戶期款或實收款金額與分別入款安排不符，請由原帳務流程核對。'
        elif facts.staff_paid_ntd is not None and facts.staff_paid_ntd >= facts.total_ntd:
            staff_reason = '月嫂已收足案件總額，不再另付補助款；請核對原應付餘額。'
    elif scheme == 'advance':
        if full or facts.customer_amount_ntd != facts.total_ntd or facts.customer_paid_ntd is None or facts.customer_paid_ntd < facts.total_ntd:
            client_reason = '客戶實際墊款依據不足，保留既有款項並待確認。'
        elif (facts.staff_subsidy_paid_ntd or 0) > 0:
            client_reason = '補助已有轉交月嫂紀錄，與退客戶安排矛盾；請由原帳務流程核對。'
    elif scheme == 'direct' and (facts.customer_amount_ntd != facts.total_ntd or (facts.customer_paid_ntd is not None and facts.customer_paid_ntd < facts.total_ntd)):
        client_reason = '政府直付安排與客戶原期款或實收金額不符，請由原帳務流程核對。'
    elif scheme == 'direct' and any((amount or 0) > 0 for amount in (
        facts.government_received_ntd, facts.staff_subsidy_paid_ntd, facts.customer_subsidy_paid_ntd)):
        client_reason = '政府直付安排與工會已經手的補助金流矛盾，請核對原始依據。'
    if scheme in {'split', 'direct'}:
        client_reason = client_reason or '既有客戶補助退款與案件方案的受款對象不符，請由原帳務流程更正。'
    elif scheme not in {'advance'} and not (historical and not manual and not facts.historical_conflict):
        client_reason = client_reason or '補助退款方案與對象待核對；既有款項保留。'
    return SubsidyPayableHandoff(scheme, manual, completed, facts.subsidy_ntd, full, manual or (not historical and not automatic_full), staff_reason, client_reason)


def subsidy_refund_amount_reason(subsidy_ntd: int | None, remaining_ntd: int, refunded_ntd: int) -> str | None:
    if subsidy_ntd is not None and remaining_ntd > 0 and remaining_ntd + refunded_ntd > subsidy_ntd:
        return '正式客戶補助退款金額超出本案補助，請由原帳務流程核對。'
    return None
