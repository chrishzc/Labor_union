import { useEffect, useRef, useState } from 'react';
import { sessionClient } from '../api/auth/session_client';
import type { AdminPublic } from '../api/auth/two_step_auth_schemas';
import { registryDeletionClient, type RegistryDeletionKind, type RegistryDeletionPreview } from '../api/registry_deletion_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedDraft, useUnsavedNavigation } from './UnsavedChanges';
import './RegistryDeletionPanel.css';

type Phase = 'idle' | 'checking' | 'ready' | 'pending' | 'unknown' | 'error';

export function RegistryDeletionPanel({ kind, identity, label, disabled = false, onBusyChange, onDeleted }: {
  kind: RegistryDeletionKind; identity: string; label: string; disabled?: boolean;
  onBusyChange: (busy: boolean) => void; onDeleted: () => void;
}) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [preview, setPreview] = useState<RegistryDeletionPreview | null>(null);
  const [message, setMessage] = useState('');
  const [principal, setPrincipal] = useState<AdminPublic | null>(null);
  const [authorityStatus, setAuthorityStatus] = useState<'checking' | 'ready' | 'error'>('checking');
  const [authorityRetry, setAuthorityRetry] = useState(0);
  const command = useRef<{ preview: RegistryDeletionPreview; key: string } | null>(null);
  const inFlight = useRef(false);
  const alive = useRef(true);
  const { requestLeave } = useUnsavedNavigation();
  const busy = phase === 'checking' || phase === 'pending' || phase === 'unknown';
  const token = sessionClient.getToken();
  const root = principal?.is_root === true && principal.id !== null;
  const deleteLabel = '刪除此案件';
  const guardRef = useUnsavedDraft('永久刪除確認', {}, { enabled: root, busy });
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusyChange(busy); return () => onBusyChange(false); }, [busy, onBusyChange]);
  useEffect(() => {
    const controller = new AbortController();
    setPrincipal(null);
    if (!token) { setAuthorityStatus('ready'); return; }
    setAuthorityStatus('checking');
    void sessionClient.fetchCurrentUser({ signal: controller.signal }).then(user => {
      if (controller.signal.aborted) return;
      setPrincipal(user); setAuthorityStatus('ready');
    }).catch(() => {
      if (!controller.signal.aborted) setAuthorityStatus('error');
    });
    return () => controller.abort();
  }, [token, authorityRetry]);

  if (authorityStatus === 'checking') return <p role="status">正在確認刪除權限…</p>;
  if (authorityStatus === 'error') return <p role="alert">無法確認刪除權限。<button type="button" onClick={() => setAuthorityRetry(value => value + 1)}>重新確認刪除權限</button></p>;
  if (!root) return <p className="registry-section-note">目前登入帳號沒有永久刪除權限。</p>;
  const inspect = async () => {
    if (inFlight.current || busy || disabled) return;
    inFlight.current = true;
    setPhase('checking'); setMessage(''); setPreview(null); command.current = null;
    try {
      const value = await registryDeletionClient.preview(kind, identity);
      if (!alive.current) return;
      setPreview(value); setPhase('ready');
    } catch (error) {
      if (!alive.current) return;
      setPhase('error'); setMessage(error instanceof Error ? error.message : '無法檢查刪除資格。');
    } finally { inFlight.current = false; }
  };
  const apply = async () => {
    if (inFlight.current || (phase !== 'unknown' && (disabled || phase !== 'ready' || !preview || preview.blockers.length > 0))) return;
    if (!command.current && preview) command.current = { preview, key: `registry-delete-${crypto.randomUUID()}` };
    const current = command.current;
    if (!current) return;
    inFlight.current = true;
    setPhase('pending'); setMessage('');
    try {
      await registryDeletionClient.apply(current.preview, current.key);
      if (!alive.current) return;
      setPhase('idle'); command.current = null; onBusyChange(false); onDeleted();
    } catch (error) {
      if (!alive.current) return;
      const rejected = error instanceof ApiHttpError && [401, 403, 404, 409, 422].includes(error.status);
      setPhase(rejected ? 'error' : 'unknown');
      setMessage(rejected ? error.message : '刪除結果尚未確認。請按「重新確認刪除結果」核對；期間請勿修改資料或離開。');
      if (rejected) { setPreview(null); command.current = null; }
    } finally { inFlight.current = false; }
  };
  return <section ref={guardRef} aria-label="root 永久刪除" className="registry-deletion-panel">
    <h3>永久刪除</h3>
    <p>永久刪除「{label}」後無法復原。未簽約案件的配對、排班、帳務及歷程會一併刪除；相關月嫂資料保留。任一月嫂或客戶已簽回時禁止刪除。</p>
    {(phase === 'idle' || phase === 'error') && <button type="button" disabled={disabled} onClick={() => requestLeave(() => { void inspect(); })}>{deleteLabel}</button>}
    {phase === 'checking' && <p role="status">正在檢查簽約狀態…</p>}
    {phase === 'ready' && preview && <>
      {preview.blockers.length > 0 ? <><p role="alert">此筆資料不可刪除：</p><ul>{preview.blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul></>
        : <><p>目前尚無月嫂或客戶簽回。確認連同關聯資料永久刪除「{label}」？</p><button type="button" disabled={disabled} onClick={() => requestLeave(() => { void apply(); })}>確認永久刪除</button></>}
      <button type="button" disabled={disabled} onClick={() => { setPreview(null); setPhase('idle'); }}>取消</button>
    </>}
    {phase === 'pending' && <p role="status">正在確認刪除結果…</p>}
    {message && <p role="alert">{message}</p>}
    {phase === 'unknown' && <button type="button" onClick={() => { void apply(); }}>重新確認刪除結果</button>}
  </section>;
}
