/**
 * File: CasePricingAdjustmentPanel.tsx
 * Description: 客戶名冊右側抽屜個案計價調整面板，支援人工設定時薪、補助上限與明確錯誤提示。
 */
import { useEffect, useRef, useState } from 'react';
import { accountingPricingClient, PricingTermsSchema, pricingRequestError, pricingTermsError, historicalPendingLabel, pricingIdentityLabel, type CasePricing, type PricingTerms, type PricingPreview } from '../api/client_finance/accounting_pricing_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedChanges } from './UnsavedChanges';
import { HistoricalCorrectionAccounting } from './HistoricalCorrectionAccounting';
import '../pages/AccountingParametersPage.css';

type Props = { caseNo: string; revision: unknown; disabled?: boolean; onCommitted: () => Promise<unknown>; onStateChange: (state: { dirty: boolean; busy: boolean }) => void };
const sameTerms = (a: PricingTerms, b: PricingTerms) => JSON.stringify(a) === JSON.stringify(b);
const staleMessage = '計價資料已變更，請重新查詢後再儲存。';
const difference = (before: number | null, after: number | null): number | string => before === null || after === null ? '待核對' : after - before;

function rebasePricingDraft(previous: PricingTerms, draft: PricingTerms, latest: PricingTerms): PricingTerms {
  return {
    ...latest,
    subsidy_hours: draft.subsidy_hours === previous.subsidy_hours ? latest.subsidy_hours : draft.subsidy_hours,
    client: {
      covered: draft.client.covered === previous.client.covered ? latest.client.covered : draft.client.covered,
      excess: draft.client.excess === previous.client.excess ? latest.client.excess : draft.client.excess,
    },
    payroll: {
      covered: draft.payroll.covered === previous.payroll.covered ? latest.payroll.covered : draft.payroll.covered,
      excess: draft.payroll.excess === previous.payroll.excess ? latest.payroll.excess : draft.payroll.excess,
    },
  };
}

export function CasePricingAdjustmentPanel({ caseNo, revision, disabled = false, onCommitted, onStateChange }: Props) {
  const [current, setCurrent] = useState<CasePricing | null>(null);
  const [draft, setDraft] = useState<PricingTerms | null>(null);
  const [reason, setReason] = useState('');
  const [status, setStatus] = useState<'loading' | 'ready' | 'previewing' | 'saving' | 'unknown' | 'error' | 'stale'>('loading');
  const [preview, setPreview] = useState<PricingPreview | null>(null);
  const [message, setMessage] = useState('');
  const alive = useRef(true);
  const request = useRef(0);
  const pending = useRef<{ terms: PricingTerms; revision: number; reason: string; key: string; fingerprint?: string } | null>(null);
  const inFlight = useRef(false);
  const busy = status === 'previewing' || status === 'saving' || status === 'unknown';
  const needsReload = status === 'stale';
  const busyRef = useRef(busy); busyRef.current = busy;
  const dirty = !!(current && draft && (!sameTerms(current.terms, draft) || reason !== ''));
  const subsidyError = draft ? pricingTermsError(draft) : '';
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const unsavedRef = useUnsavedChanges('個案計價調整', dirty && current && draft ? [
    { label: '補助上限', before: String(current.terms.subsidy_hours), after: String(draft.subsidy_hours) },
    ...(['client', 'payroll'] as const).flatMap(owner => (['covered', 'excess'] as const).filter(tier => current.terms[owner][tier] !== draft[owner][tier]).map(tier => ({ label: `${owner === 'client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '用盡後'}時薪`, before: String(current.terms[owner][tier]), after: String(draft[owner][tier]) }))),
    ...(reason ? [{ label: '調整原因', before: '', after: reason }] : []),
  ].filter(item => item.before !== item.after) : [], { busy, save: disabled || needsReload ? undefined : apply, discard: reset });
  useEffect(() => { onStateChange({ dirty, busy }); }, [dirty, busy, onStateChange]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++request.current; }; }, []);

  const load = async (previous?: PricingTerms) => {
    if (!previous && dirtyRef.current) { setMessage('尚有未儲存的修改，請先儲存或取消修改。'); return; }
    const sequence = ++request.current;
    try {
      const value = await accountingPricingClient.queryCase(caseNo);
      if (!alive.current || sequence !== request.current) return;
      if (!previous && dirtyRef.current) { setMessage('尚有未儲存的修改，請先儲存或取消修改。'); return; }
      setCurrent(value);
      setPreview(null);
      setDraft(old => previous && old ? rebasePricingDraft(previous, old, value.terms) : structuredClone(value.terms));
      setStatus('ready');
      setMessage(previous ? '已讀取最新計價資料並保留您的修改。請核對欄位後再儲存。' : '');
    } catch (error) {
      if (alive.current && sequence === request.current) {
        setStatus(previous ? 'stale' : 'error');
        const fallback = previous ? '未能讀取最新計價資料，草稿已保留。請再試一次。' : '本案計價資料暫時無法讀取。請先確認服務條件及帳務資料。';
        setMessage(error instanceof ApiHttpError ? pricingRequestError(error, fallback) : fallback);
      }
    }
  };
  useEffect(() => { if (!busyRef.current && !needsReload) void load(); }, [caseNo, revision]);

  const update = (change: Partial<PricingTerms>) => {
    setPreview(null);
    setDraft(old => old ? { ...old, ...change } : old);
    if (!needsReload) setMessage('');
  };
  function reset() {
    if (current) setDraft(structuredClone(current.terms));
    setReason(''); setPreview(null); setMessage(needsReload ? staleMessage : '');
  }
  async function prepare() {
    if (!current || !draft || inFlight.current || disabled || needsReload) return;
    if (!PricingTermsSchema.safeParse(draft).success || subsidyError) { setStatus('error'); setMessage(subsidyError || '請確認補助上限與時薪。'); return; }
    inFlight.current = true; ++request.current; setStatus('previewing'); setMessage('');
    try {
      const result = await accountingPricingClient.previewCase(caseNo, draft, current.revision);
      if (!alive.current) return;
      setPreview(result); setStatus('ready');
    } catch (error) {
      if (!alive.current) return;
      const stale = error instanceof ApiHttpError && error.status === 409;
      setStatus(stale ? 'stale' : 'error');
      setMessage(stale ? staleMessage : error instanceof ApiHttpError ? pricingRequestError(error, '無法預覽本次更正。') : '無法預覽本次更正。');
    } finally { inFlight.current = false; }
  }
  async function apply() {
    if (!current || !draft || inFlight.current || disabled || needsReload || (!dirty && !pending.current)) return;
    if (current.historical && !preview && !pending.current) { await prepare(); return; }
    if (!pending.current && (!PricingTermsSchema.safeParse(draft).success || subsidyError)) { setStatus('error'); setMessage(subsidyError || '請確認補助上限與時薪；用盡後時薪須為正整數。'); return; }
    const command = pending.current ?? { terms: structuredClone(draft), revision: current.revision, reason: reason.trim(), key: `case-pricing:${crypto.randomUUID()}`,
      ...(preview ? { fingerprint: preview.preview_fingerprint } : {}) };
    pending.current = command; inFlight.current = true; ++request.current; setStatus('saving'); setMessage('');
    let applied = false;
    try {
      const result = command.fingerprint
        ? await accountingPricingClient.applyCase(caseNo, command.terms, command.revision, command.reason, command.key, command.fingerprint)
        : await accountingPricingClient.applyCase(caseNo, command.terms, command.revision, command.reason, command.key);
      applied = true;
      await onCommitted();
      const value = await accountingPricingClient.queryCase(caseNo);
      if (!alive.current) return;
      if (value.revision < result.revision || (value.revision === result.revision && !sameTerms(value.terms, command.terms))) throw new Error('pricing readback mismatch');
      setCurrent(value); setDraft(structuredClone(value.terms)); setReason(''); setPreview(null); pending.current = null; setStatus('ready');
      const unresolved = value.accounting_pending ?? result.accounting_pending ?? [];
      setMessage(unresolved.length ? '更正及可確認差額已儲存並讀回；部分帳務仍待核對。' : value.revision === result.revision ? '本案人工計價已儲存並確認；帳務已同步。' : '原調整已完成；畫面已讀取其後的最新設定，請核對。');
    } catch (error) {
      if (!alive.current) return;
      if (!applied && error instanceof ApiHttpError && error.status < 500) {
        pending.current = null;
        const stale = error.status === 409 && ['case_pricing_stale', 'case_pricing_preview_stale', 'pricing_write_conflict'].includes(error.code);
        setStatus(stale ? 'stale' : 'error');
        setMessage(stale ? staleMessage : pricingRequestError(error, '本案調整未完成，請確認資料及權限。'));
      } else { setStatus('unknown'); setMessage('儲存或回讀結果待確認；請重試原操作，系統會沿用同一識別防止重複調整。'); }
    } finally { inFlight.current = false; }
  }
  return <section ref={unsavedRef} className="registry-editor pricing-case" aria-label="個案計價調整"><h3>個案計價調整</h3>
    <p className="pricing-notice">{current?.historical ? '歷史案件更正沿用原身分與已確認服務量。請先預覽差額，再確認保存；缺少原帳證據的部分保留待核對。' : '本案人工設定不受政策生效日或服務開始日影響。給付方式與訂金天數沿用原身分規則；變更時薪或補助上限，可能連動訂金與各期金額。'}</p>
    {message && <p className="pricing-status" role={status === 'error' || status === 'unknown' || needsReload ? 'alert' : 'status'}>{message}</p>}
    {status === 'loading' && <p role="status">正在讀取本案參數…</p>}
    {current && draft && <><p className="pricing-note">計價身分：{pricingIdentityLabel(current.terms)}；來源：{current.source === 'manual' ? '本案人工設定' : current.source === 'policy' ? '案件綁定政策' : '原案件規則'}（版本 {current.revision}）</p>
      {pricingIdentityLabel(current.terms) !== current.terms.identity_name && <p className="pricing-note">原版本名稱：{current.terms.identity_name}；本案仍依原版本的補助上限與給付規則計算。</p>}
      <fieldset disabled={busy || disabled} style={{ border: 0, padding: 0, margin: 0 }}><label className="pricing-field">補助時數上限（小時）<input type="number" min="0" step="0.5" value={draft.subsidy_hours} disabled={draft.rule === 'non_citizen'} onChange={event => update({ subsidy_hours: Number(event.target.value) })} /></label>
        <table className="pricing-table"><thead><tr><th>計價範圍</th><th>客戶時薪（元）</th><th>月嫂時薪（元）</th></tr></thead><tbody>{(['covered', 'excess'] as const).map(tier => <tr key={tier}><th scope="row">{tier === 'covered' ? '補助範圍內' : '補助用盡後'}</th>{(['client', 'payroll'] as const).map(owner => <td key={owner}><input aria-label={`${owner === 'client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '用盡後'}時薪`} type="number" min={tier === 'covered' && draft.subsidy_hours === 0 ? 0 : 1} step="1" value={draft[owner][tier]} disabled={draft.rule === 'non_citizen' && tier === 'covered'} onChange={event => update({ [owner]: { ...draft[owner], [tier]: Number(event.target.value) } })} /></td>)}</tr>)}</tbody></table>
        <p className="pricing-note">補助範圍內客戶與月嫂時薪須相等；補助用盡後可分別調整。非市民補助時數與補助內時薪均為 0。補助時數按整案累計。</p>
        {subsidyError && <p role="alert" className="pricing-status">{subsidyError}</p>}
        <label className="pricing-field">調整原因（選填）<textarea maxLength={500} value={reason} onChange={event => { setReason(event.target.value); setPreview(null); }} /></label>
      </fieldset>
      {!!current.accounting_pending?.length && <div role="status"><p>待核對帳務</p><ul>{current.accounting_pending.map(code => <li key={code}>{historicalPendingLabel(code)}</li>)}</ul></div>}
      {preview && <section aria-label="歷史計價更正預覽"><h4>更正前後與差額</h4>
        <table className="pricing-table"><thead><tr><th>項目</th><th>更正前</th><th>更正後</th><th>差額</th></tr></thead><tbody>
          <tr><th>客戶應收計算額</th><td>{preview.before.client_amount ?? '待核對'}</td><td>{preview.after.client_amount ?? '待核對'}</td><td>{difference(preview.before.client_amount, preview.after.client_amount)}</td></tr>
          <tr><th>月嫂應付計算額</th><td>{preview.before.staff_total_amount ?? '待核對'}</td><td>{preview.after.staff_total_amount ?? '待核對'}</td><td>{preview.after.staff_total_amount === null || preview.before.staff_total_amount === null ? '待核對' : preview.after.staff_total_amount - preview.before.staff_total_amount}</td></tr>
          <tr><th>補助計算額</th><td>{preview.before.subsidy_amount ?? '待核對'}</td><td>{preview.after.subsidy_amount ?? '待核對'}</td><td>{difference(preview.before.subsidy_amount, preview.after.subsidy_amount)}</td></tr>
        </tbody></table>
        {preview.historical_plan && <HistoricalCorrectionAccounting impact={preview.historical_plan} />}
      </section>}
      <p className="pricing-note">月嫂給付：客戶負擔部分為服務結束月次月 15 日；直接補助部分為次次月 15 日。兩者均不以實際入帳月起算。既有收付款與已簽文件保留原紀錄。</p>
      <div className="pricing-actions"><button type="button" disabled={busy || disabled} onClick={reset}>取消修改</button><button type="button" className="pricing-primary" disabled={disabled || status === 'saving' || status === 'previewing' || needsReload || (!pending.current && (!!subsidyError || !dirty))} onClick={() => void apply()}>{status === 'saving' ? '儲存並確認中…' : status === 'previewing' ? '預覽中…' : pending.current ? '重試原操作與回讀' : current.historical ? preview ? '確認歷史計價更正' : '預覽歷史計價更正' : '儲存本案調整'}</button></div>
    </>}
    {!busy && <button className="pricing-reload" disabled={disabled} onClick={() => void load(needsReload ? current?.terms : undefined)}>重新讀取本案參數</button>}
  </section>;
}
