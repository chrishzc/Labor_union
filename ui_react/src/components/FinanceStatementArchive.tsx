import { useId, useRef, useState } from 'react';
import { financeAccountingClient, statementColumns } from '../api/finance_import/finance_accounting_client';
import './FinanceCaseAccounting.css';
import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import { Drawer } from './Drawer';
import { ApiHttpError } from '../api/shared/typed_errors';

export function FinanceStatementArchive() {
  const [manualOpen, setManualOpen] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [direction, setDirection] = useState<'' | '存入' | '支出'>('');
  const [amount, setAmount] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const commands = useRef(new Map<string, string>());
  const manualTrigger = useRef<HTMLButtonElement>(null);
  const formId = useId();
  const { requestLeave } = useUnsavedNavigation();
  function resetDraft() { setFields({}); setDirection(''); setAmount(''); setFieldErrors({}); setError(''); }
  function closeManual() { resetDraft(); setManualOpen(false); window.requestAnimationFrame(() => manualTrigger.current?.focus()); }
  const draft = useUnsavedDraft('人工對帳明細', { '尚有未保存資料': Object.values(fields).some(Boolean) || Boolean(direction || amount) }, {
    baseline: { '尚有未保存資料': false }, enabled: manualOpen, busy: busy || unknown, save: saveManual,
    discard: resetDraft,
  });
  function key(payload: unknown) { const source = JSON.stringify(payload); let value = commands.current.get(source); if (!value) { value = crypto.randomUUID(); commands.current.set(source, value); } return value; }
  async function perform(action: () => Promise<string>, mutation = false) {
    if (busy || (unknown && !mutation)) return;
    setBusy(true); setMessage(''); setError('');
    try { setMessage(await action()); if (mutation) setUnknown(false); }
    catch (caught) { const uncertain = mutation && (!(caught instanceof ApiHttpError) || caught.status >= 500 || caught.status === 408); setUnknown(uncertain); setError(uncertain ? '儲存結果尚未確認，請重新確認原操作的結果。' : '操作失敗，請檢查資料後重試。'); }
    finally { setBusy(false); }
  }
  async function saveManual() {
    if (!manualOpen || busy) return;
    const errors: Record<string, string> = {};
    if (!fields['交易日']) errors.date = '請填寫交易日。';
    if (!direction) errors.direction = '請選擇存入或支出。';
    if (!/^[0-9]+$/.test(amount.trim()) || !/[1-9]/.test(amount)) errors.amount = '請填寫大於 0 的整數金額。';
    if (!fields['銷帳編號']?.trim() && !fields['備註']?.trim()) errors.reference = '銷帳編號或備註至少填寫一項。';
    setFieldErrors(errors);
    if (Object.keys(errors).length || !direction) {
      window.requestAnimationFrame(() => document.getElementById(formId)?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    await perform(async () => {
      const values = { ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== '')), [direction]: amount.trim() };
      const result = await financeAccountingClient.manual(values, key(values));
      closeManual(); commands.current.clear();
      return result.excluded_count ? '重複明細已略過。' : '人工明細已保存，未新增案件帳務。';
    }, true);
  }
  function editField(column: string, value: string) {
    setFields(previous => ({ ...previous, [column]: value }));
    setFieldErrors(previous => ({ ...previous, ...(column === '交易日' ? { date: '' } : column === '銷帳編號' || column === '備註' ? { reference: '' } : {}) }));
    setError('');
  }
  const fieldInput = (column: string) => <label key={column}>{column}<input type={['計息日', '入帳日'].includes(column) ? 'date' : 'text'} inputMode={column === '餘額' ? 'decimal' : undefined} value={fields[column] ?? ''} onChange={event => editField(column, event.target.value)} /></label>;
  const errorText = (name: string) => fieldErrors[name] ? <p id={`${formId}-${name}-error`} className="statement-field-error">{fieldErrors[name]}</p> : null;
  async function download() {
    await perform(async () => {
      const blob = await financeAccountingClient.download(); const url = URL.createObjectURL(blob);
      try { const anchor = document.createElement('a'); anchor.href = url; anchor.download = '銀行成功對帳明細.xlsx'; anchor.click(); }
      finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
      return '成功明細已匯出。';
    });
  }
  return <section className="case-accounting-card statement-archive" aria-label="成功對帳明細">
    <div className="finance-section-heading statement-archive-heading">
      <div><h3>成功對帳明細</h3><p>包含正式入帳與人工新增的銀行明細。</p></div>
      <div className="statement-archive-actions">
        <button type="button" className="finance-btn-primary" disabled={busy || unknown || manualOpen} onClick={() => void download()}>{busy && !manualOpen ? '匯出中…' : '匯出 Excel'}</button>
        <button ref={manualTrigger} type="button" className="finance-btn-secondary" disabled={busy || unknown || manualOpen} onClick={() => { setMessage(''); setError(''); setManualOpen(true); }}>新增人工明細</button>
      </div>
    </div>
    {message && <p role="status" className="statement-result">{message}</p>}
    {error && !manualOpen && <p role="alert" className="statement-field-error">{error}</p>}
    <Drawer isOpen={manualOpen} onClose={closeManual} title="新增人工明細" closeLabel="關閉人工新增明細" closeDisabled={busy || unknown} className="statement-manual-drawer" footer={<>
      <button type="button" className="finance-btn-secondary" disabled={busy || unknown} onClick={() => requestLeave(closeManual)}>取消</button>
      <button type="submit" form={formId} className="finance-btn-primary" disabled={busy}>{busy ? '儲存中…' : unknown ? '重新確認儲存結果' : '儲存明細'}</button>
    </>}>
      <form id={formId} ref={draft} className="statement-manual-form" noValidate onSubmit={event => { event.preventDefault(); void saveManual(); }}>
        <p className="statement-manual-note">只保存銀行明細，不會完成案件核銷。</p>
        {error && <p role="alert" className="statement-field-error">{error}</p>}
        <fieldset className="statement-manual-fields" disabled={busy || unknown} aria-label="人工明細資料">
          <div className="statement-field"><label htmlFor={`${formId}-date`}>交易日（必填）</label><input id={`${formId}-date`} type="date" required value={fields['交易日'] ?? ''} aria-invalid={!!fieldErrors.date} aria-describedby={fieldErrors.date ? `${formId}-date-error` : undefined} onChange={event => editField('交易日', event.target.value)} />{errorText('date')}</div>
          <div className="statement-field"><label htmlFor={`${formId}-direction`}>交易方向（必填）</label><select id={`${formId}-direction`} required value={direction} aria-invalid={!!fieldErrors.direction} aria-describedby={fieldErrors.direction ? `${formId}-direction-error` : undefined} onChange={event => { setDirection(event.target.value as typeof direction); setFieldErrors(previous => ({ ...previous, direction: '' })); setError(''); }}><option value="">請選擇存入或支出</option><option value="存入">存入</option><option value="支出">支出</option></select>{errorText('direction')}</div>
          <div className="statement-field statement-full-row"><label htmlFor={`${formId}-amount`}>金額（必填）</label><input id={`${formId}-amount`} className="statement-money-input" type="text" inputMode="numeric" disabled={!direction} required placeholder="輸入新臺幣整數金額" value={amount} aria-invalid={!!fieldErrors.amount} aria-describedby={fieldErrors.amount ? `${formId}-amount-error` : undefined} onChange={event => { setAmount(event.target.value); setFieldErrors(previous => ({ ...previous, amount: '' })); setError(''); }} />{errorText('amount')}</div>
          <div className="statement-full-row">
            <p className="statement-reference-hint" id={`${formId}-reference-hint`}>銷帳編號或備註，至少填寫一項。</p>
            <div className="statement-reference-fields">
              {['銷帳編號', '備註'].map(column => <label key={column}>{column}<input value={fields[column] ?? ''} aria-invalid={!!fieldErrors.reference} aria-describedby={fieldErrors.reference ? `${formId}-reference-error` : `${formId}-reference-hint`} onChange={event => editField(column, event.target.value)} /></label>)}
            </div>
            {errorText('reference')}
          </div>
          <details className="statement-full-row statement-optional-fields"><summary>其他資料（選填）</summary><div className="statement-fields">{statementColumns.filter(column => !['交易日', '支出', '存入', '銷帳編號', '備註'].includes(column)).map(fieldInput)}</div></details>
        </fieldset>
      </form>
    </Drawer>
  </section>;
}
