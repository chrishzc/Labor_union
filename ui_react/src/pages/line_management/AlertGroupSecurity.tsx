/** Existing administrator notification targets; group alerts have been retired. */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, ShieldCheck } from 'lucide-react';
import { useUnsavedDraft } from '../../components/UnsavedChanges';
import { lineRuntimeTargetClient } from '../../api/line_runtime_targets/line_runtime_target_client';
import { LineRuntimeTargetError } from '../../api/line_runtime_targets/line_runtime_target_errors';
import type { LineRuntimeTarget, LineRuntimeTargetReceipt, LineRuntimeAdminCandidate } from '../../api/line_runtime_targets/line_runtime_target_schemas';
import '../LineManagementPage.css';

export interface RuntimeTargetClient {
  listAdminCandidates?: typeof lineRuntimeTargetClient.listAdminCandidates;
  previewAddAdminTarget?: typeof lineRuntimeTargetClient.previewAddAdminTarget;
  addAdminTarget?: typeof lineRuntimeTargetClient.addAdminTarget;
  listTargets: typeof lineRuntimeTargetClient.listTargets;
  previewSetEnabled: typeof lineRuntimeTargetClient.previewSetEnabled;
  setEnabled: typeof lineRuntimeTargetClient.setEnabled;
  previewResetGroup: typeof lineRuntimeTargetClient.previewResetGroup;
  resetGroup: typeof lineRuntimeTargetClient.resetGroup;
  getPreferences?: typeof lineRuntimeTargetClient.getPreferences;
  updatePreferences?: typeof lineRuntimeTargetClient.updatePreferences;
}
export interface AlertGroupSecurityProps { client?: RuntimeTargetClient; runtimeTargetClient?: RuntimeTargetClient }
const identity = () => crypto.randomUUID();
const publicFailure = (error: unknown) => error instanceof LineRuntimeTargetError
  ? error.message : '目前無法取得或更新通知對象，請稍後再試。';

export const AlertGroupSecurity: React.FC<AlertGroupSecurityProps> = ({ client, runtimeTargetClient }) => {
  const targetClient = client ?? runtimeTargetClient ?? lineRuntimeTargetClient;
  const [targets, setTargets] = useState<LineRuntimeTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [receipt, setReceipt] = useState<LineRuntimeTargetReceipt | null>(null);
  const [readback, setReadback] = useState('');
  const [reload, setReload] = useState(0);
  const [candidates, setCandidates] = useState<LineRuntimeAdminCandidate[]>([]);
  const [candidateId, setCandidateId] = useState('');
  const [candidateError, setCandidateError] = useState('');
  const addIntent = useRef<{signature:string;key:string}|null>(null);
  const submitting = useRef(false);
  const intent = useRef<{ signature: string; key: string } | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError(null);
    try {
      const rows = await targetClient.listTargets({ correlationId: `line-target-query:${identity()}`, signal });
      if (!signal?.aborted) setTargets(rows.filter(row => row.target_kind === 'admin_user'));
    } catch (failure) {
      if (!signal?.aborted) { setTargets([]); setError(publicFailure(failure)); }
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [targetClient]);
  useEffect(() => {
    const controller = new AbortController(); void load(controller.signal);
    return () => controller.abort();
  }, [load, reload]);
  useEffect(() => {
    const controller = new AbortController();
    if (targetClient.listAdminCandidates) void targetClient.listAdminCandidates({correlationId:`line-target-candidates:${identity()}`,signal:controller.signal})
      .then(rows=>{if(!controller.signal.aborted){setCandidates(rows);setCandidateError('');}})
      .catch(failure=>{if(!controller.signal.aborted)setCandidateError(publicFailure(failure));});
    return()=>controller.abort();
  }, [targetClient, reload]);
  useUnsavedDraft('管理員通知對象', { '原因': reason }, { busy, resetKey: receipt });

  const toggle = async (target: LineRuntimeTarget) => {
    if (submitting.current) return;
    submitting.current = true;
    const signature = JSON.stringify([target.target_id, target.current_version, target.state, reason.trim()]);
    if (intent.current?.signature !== signature) intent.current = { signature, key: identity() };
    const request = {
      expected_version: target.current_version, enabled: target.state !== 'active', reason: reason.trim(),
      correlation_id: `line-target:${intent.current.key}`, idempotency_key: `line-target:${intent.current.key}`,
    };
    setBusy(true); setError(null); setReceipt(null); setReadback('');
    try {
      const preview = await targetClient.previewSetEnabled(target.target_id, request);
      if (!preview.apply_ready) { setError('目前無法變更此通知對象，請重新整理。'); return; }
      const applied = await targetClient.setEnabled(target.target_id, { ...request, preview_fingerprint: preview.preview_fingerprint });
      intent.current = null; setReceipt(applied);
      try {
        const rows = await targetClient.listTargets({ correlationId: `line-target-readback:${identity()}` });
        setTargets(rows.filter(row => row.target_kind === 'admin_user'));
        setReadback('已重新查詢並確認最新狀態。');
      } catch { setReadback('變更已受理，最新狀態暫時無法取得；請重新整理。'); }
    } catch (failure) { setError(publicFailure(failure)); }
    finally { submitting.current = false; setBusy(false); }
  };
  const add = async () => {
    if(submitting.current || !candidateId || !targetClient.previewAddAdminTarget || !targetClient.addAdminTarget)return;
    submitting.current=true;setBusy(true);setError(null);setReceipt(null);
    const signature=JSON.stringify([candidateId,reason.trim()]);
    if(addIntent.current?.signature!==signature)addIntent.current={signature,key:identity()};
    const request={admin_user_id:Number(candidateId),minimum_status:'warning' as const,reason:reason.trim(),
      correlation_id:`line-target-add:${addIntent.current.key}`,idempotency_key:`line-target-add:${addIntent.current.key}`};
    try {
      const preview=await targetClient.previewAddAdminTarget(request);
      if(!preview.apply_ready){setError('目前無法新增此通知對象，請核對 LINE 綁定。');return;}
      setReceipt(await targetClient.addAdminTarget({...request,preview_fingerprint:preview.preview_fingerprint}));
      addIntent.current=null;setCandidateId('');setReason('');setReadback('已重新查詢最新通知對象。');await load();setReload(v=>v+1);
    }catch(failure){setError(publicFailure(failure));}finally{submitting.current=false;setBusy(false);}
  };
  return <div className="alert-group-security-container">
    <header className="line-hub-page-header">
      <div className="line-hub-page-heading"><span className="line-hub-page-icon" aria-hidden="true"><ShieldCheck /></span>
        <div><p className="line-hub-eyebrow">LINE 專區</p><h1>管理員通知對象</h1>
          <p>管理員須先綁定 LINE，才能接收個人通知。</p></div>
      </div>
    </header>
    <section className="line-workspace-card" aria-labelledby="alert-targets-title">
      <div className="line-section-heading"><h2 id="alert-targets-title">目前通知對象</h2>
        <button className="line-secondary-btn" disabled={loading || busy} onClick={() => setReload(value => value + 1)}>
          <RefreshCw aria-hidden="true" />{loading ? '查詢中…' : '重新整理'}</button></div>
      {error && <p className="line-error" role="alert">{error}</p>}
      {targetClient.listAdminCandidates && <section aria-label="新增管理員通知對象">
        <h3>新增通知對象</h3>
        {candidateError && <p role="alert">{candidateError}</p>}
        {!candidateError && candidates.length===0 && !loading && <p>目前沒有已綁定 LINE 的可用管理員，請先完成身分綁定。</p>}
        <label>工會人員<select aria-label="選擇通知對象" value={candidateId} disabled={busy} onChange={event=>setCandidateId(event.target.value)}><option value="">請選擇人員</option>{candidates.map(candidate=><option key={candidate.candidate_id} value={candidate.candidate_id}>{candidate.display_label}{candidate.line_linked?'':'（未綁定 LINE）'}</option>)}</select></label>
        <button type="button" className="line-primary-btn" disabled={busy || !candidateId} onClick={()=>void add()}>新增通知對象</button>
        <a className="line-secondary-btn" href="#line-management?tab=binding">前往 LINE 身分綁定</a>
      </section>}
      {!loading && !error && targets.length === 0 && <p>目前沒有已設定的管理員通知對象。</p>}
      <div className="line-grid-cards">{targets.map(target => <article className="line-info-card" key={target.target_id}>
        <strong>{target.display_label}</strong><p>{target.state === 'active' ? '啟用' : '停用'}</p>
        <p>更新時間：{target.updated_at}</p>
        <button className="line-secondary-btn" disabled={busy} onClick={() => void toggle(target)}>
          {target.state === 'active' ? '停用通知' : '啟用通知'}</button>
      </article>)}</div>
      {targets.length > 0 && <label>變更原因（選填）<input value={reason} onChange={event => setReason(event.target.value)} disabled={busy} /></label>}
      {receipt && <p role="status">變更已受理。{readback}</p>}
    </section>
  </div>;
};
