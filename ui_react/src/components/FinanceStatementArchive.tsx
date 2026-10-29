import { useRef, useState } from 'react';
import { financeAccountingClient, statementColumns } from '../api/finance_import/finance_accounting_client';
import './FinanceCaseAccounting.css';
import { useUnsavedDraft } from './UnsavedChanges';
import { ApiHttpError } from '../api/shared/typed_errors';

export function FinanceStatementArchive() {
  const [fields, setFields] = useState<Record<string, string>>({});
  const [duplicateOf, setDuplicateOf] = useState('');
  const [candidate, setCandidate] = useState('');
  const [kept, setKept] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [pendingKind, setPendingKind] = useState<'manual' | 'duplicate' | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const commands = useRef(new Map<string, string>());
  useUnsavedDraft('人工對帳明細', { '尚有未保存資料': Object.values(fields).some(Boolean) || Boolean(duplicateOf) }, {
    baseline: { '尚有未保存資料': false }, busy: busy || unknown, save: saveManual,
    discard: () => { setFields({}); setDuplicateOf(''); },
  });
  useUnsavedDraft('重複明細處理', { '尚有未保存資料': Boolean(candidate || kept || confirmed) }, { baseline: { '尚有未保存資料': false }, busy: busy || unknown, save: saveDuplicate, discard: () => { setCandidate(''); setKept(''); setConfirmed(false); } });
  function key(payload: unknown) { const source = JSON.stringify(payload); let value = commands.current.get(source); if (!value) { value = crypto.randomUUID(); commands.current.set(source, value); } return value; }
  async function perform(action: () => Promise<string>, mutation: 'manual' | 'duplicate' | null = null) {
    if (busy || (pendingKind && mutation !== pendingKind)) return;
    if (mutation) setPendingKind(mutation);
    setBusy(true); setMessage(''); setError('');
    try { setMessage(await action()); if (mutation) { setUnknown(false); setPendingKind(null); } }
    catch (caught) { const uncertain = !!mutation && (!(caught instanceof ApiHttpError) || caught.status >= 500 || caught.status === 408); setUnknown(uncertain); if (!uncertain) setPendingKind(null); setError(uncertain ? '儲存結果尚未確認；請重試原儲存，確認前保留本畫面。' : '操作失敗，請檢查必填資料後重試。'); }
    finally { setBusy(false); }
  }
  async function saveManual() {
    await perform(async () => {
      const values = Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== ''));
      const result = await financeAccountingClient.manual(values, key({ values, duplicateOf }), duplicateOf.trim());
      setFields({}); setDuplicateOf(''); commands.current.clear();
      return result.excluded_count ? '重複明細已排除，只保留既存的一筆。' : '人工明細已保存，未新增案件帳務。';
    }, 'manual');
  }
  async function saveDuplicate() {
    if (!confirmed || !candidate.trim() || !kept.trim()) { setError('請指定兩筆明細並確認為同一筆交易。'); return; }
    await perform(async () => { await financeAccountingClient.duplicate(candidate.trim(), kept.trim(), key({ candidate, kept })); setCandidate(''); setKept(''); setConfirmed(false); return '重複明細已排除；匯出只保留既存明細，正式帳務保持不變。'; }, 'duplicate');
  }
  const required = ['交易日', '支出', '存入', '銷帳編號', '備註'];
  const fieldInput = (column: string) => <label key={column}>{column}{column === '交易日' ? '（必填）' : ''}<input disabled={busy || unknown} type={['交易日', '計息日', '入帳日'].includes(column) ? 'date' : 'text'} inputMode={['支出', '存入', '餘額'].includes(column) ? 'decimal' : undefined} required={column === '交易日'} value={fields[column] ?? ''} onChange={event => setFields(value => ({ ...value, [column]: event.target.value }))} /></label>;
  return <section className="case-accounting-card" aria-label="成功對帳明細">
    <div className="finance-section-heading"><div><h3>成功對帳明細</h3><p>匯出全部已正式入帳與人工新增明細；可在 Excel 使用篩選查找。</p></div><button type="button" className="finance-btn-primary" disabled={busy} onClick={() => void perform(async () => { const blob = await financeAccountingClient.download(); const url = URL.createObjectURL(blob); try { const anchor = document.createElement('a'); anchor.href = url; anchor.download = '銀行成功對帳明細.xlsx'; anchor.click(); } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); } return '成功明細已匯出。'; })}>匯出全部對帳明細</button></div>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <details><summary>人工新增明細</summary><form onSubmit={event => { event.preventDefault(); void saveManual(); }}>
      <p>必填：交易日、支出或存入擇一、銷帳編號或備註至少一項。其他欄位可留白。</p>
      <div className="statement-fields">{required.map(fieldInput)}</div>
      <details><summary>其他原始欄位（選填）</summary><div className="statement-fields">{statementColumns.filter(column => !required.includes(column)).map(fieldInput)}</div></details>
      <label>若已確認與既存明細重複，填入匯出檔的明細識別（選填）<input disabled={busy || unknown} value={duplicateOf} onChange={event => setDuplicateOf(event.target.value)} /></label>
      <p><button disabled={busy || pendingKind === 'duplicate'} className="finance-btn-primary">保存人工明細</button></p>
    </form></details>
    <details><summary>處理已確認的重複明細</summary><form onSubmit={event => { event.preventDefault(); void saveDuplicate(); }}>
      <p>依匯出檔的「明細識別」指定後到的銀行明細與既存明細；請先核對原始內容。</p>
      <div className="statement-fields"><label>後到的銀行明細識別<input disabled={busy || unknown} required placeholder="bank:…" value={candidate} onChange={event => { setCandidate(event.target.value); setConfirmed(false); }} /></label><label>保留的既存明細識別<input disabled={busy || unknown} required value={kept} onChange={event => { setKept(event.target.value); setConfirmed(false); }} /></label></div>
      <label><input disabled={busy || unknown} type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /> 已確認兩者為同一筆交易，保留既存明細</label>
      <p><button className="finance-btn-secondary" disabled={busy || !confirmed || pendingKind === 'manual'}>確認排除重複</button></p>
    </form></details>
  </section>;
}
