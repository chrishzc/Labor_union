import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import React, { useEffect, useState } from 'react';
import { historicalServiceAccountingClient, type HistoricalCaregiverDays, type HistoricalServiceAccountingPreview, type HistoricalServiceAccountingQuery } from '../api/orders/historical_service_accounting_client';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { OrderSummaryItem } from '../api/orders/order_query_schemas';

export interface HistoricalServiceAccountingWorkbenchProps {
  caseNo?: string;
  onSaved?: () => void;
}

export const HistoricalServiceAccountingWorkbench: React.FC<HistoricalServiceAccountingWorkbenchProps> = ({ caseNo: propCaseNo, onSaved }) => {
  const staffIdentity = useStaffIdentityLabels();
  const [caseNo, setCaseNo] = useState(propCaseNo ?? '');
  const [orderSummaries, setOrderSummaries] = useState<OrderSummaryItem[]>([]);
  const [orderListState, setOrderListState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [facts, setFacts] = useState<HistoricalServiceAccountingQuery | null>(null);
  const [days, setDays] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<HistoricalServiceAccountingPreview | null>(null);
  const [message, setMessage] = useState('');
  const [reason, setReason] = useState('');
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (propCaseNo !== undefined) {
      setCaseNo(propCaseNo);
      setFacts(null);
      setPreview(null);
      setMessage('');
      if (propCaseNo.trim()) {
        void run(async () => {
          try {
            const result = await historicalServiceAccountingClient.query(propCaseNo.trim());
            setFacts(result);
            setDays(Object.fromEntries(result.assignments.map((item) => [item.assignment_identity, ''])));
            setPreview(null);
          } catch (error) {
            setMessage(error instanceof Error ? error.message : '載入歷史服務帳務資料失敗。');
          }
        });
      }
    }
  }, [propCaseNo]);

  useEffect(() => {
    if (propCaseNo) return;
    let active = true;
    void loadAllOrderSummaries((params, options) => ordersQueryClient.getOrderSummaries(params, options))
      .then((page) => {
        if (!active) return;
        setOrderSummaries(page.items);
        setOrderListState('ready');
      })
      .catch(() => {
        if (!active) return;
        setOrderSummaries([]);
        setOrderListState('error');
      });
    return () => { active = false; };
  }, [propCaseNo]);

  const { requestLeave } = useUnsavedNavigation();
  const inputs = (): HistoricalCaregiverDays[] => (facts?.assignments ?? []).map((item) => ({ assignment_identity: item.assignment_identity, staff_id: item.staff_id, actual_service_days: Number(days[item.assignment_identity]) }));
  const run = async (operation: () => Promise<void>) => { setBusy(true); setMessage(''); try { await operation(); } catch (error) { setMessage(error instanceof Error ? error.message : '處理失敗。'); } finally { setBusy(false); } };
  const caseOptionsUnavailable = orderListState !== 'ready' || orderSummaries.length === 0;
  const casePlaceholder = orderListState === 'loading'
    ? '載入案件中…'
    : orderListState === 'error'
      ? '案件清單載入失敗'
      : orderSummaries.length === 0
        ? '目前沒有可選案件'
        : '請選擇案件';
  const unsaved = useUnsavedDraft('歷史服務天數', { '服務天數': days, '原因': reason }, { busy: busy || outcomeUnknown, resetKey: facts, save: () => run(save), discard: () => { setDays(Object.fromEntries((facts?.assignments ?? []).map(item => [item.assignment_identity, '']))); setReason(''); setPreview(null); } });
  async function save() {
    if (!facts || outcomeUnknown) return;
    const checkedInputs = inputs();
    if (checkedInputs.some(item => !Number.isInteger(item.actual_service_days) || item.actual_service_days <= 0)) throw new Error('請填寫每位月嫂的正整數服務天數。');
    const checked = await historicalServiceAccountingClient.preview(facts.case_no, checkedInputs);
    let receipt;
    try { receipt = await historicalServiceAccountingClient.apply(checked, checkedInputs, reason.trim()); }
    catch (error) { const rejected = error instanceof ApiHttpError && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429; setOutcomeUnknown(!rejected); throw error; }
    setPreview(checked); unsaved.markSaved(); setMessage(receipt.replayed ? '此筆已套用，已讀取原收據。' : '實際服務天數已儲存。若帳務有差異，請從本案正式帳務流程處理。');
    onSaved?.();
  }

  return <section className="import-workbench-card" aria-label="歷史訂單實際服務天數與帳務">
    <h2>🧮 歷史訂單實際服務天數與帳務</h2>
    <p>填寫每位月嫂的實際服務天數。重算金額供核對，原期款和核銷紀錄依正式帳務查閱。</p>
    <div className="import-result-title-row">
      {propCaseNo ? (
        <div>
          <span>案件編號：<strong>{propCaseNo}</strong></span>{' '}
          <button type="button" disabled={busy || !caseNo.trim()} onClick={() => void run(async () => { const result = await historicalServiceAccountingClient.query(caseNo.trim()); setFacts(result); setDays(Object.fromEntries(result.assignments.map((item) => [item.assignment_identity, '']))); setPreview(null); })}>重新查詢服務帳務</button>
        </div>
      ) : (
        <>
          <label>案件編號 <select aria-label="案件編號" value={caseNo} disabled={caseOptionsUnavailable || busy || outcomeUnknown} onChange={(event) => { const value = event.target.value; requestLeave(() => { setCaseNo(value); setFacts(null); setPreview(null); }); }}>
            <option value="">{casePlaceholder}</option>
            {orderSummaries.map((item) => <option key={item.case_no} value={item.case_no}>{item.case_no}｜{item.client_name}｜{item.order_status}</option>)}
          </select></label>
          <button type="button" disabled={busy || !caseNo.trim()} onClick={() => void run(async () => { const result = await historicalServiceAccountingClient.query(caseNo.trim()); setFacts(result); setDays(Object.fromEntries(result.assignments.map((item) => [item.assignment_identity, '']))); setPreview(null); })}>查詢服務帳務</button>
        </>
      )}
    </div>
    {facts && <div>
      <p>目前狀態：{facts.lifecycle_status}；原訂 {facts.contracted_service_days} 天；每日 {facts.service_hours_per_day} 小時。</p>
      {facts.assignments.map((item) => <label key={item.assignment_identity} style={{ display: 'block', marginBottom: 8 }}>{staffIdentity.label(item.staff_id, item.staff_name)}實際服務天數 <input type="number" min="1" step="1" value={days[item.assignment_identity] ?? ''} disabled={busy || outcomeUnknown} onChange={(event) => { setDays((current) => ({ ...current, [item.assignment_identity]: event.target.value })); setPreview(null); }} /></label>)}
      <label>更新原因（選填）<input value={reason} maxLength={500} disabled={busy || outcomeUnknown} onChange={event => setReason(event.target.value)} /></label>
      <button type="button" disabled={busy || outcomeUnknown || inputs().some((item) => !Number.isInteger(item.actual_service_days) || item.actual_service_days <= 0)} onClick={() => void run(save)}>儲存服務天數</button>
    </div>}
    {preview && <div className="import-result-state" role="status">
      <p>總實際服務 {preview.total_actual_service_days} 天；樓層費 {preview.historical_floor_fee_ntd.toLocaleString()} 元。</p>
      <p>重算供比較：客戶應付 {preview.client_obligation_amount_ntd.toLocaleString()} 元，月嫂應付合計 {preview.staff_obligation_amount_ntd.toLocaleString()} 元。</p>
      {preview.payroll_assignments.map((item) => <p key={item.assignment_identity}>{staffIdentity.label(item.staff_id, facts?.assignments.find(person => person.staff_id === item.staff_id)?.staff_name)}：{item.actual_service_days} 天，重算 {item.total_payable_ntd.toLocaleString()} 元。</p>)}
    </div>}
    {outcomeUnknown && <p role="alert">儲存結果尚未確認；請重新查詢服務帳務並核對目前資料，勿重複送出。</p>}
    {message && <p role="alert">{message}</p>}
  </section>;
};
