/** Shared case subsidy detail, using existing read models and owner confirmation. */
import { useEffect, useRef, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { OrderDetail } from '../api/orders/order_query_schemas';
import { clientFinanceHistoryClient, type ClientFinanceHistory } from '../api/client_finance/client_finance_history_client';
import { clientSubsidyReturnQueryClient, type ClientSubsidyReturnQuery } from '../api/client_finance/client_subsidy_return_query_client';
import { orderGovernmentSubsidyProjectionClient, type OrderGovernmentSubsidyProjection } from '../api/orders/order_government_subsidy_projection_client';
import { SubsidyAdvanceSettlementPanel } from './SubsidyAdvanceSettlementPanel';
import { financeMoney, governmentStatus, governmentServiceQuarter, serviceEndLabel, subsidyEstimateReasons } from './FinanceReceiptsWorkspace';
import { financeEntryLabels } from './FinanceCaseHistory';

type Props = { caseNo: string; onClose: () => void; onOpenBank: () => void; onChanged: () => void };
export function CaseSubsidyDetailDrawer({ caseNo, onClose, onOpenBank, onChanged }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [locked, setLocked] = useState(false);
  const [revision, setRevision] = useState(0);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [government, setGovernment] = useState<OrderGovernmentSubsidyProjection | null | undefined>();
  const [history, setHistory] = useState<ClientFinanceHistory | null | undefined>();
  const [refund, setRefund] = useState<ClientSubsidyReturnQuery['rows'][number] | null | undefined>();
  const [errors, setErrors] = useState<string[]>([]);
  const failed = (section: string) => setErrors(value => [...value, section]);
  useEffect(() => {
    const element = dialog.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => {
      element?.close();
      queueMicrotask(() => { if (!element?.open && opener?.isConnected) opener.focus(); });
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController(); const signal = controller.signal;
    setErrors([]); setOrder(null); setGovernment(undefined); setHistory(undefined); setRefund(undefined);
    queueMicrotask(() => {
    if (signal.aborted) return;
    void ordersQueryClient.getOrderDetail(caseNo, { signal }).then(value => { if (!signal.aborted) setOrder(value); }).catch(() => { if (!signal.aborted) failed('案件資料'); });
    void orderGovernmentSubsidyProjectionClient.queryAll({ case_no_search: caseNo }, { signal }).then(rows => { if (!signal.aborted) setGovernment(rows.find(row => row.case_no === caseNo) ?? null); }).catch(() => { if (!signal.aborted) { setGovernment(null); failed('政府補助'); } });
    void clientFinanceHistoryClient.query(caseNo, signal).then(value => { if (!signal.aborted) setHistory(value); }).catch(() => { if (!signal.aborted) { setHistory(null); failed('帳務歷史'); } });
    void clientSubsidyReturnQueryClient.queryAll({ caseNo, signal }).then(value => { if (!signal.aborted) setRefund(value.rows[0] ?? null); }).catch(() => { if (!signal.aborted) { setRefund(null); failed('應退補助'); } });
    });
    return () => controller.abort();
  }, [caseNo, revision]);
  const subsidyObligations = new Set(history?.obligations.filter(row => row.obligation_type === 'subsidy_return').map(row => row.obligation_identity));
  const subsidyEntryIds = new Set(history?.ledger_entries.filter(entry => ['subsidy_advance', 'subsidy_return'].includes(entry.entry_type)
    || entry.allocations.some(allocation => subsidyObligations.has(allocation.obligation_identity))).map(entry => entry.entry_id));
  const entries = history?.ledger_entries.filter(entry => subsidyEntryIds.has(entry.entry_id)
    || (entry.reversal_of_entry_id !== null && subsidyEntryIds.has(entry.reversal_of_entry_id))) ?? [];
  const changed = () => { setRevision(value => value + 1); onChanged(); };
  return <dialog className="finance-case-drawer" ref={dialog} aria-labelledby="case-subsidy-title" onCancel={event => { event.preventDefault(); if (!locked) onClose(); }}>
    <header><div><p>案件補助明細</p><h2 id="case-subsidy-title">{order?.client_name ?? caseNo}</h2><small>{caseNo}</small></div><button type="button" className="finance-reload-btn" disabled={locked} onClick={onClose} aria-label="關閉案件補助明細">關閉</button></header>
    <div className="finance-drawer-content">
      <p className="subsidy-refund-note">補助資格、政府入款、客戶退款與工會墊款，集中在這裡核對。</p>
      {errors.length > 0 && <p role="alert" className="finance-state error">{errors.join('、')}暫時無法取得。<button type="button" disabled={locked} onClick={() => setRevision(value => value + 1)}>重新查詢</button></p>}
      <section><h3>補助資格與計算依據</h3>{government && <p>{serviceEndLabel(government)}</p>}<dl className="finance-fact-grid"><div><dt>身分類別</dt><dd>{order?.identity_status ?? '待確認'}</dd></div><div><dt>請款時數</dt><dd>{government === undefined ? '查詢中…' : government?.claim_item_count ? `${government.claimed_hours} 小時` : '尚無正式請款資料'}</dd></div><div><dt>請款凍結單價</dt><dd>{government?.unit_price_ntd === undefined || government?.unit_price_ntd === null ? '待確認' : `${financeMoney(government.unit_price_ntd)}／小時`}</dd></div><div><dt>服務歸屬季度</dt><dd>{government ? governmentServiceQuarter(government) ?? '待確認' : '待確認'}</dd></div></dl></section>
      <section><h3>政府補助</h3>{government === undefined ? <p role="status">正在查詢政府補助…</p> : errors.includes('政府補助') ? <p>查詢失敗，請重新查詢。</p> : government ? <><dl className="finance-fact-grid"><div><dt>預估補助金額</dt><dd>{financeMoney(government.estimated_subsidy_amount_ntd)}</dd></div><div><dt>申請金額</dt><dd>{government.claim_item_count ? financeMoney(government.requested_amount_ntd) : '尚無正式請款資料'}</dd></div><div><dt>核准金額</dt><dd>{financeMoney(government.confirmed_approved_amount_ntd)}</dd></div><div><dt>已核准待收款</dt><dd>{financeMoney(government.outstanding_amount_ntd)}</dd></div><div><dt>已分配入款</dt><dd>{government.net_allocated_ntd > 0 ? financeMoney(government.net_allocated_ntd) : '尚未入款'}</dd></div><div><dt>進度</dt><dd>{governmentStatus[government.substatus_code]}</dd></div><div><dt>預計申請年月</dt><dd>{government.claim_application_year && government.claim_application_month ? `${government.claim_application_year}-${String(government.claim_application_month).padStart(2, '0')}` : '待確認'}</dd></div><div><dt>實際送件日期</dt><dd>{government.claim_submitted_at?.slice(0, 10) ?? '尚未送件'}</dd></div></dl>{government.estimate_unavailable_reason && <p className="subsidy-refund-note">{subsidyEstimateReasons[government.estimate_unavailable_reason]}</p>}{[...government.blockers, ...government.warnings].filter(item => item.code !== 'government_subsidy_claim_lineage_missing').map(item => <p key={item.code} className="subsidy-refund-note">{item.message}</p>)}</> : <p>尚無本案政府補助申請資料。</p>}<a href="#reports" aria-disabled={locked} onClick={event => { if (locked) event.preventDefault(); }}>前往季度補助報表</a></section>
      <section><h3>客戶補助退款</h3>{refund === undefined || history === undefined ? <p role="status">正在查詢應退補助與退款紀錄…</p> : <>
        {refund && <dl className="finance-fact-grid"><div><dt>{refund.is_estimate ? '預估應退' : '正式應退'}</dt><dd>{financeMoney(refund.amount_ntd)}</dd></div><div><dt>應退款日期</dt><dd>{refund.due_date ?? '待確認'}</dd></div></dl>}
        {!refund && !errors.includes('應退補助') && <p className="subsidy-refund-note">目前沒有待退補助項目；已付款紀錄如下。</p>}
        <ol className="finance-history-timeline">{entries.map(entry => <li key={entry.entry_id}><strong>{financeEntryLabels[entry.entry_type]} {financeMoney(entry.amount_ntd)}</strong><small>{entry.occurred_on}{entry.reversal_of_entry_id ? '・沖正' : history?.ledger_entries.some(row => row.reversal_of_entry_id === entry.entry_id) ? '・有沖正紀錄' : '・已入帳'}</small></li>)}</ol>
        {!entries.length && !errors.includes('帳務歷史') && <p className="subsidy-refund-note">尚無已入帳的補助退款紀錄。</p>}
        <button type="button" className="finance-reload-btn" disabled={locked} onClick={onOpenBank}>核對銀行出入款</button>
      </>}</section>
      <SubsidyAdvanceSettlementPanel key={caseNo} initialCaseNo={caseNo} compact onOpenImport={onOpenBank} onLockedChange={setLocked} onSettled={changed} />
    </div>
  </dialog>;
}
