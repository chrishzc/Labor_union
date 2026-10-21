import { useUnsavedDraft } from './UnsavedChanges';
import { useRef, useState, type FC } from 'react';
import { depositSkipClient, type DepositSkipPreview } from '../api/client_finance/deposit_skip_client';

interface Props {
  caseNo: string;
  onCommitted?: () => void | Promise<void>;
}

function blockerLabel(code: string): string {
  if (code === 'deposit_skip.general_citizen_required') return '僅一般市民可由此入口人工跳過訂金。';
  if (code === 'deposit_skip.deposit_obligation_required') return '目前尚未建立訂金應收，無須使用此入口。';
  if (code === 'deposit_skip.deposit_already_settled') return '訂金已付清，無須使用人工放行。';
  return code;
}

export const ClientDepositSkipActions: FC<Props> = ({ caseNo, onCommitted }) => {
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<DepositSkipPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const operation = useRef<{ preview: DepositSkipPreview; reason: string; key: string } | null>(null);
  const save = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const checked = operation.current?.preview ?? await depositSkipClient.preview(caseNo);
      setPreview(checked);
      if (checked.blockers.length) return;
      const command = operation.current ?? { preview: checked, reason: reason.trim(), key: `deposit-skip-${caseNo}-${crypto.randomUUID()}` };
      operation.current = command;
      await depositSkipClient.apply(caseNo, command.preview, command.reason, command.key);
      operation.current = null; setPreview(null); setReason('');
      setMessage('訂金仍維持未付，已允許繼續後續安排。');
      await onCommitted?.();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '無法檢查是否可跳過訂金。');
    } finally {
      setBusy(false);
    }
  };

  useUnsavedDraft('定金略過確認', { '原因': reason }, { busy });


  return (
    <section aria-label="一般市民訂金未付人工放行">
      <h4>一般市民訂金未付人工放行</h4>
      <p>僅供突發狀況使用；不會取消或改變訂金金額，系統會保留操作原因。</p>
      <label>放行原因（選填）
        <textarea value={reason} maxLength={500} disabled={busy || operation.current !== null} onChange={(event) => { setReason(event.target.value); setPreview(null); }} />
      </label>
      <div className="formal-recommendation-actions">
        <button type="button" disabled={busy} onClick={() => void save()}>{operation.current ? '以原操作確認結果' : '儲存未付訂金放行'}</button>
      </div>
      {preview?.blockers.map((blocker) => <p key={blocker}>{blockerLabel(blocker)}</p>)}
      {preview && preview.blockers.length === 0 && <p>檢查通過：訂金應收仍為 {preview.deposit_required_ntd.toLocaleString()} 元，未付狀態不變，放行後可繼續推進。</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
};
