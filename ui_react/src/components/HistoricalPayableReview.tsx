import { useEffect, useRef, useState, type FormEvent } from 'react';
import { accountsPayableQueryClient, type HistoricalUnpaidPayableCommand } from '../api/accounts_payable/accounts_payable_query_client';
import type { HistoricalPayableAuditItem } from '../api/accounts_payable/accounts_payable_query_schemas';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedChanges } from './UnsavedChanges';
import { financeMoney } from './FinanceReceiptsWorkspace';

const missingData = (item: HistoricalPayableAuditItem) =>
  ['date_not_formed', 'missing_calculation_basis', 'blocked'].includes(item.disposition);

export function HistoricalPayableLookup({ month, revision, onCase, caseNo }: {
  month: string;
  revision: number;
  onCase: (item: HistoricalPayableAuditItem) => void;
  caseNo?: string;
}) {
  const [keyword, setKeyword] = useState(caseNo ?? '');
  const [search, setSearch] = useState<{ keyword: string; month: string }>();
  const [result, setResult] = useState<{ items?: HistoricalPayableAuditItem[]; error?: string }>({});

  useEffect(() => {
    if (!search) return;
    const controller = new AbortController();
    setResult({});
    void accountsPayableQueryClient.lookupHistorical(search.keyword, search.month, controller.signal).then(items => {
      if (!controller.signal.aborted) setResult({ items: caseNo ? items.filter(item => item.case_no === caseNo) : items });
    }).catch(error => {
      if (!controller.signal.aborted) setResult({ error: error instanceof ApiHttpError
        ? error.message : '無法查核應付清冊，請稍後重試。' });
    });
    return () => controller.abort();
  }, [caseNo, search, revision]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (keyword.trim() && month) setSearch({ keyword: keyword.trim(), month });
  }

  return <details className="case-accounting-card">
    <summary>查未列入原因</summary>
    <form className="finance-filter-bar" onSubmit={submit}>
      {!caseNo && <label>案號、月嫂完整姓名或公會編號
        <input className="finance-input" value={keyword} maxLength={50}
          onChange={event => setKeyword(event.target.value)} required />
      </label>}
      <button type="submit" className="finance-btn-secondary" disabled={!keyword.trim() || !month}>查核歷史月嫂款</button>
    </form>
    {search && <p>付款月份 {search.month}。缺少付款日的案件也會列在查核結果。</p>}
    {search && !result.items && !result.error && <p role="status">正在查核…</p>}
    {result.error && <p role="alert">{result.error}</p>}
    {result.items?.length === 0 && <p role="status">找不到相符的歷史月嫂款。</p>}
    {result.items?.map(item => <div key={`${item.case_no}:${item.staff_id}:${item.obligation_identity}:${item.effective_due_date}`}>
      <strong>{item.case_no} · {item.recipient_name ?? '月嫂待確認'}</strong>
      <p>{missingData(item) ? '待確認 · ' : ''}{item.reason}
        {' '}付款日 {item.effective_due_date ?? '待確認'} · 待付 {financeMoney(item.balance_ntd)}
        {' '}· {item.source === 'formal_obligation' ? '正式應付' : '案件來源'}</p>
      <button type="button" className="finance-btn-secondary" onClick={() => onCase(item)}>
        {caseNo ? '處理這筆款項' : '查看本案帳務'}
      </button>
    </div>)}
  </details>;
}

export function HistoricalPayableEditor({ item, onSaved }: { item: HistoricalPayableAuditItem; onSaved: () => void }) {
  if (item.disposition !== 'paid_or_settled' && (!item.obligation_identity || item.effective_due_date === null)) {
    return <HistoricalPayableSync item={item} onSaved={onSaved} />;
  }
  return <HistoricalPayableCorrection item={item} onSaved={onSaved} />;
}

function HistoricalPayableSync({ item, onSaved }: { item: HistoricalPayableAuditItem; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  async function synchronize() {
    setBusy(true);
    setMessage('');
    try {
      const result = await accountsPayableQueryClient.synchronizeHistorical(item.case_no);
      if (result === 'created' || result === 'updated' || result === 'already_synced') {
        setMessage('已查回月嫂應付，清冊將重新讀取。');
        onSaved();
      } else {
        setMessage(historicalSyncMessages[result ?? ''] ?? '本案目前無法同步，請重新查核案件狀態。');
      }
    } catch {
      setMessage('無法確認同步結果，請重新查核本案。');
    } finally {
      setBusy(false);
    }
  }

  return <section className="case-accounting-card" aria-label="歷史月嫂款查核">
    <h3>{item.recipient_name ?? '月嫂待確認'} · 應付清冊查核</h3>
    <p>{item.reason}</p>
    <button type="button" className="finance-btn-primary" disabled={busy} onClick={() => void synchronize()}>
      {busy ? '同步中…' : '同步月嫂應付'}
    </button>
    {message && <p role="status">{message}</p>}
  </section>;
}

const historicalSyncMessages: Record<string, string> = {
  historical_payroll_unique_assignment_required: '請確認本案唯一的歷史月嫂指派。',
  historical_payroll_obligation_binding_conflict: '現有應付與歷史指派不一致，請查核原應付歸屬。',
  historical_payroll_original_payment_preserved: '本案已有付款或結清紀錄，請查核原付款證據。',
  historical_payroll_settled_source_required: '本案已標記帳務完成，請查核原付款及應付證據。',
  historical_payroll_service_basis_missing: '請查核 HCM 服務天數、每日服務時數和歷史結束日。',
  payroll_rate_policy_not_found: '請查核本案保存的月嫂時薪。',
  historical_payroll_nonpositive_amount: '計算出的月嫂應付金額須大於零，請查核計算依據。',
  historical_payroll_funding_conflict: '請查核本案自費與直接補助的付款來源。',
};

function HistoricalPayableCorrection({ item, onSaved }: { item: HistoricalPayableAuditItem; onSaved: () => void }) {
  const [amount, setAmount] = useState(item.amount_due_ntd?.toString() ?? '');
  const [dueDate, setDueDate] = useState(item.effective_due_date ?? '');
  const [evidence, setEvidence] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const command = useRef<HistoricalUnpaidPayableCommand | null>(null);
  const validAmount = /^\d+$/.test(amount) && Number(amount) > 0 && Number(amount) <= 9999999999;
  const targetKnown = item.staff_id !== null && item.current_event_id !== null;
  const editable = targetKnown && item.disposition !== 'paid_or_settled' && item.balance_ntd === item.amount_due_ntd;
  const title = '更正應付';

  useUnsavedChanges(title, saved ? [] : [
    { label: '原應付金額', before: item.amount_due_ntd?.toString() ?? '', after: amount },
    { label: '付款日', before: item.effective_due_date ?? '', after: dueDate },
    { label: '原帳務依據', before: '', after: evidence },
  ].filter(change => change.before !== change.after), { busy: busy || unknown });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || saved || !editable || item.staff_id === null) return;
    if (!command.current) {
      if (!confirmed || !validAmount || !evidence.trim()) return;
      command.current = {
        staff_id: item.staff_id, obligation_identity: item.obligation_identity, expected_event_id: item.current_event_id,
        amount_ntd: Number(amount), due_date: dueDate || null, evidence: evidence.trim(),
        confirmed_unpaid: true, key: crypto.randomUUID(),
      };
    }
    setBusy(true);
    setError('');
    try {
      await accountsPayableQueryClient.recordHistoricalUnpaid(item.case_no, command.current);
      setUnknown(false);
      setSaved(true);
      onSaved();
    } catch (error) {
      const unresolved = !(error instanceof ApiHttpError) || error.status >= 500 || error.status === 408;
      setUnknown(unresolved);
      if (!unresolved) command.current = null;
      setError(unresolved ? '結果尚未確認，請查回原次處理結果。'
        : error instanceof ApiHttpError && error.status === 403 ? '目前沒有補登或更正應付的權限。'
          : '本案帳務已變動，或有付款、分筆、金額控制等關聯須另行查核。請回清冊重新查核。');
    } finally {
      setBusy(false);
    }
  }

  return <section className="case-accounting-card" aria-label="歷史月嫂款查核">
    <h3>{item.recipient_name ?? '月嫂待確認'} · 應付清冊查核</h3>
    <p>{item.reason}</p>
    {item.disposition === 'blocked' && <p>缺少收款帳戶時，請到 <a href="#staff">服務人員名冊</a> 查核這位月嫂。</p>}
    <p>如需更正服務天數，請到 <a href={`#clients?case=${encodeURIComponent(item.case_no)}`}>本案客戶名冊</a> 查核。</p>
    {saved ? <p role="status">原應付已更新，清冊查核結果已重新讀取。</p>
      : editable ? <form onSubmit={submit}>
        <p>更正前請先核對原薪資、付款日及付款紀錄。已付款或付款狀態不明的款項須先查核。</p>
        <fieldset disabled={busy || unknown} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', border: '1px solid #ebdcd1', borderRadius: '8px', padding: '16px', margin: '14px 0' }}>
          <legend style={{ fontWeight: 700, padding: '0 8px' }}>{title}</legend>
          <label style={{ display: 'grid', gap: '6px' }}>原應付金額<input className="finance-input" type="number" min="1" max="9999999999" step="1" required value={amount}
            onChange={event => { setAmount(event.target.value); setConfirmed(false); }} /></label>
          <label style={{ display: 'grid', gap: '6px' }}>原付款日<input className="finance-input" type="date" value={dueDate}
            onChange={event => { setDueDate(event.target.value); setConfirmed(false); }} /></label>
          <label style={{ display: 'grid', gap: '6px', gridColumn: '1 / -1' }}>原帳務依據<textarea className="finance-input" style={{ minHeight: '64px', resize: 'vertical' }} required maxLength={500} value={evidence}
            onChange={event => { setEvidence(event.target.value); setConfirmed(false); }} /></label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', gridColumn: '1 / -1' }}><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />
            已核對原帳務及付款紀錄，確認這筆款項全額未付</label>
        </fieldset>
        <button type="submit" className="finance-btn-primary"
          disabled={busy || (!unknown && (!confirmed || !validAmount || !evidence.trim()))}>
          {busy ? '處理中…' : unknown ? '查回原次處理結果' : title}
        </button>
        {error && <p role="alert">{error}</p>}
      </form> : <p>請先核對月嫂歸屬或既有付款證據。已收付交易可由本案的手動補登或銀行對帳處理。</p>}
  </section>;
}
