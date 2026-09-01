import { useEffect, useState } from 'react';
import { paymentDestinationClient, type PaymentDestination, type PaymentDestinationPreview } from '../api/client_finance/payment_destination_client';

export function PaymentDestinationConfigurationPanel({ reload }: { reload: number }) {
  const [current, setCurrent] = useState<PaymentDestination | null>(null);
  const [account, setAccount] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<PaymentDestinationPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let active = true;
    setStatus('loading');
    paymentDestinationClient.query().then((value) => {
      if (!active) return;
      setCurrent(value); setAccount(value.account_display ?? ''); setPreview(null); setConfirmed(false); setStatus('ready');
    }).catch(() => { if (active) { setStatus('error'); setMessage('收款帳戶設定載入失敗，請重新整理。'); } });
    return () => { active = false; };
  }, [reload]);

  const runPreview = async () => {
    if (!current || !account.trim()) return;
    setStatus('saving'); setMessage('');
    try { setPreview(await paymentDestinationClient.preview(account.trim(), current.revision)); setConfirmed(false); setStatus('ready'); }
    catch { setStatus('error'); setMessage('無法完成預覽；資料可能已變更，請重新載入。'); }
  };
  const apply = async () => {
    if (!preview || !confirmed || !reason.trim()) return;
    setStatus('saving'); setMessage('');
    try {
      await paymentDestinationClient.apply(preview, reason.trim());
      const refreshed = await paymentDestinationClient.query();
      setCurrent(refreshed); setAccount(refreshed.account_display ?? ''); setPreview(null); setConfirmed(false); setReason(''); setStatus('ready'); setMessage('工會／代收付帳戶已更新，契約會使用這筆 current 設定。');
    } catch { setStatus('error'); setMessage('帳戶設定未完成，請重新載入後再次預覽。'); }
  };

  return <section className="finance-workspace" data-surface-id="finance.payment-destination.configuration">
    <div className="finance-section-heading"><div><h2>工會／代收付帳戶</h2><p>客戶契約的服務款項匯款帳號會自動帶入這筆資料；不會使用月嫂個人帳戶。</p></div></div>
    {status === 'loading' && <div className="finance-state" role="status">正在載入目前設定…</div>}
    {message && <div className={`finance-state ${status === 'error' ? 'error' : ''}`} role={status === 'error' ? 'alert' : 'status'}>{message}</div>}
    {current && <div className="finance-detail-block">
      <div className="finance-meta"><span>目前版本：{current.revision}</span><span>{current.configured ? '已設定' : '尚未設定；客戶契約將阻擋列印'}</span></div>
      <label className="finance-field"><span>工會／代收付帳戶</span><input value={account} maxLength={255} autoComplete="off" onChange={(event) => { setAccount(event.target.value); setPreview(null); setConfirmed(false); }} placeholder="例如：銀行代碼－帳號" /></label>
      <button type="button" className="finance-btn-secondary" disabled={status === 'saving' || !account.trim()} onClick={() => void runPreview()}>檢查設定影響</button>
      {preview && <div className="finance-meta" data-control-id="finance.payment-destination.preview"><span>契約將顯示：{preview.candidate_account_display}</span>
        <label className="finance-field"><span>更新原因</span><input value={reason} maxLength={255} onChange={(event) => setReason(event.target.value)} /></label>
        <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對帳戶內容，確認套用</label>
        <button type="button" className="finance-btn-primary" disabled={!confirmed || !reason.trim() || status === 'saving'} onClick={() => void apply()}>確認更新帳戶</button>
      </div>}
    </div>}
  </section>;
}
