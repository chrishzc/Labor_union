import React, { useEffect, useRef, useState } from 'react';
import { caseVirtualAccountClient, type CaseVirtualAccountCommand, type CaseVirtualAccountView } from '../api/client_finance/case_virtual_account_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { RegistryEditState } from './ClientRegistryDetailEditor';

interface Props {
  caseNo: string;
  disabled: boolean;
  onRefresh: () => Promise<unknown>;
  onStateChange: (state: RegistryEditState) => void;
}
type Phase = 'loading' | 'idle' | 'stale' | 'applying' | 'unknown' | 'readback' | 'readback_failed';
type Submission = { command: CaseVirtualAccountCommand; key: string };
const initialAccount = (view: CaseVirtualAccountView) => view.imported_virtual_accounts.length === 1 ? view.imported_virtual_accounts[0] : '';
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作失敗，請重試。';

export const ClientRegistryVirtualAccount: React.FC<Props> = ({ caseNo, disabled, onRefresh, onStateChange }) => {
  const [view, setView] = useState<CaseVirtualAccountView | null>(null);
  const [account, setAccount] = useState('');
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  const [message, setMessage] = useState('');
  const sequence = useRef(0);
  const busy = ['applying', 'unknown', 'readback', 'readback_failed'].includes(phase);
  const dirty = !!view && account !== initialAccount(view);
  useEffect(() => { onStateChange({ dirty, busy }); }, [dirty, busy, onStateChange]);
  const load = async () => {
    const request = ++sequence.current;
    setPhase('loading'); setMessage('');
    try {
      const result = await caseVirtualAccountClient.query(caseNo);
      if (request !== sequence.current) return;
      setView(result); setAccount(initialAccount(result)); setSubmission(null); setPhase('idle');
    } catch (error) {
      if (request === sequence.current) { setMessage(`虛擬帳號讀取失敗：${errorText(error)}`); setPhase('idle'); }
    }
  };
  useEffect(() => { void load(); return () => { ++sequence.current; }; }, [caseNo]);
  const readback = async (request: number) => {
    setPhase('readback');
    try {
      const [result] = await Promise.all([caseVirtualAccountClient.query(caseNo), onRefresh()]);
      if (request !== sequence.current) return;
      setView(result); setAccount(initialAccount(result)); setSubmission(null); setPhase('idle');
      setMessage('虛擬帳號已儲存，名冊資料已更新。');
    } catch (error) {
      if (request === sequence.current) { setPhase('readback_failed'); setMessage(`已儲存，但最新資料讀取失敗：${errorText(error)}`); }
    }
  };
  const apply = async () => {
    if (!view) return;
    const submitted = phase === 'unknown' && submission ? submission : {
      command: { case_no: caseNo, virtual_account: account.trim(), expected_mapping_ids: view.mapping_ids },
      key: `case-va-${crypto.randomUUID()}`,
    };
    setSubmission(submitted);
    const request = ++sequence.current;
    setPhase('applying'); setMessage('正在儲存虛擬帳號…');
    try {
      await caseVirtualAccountClient.apply(submitted.command, submitted.key);
      if (request === sequence.current) await readback(request);
    } catch (error) {
      if (request !== sequence.current) return;
      const unknown = !(error instanceof ApiHttpError) || error.status >= 500;
      setPhase(unknown ? 'unknown' : error.code === 'case_virtual_account_stale' ? 'stale' : 'idle');
      if (!unknown) setSubmission(null);
      setMessage(unknown ? `儲存結果尚未確認：${errorText(error)} 請按「確認同一筆儲存結果」核對。` : errorText(error));
    }
  };
  const locked = disabled || busy || phase === 'loading';
  return <section className="registry-editor" aria-label="虛擬帳號設定">
    <h3>虛擬帳號設定</h3>
    <p className="registry-section-note">儲存後將取代本案全部匯入虛擬帳號，供後續契約與收款辨識使用。</p>
    {phase === 'loading' && <p role="status">正在讀取虛擬帳號…</p>}
    {view && <>
      <dl className="registry-information-fields"><div><dt>目前匯入虛擬帳號</dt><dd>{view.imported_virtual_accounts.join('、') || '未登錄，使用內建帳號'}</dd></div><div><dt>內建虛擬帳號</dt><dd>{view.built_in_virtual_account ?? '此案件無法產生內建帳號'}</dd></div></dl>
      <div className="registry-fields">
        <label>匯入虛擬帳號<input inputMode="numeric" maxLength={14} value={account} disabled={locked} placeholder="99781699 開頭，共 14 碼" onChange={event => { setAccount(event.target.value); setSubmission(null); setMessage(''); }} /></label>
      </div>
      <div className="registry-actions">
        <button type="button" disabled={locked} onClick={() => { setAccount(initialAccount(view)); setSubmission(null); setMessage(''); }}>取消帳號變更</button>
        <button type="button" disabled={locked || phase === 'stale' || !account.trim() || !dirty} onClick={() => void apply()}>儲存虛擬帳號</button>
      </div>
    </>}
    {message && <p role="status">{message}</p>}
    {(!view || phase === 'stale') && phase !== 'loading' && <button type="button" disabled={disabled} onClick={() => void load()}>重新讀取虛擬帳號</button>}
    {phase === 'unknown' && <button type="button" onClick={() => void apply()}>確認同一筆儲存結果</button>}
    {phase === 'readback_failed' && <button type="button" onClick={() => void readback(++sequence.current)}>重新讀取已儲存帳號</button>}
  </section>;
};
