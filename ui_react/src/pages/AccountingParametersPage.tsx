import { useEffect, useState } from 'react';
import { accountingPricingClient, PricingPolicySchema, pricingTermsError, type PricingCatalog, type PricingPolicy, type PricingTerms } from '../api/client_finance/accounting_pricing_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedChanges, useUnsavedNavigation } from '../components/UnsavedChanges';
import './AccountingParametersPage.css';

const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei' }).format(new Date());
const identity = (identity_name: string, rule: PricingTerms['rule'], subsidy_hours: number, rate: number): PricingTerms =>
  ({ identity_name, rule, subsidy_hours, client: { covered: rule === 'non_citizen' ? 0 : rate, excess: rate }, payroll: { covered: rule === 'non_citizen' ? 0 : rate, excess: rate } });
export function initialPricingPolicy(): PricingPolicy {
  return { effective_on: today(), identities: [identity('補助市民', 'citizen', 40, 300), identity('社福', 'social', 120, 350), identity('非市民', 'non_citizen', 0, 320)],
    twins_client: { covered: 450, excess: 450 }, twins_payroll: { covered: 450, excess: 450 } };
}
const copy = <T,>(value: T): T => structuredClone(value);
const ruleLabels = { citizen: '補助市民：先墊後退', social: '社福：補助內不先墊', non_citizen: '非市民：自費' };
type Pending = { policy: PricingPolicy; revision: number; reason: string; key: string };

export function AccountingParametersPage() {
  const [catalog, setCatalog] = useState<PricingCatalog | null>(null);
  const [draft, setDraft] = useState<PricingPolicy>(initialPricingPolicy);
  const [baseline, setBaseline] = useState<PricingPolicy>(initialPricingPolicy);
  const [reason, setReason] = useState('');
  const [tab, setTab] = useState<'pricing' | 'history'>('pricing');
  const [viewVersion, setViewVersion] = useState<number | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'unknown' | 'error'>('loading');
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const [name, setName] = useState('');
  const [rule, setRule] = useState<PricingTerms['rule']>('citizen');
  const { requestLeave } = useUnsavedNavigation();
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline) || reason !== '' || name !== '';
  const busy = status === 'saving' || status === 'unknown';
  const subsidyError = draft.identities.map(pricingTermsError).find(Boolean) || (draft.twins_client.covered !== draft.twins_payroll.covered ? '雙胞胎補助內的客戶時薪與月嫂時薪必須相等。' : draft.twins_client.covered <= 0 ? '雙胞胎補助內時薪必須為正整數。' : '');
  const unsavedRef = useUnsavedChanges('帳務參數設定', dirty ? [{ label: '政策版本與四段費率', before: '已載入的參數', after: '有未儲存的政策調整' }] : [], { busy, save: () => save(), discard: () => { setDraft(copy(baseline)); setReason(''); setName(''); } });

  useEffect(() => {
    let active = true;
    accountingPricingClient.catalog().then(value => {
      if (!active) return;
      const policy = value.versions[0]?.policy ?? initialPricingPolicy();
      setCatalog(value); setDraft(copy(policy)); setBaseline(copy(policy)); setStatus('ready');
    }).catch(() => { if (active) { setStatus('error'); setMessage('帳務參數讀取失敗，請重新載入。'); } });
    return () => { active = false; };
  }, []);

  const update = (index: number, change: Partial<PricingTerms>) => setDraft(current => ({ ...current, identities: current.identities.map((item, i) => i === index ? { ...item, ...change } : item) }));
  const addIdentity = () => {
    const label = name.trim();
    if (!label || draft.identities.some(item => item.identity_name === label)) { setMessage('請輸入不重複的身分名稱。'); return; }
    const inherited = draft.identities.find(item => item.rule === rule);
    if (!inherited) return;
    setDraft(current => ({ ...current, identities: [...current.identities, { ...copy(inherited), identity_name: label }] }));
    setName(''); setMessage('');
  };
  const save = async () => {
    if (!catalog || status === 'saving') return;
    if (!pending && name.trim()) { setMessage('請先新增身分，或清空尚未新增的身分名稱。'); return; }
    const checked = PricingPolicySchema.safeParse(draft);
    if (!pending && (!checked.success || subsidyError)) { setMessage(subsidyError || '請確認生效日期、補助時數與時薪；用盡後時薪須為正整數。'); return; }
    const command = pending ?? { policy: copy(draft), revision: catalog.revision, reason: reason.trim(), key: `pricing-policy:${crypto.randomUUID()}` };
    setPending(command); setStatus('saving'); setMessage('');
    let applied = false;
    try {
      const receipt = await accountingPricingClient.savePolicy(command.policy, command.revision, command.reason, command.key);
      applied = true;
      const value = await accountingPricingClient.catalog();
      if (!value.versions.some(item => item.revision === receipt.revision && JSON.stringify(item.policy) === JSON.stringify(command.policy))) throw new Error('readback mismatch');
      setCatalog(value); setBaseline(copy(command.policy)); setDraft(copy(command.policy)); setReason(''); setPending(null); setStatus('ready');
      setMessage(`版本 ${receipt.revision} 已儲存；依生效日期套用新案件。`);
    } catch (error) {
      if (!applied && error instanceof ApiHttpError && error.status < 500) {
        setPending(null); setStatus('error'); setMessage(error.status === 409 ? '政策已被其他人更新，請重新載入後核對草稿。' : '儲存未完成，請確認欄位與權限。');
      } else { setStatus('unknown'); setMessage('儲存結果待確認。可重試原操作；會沿用相同識別，不重複新增版本。'); }
    }
  };
  const historyPolicy = catalog?.versions.find(item => item.revision === viewVersion)?.policy;
  const shown = tab === 'history' ? historyPolicy : draft;
  const renderRows = (policy: PricingPolicy, readOnly: boolean) => <div className="pricing-table-wrap"><table className="pricing-table"><thead>
    <tr><th rowSpan={2}>身分</th><th rowSpan={2}>補助上限（小時）</th><th colSpan={2}>客戶收費時薪（元）</th><th colSpan={2}>月嫂薪資時薪（元）</th></tr>
    <tr><th>補助內</th><th>用盡後</th><th>補助內</th><th>用盡後</th></tr></thead><tbody>{policy.identities.map((item, index) => <tr key={item.identity_name}>
      <th scope="row">{item.identity_name}<div className="pricing-note">{ruleLabels[item.rule]}</div></th>
      <td><input aria-label={`${item.identity_name} 補助上限`} type="number" min="0" step="0.5" value={item.subsidy_hours} disabled={readOnly || item.rule === 'non_citizen'} onChange={event => update(index, { subsidy_hours: Number(event.target.value) })} /></td>
      {(['client', 'payroll'] as const).flatMap(owner => (['covered', 'excess'] as const).map(tier => <td key={`${owner}-${tier}`}><input aria-label={`${item.identity_name} ${owner === 'client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '用盡後'}時薪`} type="number" min={tier === 'covered' && item.subsidy_hours === 0 ? 0 : 1} step="1" value={item[owner][tier]} disabled={readOnly || (item.rule === 'non_citizen' && tier === 'covered')} onChange={event => update(index, { [owner]: { ...item[owner], [tier]: Number(event.target.value) } })} /></td>))}
    </tr>)}</tbody></table></div>;
  return <main ref={unsavedRef} className="pricing-page"><header className="pricing-heading"><div><h1>帳務參數設定</h1><p>新增政策版本；既有案件維持原設定。</p></div><button className="pricing-reload" disabled={busy} onClick={() => requestLeave(() => window.location.reload())}>重新載入</button></header>
    <nav className="pricing-tabs" aria-label="帳務參數分頁" role="tablist">{(['pricing', 'history'] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} disabled={busy} onClick={() => setTab(value)}>{value === 'pricing' ? '計價與補助' : '版本紀錄'}</button>)}</nav>
    <div className="pricing-notice">依案件首次建立時間套用；生效日當天 00:00 起適用（台灣時間）。補件、改期與新政策發布不更換既有案件版本。</div>
    {message && <p className="pricing-status" role={status === 'error' || status === 'unknown' ? 'alert' : 'status'}>{message}</p>}
    {tab === 'pricing' && subsidyError && <p role="alert" className="pricing-status">{subsidyError}</p>}
    {status === 'loading' && <p role="status">正在讀取政策版本…</p>}
    {tab === 'history' && catalog && <section className="pricing-section"><h2>版本紀錄</h2>{catalog.versions.length === 0 ? <p>尚未建立政策版本。</p> : <table className="pricing-table"><thead><tr><th>版本</th><th>生效日期</th><th>操作人</th><th>變更說明</th></tr></thead><tbody>{catalog.versions.map(item => <tr className="pricing-history-row" key={item.revision}><td><button onClick={() => setViewVersion(item.revision)}>版本 {item.revision}</button></td><td>{item.policy.effective_on}</td><td>{item.actor}</td><td>{item.reason}</td></tr>)}</tbody></table>}</section>}
    {shown && catalog && <><label className="pricing-field">生效日期<input type="date" required value={shown.effective_on} disabled={busy || status === 'loading' || tab === 'history'} onChange={event => setDraft(current => ({ ...current, effective_on: event.target.value }))} /></label>
      <section className="pricing-section"><div className="pricing-section-heading"><h2>補助身分與分段時薪</h2></div>{renderRows(shown, busy || status === 'loading' || tab === 'history')}
        <p className="pricing-note">補助範圍內客戶與月嫂時薪須相等，用盡後可分別調整。非市民補助時數與補助內時薪均為 0，自費時薪維持用盡後設定。</p>
        {tab === 'pricing' && <div className="pricing-new-identity"><label className="pricing-field">新增身分名稱<input value={name} maxLength={100} disabled={busy} onChange={event => setName(event.target.value)} /></label><label className="pricing-field">沿用身分規則<select value={rule} disabled={busy} onChange={event => setRule(event.target.value as PricingTerms['rule'])}>{Object.entries(ruleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button type="button" className="pricing-reload" disabled={busy} onClick={addIdentity}>新增身分</button></div>}
      </section>
      <section className="pricing-section"><h2>雙胞胎費率</h2><div className="pricing-table-wrap"><table className="pricing-table"><thead><tr><th>客戶補助內時薪</th><th>客戶用盡後時薪</th><th>月嫂補助內時薪</th><th>月嫂用盡後時薪</th></tr></thead><tbody><tr>{(['twins_client', 'twins_payroll'] as const).flatMap(owner => (['covered', 'excess'] as const).map(tier => <td key={`${owner}-${tier}`}><input aria-label={`雙胞胎${owner === 'twins_client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '用盡後'}時薪`} type="number" min="1" step="1" value={shown[owner][tier]} disabled={busy || status === 'loading' || tab === 'history'} onChange={event => setDraft(current => ({ ...current, [owner]: { ...current[owner], [tier]: Number(event.target.value) } }))} /></td>))}</tr></tbody></table></div><p className="pricing-note">單胞胎依身分設定；雙胞胎優先套用此處費率，補助上限仍依身分。</p></section>
      {tab === 'pricing' && <><section className="pricing-section"><label className="pricing-field">變更說明（選填）<textarea maxLength={500} value={reason} disabled={busy || status === 'loading'} onChange={event => setReason(event.target.value)} /></label></section><div className="pricing-actions"><button disabled={busy} onClick={() => requestLeave(() => { setDraft(copy(baseline)); setReason(''); setName(''); })}>取消修改</button><button className="pricing-primary" disabled={status === 'saving' || (!pending && !!subsidyError)} onClick={() => void save()}>{status === 'saving' ? '儲存中…' : pending ? '重試原儲存' : '儲存新版本'}</button></div></>}
    </>}
  </main>;
}
