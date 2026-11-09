"""
File: test_finance_import_owning_domain_composite.py
Description: 驗證 Finance Import 借用 Domain context 與人工更正 dispatch。
"""

import pytest

from domains.finance_import.correction import (
    ClientRefundCorrectionPreview,
    CorrectionAllocation,
    CorrectionTargetObligation,
    FinanceImportCorrectionCandidate,
    FinanceImportCorrectionFacts,
    FinanceImportCorrectionSelection,
    FinanceOwningDomain,
    build_finance_import_correction_candidate,
)
from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from infrastructure.mysql.finance_import_owning_domain_composite import (
    MySqlFinanceImportOwningDomainComposite,
    _client_selection,
    _resolve_client_receipt,
    _resolve_client_refund,
    _resolve_staff_payout,
    _request_reason,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.correction_workflow import (
    FinanceImportCorrectionApplyRequest,
)
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalReprocessApplyRequest,
)


class _VirtualAccountCursor:
    def __init__(self, responses, staff_names=()):
        self._responses = iter(responses)
        self._staff_names = staff_names
        self._current = None
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=()):
        self.executions.append((statement, parameters))
        if statement.startswith('SELECT format_id,currency FROM finance_import_rows'):
            self._current = self._staff_source
            return
        if statement.startswith('SELECT id,format_id,memo FROM finance_import_rows'):
            self._current = self._staff_source
            return
        if statement.startswith('SELECT id,name FROM staff WHERE'):
            self._current = self._staff_names
            return
        self._current = next(self._responses)
        if statement.startswith('SELECT format_id,direction,memo,transaction_date FROM finance_import_rows'):
            self._staff_source = self._current

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current


class _VirtualAccountConnection:
    def __init__(self, responses, staff_names=()):
        self.cursor_instance = _VirtualAccountCursor(responses, staff_names)

    def cursor(self):
        return self.cursor_instance


@pytest.mark.parametrize('split,total,missing', [(False, 18000, False), (True, 30000, False), (True, 30000, True)])
def test_65_fee_auto_matching_uses_bank_funding_portion_before_owner_preview(monkeypatch, split, total, missing):
    from unittest.mock import Mock
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    import infrastructure.mysql.staff_payout_repository as payout
    from domains.staff_payables.reconciliation import OutgoingBankFact, StaffPayableFacts, StaffPrimaryBankAccount
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationFacts
    from subsystems.staff_payables.case_accounting_query import StaffFundingPortion
    from datetime import date
    row = dict(obligation_identity='obligation:fee65', due_date='2026-10-15', amount_due_ntd=total,
        has_installments=split and not missing, requires_funding_split=split)
    source = dict(format_id='sinopac', direction='outgoing', memo='合成服務', transaction_date='2026-10-15', currency='TWD')
    connection = _VirtualAccountConnection((source, (row,)))
    monkeypatch.setattr(payout, 'query_staff_funding_portions', lambda *_args, **_kwargs: (
        StaffFundingPortion('client', 18000, date(2026, 10, 15), 0, 18000),
        StaffFundingPortion('subsidy', 12000, date(2026, 10, 15), 0, 12000)))
    repository = Mock()
    repository.load.return_value = StaffPayoutReconciliationFacts(4, 8,
        (OutgoingBankFact('88', 7, MoneyNTD(17935), 'account:7'),), (StaffPrimaryBankAccount('account:7', 7),),
        (StaffPayableFacts(row['obligation_identity'], 7, MoneyNTD(total), installment_limit=MoneyNTD(18000) if split else None),))
    monkeypatch.setattr(module, 'MySqlStaffPayoutRepository', lambda *_: repository)
    candidate = CanonicalFinanceImportRow('finance-import-row:88', 0, MoneyNTD(17935), FinanceClassificationType.STAFF_PAYOUT,
        FinanceImportDisposition.BUSINESS_PENDING, PreviewFingerprint('a' * 64), target_identities=('staff:7',))
    result = _resolve_staff_payout(connection, candidate)
    if missing:
        assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
        assert result.pending_reason == 'staff_installment_funding_unconfirmed'
        repository.load.assert_not_called()
        return
    assert result.disposition is FinanceImportDisposition.CREATE
    assert result.target_identities == ('obligation:fee65',)
    assert result.pending_reason is None
    repository.load.assert_called_once()
    repository.append_events.assert_not_called()


def _pending_receipt(amount=12000):
    return CanonicalFinanceImportRow(
        "finance-import-row:97",
        0,
        MoneyNTD(amount),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("c" * 64),
    )


@pytest.mark.parametrize('blocker', [None, 'subsidy_advance_not_due', 'subsidy_advance_settlement_ambiguous'])
@pytest.mark.parametrize('memo_case', [False, True])
def test_subsidy_return_ready_requires_owner_funding_preview(monkeypatch, blocker, memo_case):
    from dataclasses import replace
    from unittest.mock import Mock, MagicMock
    import infrastructure.mysql.client_refund_reversal_repository as storage
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    from shared_kernel.errors import ErrorCategory, TypedError
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalError
    candidate = replace(_pending_receipt(), classification_type=FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
                        target_identities=('client:7',), evidence=('unique_client_refund_name_and_month_matched', 'z-existing-evidence'))
    if memo_case:
        candidate = replace(candidate, target_identities=(), evidence=(module.TAISHIN_CLIENT_SUBSIDY_MEMO_REASON,))
    case_no = 'test-case' if memo_case else None
    monkeypatch.setattr(module, '_sinopac_outgoing_case_info', lambda *args: (memo_case, case_no, '2026-10-20'))
    load_targets = Mock(return_value=(
        {'obligation_identity': 'subsidy:case', 'case_no': 'test-case', 'due_date': '2026-10-15', 'amount_due_ntd': 12000},
    ))
    monkeypatch.setattr(module, '_load_client_refund_targets', load_targets)
    selection = object()
    monkeypatch.setattr(module, '_client_subsidy_return_selection', lambda *args: selection)
    preview = Mock(return_value=Mock(candidate=Mock(transfer_fee=MoneyNTD(0))))
    if blocker:
        preview.side_effect = ClientRefundReversalError(TypedError(ErrorCategory.DOMAIN_BLOCKED,blocker,'funding pending',CorrelationId('test-funding')))
    monkeypatch.setattr(module.ClientRefundReversalWorkflow, 'preview', preview)
    connection=MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value={'format_id':'taishin' if memo_case else 'legacy','currency':'TWD'}
    monkeypatch.setattr(storage,'_verify_taishin_subsidy_cases',lambda cursor,rows,**kwargs:rows)
    result = module._resolve_client_subsidy_return(connection,candidate)
    assert load_targets.call_args.args[1:] == (None if memo_case else 7, case_no)
    assert preview.call_args.args[0] is selection
    assert preview.call_count == 1
    if blocker:
        assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
        assert result.pending_reason == blocker
        assert result.evidence == tuple(sorted(set(result.evidence)))
    else:
        assert result.disposition is FinanceImportDisposition.CREATE
        assert result.target_identities == ('subsidy:case',)


@pytest.mark.parametrize('date,due,amounts,cash,reason', [
    (None, '2026-10-15', [12000], 12000, 'bank_transaction_date_missing'),
    ('2026-10-20', '2026-10-15', [], 12000, 'outgoing_client_refund_no_open_obligation'),
    ('2026-10-20', None, [12000], 12000, 'due_date_missing'),
    ('2026-10-20', '2026-09-15', [12000], 12000, 'outgoing_client_refund_month_no_match'),
    ('2026-10-20', '2026-10-15', [12000], 10000, 'outgoing_client_refund_amount_mismatch'),
    ('2026-10-20', '2026-10-15', [12000, 12000], 12000, 'outgoing_client_refund_multiple_fee_matches'),
])
def test_taishin_subsidy_records_actual_failed_matching_step(monkeypatch, date, due, amounts, cash, reason):
    from dataclasses import replace
    from unittest.mock import Mock, MagicMock
    import infrastructure.mysql.client_refund_reversal_repository as storage
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    candidate = replace(_pending_receipt(cash), classification_type=FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
                        evidence=(module.TAISHIN_CLIENT_SUBSIDY_MEMO_REASON,))
    monkeypatch.setattr(module, '_sinopac_outgoing_case_info', lambda *args: (True, 'C-1', date))
    monkeypatch.setattr(module, '_load_client_refund_targets', lambda *args, **kwargs: tuple(
        dict(obligation_identity=f'subsidy:{i}', case_no='C-1', due_date=due, amount_due_ntd=amount)
        for i, amount in enumerate(amounts)))
    owner = Mock()
    monkeypatch.setattr(module.ClientRefundReversalWorkflow, 'preview', owner)
    connection=MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value={'format_id':'taishin','currency':'TWD'}
    monkeypatch.setattr(storage,'_verify_taishin_subsidy_cases',lambda cursor,rows,**kwargs:rows)
    result = module._resolve_client_subsidy_return(connection, candidate)
    assert result.pending_reason == reason
    assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert result.target_identities == ()
    owner.assert_not_called()



@pytest.mark.parametrize(("canonical", "reference"), [
    (None, "99781699115150"),
    ("Y", "99781699115150測試甲"),
    ("99781699115151", "99781699115150 測試甲"),
])
def test_virtual_account_resolves_one_exact_open_client_obligation(canonical, reference) -> None:
    connection = _VirtualAccountConnection(
        (
                {
                    "format_id": "sinopac",
                    "cancellation_code": canonical,
                    "bank_references": {"銷帳編號": reference},
                    "transaction_date":"2026-10-20",
                },
                (),
                ({"case_no": "115000150"},),
                ({"obligation_identity": "client-obligation:115000150:deposit"},),
        )
    )

    resolved = _resolve_client_receipt(connection, _pending_receipt())

    assert resolved.disposition is FinanceImportDisposition.CREATE
    assert resolved.target_identities == (
        "client-obligation:115000150:deposit",
    )
    assert "exact-open-client-obligation" in resolved.evidence


@pytest.mark.parametrize("format_id", ["sinopac", "legacy"])
def test_named_virtual_account_uses_imported_case_instead_of_formula(format_id) -> None:
    connection = _VirtualAccountConnection((
        {"format_id": format_id, "cancellation_code": (
            "99781699114033測試甲" if format_id == "legacy" else "Y"
         ),
         "bank_references": {"銷帳編號": "99781699114033測試甲"},"transaction_date":"2026-10-20"},
        ({"case_no": "114000018"},),
        ({"obligation_identity": "client-obligation:114000018:deposit"},),
    ))
    resolved = _resolve_client_receipt(connection, _pending_receipt())
    assert resolved.disposition is FinanceImportDisposition.CREATE
    assert resolved.target_identities == ("client-obligation:114000018:deposit",)
    assert connection.cursor_instance.executions[-1][1] == ("114000018", 12000)


def test_virtual_account_keeps_underpayment_pending() -> None:
    candidate = _pending_receipt(2400)
    connection = _VirtualAccountConnection(
        (
                {
                    "format_id": "sinopac",
                    "cancellation_code": None,
                    "bank_references": '{"銷帳編號":"99781699115150"}',
                },
                (),
                ({"case_no": "115000150"},),
                (),
        )
    )

    resolved = _resolve_client_receipt(connection, candidate)
    assert resolved.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert resolved.target_identities == ()
    assert resolved.client_receipt_review.reason == "bank_transaction_date_missing"


def test_normal_client_receipt_selection_never_inherits_correction_overage() -> None:
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:97",
        0,
        MoneyNTD(12000),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.CREATE,
        PreviewFingerprint("d" * 64),
        ("client-obligation:115000150:deposit",),
    )
    connection = _VirtualAccountConnection(
        (({"case_no": "115000150", "obligation_type": "deposit"},),)
    )

    selection = _client_selection(connection, candidate)

    assert selection.allow_overage_disposition is False


def test_correction_posting_context_uses_the_validated_selection_reason() -> None:
    selection = FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",),
        "bank statement was reviewed",
        ("bank-statement:line-1",),
    )
    request = FinanceImportCorrectionApplyRequest(
        selection,
        ExpectedVersion(0),
        ExpectedVersion(0),
        ExpectedVersion(0),
        PreviewFingerprint("a" * 64),
        IdempotencyKey("correction-context-reason"),
        ActorContext("test-operator"),
        CorrelationId("correction-context-reason"),
    )

    assert _request_reason(request) == "bank statement was reviewed"


def test_historical_reprocess_posting_context_keeps_its_request_reason() -> None:
    request = HistoricalReprocessApplyRequest(
        "finance-import-batch:1",
        ExpectedVersion(0),
        PreviewFingerprint("b" * 64),
        IdempotencyKey("historical-context-reason"),
        ActorContext("test-operator"),
        "historical owner selection was reviewed",
        CorrelationId("historical-context-reason"),
    )

    assert _request_reason(request) == "historical owner selection was reviewed"


def test_partial_refund_recovery_requires_an_explicit_operator_choice() -> None:
    facts = FinanceImportCorrectionFacts(
        "finance-import-batch:1",
        0,
        0,
        0,
        MoneyNTD(300),
        True,
        (
            CorrectionTargetObligation(
                "refund:C-1",
                FinanceOwningDomain.CLIENT_FINANCE,
                MoneyNTD(500),
            ),
        ),
    )
    normal_selection = FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",),
        "bank statement was reviewed",
        ("bank-statement:line-1",),
    )

    with pytest.raises(ValueError, match="refund_owner_preview_required"):
        build_finance_import_correction_candidate(normal_selection, facts)

    recovery_selection = FinanceImportCorrectionSelection(
        "finance-import-row:1",
        FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",),
        "operator confirmed an actual underpayment",
        ("bank-statement:line-1",),
        allow_partial_refund_recovery=True,
    )
    candidate = build_finance_import_correction_candidate(recovery_selection, facts,
        refund_preview=ClientRefundCorrectionPreview(('refund:C-1',), (CorrectionAllocation('refund:C-1', MoneyNTD(300)),),
            MoneyNTD(0), MoneyNTD(200), PreviewFingerprint('c'*64)))

    assert candidate.allow_partial_refund_recovery is True
    assert candidate.allocations[0].amount == MoneyNTD(300)


@pytest.mark.parametrize(
    ("classification_type", "post_method"),
    (
        (FinanceClassificationType.CLIENT_RECEIPT, "_post_client_receipt"),
        (FinanceClassificationType.CLIENT_REFUND, "_post_client_refund"),
        (FinanceClassificationType.CLIENT_REFUND_RETURN, "_post_client_refund_return"),
        (FinanceClassificationType.CLIENT_SUBSIDY_RETURN, "_post_client_subsidy_return"),
        (FinanceClassificationType.GOVERNMENT_SUBSIDY, "_post_government_subsidy"),
        (FinanceClassificationType.STAFF_PAYOUT, "_post_staff_payout"),
    ),
)
def test_manual_correction_dispatches_each_registered_classification_to_owner(
    monkeypatch, classification_type, post_method
) -> None:
    candidate = FinanceImportCorrectionCandidate(
        "finance-import-row:1",
        "finance-import-batch:1",
        classification_type,
        FinanceOwningDomain.GOVERNMENT_SUBSIDY
        if classification_type is FinanceClassificationType.GOVERNMENT_SUBSIDY
        else FinanceOwningDomain.STAFF_PAYABLES
        if classification_type is FinanceClassificationType.STAFF_PAYOUT
        else FinanceOwningDomain.CLIENT_FINANCE,
        MoneyNTD(100),
        (CorrectionAllocation("obligation:1", MoneyNTD(100)),),
        "reviewed",
        ("statement:1",),
        PreviewFingerprint("e" * 64),
    )
    composite = MySqlFinanceImportOwningDomainComposite(object())
    monkeypatch.setattr(composite, post_method, lambda *_args: classification_type.value)

    assert composite._post(candidate, object()) == classification_type.value


def test_non_business_review_is_not_a_manual_correction_classification() -> None:
    with pytest.raises(ValueError, match="classification_conflict"):
        FinanceImportCorrectionSelection(
            "finance-import-row:1",
            FinanceClassificationType.NON_BUSINESS_REVIEW,
            ("obligation:1",),
            "reviewed",
            ("statement:1",),
        )


def test_sinopac_receipt_non_exact_month_matched_pairs_target_and_computes_difference() -> None:
    candidate = _pending_receipt(25900)
    connection = _VirtualAccountConnection(
        (
            {
                "format_id": "sinopac",
                "cancellation_code": None,
                "bank_references": '{"銷帳編號":"99781699115003"}',
                "transaction_date": "2026-01-14",
            },
            ({"case_no": "115000003"},),
            (),
            (
                {
                    "obligation_identity": "client-obligation:115000003:first",
                    "due_date": "2026-01-12",
                    "amount_due_ntd": 36000,
                },
            ),
        )
    )
    resolved = _resolve_client_receipt(connection, candidate)
    assert resolved.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert resolved.target_identities == ("client-obligation:115000003:first",)
    assert "month-matched-client-obligation" in resolved.evidence
    assert "diff_under:10100" in resolved.evidence


def test_sinopac_receipt_month_mismatch_remains_unpaired_pending() -> None:
    candidate = _pending_receipt(25900)
    connection = _VirtualAccountConnection(
        (
            {
                "format_id": "sinopac",
                "cancellation_code": None,
                "bank_references": '{"銷帳編號":"99781699115003"}',
                "transaction_date": "2026-03-14",
            },
            ({"case_no": "115000003"},),
            (),
            (
                {
                    "obligation_identity": "client-obligation:115000003:first",
                    "due_date": "2026-01-12",
                    "amount_due_ntd": 36000,
                },
            ),
        )
    )
    resolved = _resolve_client_receipt(connection, candidate)
    assert resolved.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert resolved.target_identities == ()
    assert "month-matched-client-obligation" not in resolved.evidence


def test_missing_due_date_is_reported_instead_of_a_month_mismatch():
    connection = _VirtualAccountConnection((
        {'format_id':'sinopac','bank_references':{'銷帳編號':'99781699115003'},'transaction_date':'2026-10-20'},
        ({'case_no':'115000003'},), (),
        ({'obligation_identity':'first','obligation_type':'first','due_date':None,'amount_due_ntd':10000},),
    ))
    result = _resolve_client_receipt(connection, _pending_receipt(9000))
    assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert result.client_receipt_review.reason == 'due_date_missing'
    assert result.client_receipt_review.candidates[0].due_date is None
    assert result.client_receipt_review.candidates[0].obligation_identity == 'first'
    assert result.target_identities == ()


@pytest.mark.parametrize('changes,reason', [
    ({'transaction_date':None},'bank_transaction_date_missing'),
    ({'currency':'USD'},'bank_currency_not_twd'),
])
def test_invalid_receipt_source_is_not_marked_ready_even_when_amount_matches(changes,reason):
    source={'format_id':'sinopac','bank_references':{'銷帳編號':'99781699115003'},'transaction_date':'2026-10-20',**changes}
    connection=_VirtualAccountConnection((source,({'case_no':'115000003'},)))
    result=_resolve_client_receipt(connection,_pending_receipt(12000))
    assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert result.client_receipt_review.reason==reason
    assert result.target_identities==()
    assert len(connection.cursor_instance.executions)==2


@pytest.mark.parametrize(("second_due", "expected"), [
    ("2026-02-12", FinanceImportDisposition.CREATE),
    ("2026-01-18", FinanceImportDisposition.BUSINESS_PENDING),
])
def test_sinopac_equal_installments_require_unique_same_month_exact_match(second_due, expected):
    first = {"obligation_identity": "client-obligation:115000003:first", "obligation_type": "first", "due_date": "2026-01-12", "amount_due_ntd": 12000}
    second = {**first, "obligation_identity": "client-obligation:115000003:second", "obligation_type": "second", "due_date": second_due}
    connection = _VirtualAccountConnection((
        {"format_id": "sinopac", "cancellation_code": None, "bank_references": {"銷帳編號": "99781699115003"},
         "transaction_date": "2026-01-14"},
        ({"case_no": "115000003"},),
        (first, second),
        (first, second),
    ))
    resolved = _resolve_client_receipt(connection, _pending_receipt())
    assert resolved.disposition is expected
    if expected is FinanceImportDisposition.CREATE:
        assert resolved.target_identities == (first["obligation_identity"],)
        assert resolved.client_receipt_review is None
    else:
        assert resolved.client_receipt_review.reason == "sinopac_client_receipt_multiple_month_candidates"
        assert [(item.obligation_type, item.due_date) for item in resolved.client_receipt_review.candidates] == [
            ("first", "2026-01-12"), ("second", second_due),
        ]


def test_resolve_staff_payout_with_transfer_fee_within_100(monkeypatch) -> None:
    from unittest.mock import Mock
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    monkeypatch.setattr(module.StaffPayoutReconciliationWorkflow,'preview',Mock())
    # 應付 12000，實付 11970（手續費 30 元 <= 100 元）：四階段配對成功並直接可核銷
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:88",
        0,
        MoneyNTD(11970),
        FinanceClassificationType.STAFF_PAYOUT,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("a" * 64),
        target_identities=("staff:7",),
        evidence=("unique_staff_payout_name_month_fee_matched",),
    )
    connection = _VirtualAccountConnection(
        (
            {"format_id": "taishin", "direction": "outgoing", "memo": "張美美薪資", "transaction_date": "2026-10-20"},
            (
                {
                    "obligation_identity": "staff-obligation:7:oct",
                    "due_date": "2026-10-15",
                    "amount_due_ntd": 12000,
                },
            ),
        ), staff_names=({'id':7,'name':'張美美'},)
    )
    resolved = _resolve_staff_payout(connection, candidate)
    assert resolved.disposition is FinanceImportDisposition.CREATE
    assert resolved.target_identities == ("staff-obligation:7:oct",)
    assert "unique-staff-payout-transfer-fee-reconciled" in resolved.evidence
    assert resolved.available_actions == ("preview_apply",)


def test_resolve_staff_payout_fee_over_100_remains_pending() -> None:
    # 應付 12000，實付 11800（差額 200 元 > 100 元）：不得直接核銷，保持 pending
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:88",
        0,
        MoneyNTD(11800),
        FinanceClassificationType.STAFF_PAYOUT,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("a" * 64),
        target_identities=("staff:7",),
        evidence=("unique_staff_payout_name_month_fee_matched",),
    )
    connection = _VirtualAccountConnection(
        (
            {"format_id": "taishin", "direction": "outgoing", "memo": "張美美薪資", "transaction_date": "2026-10-20"},
            (
                {
                    "obligation_identity": "staff-obligation:7:oct",
                    "due_date": "2026-10-15",
                    "amount_due_ntd": 12000,
                },
            ),
        ), staff_names=({'id':7,'name':'張美美'},)
    )
    resolved = _resolve_staff_payout(connection, candidate)
    assert resolved.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert resolved.available_actions == ('resolve_owning_domain_target',)
    assert resolved.pending_reason == 'staff_payout_amount_mismatch'


@pytest.mark.parametrize('amounts,cash,due,reason', [
    ((6000,7000),5000,'2026-10-15','staff_payout_amount_mismatch'),
    ((12000,),12000,None,'due_date_missing'),
    ((12000,12000),12000,'2026-10-15','outgoing_staff_payout_multiple_fee_matches'),
    ((),12000,'2026-10-15','outgoing_staff_payout_no_open_obligation'),
    ((12000,),12000,'2026-11-15','outgoing_staff_payout_month_no_match'),
    ((7000,5000),11970,'2026-10-15',None),
])
@pytest.mark.parametrize('initial',[FinanceImportDisposition.CREATE,FinanceImportDisposition.BUSINESS_PENDING])
def test_sinopac_staff_resolver_records_actual_reason_and_preflights_the_real_owner(monkeypatch,amounts,cash,due,reason,initial):
    from unittest.mock import Mock
    from domains.staff_payables.reconciliation import OutgoingBankFact,StaffPayableFacts,StaffPrimaryBankAccount
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationFacts
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    rows=tuple(dict(obligation_identity=f'staff:{i}',due_date=due,amount_due_ntd=amount) for i,amount in enumerate(amounts))
    source={'format_id':'sinopac','direction':'outgoing','memo':'合成服務甲','transaction_date':'2026-10-20','currency':'TWD'}
    connection=_VirtualAccountConnection((source,rows))
    candidate=CanonicalFinanceImportRow('finance-import-row:88',0,MoneyNTD(cash),FinanceClassificationType.STAFF_PAYOUT,
        initial,PreviewFingerprint('a'*64),target_identities=('staff:7',),
        evidence=('sinopac_unique_staff_account_in_transaction_reference',))
    repository=Mock()
    repository.load.side_effect=lambda selection,**kwargs:StaffPayoutReconciliationFacts(4,8,
        (OutgoingBankFact('88',7,MoneyNTD(cash),'account:7'),),(StaffPrimaryBankAccount('account:7',7),),
        tuple(StaffPayableFacts(row['obligation_identity'],7,MoneyNTD(row['amount_due_ntd'])) for row in rows if row['obligation_identity'] in selection.obligation_identities))
    monkeypatch.setattr(module,'MySqlStaffPayoutRepository',lambda *args:repository)
    result=_resolve_staff_payout(connection,candidate)
    assert result.pending_reason==reason
    if reason:
        assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
        repository.load.assert_not_called()
    else:
        assert result.disposition is FinanceImportDisposition.CREATE
        assert result.target_identities==('staff:0','staff:1')
        repository.load.assert_called_once()
    repository.append_events.assert_not_called()


@pytest.mark.parametrize('code',['staff_bank_account_ambiguous','cross_staff_allocation_forbidden'])
def test_sinopac_staff_auto_plan_keeps_the_actual_owner_rejection_before_posting(monkeypatch,code):
    from unittest.mock import Mock
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    connection=_VirtualAccountConnection((
        {'format_id':'sinopac','direction':'outgoing','memo':'合成服務甲','transaction_date':'2026-10-20'},
        ({'obligation_identity':'staff:0','due_date':'2026-10-15','amount_due_ntd':12000},),
    ))
    candidate=CanonicalFinanceImportRow('finance-import-row:88',0,MoneyNTD(12000),FinanceClassificationType.STAFF_PAYOUT,
        FinanceImportDisposition.CREATE,PreviewFingerprint('a'*64),target_identities=('staff:7',))
    repo=Mock();repo.load.side_effect=ValueError(code)
    monkeypatch.setattr(module,'MySqlStaffPayoutRepository',lambda *args:repo)
    result=_resolve_staff_payout(connection,candidate)
    assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert result.pending_reason==code
    assert result.available_actions==('resolve_owning_domain_target',)
    repo.append_events.assert_not_called()


def test_sinopac_posted_staff_source_is_not_reopened_as_a_new_pending_item():
    source={'format_id':'sinopac','direction':'outgoing','memo':'合成服務甲','transaction_date':'2026-10-20'}
    connection=_VirtualAccountConnection((source,))
    candidate=CanonicalFinanceImportRow('finance-import-row:88',0,MoneyNTD(12000),FinanceClassificationType.STAFF_PAYOUT,
        FinanceImportDisposition.EXISTING,PreviewFingerprint('a'*64),target_identities=('staff:7',))
    assert _resolve_staff_payout(connection,candidate)==candidate


@pytest.mark.parametrize('amounts,cash,due,trans,currency,memo,names,reason', [
    ((12000,),12000,'2026-10-15',None,'TWD','合成月嫂甲',(), 'bank_transaction_date_missing'),
    ((12000,),12000,'2026-10-15','2026-10-20','USD','合成月嫂甲',(), 'bank_currency_not_twd'),
    ((),12000,'2026-10-15','2026-10-20','TWD','合成月嫂甲',((7,'合成月嫂甲'),),'outgoing_staff_payout_no_open_obligation'),
    ((12000,),12000,None,'2026-10-20','TWD','合成月嫂甲',((7,'合成月嫂甲'),),'due_date_missing'),
    ((12000,),12000,'2026-09-15','2026-10-20','TWD','合成月嫂甲',((7,'合成月嫂甲'),),'outgoing_staff_payout_month_no_match'),
    ((6000,7000),5000,'2026-10-15','2026-10-20','TWD','合成月嫂甲',((7,'合成月嫂甲'),),'staff_payout_amount_mismatch'),
    ((12000,12000),12000,'2026-10-15','2026-10-20','TWD','合成月嫂甲',((7,'合成月嫂甲'),),'outgoing_staff_payout_multiple_fee_matches'),
    ((7000,5000),11900,'2026-10-15','2026-10-20','TWD','合成月嫂甲 HC115003',((7,'合成月嫂甲'),),None),
    # Existing canonical source with a known selection: fresh proof must reject stale identity;
    # this does not create a new P台 source from six digits alone.
    ((12000,),12000,'2026-10-15','2026-10-20','TWD','HC115003',((7,'合成月嫂甲'),),'staff_memo_recipient_unconfirmed'),
    ((12000,),12000,'2026-10-15','2026-10-20','TWD','合成月嫂甲',((7,'合成月嫂甲'),(8,'合成月嫂甲')),'staff_memo_recipient_unconfirmed'),
    ((12000,),12000,'2026-10-15','2026-10-20','TWD','合成月嫂乙',((8,'合成月嫂乙'),),'cross_staff_allocation_forbidden'),
])
def test_taishin_staff_pending_reason_follows_raw_memo_and_actual_matching_step(monkeypatch,amounts,cash,due,trans,currency,memo,names,reason):
    from unittest.mock import Mock
    from domains.staff_payables.reconciliation import OutgoingBankFact,StaffPayableFacts
    from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationFacts
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    rows=tuple(dict(obligation_identity=f'staff:{i}',due_date=due,amount_due_ntd=a) for i,a in enumerate(amounts))
    source=dict(id=88,format_id='taishin',direction='outgoing',transaction_date=trans,currency=currency,memo=memo)
    connection=_VirtualAccountConnection((source,rows),staff_names=tuple(dict(id=i,name=n) for i,n in names))
    candidate=CanonicalFinanceImportRow('finance-import-row:88',0,MoneyNTD(cash),FinanceClassificationType.STAFF_PAYOUT,
        FinanceImportDisposition.BUSINESS_PENDING,PreviewFingerprint('a'*64),target_identities=('staff:7',))
    repo=Mock()
    repo.load.side_effect=lambda selection,**kwargs:StaffPayoutReconciliationFacts(4,8,
        (OutgoingBankFact('88',7,MoneyNTD(cash),taishin_memo_staff_id=7),),(),
        tuple(StaffPayableFacts(row['obligation_identity'],7,MoneyNTD(row['amount_due_ntd'])) for row in rows if row['obligation_identity'] in selection.obligation_identities))
    monkeypatch.setattr(module,'MySqlStaffPayoutRepository',lambda *args:repo)
    result=module._resolve_staff_payout(connection,candidate)
    assert result.pending_reason==reason
    if reason:
        assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
        assert result.available_actions==('resolve_owning_domain_target',)
        repo.load.assert_not_called()
    else:
        assert result.disposition is FinanceImportDisposition.CREATE
        assert result.target_identities==('staff:0','staff:1')
        repo.load.assert_called_once()
    repo.append_events.assert_not_called()


@pytest.mark.parametrize('bank', ['sinopac', 'taishin'])
@pytest.mark.parametrize(('second_month', 'expected'), [
    ('10', ('staff:first', 'staff:second')),
    ('11', ()),
])
def test_staff_payout_can_only_combine_obligations_in_the_transaction_month(monkeypatch, bank, second_month, expected):
    from unittest.mock import Mock
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    monkeypatch.setattr(module.StaffPayoutReconciliationWorkflow,'preview',Mock())
    candidate = CanonicalFinanceImportRow(
        'finance-import-row:88', 0, MoneyNTD(11970),
        FinanceClassificationType.STAFF_PAYOUT, FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint('a' * 64), target_identities=('staff:7',),
        evidence=('unique_staff_payout_name_month_fee_matched',),
    )
    connection = _VirtualAccountConnection((
        {'format_id': bank, 'direction': 'outgoing', 'memo': '合成月嫂', 'transaction_date': '2026-10-20'},
        (
            {'obligation_identity': 'staff:first', 'due_date': '2026-10-05', 'amount_due_ntd': 7000},
            {'obligation_identity': 'staff:second', 'due_date': f'2026-{second_month}-15', 'amount_due_ntd': 5000},
        ),
    ),staff_names=({'id':7,'name':'合成月嫂'},))
    resolved = _resolve_staff_payout(connection, candidate)
    if expected:
        assert resolved.disposition is FinanceImportDisposition.CREATE
        assert resolved.target_identities == expected
    else:
        assert resolved.pending_reason == 'staff_payout_amount_mismatch'


def test_resolve_client_refund_with_transfer_fee_within_100() -> None:
    # 客戶退款：應付 10000，實付 9970（手續費 30 元 <= 100 元）：四階段配對成功並直接可核銷
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:99",
        0,
        MoneyNTD(9970),
        FinanceClassificationType.CLIENT_REFUND,
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("b" * 64),
        target_identities=("client:101",),
        evidence=("unique_client_refund_name_month_fee_matched",),
    )
    connection = _VirtualAccountConnection(
        (
            {"format_id": "taishin", "direction": "outgoing", "memo": "林小美退款", "transaction_date": "2026-10-20"},
            (
                {
                    "case_no": "115001",
                    "obligation_identity": "client-obligation:115001:refund",
                    "due_date": "2026-10-15",
                    "amount_due_ntd": 10000,
                },
            ),
        )
    )
    resolved = _resolve_client_refund(connection, candidate)
    assert resolved.disposition is FinanceImportDisposition.CREATE
    assert resolved.target_identities == ("client-obligation:115001:refund",)
    assert "unique-client-refund-transfer-fee-reconciled" in resolved.evidence
    assert resolved.available_actions == ("preview_apply",)


@pytest.mark.parametrize('amounts,cash,due,trans_date,currency,reason', [
    ([12000],12000,'2026-10-15',None,'TWD','bank_transaction_date_missing'),
    ([12000],12000,'2026-10-15','2026-10-20','USD','bank_currency_not_twd'),
    ([],12000,'2026-10-15','2026-10-20','TWD','outgoing_client_refund_no_open_obligation'),
    ([12000],12000,None,'2026-10-20','TWD','due_date_missing'),
    ([12000],12000,'2026-09-15','2026-10-20','TWD','outgoing_client_refund_month_no_match'),
    ([6000,7000],5000,'2026-10-15','2026-10-20','TWD','outgoing_client_refund_amount_mismatch'),
    ([12000,12000],12000,'2026-10-15','2026-10-20','TWD','outgoing_client_refund_multiple_fee_matches'),
])
@pytest.mark.parametrize('initial',[FinanceImportDisposition.BUSINESS_PENDING,FinanceImportDisposition.CREATE])
def test_sinopac_refund_resolver_saves_actual_step_and_keeps_manual_action(monkeypatch,amounts,cash,due,trans_date,currency,reason,initial):
    from dataclasses import replace
    from unittest.mock import Mock
    import infrastructure.mysql.finance_import_owning_domain_composite as module
    connection=Mock()
    connection.cursor.return_value.__enter__=Mock(return_value=Mock(fetchone=Mock(return_value={'format_id':'sinopac','currency':currency})))
    connection.cursor.return_value.__exit__=Mock(return_value=False)
    monkeypatch.setattr(module,'_sinopac_outgoing_case_info',lambda *args:(True,'SYNTHETIC',trans_date))
    monkeypatch.setattr(module,'_load_client_refund_targets',lambda *args:tuple(dict(case_no='SYNTHETIC',obligation_identity=f'refund:{i}',due_date=due,amount_due_ntd=a) for i,a in enumerate(amounts)))
    owner=Mock()
    monkeypatch.setattr(module.ClientRefundReversalWorkflow,'preview',owner)
    candidate=replace(_pending_receipt(cash),classification_type=FinanceClassificationType.CLIENT_REFUND,disposition=initial,target_identities=('client:7',),evidence=('sinopac_unique_client_refund_account_in_transaction_reference',))
    result=module._resolve_client_refund(connection,candidate)
    assert result.pending_reason==reason
    assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert result.available_actions==('resolve_owning_domain_target',)
    owner.assert_not_called()



def test_sinopac_receipt_with_same_month_open_obligation_does_not_steal_earlier_month_exact_deposit() -> None:
    deposit = {
        "obligation_identity": "client-obligation:115000038:deposit",
        "obligation_type": "deposit",
        "due_date": "2026-03-15",
        "amount_due_ntd": 6000,
    }
    second = {
        "obligation_identity": "client-obligation:115000038:second",
        "obligation_type": "second",
        "due_date": "2026-10-06",
        "amount_due_ntd": 18000,
    }
    march_conn = _VirtualAccountConnection((
        {"format_id": "sinopac", "cancellation_code": None, "bank_references": {"銷帳編號": "99781699115038"}, "transaction_date": "2026-03-18"},
        ({"case_no": "115000038"},),
        (deposit,),
    ))
    march_resolved = _resolve_client_receipt(march_conn, _pending_receipt(6000))
    assert march_resolved.disposition is FinanceImportDisposition.CREATE
    assert march_resolved.target_identities == (deposit["obligation_identity"],)
    assert "exact-open-client-obligation-in-transaction-month" in march_resolved.evidence

    october_conn = _VirtualAccountConnection((
        {"format_id": "sinopac", "cancellation_code": None, "bank_references": {"銷帳編號": "99781699115038"}, "transaction_date": "2026-10-08"},
        ({"case_no": "115000038"},),
        (deposit,),
        (deposit, second),
    ))
    october_resolved = _resolve_client_receipt(october_conn, _pending_receipt(6000))
    assert october_resolved.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert october_resolved.target_identities == (second["obligation_identity"],)
    assert october_resolved.client_receipt_review.reason == "client_receipt_underpaid"
    assert "diff_under:12000" in october_resolved.evidence
