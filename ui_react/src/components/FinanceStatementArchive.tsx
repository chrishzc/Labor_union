/** Export formally reconciled bank statement details. */
import { useState } from 'react';
import { financeAccountingClient } from '../api/finance_import/finance_accounting_client';
import './FinanceCaseAccounting.css';

export function FinanceStatementArchive({ compact = false }: {compact?: boolean} = {}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function download() {
    if (busy) return;
    setBusy(true); setMessage(''); setError('');
    try {
      const blob = await financeAccountingClient.download();
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement('a'); anchor.href = url;
        anchor.download = '銀行對帳明細.xlsx';
        anchor.click();
      } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
      setMessage('對帳明細已匯出。');
    } catch { setError('匯出失敗，請稍後重試。'); }
    finally { setBusy(false); }
  }

  const controls = <>
    <button type="button" className="finance-btn-primary" disabled={busy}
      onClick={() => void download()} aria-label="匯出對帳明細">
      {busy ? '匯出中…' : '匯出對帳明細'}
    </button>
    {message && <span role="status" className="statement-result">{message}</span>}
    {error && <span role="alert" className="statement-field-error">{error}</span>}
  </>;
  if (compact) return controls;
  return <section className="case-accounting-card statement-archive" aria-label="成功對帳明細">
    <div className="finance-section-heading statement-archive-heading">
      <div><h3>成功對帳明細</h3><p>包含正式核銷資料。</p></div>
      <div className="statement-archive-actions">{controls}</div>
    </div>
  </section>;
}
