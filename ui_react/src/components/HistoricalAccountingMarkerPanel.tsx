import { useRef, useState } from 'react';
import { monthlyAccountingClient, type HistoricalAccountingMarker } from '../api/finance_import/monthly_accounting_client';
import type { CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { useUnsavedDraft } from './UnsavedChanges';

export function HistoricalAccountingMarkerPanel({ data, onMarked }: { data: CaseAccounting; onMarked: (marker: HistoricalAccountingMarker) => void }) {
  const [marker, setMarker] = useState(data.historical_marker ?? null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState('');
  const command = useRef<{ key: string; reason: string; versions: Record<string, string> } | null>(null);
  useUnsavedDraft('歷史案件人工核銷', { '確認說明': reason, '已確認無法查明': confirmed ? '是' : '' }, { baseline: { '確認說明': '', '已確認無法查明': '' }, enabled: !marker, busy: busy || unknown, discard: () => { setReason(''); setConfirmed(false); } });
  function accept(value: HistoricalAccountingMarker) { if (value.case_no !== data.case_no) throw new Error('案件標記與目前案件不符。'); setMarker(value); setUnknown(false); onMarked(value); }
  async function queryOriginal() {
    setBusy(true); setError('');
    try {
      const value = await monthlyAccountingClient.marker(data.case_no);
      if (value) accept(value);
      else if (command.current) {
        const original = command.current;
        accept(await monthlyAccountingClient.mark(data.case_no, original.reason, original.versions, original.key));
      }
    }
    catch { setError('案件標記結果暫時無法查明，請稍後再查詢。'); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!confirmed || !reason.trim() || busy || unknown) return;
    const saved = command.current;
    if (!saved || saved.reason !== reason) command.current = { key: crypto.randomUUID(), reason, versions: Object.fromEntries([...data.client_items, ...data.staff_items].map(item => [item.identity, item.version])) };
    const current = command.current!; setBusy(true); setError('');
    try { accept(await monthlyAccountingClient.mark(data.case_no, current.reason, current.versions, current.key)); }
    catch (failure) { const status = Number((failure as { status?: number }).status ?? 0); const uncertain = status === 0 || status >= 500; setUnknown(uncertain); setError(status === 409 ? '帳務資料或案件標記已變更；請重新讀取本案後確認，說明已保留。' : uncertain ? '尚未確認是否已保存，請先查詢案件標記，不要建立另一筆操作。' : status === 401 || status === 403 ? '目前登入狀態或權限無法保存，請確認登入後再試。' : '未能保存，請確認已勾選歷史差額確認，並填寫有效的確認說明。'); }
    finally { setBusy(false); }
  }
  return <section className="case-accounting-card" aria-label="歷史案件人工核銷"><h3>歷史案件人工核銷</h3><p>人員已確認無法查明歷史金額差異，才使用此選項。只標記案件帳務已人工核銷，不補足實際收付，也不直接列工會損失或盈餘。</p>
    {marker ? <div className="finance-scope-note"><strong>案件帳務已人工核銷</strong><p>整案金額不納入統計；原始資料及差額保留。此標記不表示訂單或服務已完成。</p><p>{marker.reason}</p><small>{marker.actor} · {marker.created_at}</small></div> : <form className="finance-marker-form" onSubmit={event => { event.preventDefault(); void submit(); }}><label><input type="checkbox" required checked={confirmed} disabled={busy || unknown} onChange={event => setConfirmed(event.target.checked)} /> 我已確認本案為歷史差額，且原因無法查明</label><label>確認說明<textarea required rows={3} maxLength={500} disabled={busy || unknown} value={reason} onChange={event => setReason(event.target.value)} /></label><button className="finance-btn-primary" disabled={!confirmed || !reason.trim() || busy || unknown}>標記案件帳務已人工核銷</button></form>}
    {marker?.amounts && <details><summary>人工核銷當時的金額與差額</summary><div className="finance-table-container"><table className="finance-table"><thead><tr><th>款項識別</th><th>方向</th><th>原應收／應付</th><th>原已收／已付</th><th>原待收／待付</th></tr></thead><tbody>{marker.amounts.map(item=><tr key={item.identity}><td>{item.identity}</td><td>{item.direction==='receivable'?'收':'付'}</td><td>{item.expected_ntd.toLocaleString('zh-TW')}</td><td>{item.actual_ntd.toLocaleString('zh-TW')}</td><td>{item.remaining_ntd.toLocaleString('zh-TW')}</td></tr>)}</tbody></table></div></details>}
    {error && <p role="alert">{error}</p>}{unknown && <><p>保留原操作鍵與原內容，查詢或確認同一筆案件標記，不建立新操作。</p><button type="button" className="finance-btn-secondary" disabled={busy} onClick={() => void queryOriginal()}>確認原操作結果</button></>}
  </section>;
}
