import { useSaveValidation } from './useSaveValidation';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
/**
 * File: LineIdentityWorkbench.tsx
 * Description: 以三個任務分頁呈現真實 LINE 身分查詢、角色限定維護、人工審核與待配對流程。
 */
import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import type {
  LineBindingSubjectType, LineIdentityBindingView, LineIdentityBindingPageView,
  LineIdentityCandidate, LineIdentityCandidatePage, LineIdentityReplacementPreviewView,
  LineIdentityRevocationPreviewView,
  LineIdentityReviewView, LineIdentityReviewPageView, LineIdentityReviewDecision,
  LineIdentityReviewPreviewView, LineIdentityReviewType, UnboundPairingCandidatesView,
  UnboundProvisionalCandidate, UnboundOrderCandidate,
} from '../api/line_identity/line_identity_schemas';
import { adaptLineIdentityReplacementPreview, adaptLineIdentityRevocationPreview, maskLineUserId } from '../adapters/line_identity/line_identity_adapter';
import { Drawer } from './Drawer';
import './LineIdentityWorkbench.css';

type Client = Partial<LineIdentityClient>;
type Section = 'bindings' | 'reviews' | 'pairing';
const roles: Record<LineBindingSubjectType, string> = { customer: '客戶', staff: '月嫂', admin: '內部人員' };
const reviewTypes = { client_rebind: '客戶重新綁定', staff_verification: '月嫂身分驗證', admin_binding: '內部人員綁定' };
const pageSize = 25;
const identity = () => globalThis.crypto.randomUUID();
const reference = (item: LineIdentityBindingView | LineIdentityCandidate) => item.subject_type === 'staff' ? '月嫂' : item.subject_display_reference || `${roles[item.subject_type]} #${item.subject_reference}`;
const phone = (value: string) => value.length > 4 ? `${value.slice(0, 2)}••••${value.slice(-3)}` : '••••';
function date(value?: string | null) {
  if (!value) return '—';
  const normalized = /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value.replace(' ', 'T')}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Taipei' });
}
function errorText(error: unknown) {
  if (error instanceof LineIdentityClientError) {
    if (error.outcomeUnknown) return '操作結果尚未確認，請重新查詢最新狀態，避免重複提交。';
    if (error.code === 'UNAUTHENTICATED') return '登入已失效，請重新登入。';
    if (error.code === 'FORBIDDEN') return '目前帳號沒有執行這項操作的權限。';
    if (error.code === 'CONFLICT') return '資料已變更，請重新查詢後再次確認。';
    if (error.code === 'NOT_FOUND') return '找不到這筆資料，請重新整理清單。';
  }
  return '目前無法完成這項操作，請稍後重新查詢。';
}
const unavailable = () => new Error('identity client method unavailable');
function Status({ item }: { item: LineIdentityBindingView }) {
  const disabled = item.status === 'revocation_pending' || item.status === 'revoked';
  const label = item.status === 'bound' ? '已綁定' : disabled ? '身分已停用' : item.status === 'pending_review' ? '待審核' : '未綁定';
  return <><span className={`identity-status ${item.status === 'bound' ? 'good' : 'muted'}`}>{label}</span>{item.revocation_status === 'menu_reset_failed' || item.revocation_status === 'manual_completed' ? <small className="identity-secondary identity-warning-text">訪客選單待修復</small> : item.revocation_status === 'pending_menu_reset' ? <small className="identity-secondary">訪客選單回復中</small> : null}</>;
}
function Pagination({ page, pageSize: size, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return pages > 1 ? <nav className="identity-pagination" aria-label="清單分頁"><span>第 {page}／{pages} 頁，共 {total} 筆</span><div><button type="button" className="identity-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>上一頁</button><button type="button" className="identity-button" disabled={page >= pages} onClick={() => onPage(page + 1)}>下一頁</button></div></nav> : null;
}
function Empty({ filtered, label, onClear }: { filtered: boolean; label: string; onClear: () => void }) {
  return <div className="identity-empty"><h3>{filtered ? '找不到符合條件的資料' : label}</h3>{filtered && <button type="button" className="identity-button" onClick={onClear}>清除篩選</button>}</div>;
}
function SearchField({ value, onChange, label }: { value: string; onChange: (value: string) => void; label: string }) {
  return <label className="identity-search"><span className="sr-only">{label}</span><Search aria-hidden="true" /><input type="search" maxLength={191} placeholder={label} value={value} onChange={event => onChange(event.target.value)} /></label>;
}

export function LineIdentityWorkbench({ client }: { client: Client }) {
  const initial = useRef(new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '')).current;
  const [section, setSection] = useState<Section>(() => initial.get('identity') === 'reviews' ? 'reviews' : initial.get('identity') === 'pairing' ? 'pairing' : 'bindings');
  const [reload, setReload] = useState(0);
  const [pending, setPending] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController(); setPending(null);
    if (client.getReviewSummary) void client.getReviewSummary({ signal: controller.signal }).then(result => { if (!controller.signal.aborted) setPending(result.pending_total); }).catch(() => {});
    return () => controller.abort();
  }, [client, reload]);
  useEffect(() => {
    const [route, query = ''] = window.location.hash.split('?', 2);
    if (!['#line-management', '#/line-management', '#line', '#/line'].includes(route)) return;
    const params = new URLSearchParams(query); if (section === 'bindings') params.delete('identity'); else params.set('identity', section);
    const suffix = params.toString(); window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${route}${suffix ? `?${suffix}` : ''}`);
  }, [section]);
  const changed = () => setReload(value => value + 1);
  const labels = [['bindings', '身分綁定'], ['reviews', '待審核'], ['pairing', '待配對']] as const;
  return <section className="line-identity-workspace" aria-label="LINE 身分工作區"><h2>身分與授權</h2><div className="identity-card"><div className="identity-top"><div className="identity-tabs" role="tablist" aria-label="身分工作">{labels.map(([key, label], index) => <button type="button" key={key} id={`identity-tab-${key}`} role="tab" aria-selected={section === key} aria-controls="identity-panel" tabIndex={section === key ? 0 : -1} onClick={() => setSection(key)} onKeyDown={event => { const direction = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0; if (direction) { event.preventDefault(); const next = labels[(index + direction + labels.length) % labels.length][0]; setSection(next); document.getElementById(`identity-tab-${next}`)?.focus(); } }}>{label}{key === 'reviews' && pending !== null && pending > 0 && <span className="identity-count">{pending}</span>}</button>)}</div><button type="button" className="identity-button" onClick={changed}><RefreshCw aria-hidden="true" />重新整理</button></div><section id="identity-panel" role="tabpanel" aria-labelledby={`identity-tab-${section}`}>
    {section === 'bindings' && <BindingPanel client={client} reload={reload} onChanged={changed} />}
    {section === 'reviews' && <ReviewPanel client={client} reload={reload} onChanged={changed} />}
    {section === 'pairing' && <PairingPanel client={client} reload={reload} onChanged={changed} />}
  </section></div></section>;
}

type BindingAction = 'view' | 'correct' | 'revoke' | 'restore';

function useLineSubjectLabels() {
  const identities = useStaffIdentityLabels();
  return (item: { subject_type?: string | null; subject_reference?: string | null; subject_name?: string; display_name?: string; review_type?: string }) => {
    const name = item.subject_name || item.display_name || '姓名未設定';
    if (item.subject_type === 'staff' && /^[1-9][0-9]*$/.test(item.subject_reference ?? '')) return identities.label(Number(item.subject_reference), name);
    if (item.review_type === 'staff_verification') return `尚未連結 ${name}`;
    return name;
  };
}

function BindingPanel({ client, reload, onChanged }: { client: Client; reload: number; onChanged: () => void }) {
  const staffIdentity = useStaffIdentityLabels();
  const [allStaffCandidates, setAllStaffCandidates] = useState<LineIdentityCandidate[]>([]);
  const subjectLabel = useLineSubjectLabels();
  const initial = useRef(new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '')).current;
  const initialRole = initial.get('binding_role');
  const [role, setRole] = useState<LineBindingSubjectType | 'all'>(initialRole === 'customer' || initialRole === 'staff' || initialRole === 'admin' ? initialRole : 'all');
  const [search, setSearch] = useState(initial.get('binding_q') ?? ''); const [page, setPage] = useState(() => { const value=Number(initial.get('binding_page'));return Number.isSafeInteger(value)&&value>0?value:1; });
  const [result, setResult] = useState<LineIdentityBindingPageView | null>(null); const [loading, setLoading] = useState(true); const [listError, setListError] = useState<string | null>(null);
  const [selected, setSelected] = useState<LineIdentityBindingView | null>(null); const [detail, setDetail] = useState<LineIdentityBindingView | null>(null);
  const [action, setAction] = useState<BindingAction>('view'); const [reason, setReason] = useState(''); const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<LineIdentityReplacementPreviewView | LineIdentityRevocationPreviewView | null>(null);
  const [candidatePage, setCandidatePage] = useState<LineIdentityCandidatePage | null>(null); const [candidateSearch, setCandidateSearch] = useState(''); const [candidateNumber, setCandidateNumber] = useState(1); const [target, setTarget] = useState<LineIdentityCandidate | null>(null); const [candidateError, setCandidateError] = useState<string | null>(null);
  const [stage, setStage] = useState<'form' | 'confirm'>('form'); const [busy, setBusy] = useState(false); const [applying, setApplying] = useState(false); const [operationError, setOperationError] = useState<string | null>(null); const [notice, setNotice] = useState<string | null>(null); const [uncertain, setUncertain] = useState(false);
  const controller = useRef<AbortController | null>(null); const intent = useRef<{ key: string; correlation: string } | null>(null); const locked = useRef(false); const minimumVersion = useRef<number | null>(null);
  useEffect(() => {
    const [route,query='']=window.location.hash.split('?',2);if(!['#line-management','#/line-management','#line','#/line'].includes(route))return;
    const params=new URLSearchParams(query);const set=(key:string,value:string,fallback:string)=>value===fallback||!value?params.delete(key):params.set(key,value);
    set('binding_q',search,'');set('binding_role',role,'all');set('binding_page',String(page),'1');const suffix=params.toString();window.history.replaceState(window.history.state,'',`${window.location.pathname}${window.location.search}${route}${suffix?`?${suffix}`:''}`);
  },[role,search,page]);
  useEffect(() => {
    const abort = new AbortController();setLoading(true);setListError(null);setResult(null);
    const timer = window.setTimeout(() => { void (client.listBindings?.({ subject_type: role === 'all' ? undefined : role, search: search.trim() || undefined, page, page_size: pageSize }, { signal: abort.signal }) ?? Promise.reject(unavailable())).then(value => { if (!abort.signal.aborted) setResult(value); }).catch(error => { if (!abort.signal.aborted) setListError(errorText(error)); }).finally(() => { if (!abort.signal.aborted) setLoading(false); }); }, 150);
    return () => { abort.abort();window.clearTimeout(timer); };
  }, [client, role, search, page, reload]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (action !== 'correct' || !selected) return;
    const abort = new AbortController();setCandidatePage(null);setCandidateError(null);setAllStaffCandidates([]);
    const timer = window.setTimeout(() => { void (async () => {
      if (!client.listReplacementCandidates) throw unavailable();
      const query = { subject_type: selected.subject_type, search: candidateSearch.trim() || undefined, page: selected.subject_type === 'staff' ? 1 : candidateNumber, page_size: pageSize };
      const value = await client.listReplacementCandidates(query, { signal: abort.signal });
      const all = [...value.items];
      const seen = new Set(all.map(item => item.subject_reference));
      if (selected.subject_type === 'staff') {
        for (let next = value.page + 1; all.length < value.total; next += 1) {
          abort.signal.throwIfAborted();
          const page = await client.listReplacementCandidates({ ...query, page: next }, { signal: abort.signal });
          if (page.page !== next || page.total !== value.total || page.items.length === 0 || page.items.some(item => seen.has(item.subject_reference))) throw unavailable();
          page.items.forEach(item => seen.add(item.subject_reference));
          all.push(...page.items);
        }
      }
      if (!abort.signal.aborted) { setAllStaffCandidates(all); setCandidatePage(value); }
    })().catch(error => { if (!abort.signal.aborted) setCandidateError(errorText(error)); }); }, 150);
    return () => { abort.abort();window.clearTimeout(timer); };
  }, [client, action, selected, candidateSearch, candidateNumber]);
  const loadDetail = async (item: LineIdentityBindingView) => {
    controller.current?.abort(); const abort = new AbortController();controller.current = abort;setBusy(true);setOperationError(null);
    try {
      const value = await (client.getBinding?.(item.line_user_id, { subjectType: item.subject_type, signal: abort.signal }) ?? Promise.reject(unavailable()));
      if (!abort.signal.aborted) { if (value.line_user_id !== item.line_user_id || value.subject_type !== item.subject_type || (minimumVersion.current!==null&&value.version<minimumVersion.current)) throw unavailable(); setDetail(value);setUncertain(false);minimumVersion.current=null; }
    } catch (error) { if (!abort.signal.aborted) setOperationError(errorText(error)); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  };
  const open = (item: LineIdentityBindingView) => { minimumVersion.current=null;setSelected(item);setDetail(null);setAction('view');setPreview(null);setReason('');setNotice(null);setUncertain(false);setConfirmed(false);void loadDetail(item); };
  const close = () => { if (locked.current) return; controller.current?.abort();setSelected(null);setDetail(null); };
  const begin = (value: BindingAction) => { setAction(value);setStage('form');setReason('');setConfirmed(false);setTarget(null);setCandidateSearch('');setCandidateNumber(1);setPreview(null);setOperationError(null);setNotice(null);intent.current=null; };
  const runPreview = async () => {
    if (!selected || !detail || !reason.trim() || (action === 'correct' && !target) || locked.current || uncertain) return;
    setBusy(true);setOperationError(null);setConfirmed(false); const abort = new AbortController();controller.current=abort;
    try {
      const options = { subjectType: selected.subject_type, signal: abort.signal };
      const value = action === 'correct' ? await (client.previewReplacement?.(selected.line_user_id, target!.subject_reference, options) ?? Promise.reject(unavailable())) : action === 'revoke' ? await (client.previewRevocation?.(selected.line_user_id, options) ?? Promise.reject(unavailable())) : null;
      if (abort.signal.aborted) return;
      if (value && (value.binding.subject_type !== selected.subject_type || value.binding.line_user_id !== selected.line_user_id)) throw unavailable();
      if (action === 'correct' && value && ('target_subject_reference' in value) && value.target_subject_reference !== target?.subject_reference) throw unavailable();
      setPreview(value); intent.current={key: identity(),correlation:identity()}; setStage('confirm');
    } catch (error) { if (!abort.signal.aborted) setOperationError(errorText(error)); }
    finally { if (!abort.signal.aborted) setBusy(false); }
  };
  const apply = async () => {
    if (!selected || !detail || !confirmed || !reason.trim() || !intent.current || locked.current || uncertain) return;
    if (action === 'correct' && (!preview || !('target_subject_reference' in preview) || preview.target_subject_reference !== target?.subject_reference)) return;
    if (preview?.blockers.length) return; locked.current=true;setBusy(true);setApplying(true);setOperationError(null);
    const abort = new AbortController();controller.current=abort;
    try {
      const options={subjectType:selected.subject_type,signal:abort.signal};const common={expected_version:preview?.binding.version ?? detail.version, reason:reason.trim(),idempotency_key:intent.current.key,correlation_id:intent.current.correlation};
      if (action === 'correct' && target) { const receipt=await (client.applyReplacement?.(selected.line_user_id,{...common,target_subject_reference:target.subject_reference},options) ?? Promise.reject(unavailable()));minimumVersion.current=receipt.version; }
      else if (action === 'revoke') { const receipt=await (client.applyRevocation?.(selected.line_user_id,common,options) ?? Promise.reject(unavailable()));minimumVersion.current=receipt.pending_binding_version; }
      else if (action === 'restore' && detail.revocation_request_id) { const receipt=await (client.retryRevocation?.(detail.revocation_request_id,{reason:reason.trim()},options) ?? Promise.reject(unavailable()));minimumVersion.current=receipt.pending_binding_version; }
      else throw unavailable();
      setNotice(action === 'correct' ? '綁定對象更正已受理。' : action === 'revoke' ? '解除申請已受理，訪客選單仍需等待回復結果。' : '已重新安排訪客選單回復。');
      setUncertain(true);setDetail(null);setAction('view');setPreview(null);setConfirmed(false);onChanged();
      await loadDetail(selected);
    } catch (error) { if (!abort.signal.aborted) { setOperationError(errorText(error));if (error instanceof LineIdentityClientError && error.outcomeUnknown) {minimumVersion.current=(preview?.binding.version??detail.version)+1;setUncertain(true);setPreview(null);} } }
    finally { locked.current=false;setBusy(false);setApplying(false); }
  };
  const blockers = preview ? ('target_subject_reference' in preview ? adaptLineIdentityReplacementPreview(preview).blockers : adaptLineIdentityRevocationPreview(preview).blockers) : [];
  const view = detail;
  return <>
    <div className="identity-filters"><SearchField value={search} onChange={value=>{setSearch(value);setPage(1);}} label="搜尋姓名或案件編號" /><select aria-label="篩選身分角色" value={role} onChange={event=>{setRole(event.target.value as typeof role);setPage(1);}}><option value="all">全部身分角色</option>{Object.entries(roles).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></div>
    {loading && <p className="identity-message" role="status">正在載入身分綁定…</p>}{listError && <p className="identity-message identity-error" role="alert">{listError}</p>}
    {result && (result.items.length ? <><div className="identity-table-scroll"><table className="identity-table" data-control-id="line.identity.table"><caption className="sr-only">LINE 身分綁定清單</caption><thead><tr><th>對象</th><th>角色</th><th>狀態</th><th>更新時間</th><th>操作</th></tr></thead><tbody>{result.items.map(item=><tr key={`${item.line_user_id}:${item.subject_type}`}><td><strong>{subjectLabel(item)}</strong><small className="identity-secondary">{item.subject_type === 'staff' ? '' : reference(item)}</small></td><td data-label="角色">{roles[item.subject_type]}</td><td data-label="狀態"><Status item={item} /></td><td data-label="更新時間">{date(item.updated_at)}</td><td><button type="button" className="identity-row-action" aria-label={`查看${subjectLabel(item)}的${roles[item.subject_type]}身分`} onClick={()=>open(item)}>查看</button></td></tr>)}</tbody></table></div><Pagination page={result.page} pageSize={result.page_size} total={result.total} onPage={setPage} /></> : <Empty filtered={!!search.trim()||role!=='all'} label="目前沒有身分綁定紀錄" onClear={()=>{setSearch('');setRole('all');setPage(1);}} />)}
    <Drawer className="identity-drawer" isOpen={selected!==null} onClose={close} closeDisabled={applying} closeLabel="關閉身分明細" title={action==='view'?'身分明細':action==='correct'?'更正綁定對象':action==='revoke'?'解除身分':'修復訪客選單'} footer={view&&!uncertain ? action==='view' ? view.status==='bound' ? <><button type="button" className="identity-button" disabled={!client.previewReplacement||!client.applyReplacement} onClick={()=>begin('correct')}>更正綁定對象</button><button type="button" className="identity-button" disabled={!client.previewRevocation||!client.applyRevocation} onClick={()=>begin('revoke')}>解除此身分</button></> : view.revocation_request_id && (view.revocation_status==='menu_reset_failed'||view.revocation_status==='manual_completed') ? <button type="button" className="identity-button primary" disabled={!client.retryRevocation} onClick={()=>begin('restore')}>修復訪客選單</button> : undefined : <><button type="button" className="identity-button" disabled={busy} onClick={()=>{setStage('form');setAction(stage==='form'?'view':action);setPreview(null);setConfirmed(false);}}>返回</button>{stage==='form'?<button type="button" className="identity-button primary" disabled={busy||!reason.trim()||(action==='correct'&&!target)} onClick={()=>void runPreview()}>下一步：確認</button>:<button type="button" className={`identity-button ${action==='revoke'?'danger':'primary'}`} disabled={busy||!confirmed||blockers.length>0} onClick={()=>void apply()}>{applying?'正在提交…':action==='correct'?'確認更正':action==='revoke'?'確認解除此身分':'確認重新回復'}</button>}</> : undefined}>
      {busy && <p role="status">{applying?'正在提交操作…':'正在查詢最新資料…'}</p>}{operationError && <p role="alert" className="identity-error">{operationError}</p>}{notice && <p className="identity-note" role="status">{notice}</p>}
      {selected && (operationError||uncertain) && !busy && <button type="button" className="identity-button" onClick={()=>void loadDetail(selected)}>重新查詢綁定狀態</button>}
      {view && <><div className="identity-person"><div><h3>{subjectLabel(view)}</h3><small className="identity-secondary">{roles[view.subject_type]}{view.subject_type !== 'staff' && ` · ${reference(view)}`}</small></div><Status item={view} /></div><dl className="identity-facts"><div><dt>LINE 帳號</dt><dd>{maskLineUserId(view.line_user_id)}</dd></div><div><dt>更新時間</dt><dd>{date(view.updated_at)}</dd></div></dl>
      {action!=='view' && <p className="identity-note">本次只操作「{roles[view.subject_type]}」身分，其他角色保留。</p>}
      {action==='revoke'&&<p className="identity-note warning">提交後，這筆身分會立即停止系統授權，並安排回復訪客選單。</p>}
      {action==='restore'&&<p className="identity-note">重新安排訪客選單回復，此身分仍維持停用。</p>}
      {action!=='view'&&stage==='form'&&!uncertain&&<fieldset className="identity-action-form" disabled={busy}>{action==='correct'&&<><SearchField value={candidateSearch} onChange={value=>{setCandidateSearch(value);setCandidateNumber(1);setTarget(null);}} label="搜尋新的綁定對象" />{candidateError&&<p className="identity-error" role="alert">{candidateError}</p>}{!candidatePage&&!candidateError&&<p role="status">正在查詢可更正對象…</p>}{candidatePage&&<><label className="identity-field">新的{roles[view.subject_type]}對象<select aria-label="新的綁定對象" value={target?.subject_reference??''} onChange={event=>setTarget((view.subject_type === 'staff' ? allStaffCandidates : candidatePage.items).find(item=>item.subject_reference===event.target.value)??null)}><option value="">請選擇同角色對象</option>{(view.subject_type === 'staff' ? [...allStaffCandidates].sort((a,b)=>staffIdentity.compare(Number(a.subject_reference),Number(b.subject_reference))) : candidatePage.items).map(item=><option key={item.subject_reference} value={item.subject_reference}>{subjectLabel(item)}{item.subject_type !== 'staff' && ` · ${reference(item)}`}</option>)}</select></label>{candidatePage.total===0&&<p className="identity-secondary">目前沒有可選擇的同角色對象。</p>}{view.subject_type !== 'staff' && <Pagination page={candidatePage.page} pageSize={candidatePage.page_size} total={candidatePage.total} onPage={value=>{setCandidateNumber(value);setTarget(null);}} />}</>}</>}
      <label className="identity-field">{action==='correct'?'更正原因':action==='revoke'?'解除原因':'修復原因'}<textarea rows={3} maxLength={1000} value={reason} onChange={event=>setReason(event.target.value)} /></label></fieldset>}
      {stage==='confirm'&&action!=='view'&&!uncertain&&<>{action==='correct'&&target&&<div className="identity-note"><strong>{subjectLabel(view)} → {subjectLabel(target)}</strong>{view.subject_type !== 'staff' && <p>{reference(view)} → {reference(target)}</p>}</div>}<dl className="identity-facts"><div><dt>原因</dt><dd>{reason}</dd></div></dl>{blockers.length>0?<ul className="identity-error" role="alert">{blockers.map(item=><li key={item}>{item}</li>)}</ul>:<label className="identity-check"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)} />我已確認{subjectLabel(view)}的{roles[view.subject_type]}身分與操作影響</label>}</>}
      </>}
    </Drawer>
  </>;
}

function ReviewPanel({ client, reload, onChanged }: { client: Client; reload: number; onChanged: () => void }) {
  const subjectLabel = useLineSubjectLabels();
  const [search,setSearch]=useState(''); const [type,setType]=useState<'all'|LineIdentityReviewType>('all'); const [page,setPage]=useState(1);
  const [result,setResult]=useState<LineIdentityReviewPageView|null>(null); const [loading,setLoading]=useState(true);const [listError,setListError]=useState<string|null>(null);
  const [requestId,setRequestId]=useState<number|null>(null);const [detail,setDetail]=useState<LineIdentityReviewView|null>(null);const [decision,setDecision]=useState<LineIdentityReviewDecision|null>(null);const [reason,setReason]=useState('');const [preview,setPreview]=useState<LineIdentityReviewPreviewView|null>(null);const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);const [applying,setApplying]=useState(false);const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState<string|null>(null);const [uncertain,setUncertain]=useState(false);
  const controller=useRef<AbortController|null>(null);const key=useRef<string|null>(null);const locked=useRef(false);const minimumVersion=useRef<number|null>(null);
  useEffect(()=>{const abort=new AbortController();setLoading(true);setResult(null);setListError(null);const timer=window.setTimeout(()=>{void(client.listReviews?.({review_status:'pending',review_type:type==='all'?undefined:type,search:search.trim()||undefined,page,page_size:pageSize},{signal:abort.signal})??Promise.reject(unavailable())).then(value=>{if(!abort.signal.aborted)setResult(value);}).catch(error=>{if(!abort.signal.aborted)setListError(errorText(error));}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});},150);return()=>{abort.abort();window.clearTimeout(timer);};},[client,type,search,page,reload]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const load=async(id:number)=>{controller.current?.abort();const abort=new AbortController();controller.current=abort;setBusy(true);setError(null);try{const value=await(client.getReview?.(id,{signal:abort.signal})??Promise.reject(unavailable()));if(!abort.signal.aborted){if(value.request_id!==id||(minimumVersion.current!==null&&value.version<minimumVersion.current))throw unavailable();setDetail(value);setUncertain(false);minimumVersion.current=null;}}catch(error){if(!abort.signal.aborted)setError(errorText(error));}finally{if(!abort.signal.aborted)setBusy(false);}};
  const open=(id:number)=>{minimumVersion.current=null;setRequestId(id);setDetail(null);setDecision(null);setReason('');setPreview(null);setConfirmed(false);setNotice(null);setUncertain(false);void load(id);};
  const close=()=>{if(locked.current)return;controller.current?.abort();setRequestId(null);};
  const runPreview=async()=>{if(!detail||detail.status!=='pending'||!decision||!reason.trim()||busy||uncertain)return;const abort=new AbortController();controller.current=abort;setBusy(true);setError(null);try{const value=await(client.previewReviewDecision?.(detail.request_id,decision,{expected_version:detail.version,reason:reason.trim()},{signal:abort.signal})??Promise.reject(unavailable()));if(!abort.signal.aborted){if(value.request_id!==detail.request_id||value.decision!==decision)throw unavailable();setPreview(value);setConfirmed(false);key.current=identity();}}catch(error){if(!abort.signal.aborted)setError(errorText(error));}finally{if(!abort.signal.aborted)setBusy(false);}};
  const apply=async()=>{if(!preview||!confirmed||!key.current||locked.current||uncertain)return;locked.current=true;setBusy(true);setApplying(true);setError(null);const abort=new AbortController();controller.current=abort;try{const receipt=await(client.applyReviewDecision?.(preview.request_id,preview.decision,{expected_version:preview.expected_version,reason:reason.trim(),preview_fingerprint:preview.preview_fingerprint,idempotency_key:key.current},{signal:abort.signal})??Promise.reject(unavailable()));minimumVersion.current=receipt.version;setDetail(null);setNotice('審核決定已受理，請以最新查詢結果確認。');setPreview(null);setUncertain(true);onChanged();await load(preview.request_id);}catch(error){if(!abort.signal.aborted){setError(errorText(error));if(error instanceof LineIdentityClientError&&error.outcomeUnknown){minimumVersion.current=preview.expected_version+1;setUncertain(true);setPreview(null);}}}finally{locked.current=false;setBusy(false);setApplying(false);}};
  return <><div className="identity-filters"><SearchField value={search} onChange={value=>{setSearch(value);setPage(1);}} label="搜尋申請人或案件編號" /><select aria-label="篩選審核類型" value={type} onChange={event=>{setType(event.target.value as typeof type);setPage(1);}}><option value="all">全部審核類型</option>{Object.entries(reviewTypes).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></div>
    {loading&&<p className="identity-message" role="status">正在載入待審核申請…</p>}{listError&&<p className="identity-message identity-error" role="alert">{listError}</p>}
    {result&&(result.items.length?<><table className="identity-table"><caption className="sr-only">LINE 待審核清單</caption><thead><tr><th>申請對象</th><th>申請事項</th><th>申請時間</th><th>操作</th></tr></thead><tbody>{result.items.map(item=><tr key={item.request_id}><td><strong>{subjectLabel(item)}</strong><small className="identity-secondary">{item.subject_display_reference||`申請 #${item.request_id}`}</small></td><td data-label="申請事項">{reviewTypes[item.review_type]}</td><td data-label="申請時間">{date(item.created_at)}</td><td><button type="button" className="identity-row-action" aria-label={`審核${subjectLabel(item)}的綁定申請`} onClick={()=>open(item.request_id)}>審核</button></td></tr>)}</tbody></table><Pagination page={result.page} pageSize={result.page_size} total={result.total} onPage={setPage} /></>:<Empty filtered={!!search.trim()||type!=='all'} label="目前沒有待審核申請" onClear={()=>{setSearch('');setType('all');setPage(1);}} />)}
    <Drawer className="identity-drawer" isOpen={requestId!==null} onClose={close} closeDisabled={applying} closeLabel="關閉審核明細" title="審核綁定申請" footer={detail?.status==='pending'&&!uncertain?<>{preview?<><button type="button" className="identity-button" disabled={busy} onClick={()=>{setPreview(null);setConfirmed(false);}}>修改決定</button><button type="button" className="identity-button primary" disabled={busy||!confirmed} onClick={()=>void apply()}>{applying?'正在提交…':`確認${preview.decision==='approve'?'核准':'拒絕'}`}</button></>:<button type="button" className="identity-button primary" disabled={busy||!decision||!reason.trim()} onClick={()=>void runPreview()}>下一步：確認</button>}</>:undefined}>
      {busy&&<p role="status">{applying?'正在提交審核…':'正在查詢審核資料…'}</p>}{error&&<p className="identity-error" role="alert">{error}</p>}{notice&&<p className="identity-note" role="status">{notice}</p>}{requestId!==null&&(error||uncertain||notice)&&!busy&&<button type="button" className="identity-button" onClick={()=>void load(requestId)}>重新查詢審核結果</button>}
      {detail&&<><div className="identity-person"><div><h3>{subjectLabel(detail)}</h3><small className="identity-secondary">{reviewTypes[detail.review_type]} · {detail.subject_display_reference||`申請 #${detail.request_id}`}</small></div><span className="identity-status attention">{detail.status==='pending'?'待審核':detail.status==='approved'?'已核准':detail.status==='rejected'?'已拒絕':detail.status==='cancelled'?'已取消':'已到期'}</span></div><div className="identity-comparison"><div><span>目前 LINE</span><strong>{detail.current_line_user_id?maskLineUserId(detail.current_line_user_id):'尚無可確認的綁定資料'}</strong></div><div><span>申請帳號</span><strong>{maskLineUserId(detail.line_user_id)}</strong></div></div>
      {detail.subject_type==='admin'&&<p className="identity-note">這項審核只更新 LINE 綁定，後台帳號權限維持原設定。</p>}
      {detail.status==='pending'&&!uncertain&&(preview?<><h3>確認{preview.decision==='approve'?'核准':'拒絕'}這筆申請</h3><p className="identity-note">{reason}</p><label className="identity-check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>setConfirmed(event.target.checked)} />我已核對申請對象與審核決定</label></>:<><fieldset className="identity-decisions" disabled={busy}><legend>審核決定</legend>{(['approve','reject']as const).map(value=><label key={value}><input type="radio" name="identity-review-decision" checked={decision===value} onChange={()=>setDecision(value)} />{value==='approve'?'核准':'拒絕'}</label>)}</fieldset><label className="identity-field">審核原因<textarea value={reason} disabled={busy} maxLength={1000} rows={3} onChange={event=>setReason(event.target.value)} /></label></>)}
      </>}
    </Drawer></>;
}

function PairingPanel({client,reload,onChanged}:{client:Client;reload:number;onChanged:()=>void}) {
  const saveValidation = useSaveValidation();
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const [result,setResult]=useState<UnboundPairingCandidatesView|null>(null);const [loading,setLoading]=useState(true);const [listError,setListError]=useState<string|null>(null);const [search,setSearch]=useState('');const [page,setPage]=useState(1);
  const [registration,setRegistration]=useState<UnboundProvisionalCandidate|null>(null);const [order,setOrder]=useState<UnboundOrderCandidate|null>(null);const [orderSearch,setOrderSearch]=useState('');const [reason,setReason]=useState('');const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);const [uncertain,setUncertain]=useState(false);const [error,setError]=useState<string|null>(null);const [notice,setNotice]=useState<string|null>(null);
  const mutation=useRef<AbortController|null>(null);const key=useRef<string|null>(null);const locked=useRef(false);
  useEffect(()=>{const abort=new AbortController();setLoading(true);setListError(null);setResult(null);void(client.listUnboundCandidates?.({signal:abort.signal})??Promise.reject(unavailable())).then(value=>{if(!abort.signal.aborted)setResult(value);}).catch(error=>{if(!abort.signal.aborted)setListError(errorText(error));}).finally(()=>{if(!abort.signal.aborted)setLoading(false);});return()=>abort.abort();},[client,reload]);
  useEffect(()=>()=>mutation.current?.abort(),[]);
  const candidates=(result?.provisional_registrations??[]).filter(item=>!search.trim()||item.name.includes(search.trim())||phone(item.phone).includes(search.trim()));
  const rows=candidates.slice((page-1)*pageSize,page*pageSize);
  const orders=(result?.orders??[]).filter(item=>!orderSearch.trim()||item.client_name.includes(orderSearch.trim())||item.case_no.toLowerCase().includes(orderSearch.trim().toLowerCase()));
  const close=()=>{if(locked.current)return;setRegistration(null);};
  const open=(item:UnboundProvisionalCandidate)=>{setRegistration(item);setOrder(null);setOrderSearch('');setReason('');setConfirmed(false);setError(null);setNotice(null);setUncertain(false);key.current=identity();};
  const apply=async()=>{if(!registration||!order||!confirmed||locked.current||uncertain||!key.current)return;if(!saveValidation.validate([{value:reason,label:'配對原因',ref:reasonRef}]))return;locked.current=true;setBusy(true);setError(null);const abort=new AbortController();mutation.current=abort;try{const value=await(client.pairProvisionalRegistration?.({provisional_registration_id:registration.registration_id,target_case_no:order.case_no,reason:reason.trim(),idempotency_key:key.current,correlation_id:key.current},{signal:abort.signal})??Promise.reject(unavailable()));if(abort.signal.aborted)return;setNotice(`已完成 ${value.case_no} 的身分配對，LINE 選單仍需等待套用結果。`);setRegistration(null);onChanged();}catch(error){if(!abort.signal.aborted){setError(errorText(error));if(error instanceof LineIdentityClientError&&error.outcomeUnknown)setUncertain(true);}}finally{locked.current=false;setBusy(false);}};
  const readBack=async()=>{if(!registration)return;setBusy(true);setError(null);try{const fresh=await(client.listUnboundCandidates?.()??Promise.reject(unavailable()));setResult(fresh);if(!fresh.provisional_registrations.some(item=>item.registration_id===registration.registration_id)){setNotice('這筆登記已離開待配對清單，請至身分綁定查詢最新結果。');setRegistration(null);onChanged();}else setError('這筆登記仍在待配對清單，操作結果尚未確認，請稍後再查詢。');}catch(error){setError(errorText(error));}finally{setBusy(false);}};
  return <><div className="identity-filters"><SearchField value={search} onChange={value=>{setSearch(value);setPage(1);}} label="搜尋登記姓名或電話末碼" /></div>{loading&&<p className="identity-message" role="status">正在載入待配對登記…</p>}{listError&&<p className="identity-message identity-error" role="alert">{listError}</p>}{notice&&<p className="identity-message" role="status">{notice}</p>}
    {result&&(rows.length?<><table className="identity-table"><caption className="sr-only">LINE 待配對登記清單</caption><thead><tr><th>登記對象</th><th>待配對事項</th><th>登記時間</th><th>操作</th></tr></thead><tbody>{rows.map(item=><tr key={item.registration_id}><td><strong>{item.name}</strong><small className="identity-secondary">{phone(item.phone)}</small></td><td data-label="待配對事項">尚未對應正式訂單</td><td data-label="登記時間">{date(item.submitted_at)}</td><td><button type="button" className="identity-row-action" aria-label={`為${item.name}尋找對應訂單`} onClick={()=>open(item)}>配對</button></td></tr>)}</tbody></table><Pagination page={page} pageSize={pageSize} total={candidates.length} onPage={setPage} /></>:<Empty filtered={!!search.trim()} label="目前沒有待配對登記" onClear={()=>{setSearch('');setPage(1);}} />)}
    <Drawer className="identity-drawer" isOpen={registration!==null} onClose={close} closeDisabled={busy} closeLabel="關閉配對明細" title="配對客戶與訂單" footer={order&&!uncertain?<><button type="button" className="identity-button" disabled={busy} onClick={()=>{setOrder(null);setConfirmed(false);}}>重新選擇</button><button type="button" className="identity-button primary" disabled={busy||!confirmed} onClick={()=>void apply()}>{busy?'正在配對…':'確認配對並綁定'}</button></>:undefined}>
      {error&&<p className="identity-error" role="alert">{error}</p>}{uncertain&&<button type="button" className="identity-button" disabled={busy} onClick={()=>void readBack()}>重新查詢配對結果</button>}
      {registration&&<><p className="identity-secondary">{order?'2 核對配對':'1 選擇訂單'}</p><div className="identity-person"><div><h3>{registration.name}</h3><small className="identity-secondary">LINE 登記 · {phone(registration.phone)}</small></div></div>
      {!order?<><SearchField value={orderSearch} onChange={setOrderSearch} label="搜尋訂單姓名或案件編號" /><div className="identity-order-options">{orders.length?orders.map(item=><div key={item.case_no} className="identity-order-option"><div><strong>{item.client_name}</strong><small className="identity-secondary">{item.case_no} · {phone(item.client_phone)}</small></div><button type="button" className="identity-button" aria-label={`選擇${item.client_name}的訂單`} onClick={()=>{setOrder(item);setConfirmed(false);}}>選擇</button></div>):<p className="identity-note">找不到符合條件的訂單，尚無對應訂單時可先保留這筆登記。</p>}</div></>:<><div className="identity-comparison"><div><span>LINE 登記</span><strong>{registration.name}</strong><small>{phone(registration.phone)}</small></div><div><span>正式訂單</span><strong>{order.client_name}</strong><small>{phone(order.client_phone)}<br/>{order.case_no}</small></div></div>{registration.name!==order.client_name&&<p className="identity-note warning">兩側姓名有差異，請確認為同一位客戶後再配對。</p>}<><label className="identity-field">配對原因<textarea ref={reasonRef} aria-required="true" rows={3} maxLength={1000} value={reason} disabled={busy||uncertain} onChange={event=>{setReason(event.target.value);setConfirmed(false);}} /></label>{saveValidation.feedback}</><label className="identity-check"><input type="checkbox" checked={confirmed} disabled={busy||uncertain} onChange={event=>setConfirmed(event.target.checked)} />我已核對姓名、電話與案件，確認為同一位客戶</label></>}
      </>}
    </Drawer>
  </>;
}
