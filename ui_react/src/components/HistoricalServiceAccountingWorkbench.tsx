import React, { useState } from 'react';
import { historicalServiceAccountingClient, type HistoricalCaregiverDays, type HistoricalServiceAccountingPreview, type HistoricalServiceAccountingQuery } from '../api/orders/historical_service_accounting_client';

export const HistoricalServiceAccountingWorkbench: React.FC = () => {
  const [caseNo, setCaseNo] = useState('');
  const [facts, setFacts] = useState<HistoricalServiceAccountingQuery | null>(null);
  const [days, setDays] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<HistoricalServiceAccountingPreview | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const inputs = (): HistoricalCaregiverDays[] => (facts?.assignments ?? []).map((item) => ({ assignment_identity: item.assignment_identity, staff_id: item.staff_id, actual_service_days: Number(days[item.assignment_identity]) }));
  const run = async (operation: () => Promise<void>) => { setBusy(true); setMessage(''); try { await operation(); } catch (error) { setMessage(error instanceof Error ? error.message : '處理失敗。'); } finally { setBusy(false); } };

  return <section className="import-workbench-card" aria-label="歷史訂單實際服務天數與帳務">
    <h2>🧮 歷史訂單實際服務天數與帳務</h2>
    <p>只填每位月嫂的實際服務天數；系統會以單薪計算應收應付，不建立逐日排班。</p>
    <div className="import-result-title-row">
      <label>案件編號 <input value={caseNo} onChange={(event) => { setCaseNo(event.target.value); setFacts(null); setPreview(null); }} /></label>
      <button type="button" disabled={busy || !caseNo.trim()} onClick={() => void run(async () => { const result = await historicalServiceAccountingClient.query(caseNo.trim()); setFacts(result); setDays(Object.fromEntries(result.assignments.map((item) => [item.assignment_identity, '']))); setPreview(null); })}>查詢服務帳務</button>
    </div>
    {facts && <div>
      <p>目前狀態：{facts.lifecycle_status}；原訂 {facts.contracted_service_days} 天；每日 {facts.service_hours_per_day} 小時。</p>
      {facts.assignments.map((item) => <label key={item.assignment_identity} style={{ display: 'block', marginBottom: 8 }}>{item.staff_name}（月嫂 ID {item.staff_id}）實際服務天數 <input type="number" min="1" step="1" value={days[item.assignment_identity] ?? ''} onChange={(event) => { setDays((current) => ({ ...current, [item.assignment_identity]: event.target.value })); setPreview(null); }} /></label>)}
      <button type="button" disabled={busy || inputs().some((item) => !Number.isInteger(item.actual_service_days) || item.actual_service_days <= 0)} onClick={() => void run(async () => setPreview(await historicalServiceAccountingClient.preview(facts.case_no, inputs())))}>預覽應收應付</button>
    </div>}
    {preview && <div className="import-result-state" role="status">
      <p>總實際服務 {preview.total_actual_service_days} 天；樓層費 {preview.historical_floor_fee_ntd.toLocaleString()} 元；雙薪 0 小時。</p>
      <p>客戶應收 {preview.client_obligation_amount_ntd.toLocaleString()} 元；月嫂應付合計 {preview.staff_obligation_amount_ntd.toLocaleString()} 元。</p>
      {preview.payroll_assignments.map((item) => <p key={item.assignment_identity}>月嫂 ID {item.staff_id}：{item.actual_service_days} 天，應付 {item.total_payable_ntd.toLocaleString()} 元。</p>)}
      <button type="button" disabled={busy} onClick={() => void run(async () => { const receipt = await historicalServiceAccountingClient.apply(preview, inputs(), '核對舊系統實際服務天數'); setMessage(receipt.replayed ? '此筆已套用，已讀取原收據。' : '實際服務天數與應收應付已建立。'); setPreview(null); })}>確認建立帳務</button>
    </div>}
    {message && <p role="alert">{message}</p>}
  </section>;
};
