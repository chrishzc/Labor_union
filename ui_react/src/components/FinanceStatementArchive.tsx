/** Successful formal statements and separately retained historical references. */
import { useState } from 'react';
import { financeAccountingClient } from '../api/finance_import/finance_accounting_client';
import './FinanceCaseAccounting.css';

export function FinanceStatementArchive({ compact = false }: {compact?: boolean} = {}) {
  const [busy, setBusy] = useState<'success' | 'reference' | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function download(reference = false) {
    if (busy) return;
    setBusy(reference ? 'reference' : 'success'); setMessage(''); setError('');
    try {
      const blob = reference ? await financeAccountingClient.downloadLegacyReferences() : await financeAccountingClient.download();
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement('a'); anchor.href = url;
        anchor.download = reference ? '歷史人工備查明細.xlsx' : '銀行成功對帳明細.xlsx';
        anchor.click();
      } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
      setMessage(reference ? '歷史備查明細已匯出，不代表已核銷。' : '成功明細已匯出。');
    } catch { setError('匯出失敗，請稍後重試。'); }
    finally { setBusy(null); }
  }

  const controls = <>
    <button type="button" className="finance-btn-primary" disabled={busy !== null}
      onClick={() => void download()} aria-label="匯出 Excel">
      {busy === 'success' ? '匯出中…' : '匯出 Excel'}
    </button>
    <button type="button" className="finance-btn-secondary" disabled={busy !== null}
      onClick={() => void download(true)} aria-label="匯出歷史備查">
      {busy === 'reference' ? '匯出中…' : '匯出歷史備查'}
    </button>
    {message && <span role="status" className="statement-result">{message}</span>}
    {error && <span role="alert" className="statement-field-error">{error}</span>}
  </>;
  if (compact) return controls;
  return <section className="case-accounting-card statement-archive" aria-label="成功對帳明細">
    <div className="finance-section-heading statement-archive-heading">
      <div><h3>成功對帳明細</h3><p>只包含正式核銷資料；歷史人工備查另行匯出。</p></div>
      <div className="statement-archive-actions">{controls}</div>
    </div>
  </section>;
}
