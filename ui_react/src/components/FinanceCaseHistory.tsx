/** Preserve access to every immutable entry, including reversals and advances. */
import { useEffect, useState } from 'react';
import { clientFinanceHistoryClient, type ClientFinanceHistory } from '../api/client_finance/client_finance_history_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
export const financeEntryLabels: Record<string, string> = { receipt: '客戶收款', refund: '客戶退款', adjustment: '調整', reversal: '沖正', subsidy_return: '補助退款', subsidy_advance: '工會代墊補助' };
export function FinanceCaseHistory({ caseNo, revision }: { caseNo: string; revision: number }) {
  const [data, setData] = useState<ClientFinanceHistory | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError(false);
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      void clientFinanceHistoryClient.query(caseNo, controller.signal).then(value => { if (!controller.signal.aborted) setData(value); }).catch(() => { if (!controller.signal.aborted) setError(true); });
    });
    return () => controller.abort();
  }, [caseNo, revision]);
  return <section className="finance-workspace" aria-label="案件帳務歷史紀錄"><h2>案件帳務歷史紀錄</h2>
    {error ? <p role="alert">案件帳務歷史暫時無法取得，請重新整理。</p> : !data ? <p role="status">正在查詢歷史紀錄…</p> : <div className="finance-table-container"><table className="finance-table"><thead><tr><th>日期</th><th>類型</th><th>金額</th><th>狀態</th></tr></thead><tbody>{data.ledger_entries.map(entry => <tr key={entry.entry_id}><td>{entry.occurred_on}</td><td>{financeEntryLabels[entry.entry_type]}</td><td>{financeMoney(entry.amount_ntd)}</td><td>{entry.reversal_of_entry_id ? '沖回原紀錄' : data.ledger_entries.some(other => other.reversal_of_entry_id === entry.entry_id) ? '有沖正紀錄' : '已入帳'}</td></tr>)}</tbody></table>{!data.ledger_entries.length && <p className="finance-state">本案尚無正式入帳紀錄。</p>}</div>}
  </section>;
}
