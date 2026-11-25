import {useEffect, useState} from 'react';
import {financeAccountingClient, type CaseAccounting} from '../api/finance_import/finance_accounting_client';
import {subsidyPlanLabels, subsidyPlanTargets} from './FinanceSubsidyPlanForm';
import {CancellationSettlementAccounting} from './CancellationSettlementAccounting';
import {accountingReason,unallocatedPaymentLabel} from './case_accounting_presentation';

const receiptSources:Record<string,string>={manual:'人工補登',sinopac:'永豐',taishin:'台新',legacy:'歷史來源'};

/** Read the same typed accounting result as the finance workspace. No local formulas/writers. */
export function ClientRegistryAccountingSummary({caseNo, revision}: {caseNo: string; revision: unknown}) {
  const [state, setState] = useState<{data?: CaseAccounting; error?: boolean}>({});
  useEffect(() => {
    const controller = new AbortController();
    setState({});
    void financeAccountingClient.query(caseNo, controller.signal).then(data => {
      if (!controller.signal.aborted) setState({data});
    }).catch(() => { if (!controller.signal.aborted) setState({error: true}); });
    return () => controller.abort();
  }, [caseNo, revision]);
  const money = (value: number | bigint | null | undefined) => value == null ? '待確認' : `${value.toLocaleString('zh-TW')} 元`;
  const staffPayables = state.data?.staff_items.filter(item => item.direction === 'payable') ?? [];
  const originalClientItems=state.data?.client_items.filter(item=>item.direction==='receivable')??[];
  const unallocatedTransactions=state.data?.transactions.filter(item=>item.item_identity==='unallocated')??[];
  const scheme = state.data?.scheme;
  const manual = state.data?.subsidy_plan?.events.at(-1)?.scheme;
  const subsidyPayments=state.data?.subsidy_payments?.filter(payment=>
    !state.data?.historical_stages||payment.recipient!=='client'||payment.source==='formal')??[];
  const known = scheme === 'split' || scheme === 'advance' || scheme === 'direct' ? scheme : undefined;
  return <>
    {state.data && <CancellationSettlementAccounting data={state.data} registry />}
    <section className="registry-editor" aria-label="補助及退款方案摘要（唯讀）"><h3>補助及退款方案摘要（唯讀）</h3>
    {!state.data ? <p role="status">{state.error ? '共用帳務來源暫時無法讀取，金額及方案待確認。' : '正在讀取共用帳務資料…'}</p> : <>
      {state.data.historical_stages&&<>
        {state.data.full_subsidy&&!state.data.scheme_conflict&&<p>全額補助／免自備，客戶應付 {money(state.data.customer_amount_ntd)}</p>}
        {state.data.accounting_pending_reasons?.map(reason=><p key={reason} role="status">{accountingReason(reason)}</p>)}
        {!!state.data.pending_bank_row_identities?.length&&<section aria-label="本案銀行收付款待核對"><p>原銀行來源待核對，尚未認列本案實收或實付。</p><ul>{state.data.pending_bank_row_identities.map(identity=><li key={identity}>{identity}</li>)}</ul></section>}
        {!!state.data.stale_payment_evidence_identities?.length&&<section aria-label="歷史付款證據待核對"><p>歷史付款證據已過期待核對</p><ul>{state.data.stale_payment_evidence_identities.map(identity=><li key={identity}>{identity}</li>)}</ul></section>}
        <section aria-label="歷史客戶原款項" tabIndex={0} style={{overflowX:'auto'}}><h4>歷史客戶原款項</h4>
          {originalClientItems.length===0?<p>{state.data.full_subsidy&&!state.data.scheme_conflict
            ?'沒有原期款證據；免自備判定不代表原款已付或帳務結清。'
            :'沒有原期款證據；整案總額僅供查閱，原期款與收付仍待核對。'}</p>
            :<table><thead><tr><th>原款項</th><th>原到期日</th><th>應繳</th><th>已收／待收</th><th>入帳來源</th></tr></thead><tbody>
              {originalClientItems.map(item=><tr key={item.identity}>
                <td>{item.label}<small>{item.identity}</small>{!item.payment_stage&&<small>期別待確認</small>}{item.source_event_identity&&<small>{item.source_event_identity}</small>}</td>
                <td>{item.due_date??'日期待確認'}</td><td>{money(item.expected_ntd)}</td>
                <td>已收 {money(item.actual_ntd)}，待收 {money(item.remaining_ntd)}{item.noncash_ntd!=null&&item.noncash_ntd>0&&<small>非現金結清 {money(item.noncash_ntd)}</small>}</td>
                <td>{state.data?.transactions.filter(row=>row.item_identity===item.identity).map(row=><p key={row.identity}>{row.occurred_on} · {row.bank?receiptSources[row.bank]??'原來源':'原來源'} · {row.kind==='reversal'||row.amount_ntd<0?'沖正':'入帳'} · {money(row.amount_ntd)}</p>)}
                  {item.payment_evidence==='historical_paid'&&<p>歷史已付證據，非銀行入帳</p>}{item.payment_evidence==='historical_settled'&&<p>歷史結清證據，非銀行入帳</p>}
                  {item.payment_date&&<p>歷史確認日 {item.payment_date}</p>}
                </td>
              </tr>)}
            </tbody></table>}
        </section>
        {unallocatedTransactions.length>0&&<section aria-label="期別待確認的原收付款"><p>以下原收付款尚未分配到期款，保留原來源供核對。</p>
          {unallocatedTransactions.map(row=><p key={row.identity}>{row.occurred_on} · {row.bank?receiptSources[row.bank]??'原來源':'原來源'} · {unallocatedPaymentLabel(row.kind)} · {money(row.amount_ntd)} · {row.identity}</p>)}
        </section>}
      </>}
      <dl className="registry-information-fields">
        <div><dt>歷史金流辨識</dt><dd>{known ? subsidyPlanLabels[known] : scheme === 'waiting' ? '尚待款項事實確認' : '來源不足，待確認'}</dd></div>
        <div><dt>進行中人工設定</dt><dd>{manual ? subsidyPlanLabels[manual] : '尚未設定'}</dd></div>
        <div><dt>{state.data.historical_stages?'客戶應付':'案件金額'}</dt><dd>{money(state.data.customer_amount_ntd)}</dd></div>
        <div><dt>補助金額</dt><dd>{money(state.data.subsidy_ntd)}</dd></div>
        <div><dt>自備金額（共用帳務判定）</dt><dd>{money(state.data.customer_burden_ntd)}</dd></div>
        <div><dt>歷史方案補助對象</dt><dd>{known ? subsidyPlanTargets[known] : '待確認'}</dd></div>
        <div><dt>人工設定補助對象</dt><dd>{manual ? subsidyPlanTargets[manual] : '待確認'}</dd></div>
      </dl>
      {state.data.subsidy_pending_reason&&<p role="status">{accountingReason(state.data.subsidy_pending_reason)}</p>}
      <h4>月嫂應付</h4>
      {!!state.data.staff_accounting_availability?.length&&<section aria-label="歷史月嫂應付依據">
        {state.data.staff_accounting_availability.map((item,index)=><div key={`${item.assignment_id??'unknown'}:${item.staff_id??'unknown'}:${index}`}>
          <strong>{item.party||'月嫂歸屬待確認'}</strong>
          <p>{item.status==='formal'?'已有正式應付':item.status==='not_established'?'尚未建立正式應付':'應付來源待核對'}</p>
          {item.pending_reasons.map(reason=><p key={reason}>{accountingReason(reason)}</p>)}
          {item.estimated_self_pay_date&&<p>自備款預計付款日 {item.estimated_self_pay_date}</p>}
          {item.estimated_subsidy_date&&<p>補助款預計付款日 {item.estimated_subsidy_date}</p>}
          {item.recorded_due_date&&<p>原已保存付款日 {item.recorded_due_date}</p>}
        </div>)}
      </section>}
      {staffPayables.length > 0 ? <ul>
        {staffPayables.map(item =>
          <li key={item.identity}>{item.party}／{item.label}：{money(item.expected_ntd)}，應付日 {item.due_date ?? '待確認'}</li>
        )}
      </ul> : <p>{state.data.staff_receivable_ntd == null
        ? '尚無月嫂應付明細。'
        : `月嫂薪資預估 ${money(state.data.staff_receivable_ntd)}，正式應付待確認。`}</p>}
      <h4>補助給付</h4>
      {subsidyPayments.length ? <ul>
        {subsidyPayments.map((payment, index) =>
          <li key={index}>{payment.recipient === 'staff' ? '轉付月嫂' : '退還客戶'}{payment.party && `／${payment.party}`}：
            {payment.source === 'estimate' && '預估 '}{money(payment.amount_ntd)}，給付日 {payment.due_date ?? '待確認'}</li>
        )}
      </ul> : <p>{state.data.subsidy_ntd === 0 || scheme === 'direct' ? '不適用' : '給付款項待確認。'}</p>}
      {state.data.scheme_conflict && <p role="status">方案與正式金流事實衝突，請由原帳務入口核對。</p>}
      <p>金額與方案沿用案件帳務結果；此處僅供查閱，未設定的人工方案仍須由原帳務入口確認。</p>
    </>}
  </section></>;
}
