import { useEffect, useRef, useState } from 'react';
import { accountingPricingClient, PricingTermsSchema, pricingTermsError, type CasePricing, type PricingTerms } from '../api/client_finance/accounting_pricing_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedChanges } from './UnsavedChanges';
import '../pages/AccountingParametersPage.css';

type Props = { caseNo: string; revision: unknown; disabled?: boolean; onCommitted: () => Promise<unknown>; onStateChange: (state: { dirty: boolean; busy: boolean }) => void };
const sameTerms = (a: PricingTerms, b: PricingTerms) => JSON.stringify(a) === JSON.stringify(b);

export function CasePricingAdjustmentPanel({ caseNo, revision, disabled = false, onCommitted, onStateChange }: Props) {
  const [current, setCurrent] = useState<CasePricing | null>(null);
  const [draft, setDraft] = useState<PricingTerms | null>(null);
  const [reason, setReason] = useState('');
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'unknown' | 'error'>('loading');
  const [message, setMessage] = useState('');
  const alive = useRef(true);
  const request = useRef(0);
  const pending = useRef<{ terms: PricingTerms; revision: number; reason: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const busy = status === 'saving' || status === 'unknown';
  const busyRef = useRef(busy); busyRef.current = busy;
  const dirty = !!(current && draft && (!sameTerms(current.terms, draft) || reason !== ''));
  const subsidyError = draft ? pricingTermsError(draft) : '';
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const unsavedRef = useUnsavedChanges('個案計價調整', dirty && current && draft ? [
    { label: '補助上限', before: String(current.terms.subsidy_hours), after: String(draft.subsidy_hours) },
    ...(['client', 'payroll'] as const).flatMap(owner => (['covered', 'excess'] as const).filter(tier => current.terms[owner][tier] !== draft[owner][tier]).map(tier => ({ label: `${owner === 'client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '用盡後'}時薪`, before: String(current.terms[owner][tier]), after: String(draft[owner][tier]) }))),
    ...(reason ? [{ label: '調整原因', before: '', after: reason }] : []),
  ].filter(item => item.before !== item.after) : [], { busy, save: disabled ? undefined : apply, discard: reset });
  useEffect(() => { onStateChange({ dirty, busy }); }, [dirty, busy, onStateChange]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++request.current; }; }, []);

  const load = async () => {
    if (dirtyRef.current) { setMessage('尚有未儲存的修改，請先儲存或取消修改。'); return; }
    const sequence = ++request.current;
    try {
      const value = await accountingPricingClient.queryCase(caseNo);
      if (!alive.current || sequence !== request.current) return;
      if (dirtyRef.current) { setMessage('尚有未儲存的修改，請先儲存或取消修改。'); return; }
      setCurrent(value);
      setDraft(structuredClone(value.terms));
      setStatus('ready'); setMessage('');
    } catch {
      if (alive.current && sequence === request.current) { setStatus('error'); setMessage('本案計價資料暫時無法讀取；請先確認服務條件及帳務資料。'); }
    }
  };
  useEffect(() => { if (!busyRef.current) void load(); }, [caseNo, revision]);

  const update = (change: Partial<PricingTerms>) => {
    setDraft(old => old ? { ...old, ...change } : old); setMessage('');
  };
  function reset() {
    if (current) setDraft(structuredClone(current.terms));
    setReason(''); setMessage('');
  }
  async function apply() {
    if (!current || !draft || inFlight.current || disabled || (!dirty && !pending.current)) return;
    if (!pending.current && (!PricingTermsSchema.safeParse(draft).success || subsidyError)) { setStatus('error'); setMessage(subsidyError || '請確認補助上限與時薪；用盡後時薪須為正整數。'); return; }
    const command = pending.current ?? { terms: structuredClone(draft), revision: current.revision, reason: reason.trim(), key: `case-pricing:${crypto.randomUUID()}` };
    pending.current = command; inFlight.current = true; ++request.current; setStatus('saving'); setMessage('');
    let applied = false;
    try {
      const result = await accountingPricingClient.applyCase(caseNo, command.terms, command.revision, command.reason, command.key);
      applied = true;
      await onCommitted();
      const value = await accountingPricingClient.queryCase(caseNo);
      if (!alive.current) return;
      if (value.revision < result.revision || (value.revision === result.revision && !sameTerms(value.terms, command.terms))) throw new Error('pricing readback mismatch');
      setCurrent(value); setDraft(structuredClone(value.terms)); setReason(''); pending.current = null; setStatus('ready');
      setMessage(value.revision === result.revision ? '本案人工計價已儲存並確認；帳務已同步。' : '原調整已完成；畫面已讀取其後的最新設定，請核對。');
    } catch (error) {
      if (!alive.current) return;
      if (!applied && error instanceof ApiHttpError && error.status < 500) {
        pending.current = null; setStatus('error');
        setMessage(error.status === 409 ? '資料已變更，或涉及已核銷補助的更正；請重新查詢並核對。' : '本案調整未完成，請確認資料及權限。');
      } else { setStatus('unknown'); setMessage('儲存或回讀結果待確認；請重試原操作，系統會沿用同一識別防止重複調整。'); }
    } finally { inFlight.current = false; }
  }
  return <section ref={unsavedRef} className="registry-editor pricing-case" aria-label="個案計價調整"><h3>個案計價調整</h3>
    <p className="pricing-notice">本案人工設定不受政策生效日或服務開始日影響；不修改身分給付方式與訂金。</p>
    {message && <p className="pricing-status" role={status === 'error' || status === 'unknown' ? 'alert' : 'status'}>{message}</p>}
    {status === 'loading' && <p role="status">正在讀取本案參數…</p>}
    {current && draft && <><p className="pricing-note">計價身分：{current.terms.identity_name}；來源：{current.source === 'manual' ? '本案人工設定' : current.source === 'policy' ? '案件綁定政策' : '原案件規則'}（版本 {current.revision}）</p>
      <fieldset disabled={busy || disabled} style={{ border: 0, padding: 0, margin: 0 }}><label className="pricing-field">補助時數上限（小時）<input type="number" min="0" step="0.5" value={draft.subsidy_hours} disabled={draft.rule === 'non_citizen'} onChange={event => update({ subsidy_hours: Number(event.target.value) })} /></label>
        <table className="pricing-table"><thead><tr><th>計價範圍</th><th>客戶時薪（元）</th><th>月嫂時薪（元）</th></tr></thead><tbody>{(['covered', 'excess'] as const).map(tier => <tr key={tier}><th scope="row">{tier === 'covered' ? '補助範圍內' : '補助用盡後'}</th>{(['client', 'payroll'] as const).map(owner => <td key={owner}><input aria-label={`${owner === 'client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '用盡後'}時薪`} type="number" min={tier === 'covered' && draft.subsidy_hours === 0 ? 0 : 1} step="1" value={draft[owner][tier]} disabled={draft.rule === 'non_citizen' && tier === 'covered'} onChange={event => update({ [owner]: { ...draft[owner], [tier]: Number(event.target.value) } })} /></td>)}</tr>)}</tbody></table>
        <p className="pricing-note">補助範圍內客戶與月嫂時薪須相等；補助用盡後可分別調整。非市民補助時數與補助內時薪均為 0。補助時數按整案累計。</p>
        {subsidyError && <p role="alert" className="pricing-status">{subsidyError}</p>}
        <label className="pricing-field">調整原因（選填）<textarea maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
      </fieldset>
      <p className="pricing-note">月嫂給付：客戶負擔部分為服務結束月次月 15 日；直接補助部分為次次月 15 日。兩者均不以實際入帳月起算。既有收付款與已簽文件保留原紀錄。</p>
      <div className="pricing-actions"><button type="button" disabled={busy || disabled} onClick={reset}>取消修改</button><button type="button" className="pricing-primary" disabled={disabled || status === 'saving' || (!pending.current && (!!subsidyError || !dirty))} onClick={() => void apply()}>{status === 'saving' ? '儲存並確認中…' : pending.current ? '重試原操作與回讀' : '儲存本案調整'}</button></div>
    </>}
    {!busy && <button className="pricing-reload" disabled={disabled} onClick={() => void load()}>重新讀取本案參數</button>}
  </section>;
}
