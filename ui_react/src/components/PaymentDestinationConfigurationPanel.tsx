import { useUnsavedChanges } from './UnsavedChanges';
import { useEffect, useRef, useState } from 'react';
import { ApiHttpError } from '../api/shared/typed_errors';
import { paymentDestinationClient, type PaymentDestination, type PaymentDestinationPreview } from '../api/client_finance/payment_destination_client';

export function PaymentDestinationConfigurationPanel({ reload }: { reload: number }) {
  const [current, setCurrent] = useState<PaymentDestination | null>(null);
  const [account, setAccount] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<PaymentDestinationPreview | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'unknown' | 'error'>('loading');
  const [message, setMessage] = useState('');
  const pending = useRef<{ preview: PaymentDestinationPreview; reason: string; key: string } | null>(null);
  const dirty = !!current && (account !== (current.account_display ?? '') || reason !== '');
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const locked = status === 'saving' || status === 'unknown';

  useEffect(() => {
    if (dirtyRef.current || pending.current) return;
    let active = true;
    setStatus('loading');
    paymentDestinationClient.query().then((value) => {
      if (!active || dirtyRef.current) return;
      setCurrent(value); setAccount(value.account_display ?? ''); setPreview(null); setStatus('ready');
    }).catch(() => { if (active) { setStatus('error'); setMessage('收款帳戶設定載入失敗，請重新整理。'); } });
    return () => { active = false; };
  }, [reload]);

  useUnsavedChanges('工會／代收付帳戶', dirty ? [{ label: '帳戶設定', before: '既有設定（不顯示帳號）', after: '已修改，請核對原畫面的設定' }] : [], { busy: locked, save: () => apply(), discard: () => { setAccount(current?.account_display ?? ''); setReason(''); } });
  const apply = async () => {
    if (!current || !account.trim() || status === 'saving') return;
    setStatus('saving'); setMessage('');
    let submitted = false;
    let applied = false;
    try {
      const approved = pending.current?.preview ?? preview ?? await paymentDestinationClient.preview(account.trim(), current.revision);
      setPreview(approved);
      const command = pending.current ?? { preview: approved, reason: reason.trim(), key: `payment-destination-${crypto.randomUUID()}` };
      pending.current = command; submitted = true;
      const receipt = await paymentDestinationClient.apply(command.preview, command.reason, command.key);
      applied = true;
      const refreshed = await paymentDestinationClient.query();
      if (refreshed.revision < receipt.resulting_revision || (refreshed.revision === receipt.resulting_revision && refreshed.account_display !== receipt.account_display)) throw new Error('readback mismatch');
      pending.current = null;
      setCurrent(refreshed); setAccount(refreshed.account_display ?? ''); setPreview(null); setReason(''); setStatus('ready'); setMessage('工會／代收付帳戶已更新。');
    } catch (error) {
      const unknown = applied || (submitted && (!(error instanceof ApiHttpError) || error.status >= 500 || error.status === 408));
      if (!unknown) pending.current = null;
      setStatus(unknown ? 'unknown' : 'error'); setMessage(unknown ? '儲存結果尚未確認；請重試原儲存，確認完成前保留本畫面。' : '帳戶設定未完成，請重新查詢目前設定。');
    }
  };

  return <section className="finance-workspace" data-surface-id="finance.payment-destination.configuration">
    <div className="finance-section-heading"><div><h2>工會／代收付帳戶</h2><p>客戶契約的服務款項匯款帳號會自動帶入這筆資料；不會使用月嫂個人帳戶。</p></div></div>
    {status === 'loading' && <div className="finance-state" role="status">正在載入目前設定…</div>}
    {message && <div className={`finance-state ${status === 'error' ? 'error' : ''}`} role={status === 'error' ? 'alert' : 'status'}>{message}</div>}
    {current && <div className="finance-detail-block">
      <div className="finance-meta"><span>目前版本：{current.revision}</span><span>{current.configured ? '已設定' : '尚未設定；客戶契約將阻擋列印'}</span></div>
      <label className="finance-field"><span>工會／代收付帳戶</span><input value={account} maxLength={255} disabled={locked} autoComplete="off" onChange={(event) => { setAccount(event.target.value); setPreview(null); }} placeholder="例如：銀行代碼－帳號" /></label>
      <label className="finance-field"><span>備註（選填）</span><input value={reason} maxLength={255} disabled={locked} onChange={(event) => setReason(event.target.value)} /></label>
      <button type="button" className="finance-btn-primary" disabled={status === 'saving' || !account.trim()} onClick={() => void apply()}>{status === 'saving' ? '正在儲存…' : status === 'unknown' ? '重試原儲存' : '儲存帳戶'}</button>
    </div>}
  </section>;
}
