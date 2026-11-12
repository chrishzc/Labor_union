import {useEffect, useState} from 'react';
import {financeAccountingClient, type CaseAccounting} from '../api/finance_import/finance_accounting_client';
import {subsidyPlanLabels, subsidyPlanTargets} from './FinanceSubsidyPlanForm';
import {CancellationSettlementAccounting} from './CancellationSettlementAccounting';

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
  const scheme = state.data?.scheme;
  const manual = state.data?.subsidy_plan?.events.at(-1)?.scheme;
  const known = scheme === 'split' || scheme === 'advance' || scheme === 'direct' ? scheme : undefined;
  return <>
    {state.data && <CancellationSettlementAccounting data={state.data} registry />}
    <section className="registry-editor" aria-label="補助及退款方案摘要（唯讀）"><h3>補助及退款方案摘要（唯讀）</h3>
    {!state.data ? <p role="status">{state.error ? '共用帳務來源暫時無法讀取，金額及方案待確認。' : '正在讀取共用帳務資料…'}</p> : <>
      <dl className="registry-information-fields">
        <div><dt>歷史金流辨識</dt><dd>{known ? subsidyPlanLabels[known] : scheme === 'waiting' ? '尚待款項事實確認' : '來源不足，待確認'}</dd></div>
        <div><dt>進行中人工設定</dt><dd>{manual ? subsidyPlanLabels[manual] : '尚未設定'}</dd></div>
        <div><dt>案件金額</dt><dd>{money(state.data.customer_amount_ntd)}</dd></div>
        <div><dt>補助金額</dt><dd>{money(state.data.subsidy_ntd)}</dd></div>
        <div><dt>自備金額（共用帳務判定）</dt><dd>{money(state.data.customer_burden_ntd)}</dd></div>
        <div><dt>歷史方案補助對象</dt><dd>{known ? subsidyPlanTargets[known] : '待確認'}</dd></div>
        <div><dt>人工設定補助對象</dt><dd>{manual ? subsidyPlanTargets[manual] : '待確認'}</dd></div>
      </dl>
      <h4>月嫂應付</h4>
      {staffPayables.length > 0 ? <ul>
        {staffPayables.map(item =>
          <li key={item.identity}>{item.party}／{item.label}：{money(item.expected_ntd)}，應付日 {item.due_date ?? '待確認'}</li>
        )}
      </ul> : <p>{state.data.staff_receivable_ntd == null
        ? '尚無月嫂應付明細。'
        : `月嫂薪資預估 ${money(state.data.staff_receivable_ntd)}，正式應付待確認。`}</p>}
      <h4>補助給付</h4>
      {state.data.subsidy_payments?.length ? <ul>
        {state.data.subsidy_payments.map((payment, index) =>
          <li key={index}>{payment.recipient === 'staff' ? '轉付月嫂' : '退還客戶'}{payment.party && `／${payment.party}`}：
            {payment.source === 'estimate' && '預估 '}{money(payment.amount_ntd)}，給付日 {payment.due_date ?? '待確認'}</li>
        )}
      </ul> : <p>{state.data.subsidy_ntd === 0 || scheme === 'direct' ? '不適用' : '給付款項待確認。'}</p>}
      {state.data.scheme_conflict && <p role="status">方案與正式金流事實衝突，請由原帳務入口核對。</p>}
      <p>金額與方案沿用案件帳務結果；此處僅供查閱，未設定的人工方案仍須由原帳務入口確認。</p>
    </>}
  </section></>;
}
