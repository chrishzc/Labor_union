import type { CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { CancellationSettlementNotices } from './CancellationSettlementNotices';
import { financeMoney } from './FinanceReceiptsWorkspace';

const money = (value: number | bigint | null | undefined) => value == null ? '待確認' : financeMoney(value);

export function CancellationSettlementAccounting({ data, registry = false }: { data: CaseAccounting; registry?: boolean }) {
  const settlement = data.cancellation_settlement;
  if (!settlement) return null;
  const item = data.client_items.find(row => row.identity === settlement.obligation_identity);
  const remaining = item?.remaining_ntd;
  const refund = settlement.refund_due_ntd > 0;
  const collection = settlement.additional_charge_due_ntd > 0;

  return <section className="finance-case-block" aria-label="取消結算"><div className="finance-case-block-body">
    <h3>取消結算</h3>
    <dl className="finance-compact-facts">
      <div><dt>服務應付</dt><dd>{money(settlement.service_due_ntd)}</dd></div>
      <div><dt>取消違約金</dt><dd>{money(settlement.fee_ntd)}</dd></div>
      <div><dt>已收違約金／公會營收</dt><dd>{money(settlement.fee_received_ntd)}</dd></div>
      <div><dt>取消時淨實收</dt><dd>{money(settlement.net_received_ntd)}</dd></div>
      <div><dt>{refund ? '原應退款' : '原應補收'}</dt><dd>{money(refund ? settlement.refund_due_ntd : settlement.additional_charge_due_ntd)}</dd></div>
      {item && <>
        <div><dt>已核銷</dt><dd>{money(remaining == null ? null : BigInt(item.expected_ntd) - BigInt(remaining))}</dd></div>
        <div><dt>{refund ? '剩餘待退' : '剩餘待收'}</dt><dd>{money(remaining)}</dd></div>
      </>}
      {collection && <>
        <div><dt>服務費待收</dt><dd>{money(settlement.service_remaining_ntd)}</dd></div>
        <div><dt>違約金待收</dt><dd>{money(settlement.fee_remaining_ntd)}</dd></div>
      </>}
      {refund && <>
        <div><dt>銀行實退</dt><dd>{money(settlement.bank_refunded_ntd)}</dd></div>
        <div><dt>匯款手續費</dt><dd>{money(settlement.transfer_fee_ntd)}</dd></div>
      </>}
    </dl>
    <p role="status">{settlement.obligation_identity
      ? remaining === 0 || remaining === 0n ? '已結清' : item ? '待核銷' : '核銷來源待確認'
      : '無待收付差額'}</p>
    <CancellationSettlementNotices key={data.case_no} caseNo={data.case_no} />
    {registry && <p>核銷請由銀行對帳辦理。</p>}
  </div></section>;
}
