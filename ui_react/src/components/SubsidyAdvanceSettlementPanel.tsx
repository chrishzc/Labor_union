/** Government receipts recover an existing union advance; no customer payout. */
import { useEffect, useRef, useState } from 'react';
import {
  subsidyAdvanceSettlementClient as client,
  type AdvanceSettlementRow, type AdvanceSettlementPreview, type AdvanceSettlementApply,
} from '../api/client_finance/subsidy_advance_settlement_client';
import { ApiHttpError } from '../api/shared/typed_errors';

const labels = { waiting_receipt: '待政府入款', ready: '可銷帳', recovered: '已銷帳', review_required: '需核對' };
const reasons: Record<string, string> = {
  reversed_source: '墊款或政府入款已有沖正，請核對原帳務。',
  owner_facts_incomplete: '缺少正式結案或帳務資料。',
  advance_obligation_not_unique: '墊款與客戶補助退還義務的對應待確認。',
  entitlement_not_unique: '尚無唯一的正式補助申請對應。',
  receipt_not_unique: '政府入款與原墊款的對應不唯一。',
  allocation_evidence_missing: '缺少可核對的政府入款分配證據。',
  amount_mismatch: '政府核准、入款或原墊款金額不一致。',
  recovery_mismatch: '既有回收紀錄與來源不一致，請核對。',
};
const money = (value: number) => `NT$ ${value.toLocaleString('zh-TW')}`;
function errorText(error: unknown) {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '請先登入後再操作。';
    if (error.status === 403) return '目前帳號沒有處理墊款銷帳的權限。';
    if (error.status === 409) return '資料已變更或不符合銷帳條件，請重新查詢並再次預覽。';
  }
  return '銷帳資料暫時無法取得，請重新查詢。';
}
type Result = { kind: 'loading' } | { kind: 'ready'; rows: AdvanceSettlementRow[] } | { kind: 'error' };
type Command = { advanceId: number; caseNo: string; amount: number; key: string; body: AdvanceSettlementApply };

export function SubsidyAdvanceSettlementPanel({ initialCaseNo = '', onOpenImport, compact = false, onLockedChange, onSettled }: {
  initialCaseNo?: string; onOpenImport: () => void; compact?: boolean;
  onLockedChange?: (locked: boolean) => void; onSettled?: () => void;
}) {
  const [draft, setDraft] = useState(initialCaseNo);
  const [search, setSearch] = useState(initialCaseNo);
  const [status, setStatus] = useState('all');
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState<Result>({ kind: 'loading' });
  const [preview, setPreview] = useState<AdvanceSettlementPreview | null>(null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const command = useRef<Command | null>(null);
  const action = useRef<AbortController | null>(null);
  const previewHeading = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => () => action.current?.abort(), []);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);
  useEffect(() => {
    const controller = new AbortController();
    setResult({ kind: 'loading' });
    void client.queryAll(search, controller.signal)
      .then(rows => { if (!controller.signal.aborted) setResult({ kind: 'ready', rows: compact ? rows.filter(row => row.case_no === initialCaseNo) : rows }); })
      .catch(caught => { if (!controller.signal.aborted) { setResult({ kind: 'error' }); setError(errorText(caught)); } });
    return () => controller.abort();
  }, [search, reload, compact, initialCaseNo]);
  useEffect(() => { onLockedChange?.(busy || unknown); }, [busy, unknown, onLockedChange]);

  const resetPreview = () => { action.current?.abort(); setPreview(null); setConfirmed(false); setReason(''); command.current = null; setNotice(null); setError(null); };
  const openPreview = async (row: AdvanceSettlementRow) => {
    resetPreview(); setError(null); setBusy(true);
    const controller = new AbortController(); action.current = controller;
    try { const value = await client.preview(row.advance_id, controller.signal); if (!controller.signal.aborted) setPreview(value); }
    catch (caught) { if (!controller.signal.aborted) setError(errorText(caught)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const readOutcome = async (submitted: Command, signal: AbortSignal) => {
    const rows = await client.queryAll(submitted.caseNo, signal);
    const fresh = rows.find(row => row.advance_id === submitted.advanceId);
    if (signal.aborted) return;
    if (fresh?.status === 'recovered' && fresh.recovered_amount_ntd === submitted.amount) {
      setUnknown(false); setPreview(null); setConfirmed(false); command.current = null;
      setNotice(`${submitted.caseNo} 已銷帳 ${money(fresh.recovered_amount_ntd)}，已重新查詢確認。`);
      setReload(value => value + 1);
      onSettled?.();
    } else if (fresh?.status === 'ready') {
      setUnknown(false); setNotice('重新查詢後仍未銷帳，可安全重試原操作。');
    } else {
      setUnknown(true); setError('尚無法確認本次銷帳結果，請重新查詢銷帳結果；資料不一致時須先核對。');
    }
  };
  const apply = async () => {
    if (!preview || !confirmed || !reason.trim() || busy || unknown) return;
    const submitted = command.current ?? {
      advanceId: preview.row.advance_id, caseNo: preview.row.case_no, amount: preview.row.advance_amount_ntd,
      key: `advance-settlement:${crypto.randomUUID()}`,
      body: { expected_account_version: preview.account_version, expected_batch_version: preview.batch_version,
        preview_fingerprint: preview.preview_fingerprint, reason: reason.trim() },
    };
    command.current = submitted;
    const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(null); setNotice(null);
    try {
      const receipt = await client.apply(submitted.advanceId, submitted.body, submitted.key, controller.signal);
      if (receipt.case_no !== submitted.caseNo || receipt.recovered_amount_ntd !== submitted.amount) throw new Error('receipt mismatch');
      await readOutcome(submitted, controller.signal);
    } catch (caught) {
      if (controller.signal.aborted) return;
      if (caught instanceof ApiHttpError && [401, 403, 404, 409, 422].includes(caught.status)) {
        setError(errorText(caught)); setPreview(null); setConfirmed(false); command.current = null; setReload(value => value + 1);
      } else {
        setUnknown(true); setError('本次銷帳結果尚未確認，請先重新查詢銷帳結果。');
      }
    } finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const checkOutcome = async () => {
    if (!command.current || busy) return;
    const controller = new AbortController(); action.current = controller;
    setBusy(true); setError(null);
    try { await readOutcome(command.current, controller.signal); }
    catch (caught) { if (!controller.signal.aborted) setError(errorText(caught)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const rows = result.kind === 'ready' ? result.rows.filter(row => status === 'all' || row.status === status) : [];
  const locked = busy || unknown;

  return <section className={compact ? 'finance-advance-detail' : 'finance-workspace subsidy-refund-panel'} aria-labelledby="advance-settlement-heading">
    <div className="finance-section-heading">
      <div><h2 id="advance-settlement-heading">{compact ? '工會墊款與回收' : '代墊補助款銷帳清冊'}</h2>{!compact && <p>核對政府入款，沖回工會先前墊付給客戶的補助款。</p>}</div>
      {!compact && <button type="button" className="finance-reload-btn" disabled={locked} onClick={onOpenImport}>前往銀行交易明細匯入</button>}
    </div>
    {!compact && <p className="subsidy-refund-note">僅列已正式入帳的工會墊款。政府入款須先完成案件分配；銷帳只記錄墊款回收，不會再次退款給客戶。</p>}
    {!compact && <form className="subsidy-refund-case-form" onSubmit={event => { event.preventDefault(); resetPreview(); setSearch(draft.trim()); setReload(value => value + 1); }}>
      <label>客戶姓名或案件編號<input className="finance-input" disabled={locked} maxLength={100} value={draft} onChange={event => setDraft(event.target.value)} placeholder="輸入姓名或案件編號" /></label>
      <label>銷帳狀態<select className="finance-input" disabled={locked} value={status} onChange={event => { resetPreview(); setStatus(event.target.value); }}><option value="all">全部</option>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <button type="submit" disabled={locked} className="finance-btn-primary">查詢</button>
      <button type="button" disabled={locked} className="finance-reload-btn" onClick={() => { resetPreview(); setReload(value => value + 1); }}>重新查詢</button>
    </form>}
    {error && <div className="finance-state error" role="alert">{error}</div>}
    {notice && <div className="finance-state" role="status">{notice}</div>}
    {unknown && <button type="button" className="finance-btn-primary" disabled={busy} onClick={() => void checkOutcome()}>重新查詢銷帳結果</button>}
    {busy && <p role="status">正在核對銷帳資料…</p>}
    {result.kind === 'loading' && <div className="finance-state" role="status">正在查詢工會墊款與政府入款…</div>}
    {result.kind === 'ready' && <>
      {!compact && <div className="finance-kpi-grid" role="group" aria-label="墊款銷帳摘要">
        <div className="finance-kpi-item"><span className="finance-kpi-label">原墊款合計</span><strong className="finance-kpi-value">{money(rows.reduce((total, row) => total + row.advance_amount_ntd, 0))}</strong></div>
        <div className="finance-kpi-item"><span className="finance-kpi-label">已回收合計</span><strong className="finance-kpi-value">{money(rows.reduce((total, row) => total + row.recovered_amount_ntd, 0))}</strong></div>
        <div className="finance-kpi-item"><span className="finance-kpi-label">可銷帳筆數</span><strong className="finance-kpi-value">{rows.filter(row => row.status === 'ready').length} 筆</strong></div>
      </div>}
      {compact ? <div className="finance-advance-timeline">{!rows.length && <p className="subsidy-refund-note">尚無正式工會墊款紀錄。</p>}{rows.map(row => <article key={row.advance_id}>
        <strong>{labels[row.status]}</strong><p>{row.advanced_on} 墊付 {money(row.advance_amount_ntd)}</p><p>政府已分配 {money(row.government_received_ntd)}{row.received_on ? `（${row.received_on}）` : ''}；已回收 {money(row.recovered_amount_ntd)}</p>
        {row.review_reason && <p>{reasons[row.review_reason] ?? '來源資料待人工核對。'}</p>}
        {row.status === 'ready' && <button type="button" className="finance-btn-primary" disabled={locked} aria-label={`預覽 ${row.case_no} 銷帳`} onClick={() => void openPreview(row)}>預覽銷帳</button>}
      </article>)}</div> : !rows.length ? <div className="finance-state">沒有符合條件的正式墊款。尚未付款或只有預估退款的案件不會列入。</div> : <div className="finance-table-container"><table className="finance-table">
        <caption className="subsidy-refund-caption">依正式墊款、政府入款分配與回收紀錄核對。</caption>
        <thead><tr><th scope="col">客戶／案件</th><th scope="col">墊款日期</th><th scope="col">原墊款</th><th scope="col">政府入款分配</th><th scope="col">已回收</th><th scope="col">狀態／核對事項</th><th scope="col">操作</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.advance_id}>
          <td><strong>{row.client_name}</strong><br />{row.case_no}</td><td>{row.advanced_on}</td>
          <td className="subsidy-refund-money">{money(row.advance_amount_ntd)}</td>
          <td>{money(row.government_received_ntd)}<br />{row.received_on ?? '日期待確認'}</td>
          <td>{money(row.recovered_amount_ntd)}</td><td>{labels[row.status]}{row.review_reason && <p className="advance-settlement-reason">{reasons[row.review_reason] ?? '來源資料待人工核對。'}</p>}</td>
          <td>{row.status === 'ready' && <button type="button" className="subsidy-refund-case-button" disabled={locked || result.kind !== 'ready'} aria-label={`預覽 ${row.case_no} 銷帳`} onClick={() => void openPreview(row)}>預覽銷帳</button>}</td>
        </tr>)}</tbody>
      </table></div>}
    </>}
    {preview && <section className="advance-settlement-preview" aria-label="墊款銷帳預覽">
      <h3 ref={previewHeading} tabIndex={-1}>確認墊款回收</h3><p>{preview.row.client_name}｜{preview.row.case_no}</p>
      <p>原墊款：<strong>{money(preview.row.advance_amount_ntd)}</strong>｜政府入款分配：<strong>{money(preview.row.government_received_ntd)}</strong></p>
      <p>本次銷帳：<strong>{money(preview.row.advance_amount_ntd)}</strong>。完成後建立正式回收關聯，客戶退款紀錄維持原結果。</p>
      <label className="advance-settlement-field">核對說明<textarea className="finance-input" disabled={locked || command.current !== null} maxLength={500} value={reason} onChange={event => { setReason(event.target.value); setConfirmed(false); }} /></label>
      <label className="advance-settlement-confirm"><input type="checkbox" disabled={locked} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />我已核對原墊款與政府入款，確認建立回收銷帳。</label>
      <div className="subsidy-refund-period"><button type="button" className="finance-btn-primary" disabled={locked || !confirmed || !reason.trim()} onClick={() => void apply()}>{busy ? '處理中…' : '確認銷帳'}</button><button type="button" className="finance-reload-btn" disabled={locked} onClick={resetPreview}>取消</button></div>
    </section>}
  </section>;
}
