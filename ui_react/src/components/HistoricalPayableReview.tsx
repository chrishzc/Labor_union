import { useEffect, useRef, useState, type FormEvent } from 'react';
import { accountsPayableQueryClient, type HistoricalPayrollSyncItem, type HistoricalUnpaidPayableCommand } from '../api/accounts_payable/accounts_payable_query_client';
import type { HistoricalPayableAuditItem } from '../api/accounts_payable/accounts_payable_query_schemas';
import { financeAccountingClient, type CaseAccounting } from '../api/finance_import/finance_accounting_client';
import { ApiDecodeError, ApiHttpError } from '../api/shared/typed_errors';
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

interface HistoricalPayableEditorProps {
  item: HistoricalPayableAuditItem;
  onSaved: () => void;
  recheckRequired?: boolean;
  onRecheckRequired?: (caseNo: string) => void;
}

export function HistoricalPayableEditor(props: HistoricalPayableEditorProps) {
  const { item, onSaved, recheckRequired } = props;
  const useSync = item.disposition !== 'paid_or_settled' && (!item.obligation_identity || item.effective_due_date === null);
  if (useSync) return <HistoricalPayableSync {...props} />;
  if (recheckRequired) return <>
    <HistoricalPayableSync {...props} />
    {item.disposition !== 'paid_or_settled' && <details className="case-accounting-card">
      <summary>查看更正應付</summary>
      <HistoricalPayableCorrection item={item} onSaved={onSaved} />
    </details>}
  </>;
  return <HistoricalPayableCorrection item={item} onSaved={onSaved} />;
}

type HistoricalPayableSyncState =
  | { kind: 'sync'; messages: string[] }
  | { kind: 'syncing' }
  | { kind: 'recheck'; messages: string[] }
  | { kind: 'rechecking' };

const historicalRecheckPending = '正式應付待確認。';

function HistoricalPayableSync({ item, onSaved, recheckRequired, onRecheckRequired }: HistoricalPayableEditorProps) {
  const [localState, setState] = useState<HistoricalPayableSyncState>({ kind: 'sync', messages: [] });
  const state: HistoricalPayableSyncState = recheckRequired && localState.kind === 'sync'
    ? { kind: 'recheck', messages: ['同步結果尚未確認，請重新查核所選月嫂。'] }
    : localState;

  function requireRecheck(message: string) {
    setState({ kind: 'recheck', messages: [message] });
    onRecheckRequired?.(item.case_no);
  }

  async function synchronize() {
    if (state.kind !== 'sync') return;
    setState({ kind: 'syncing' });
    let result: Awaited<ReturnType<typeof accountsPayableQueryClient.synchronizeHistorical>>;
    try {
      result = await accountsPayableQueryClient.synchronizeHistorical(item.case_no);
    } catch (error) {
      if (error instanceof ApiHttpError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        setState({ kind: 'sync', messages: ['無法同步月嫂應付，請先查核案件狀態。'] });
      } else {
        requireRecheck('同步結果尚未確認，請重新查核本案。');
      }
      return;
    }
    if (!result) {
      requireRecheck('未取得正式同步回執，請重新查核本案。');
      return;
    }
    const outcomes = result.items?.length ? result.items : [result];
    if (!outcomes.some(outcome => outcome.action !== 'skipped' || outcome.obligation_identity)) {
      setState({ kind: 'sync', messages: outcomes.map(historicalSyncMessage) });
      return;
    }
    try {
      const accounting = await financeAccountingClient.query(item.case_no);
      setState({ kind: 'sync', messages: outcomes.map(outcome => historicalReadback(outcome, accounting)) });
    } catch {
      requireRecheck('尚未查回正式應付，請重新查核本案。');
      return;
    }
    onSaved();
  }

  async function recheck() {
    if (state.kind !== 'recheck') return;
    setState({ kind: 'rechecking' });
    try {
      const accounting = await financeAccountingClient.query(item.case_no);
      setState({ kind: 'recheck', messages: [historicalRecheckMessage(item, accounting)] });
    } catch (error) {
      const reason = error instanceof ApiDecodeError
        ? '回傳的案件或應付明細不一致，請在本案帳務核對。'
        : error instanceof ApiHttpError && (error.status === 401 || error.status === 403)
          ? '目前無法讀取本案帳務，請確認登入及查閱權限。'
          : '本次帳務查詢失敗，請再按重新查核。';
      setState({ kind: 'recheck', messages: [`${historicalRecheckPending} ${reason}`] });
    }
  }

  const recheckMode = state.kind === 'recheck' || state.kind === 'rechecking';
  const busy = state.kind === 'syncing' || state.kind === 'rechecking';
  const messages = 'messages' in state ? state.messages : [];

  return <section className="case-accounting-card" aria-label="歷史月嫂款查核">
    <h3>{item.recipient_name ?? '月嫂待確認'} · 應付清冊查核</h3>
    {!recheckMode && <p>{item.reason}</p>}
    {recheckMode
      ? <button type="button" className="finance-btn-secondary" disabled={busy} onClick={() => void recheck()}>
        {busy ? '查核中…' : '重新查核'}
      </button>
      : <button type="button" className="finance-btn-primary" disabled={busy} onClick={() => void synchronize()}>
        {busy ? '同步中…' : '同步月嫂應付'}
      </button>}
    {messages.length > 0 && <div role="status">{messages.map((message, index) => <p key={index}>{message}</p>)}</div>}
  </section>;
}

function historicalRecheckMessage(item: HistoricalPayableAuditItem, accounting: CaseAccounting): string {
  const pending = (detail: string) => `${historicalRecheckPending} ${detail}`;
  if (accounting.case_no !== item.case_no) return pending('回傳的案號與所選案件不同，請從清冊重開本案。');
  if (item.staff_id === null) return pending('清冊這一列沒有月嫂識別，請先在案件確認歷史服務歸屬。');

  const availability = accounting.staff_accounting_availability ?? [];
  const people = availability.filter(person => person.staff_id === item.staff_id);
  const [person] = people;
  if (people.length > 1) return pending('同一位月嫂有多筆歷史指派，請在案件核對服務歸屬。');
  if (!person || person.assignment_id === null || person.assignment_id <= 0) {
    return pending('本案帳務沒有回傳所選月嫂的有效歷史指派，請在案件核對服務歸屬。');
  }
  if (person.status !== 'formal') {
    const reasons = [...new Set(person.pending_reasons)].flatMap(reason => {
      const detail = historicalSyncMessages[reason] ?? historicalRecheckSourceMessages[reason];
      return detail ? [detail] : [];
    });
    if (reasons.length > 0) return pending(`本案尚無該指派的正式應付。 ${reasons.join(' ')}`);
    return pending('本案尚無該指派的正式應付，帳務未回傳原因。請在本案帳務核對服務量及計薪費率。');
  }
  const [identity] = person.obligation_identities;
  if (person.obligation_identities.length !== 1 || !identity?.trim() || availability.some(other => other !== person &&
    (other.assignment_id === person.assignment_id || other.obligation_identities.includes(identity)))) {
    return pending('本案已建帳，但無法唯一對上所選月嫂的指派與應付明細。請在本案帳務核對歸屬。');
  }
  const matches = accounting.staff_items.filter(row => row.identity === identity);
  const [payable] = matches;
  if (matches.length !== 1 || payable?.direction !== 'payable') {
    return pending('本案已建帳，但帳務查詢找不到對應的正式應付明細。請在本案帳務核對。');
  }
  const amount = `正式應付 ${financeMoney(payable.expected_ntd)}`;
  const portions = payable.funding_portions;
  if (!portions?.length) return `${amount} · 付款日 ${payable.due_date ?? '待確認'}`;
  const dates = portions.map(({ funding_kind, due_date }) =>
    `${funding_kind === 'client' ? '自備款' : '補助款'}付款日${due_date ? ` ${due_date}` : '待確認'}`,
  );
  return [amount, ...dates].join(' · ');
}

const historicalRecheckSourceMessages: Record<string, string> = {
  historical_payroll_assignment_source_missing: '請在案件核對歷史月嫂指派及服務歸屬。',
  historical_payroll_assignment_source_ambiguous: '歷史指派來源不唯一，請在案件核對服務歸屬。',
  historical_payroll_service_attribution_missing: '請先按月嫂確認各人的實際服務量。',
  historical_service_not_completed: '歷史服務尚未完成，請在完工後查核正式應付。',
};

const historicalSyncMessages: Record<string, string> = {
  historical_payroll_unique_assignment_required: '請確認本案唯一的歷史月嫂指派。',
  historical_payroll_obligation_binding_conflict: '現有應付與歷史指派不一致，請查核原應付歸屬。',
  historical_payroll_original_payment_preserved: '本案已有付款或結清紀錄，請查核原付款證據。',
  historical_payroll_settled_source_required: '本案已標記帳務完成，請查核原付款及應付證據。',
  historical_payroll_service_basis_missing: '請查核 HCM 服務天數、每日服務時數和歷史結束日。',
  payroll_rate_policy_not_found: '請查核本案保存的月嫂時薪。',
  historical_payroll_nonpositive_amount: '計算出的月嫂應付金額須大於零，請查核計算依據。',
  historical_payroll_funding_conflict: '請查核本案自費與直接補助的付款來源。',
  historical_payroll_funding_pending: '月嫂付款來源與補助流向尚未確認，預計付款日與分期保留待確認。',
  historical_payroll_end_date_missing: '請查核已採納之歷史服務結束日。',
  historical_payroll_attribution_pending: '請回到歷史服務歸屬更正，查核應付與原付款證據。',
};

function historicalSyncMessage(outcome: HistoricalPayrollSyncItem): string {
  return outcome.detail ?? historicalSyncMessages[outcome.pending_reason ?? '']
    ?? (outcome.action === 'skipped' ? historicalSyncMessages[outcome.reason] : undefined)
    ?? '本案目前無法同步，請重新查核案件狀態。';
}

function historicalReadback(outcome: HistoricalPayrollSyncItem, accounting: CaseAccounting): string {
  const person = accounting.staff_accounting_availability?.find(person =>
    outcome.staff_id != null && outcome.assignment_id != null &&
    person.staff_id === outcome.staff_id && person.assignment_id === outcome.assignment_id,
  );
  const identity = outcome.obligation_identity;
  const payable = identity && person?.status === 'formal' && person.obligation_identities.includes(identity)
    ? accounting.staff_items.find(row => row.direction === 'payable' && row.identity === identity)
    : undefined;
  const name = person?.party || (outcome.staff_id ? `月嫂編號 ${outcome.staff_id}` : '月嫂歸屬待確認');
  if (!payable) {
    const detail = outcome.action === 'skipped' ? historicalSyncMessage(outcome) : '尚未查回對應指派的正式應付。';
    return `${name} · ${detail}`;
  }
  const settled = payable.settled === true || payable.remaining_ntd === 0;
  const arrangementPending = !settled && (outcome.payment_arrangement_pending === true ||
    (payable.funding_portions?.length ? payable.funding_portions.some(portion => portion.due_date === null) : payable.due_date === null));
  const status = arrangementPending ? '付款安排待確認' : settled ? '已結清' : '付款日已讀回';
  const detail = outcome.action === 'skipped' && outcome.reason !== 'already_synced'
    ? ` · ${historicalSyncMessage(outcome)}` : '';
  return `${name} · 正式應付 ${financeMoney(payable.expected_ntd)} · ${status}${detail}`;
}

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
