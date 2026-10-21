import { useEffect, useRef, useState } from 'react';
import { depositSkipClient, type DepositSkipPreview, type DepositSkipStatus } from '../api/client_finance/deposit_skip_client';
import { ApiHttpError } from '../api/shared/typed_errors';

interface Props { caseNo: string; revision?: number; onCommitted?: () => void; onBusyChange?: (busy: boolean) => void }
export function ServiceArrangementDepositGate({ caseNo, revision, onCommitted, onBusyChange }: Props) {
  const [facts, setFacts] = useState<DepositSkipStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const command = useRef<{ preview: DepositSkipPreview; key: string } | null>(null);
  useEffect(() => { onBusyChange?.(busy || unknown); }, [busy, unknown, onBusyChange]);
  useEffect(() => {
    let active = true;
    if (command.current) return;
    void depositSkipClient.query(caseNo).then(value => {
      if (value.case_no !== caseNo) throw new Error('訂金狀態案件不一致。');
      if (active) { setFacts(value); setError(''); }
    }).catch(caught => { if (active) setError(caught instanceof Error ? caught.message : '無法讀取訂金狀態。'); });
    return () => { active = false; };
  }, [caseNo, revision]);
  const paid = facts !== null && facts.deposit_net_received_ntd >= facts.deposit_required_ntd && facts.deposit_required_ntd > 0;
  const released = facts?.unpaid_progression_allowed === true;
  const release = async () => {
    if (busy || !facts || (!unknown && facts.blockers.length > 0)) return;
    setBusy(true); setError('');
    try {
      if (!command.current) {
        const fresh = await depositSkipClient.preview(caseNo);
        if (fresh.case_no !== caseNo) throw new Error('訂金狀態案件不一致。');
        if (fresh.blockers.length > 0) { setFacts(await depositSkipClient.query(caseNo)); setError('訂金條件已更新，請依目前訂金鎖狀態接續處理。'); return; }
        command.current = { preview: fresh, key: `deposit-skip-${caseNo}-${crypto.randomUUID()}` };
      }
      const original = command.current;
      const receipt = await depositSkipClient.apply(caseNo, original.preview, '', original.key);
      if (receipt.case_no !== caseNo || !receipt.unpaid_progression_allowed) throw new Error('未付款放行結果尚未確認。');
      const current = await depositSkipClient.query(caseNo);
      if (current.case_no !== caseNo || !current.unpaid_progression_allowed || current.account_version < receipt.account_version) throw new Error('未付款放行尚未完成正式回讀。');
      setFacts(current); command.current = null; setUnknown(false);
      setNotice('已人工放行；訂金仍維持未付，預留檔期會在自動排班時轉為正式班表。');
      onCommitted?.();
    } catch (caught) {
      const definitive = caught instanceof ApiHttpError && caught.status >= 400 && caught.status < 500 && ![408, 429].includes(caught.status);
      if (definitive && !unknown) command.current = null;
      else if (command.current) setUnknown(true);
      setError(caught instanceof Error ? caught.message : '尚未確認放行結果，請確認原操作結果。');
    } finally { setBusy(false); }
  };
  return <section className="service-arrangement-deposit" aria-label="訂金鎖狀態"><header><div><h3>訂金鎖狀態</h3><p>{!facts ? '正在讀取訂金狀態…' : paid ? '已解除・訂金已付清' : released ? '已解除・未付款人工放行' : facts.deposit_required_ntd === 0 ? '尚未建立訂金應收' : '鎖定中・訂金未付清'}</p></div>
    {facts && !paid && !released && <button type="button" disabled={busy || (!unknown && facts.blockers.length > 0)} onClick={() => void release()}>{busy ? '放行並回讀中…' : unknown ? '確認原放行處理結果' : '未付款人工放行'}</button>}
  </header>{facts && <p>訂金應收 NT$ {facts.deposit_required_ntd.toLocaleString()} · 已核銷 NT$ {facts.deposit_net_received_ntd.toLocaleString()}</p>}
    {facts && !paid && !released && facts.blockers.map(code => <p key={code}>{code === 'deposit_skip.general_citizen_required' ? '此案件類型尚不適用未付款放行。' : code === 'deposit_skip.deposit_obligation_required' ? '請先完成契約及訂金應收建立。' : code}</p>)}
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
