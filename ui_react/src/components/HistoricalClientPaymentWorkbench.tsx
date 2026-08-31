/** Client Finance owner workbench for bounded historical payment evidence. */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  historicalClientPaymentClient,
  HistoricalClientPaymentClientError,
  type HistoricalClientPaymentIntent,
  type HistoricalClientPaymentPreview,
  type HistoricalClientPaymentQuery,
  type HistoricalClientPaymentReadback,
} from '../api/client_finance/historical_client_payment_client';

export const HistoricalClientPaymentWorkbench: React.FC<{ caseNo: string }> = ({ caseNo }) => {
  const [query, setQuery] = useState<HistoricalClientPaymentQuery | null>(null);
  const [direction, setDirection] = useState<HistoricalClientPaymentIntent['direction']>('receivable_from_client');
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<'paid' | 'settled'>('paid');
  const [paymentDate, setPaymentDate] = useState('');
  const [unknownReason, setUnknownReason] = useState('原始付款日期無法可靠還原');
  const [sourceAvailability, setSourceAvailability] = useState<HistoricalClientPaymentIntent['source_availability']>('missing');
  const [evidenceReference, setEvidenceReference] = useState('');
  const [reason, setReason] = useState('已核對歷史案件與 exact obligations');
  const [preview, setPreview] = useState<HistoricalClientPaymentPreview | null>(null);
  const [readback, setReadback] = useState<HistoricalClientPaymentReadback | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const generation = useRef(0);
  const idempotency = useRef<string | null>(null);

  const load = useCallback(async () => {
    const current = ++generation.current; setBusy(true); setMessage(null);
    try { const value = await historicalClientPaymentClient.query(caseNo); if (current === generation.current) setQuery(value); }
    catch { if (current === generation.current) setMessage('歷史客戶付款候選目前無法取得。'); }
    finally { if (current === generation.current) setBusy(false); }
  }, [caseNo]);
  useEffect(() => { setQuery(null); setSelected([]); setPreview(null); setReadback(null); setConfirmed(false); idempotency.current = null; void load(); return () => { generation.current += 1; }; }, [load]);
  const obligations = useMemo(() => query?.obligations.filter((item) => item.direction === direction && item.status === 'open') ?? [], [direction, query]);
  const invalidate = () => { setPreview(null); setConfirmed(false); setReadback(null); idempotency.current = null; };
  const intent = (): HistoricalClientPaymentIntent => ({
    case_no: caseNo, direction, confirmation_kind: confirmation, obligation_identities: selected,
    payment_date: paymentDate || null, payment_date_unknown_reason: paymentDate ? null : unknownReason.trim() || null,
    source_availability: sourceAvailability, evidence_reference: evidenceReference.trim() || null,
  });
  const runPreview = async () => {
    if (!selected.length) { setMessage('請至少選擇一筆同方向義務。'); return; }
    setBusy(true); setMessage(null); setPreview(null); setConfirmed(false);
    try { const value = await historicalClientPaymentClient.preview(intent()); setPreview(value); if (!value.can_apply) setMessage(`目前不可提交：${value.blockers.join('、') || 'owner eligibility 未成立'}`); }
    catch { setMessage('預覽失敗；資料不會被修改。'); }
    finally { setBusy(false); }
  };
  const runApply = async () => {
    if (!preview?.can_apply || preview.adoption_receipt_id === null || !confirmed || !reason.trim()) return;
    setBusy(true); setMessage(null);
    const key = idempotency.current ?? `historical-client-${crypto.randomUUID()}`; idempotency.current = key;
    try {
      await historicalClientPaymentClient.apply(intent(), preview, reason.trim(), key);
      const fresh = await historicalClientPaymentClient.readback(caseNo); setReadback(fresh); setPreview(null); setConfirmed(false);
      setMessage(fresh.owner_terminal ? '已提交並重新確認 Client Finance 全部義務已結清。' : '已提交；仍有未結清的 Client Finance 義務。');
    } catch (error) {
      const stale = error instanceof HistoricalClientPaymentClientError && (error.status === 409 || error.code.toLowerCase().includes('stale'));
      setMessage(stale ? '資料已變更，請重新查詢並再次預覽。' : '結果目前無法安全確認；請先重新查詢，不要改用另一個操作。');
    } finally { setBusy(false); }
  };

  return <section className="finance-detail-block" aria-label="歷史客戶付款人工確認">
    <h3>歷史客戶付款人工確認</h3>
    <p>只供已採納的 pre-system 案件且銀行證據缺失、歸屬不明或無法還原時使用；正常銀行候選存在時請回銀行流水核銷。</p>
    {query?.normal_bank_candidate_identities.length ? <p role="alert">已找到正常銀行候選：{query.normal_bank_candidate_identities.join('、')}。歷史人工路徑應保持阻擋。</p> : null}
    <div className="finance-filter-bar">
      <label>方向<select value={direction} onChange={(event) => { setDirection(event.target.value as HistoricalClientPaymentIntent['direction']); setSelected([]); invalidate(); }}><option value="receivable_from_client">客戶付款給工會</option><option value="payable_to_client">工會付款給客戶</option></select></label>
      <label>確認類型<select value={confirmation} onChange={(event) => { setConfirmation(event.target.value as 'paid' | 'settled'); invalidate(); }}><option value="paid">已付款</option><option value="settled">已結清</option></select></label>
      <label>舊來源狀態<select value={sourceAvailability} onChange={(event) => { setSourceAvailability(event.target.value as HistoricalClientPaymentIntent['source_availability']); invalidate(); }}><option value="missing">缺失</option><option value="ambiguous">歸屬不明</option><option value="unrecoverable">無法可靠還原</option></select></label>
    </div>
    {obligations.map((item) => <label key={item.obligation_identity}><input type="checkbox" checked={selected.includes(item.obligation_identity)} onChange={(event) => { setSelected((values) => event.target.checked ? [...values, item.obligation_identity] : values.filter((value) => value !== item.obligation_identity)); invalidate(); }} /> {item.obligation_type}｜{item.obligation_identity}｜NT$ {item.amount_due_ntd.toLocaleString('zh-TW')}</label>)}
    {!busy && query && obligations.length === 0 ? <p>此方向目前沒有可處理的 open obligation。</p> : null}
    <div className="finance-filter-bar">
      <label>付款日期（不確定可留空）<input type="date" value={paymentDate} onChange={(event) => { setPaymentDate(event.target.value); invalidate(); }} /></label>
      {!paymentDate && <label>日期未知原因<input value={unknownReason} maxLength={500} onChange={(event) => { setUnknownReason(event.target.value); invalidate(); }} /></label>}
      <label>證據參考（選填）<input value={evidenceReference} maxLength={191} onChange={(event) => { setEvidenceReference(event.target.value); invalidate(); }} /></label>
    </div>
    <button type="button" disabled={busy || !query} onClick={() => void runPreview()}>預覽歷史付款影響</button>
    {preview && <div><p>本次 exact obligations：{preview.obligations.map((item) => item.obligation_identity).join('、')}</p><p>金額快照：NT$ {preview.amount_snapshot_ntd.toLocaleString('zh-TW')}</p>{preview.can_apply && <><label>原因<input value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} /></label><label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對方向、付款人／收款人、義務與金額</label><button type="button" disabled={busy || !confirmed || !reason.trim()} onClick={() => void runApply()}>確認並提交</button></>}</div>}
    {readback && <p>Fresh readback：{readback.owner_terminal ? 'Client Finance 已結清' : '仍有未結清義務'}（版本 {readback.account_version}）</p>}
    {message && <p role="status">{message}</p>}
    <button type="button" disabled={busy} onClick={() => void load()}>重新查詢 owner facts</button>
  </section>;
};
