/** Client and government receipts share one workspace; source owners supply money. */
import { useEffect, useState } from 'react';
import { clientFinanceHistoryClient, type ClientFinanceSummary } from '../api/client_finance/client_finance_history_client';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { orderGovernmentSubsidyProjectionClient, type OrderGovernmentSubsidyProjection } from '../api/orders/order_government_subsidy_projection_client';
import { subsidyAdvanceSettlementClient, type AdvanceSettlementRow } from '../api/client_finance/subsidy_advance_settlement_client';

export const financeMoney = (value: number | null) => value === null ? '待確認' : `NT$ ${value.toLocaleString('zh-TW')}`;
export const governmentStatus: Record<OrderGovernmentSubsidyProjection['substatus_code'], string> = {
  claim_lineage_missing: '尚無正式申請紀錄', draft: '申請資料整理中', submitted: '已送件', approved: '政府撥款中', partially_paid: '部分入款', paid: '已入款',
  pending_review: '溢撥待核對', offset_reserved: '折抵保留中', offset_applied: '折抵完成',
};
export const serviceEndLabel = (row: OrderGovernmentSubsidyProjection) => row.service_end_confirmed ? '已確認服務結束' : '待確認服務結束';
export const subsidyEstimateReasons = { eligibility_pending: '補助資格待確認', service_volume_pending: '服務時數待確認', rate_snapshot_missing: '補助單價待確認', amount_not_integer: '補助金額需核對' };
export const governmentServiceQuarter = (row: OrderGovernmentSubsidyProjection) => row.service_end_date && row.claim_quarter ? `${row.service_end_date.slice(0, 4)} 年第 ${row.claim_quarter} 季` : null;
type ClientRow = Omit<ClientFinanceSummary, 'open_receivable_amount_ntd'> & { name: string; open_receivable_amount_ntd: number | null };
type Props = { revision: number; initialSource?: 'client' | 'government'; initialRecovery?: boolean; onOpenCase: (caseNo: string) => void; onOpenSubsidy: (caseNo: string) => void };

export function FinanceReceiptsWorkspace({ revision, initialSource = 'client', initialRecovery = false, onOpenCase, onOpenSubsidy }: Props) {
  const [source, setSource] = useState(initialSource);
  const [status, setStatus] = useState(initialRecovery ? 'recovery' : 'all');
  const [search, setSearch] = useState('');
  const [quarter, setQuarter] = useState('');
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [government, setGovernment] = useState<OrderGovernmentSubsidyProjection[]>([]);
  const [advances, setAdvances] = useState<AdvanceSettlementRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    queueMicrotask(() => {
    if (controller.signal.aborted) return;
    void (async () => {
      if (source === 'client') {
        const [facts, orders] = await Promise.all([
          clientFinanceHistoryClient.queryAll(controller.signal),
          loadAllOrderSummaries(ordersQueryClient.getOrderSummaries.bind(ordersQueryClient), { page_size: 200 }, { signal: controller.signal }),
        ]);
        const names = new Map(orders.items.map(row => [row.case_no, row.client_name]));
        const byCase = new Map<string, ClientRow>(facts.map(row => [row.case_no, { ...row, name: names.get(row.case_no) ?? '客戶資料待確認' }]));
        for (const item of orders.items) {
          if (!byCase.has(item.case_no)) byCase.set(item.case_no, { case_no: item.case_no, name: item.client_name, account_version: '0', open_receivable_amount_ntd: null, open_payable_amount_ntd: 0, obligation_count: 0, ledger_entry_count: 0, receipt_entry_count: 0 });
        }
        if (!controller.signal.aborted) setClients([...byCase.values()]);
      } else if (status === 'recovery') {
        const rows = await subsidyAdvanceSettlementClient.queryAll('', controller.signal);
        if (!controller.signal.aborted) setAdvances(rows);
      } else {
        const rows = await orderGovernmentSubsidyProjectionClient.queryAll({}, { signal: controller.signal });
        if (!controller.signal.aborted) setGovernment(rows);
      }
    })().catch(() => { if (!controller.signal.aborted) setError('收款資料暫時無法取得，請確認權限後重新整理。'); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    });
    return () => controller.abort();
  }, [source, status === 'recovery', revision, refresh]);
  const matches = (value: string) => value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
  const clientRows = clients.filter(row => matches(`${row.case_no} ${row.name}`) && (status === 'all' || (status === 'unpaid' ? row.open_receivable_amount_ntd !== null && row.open_receivable_amount_ntd > 0 : row.receipt_entry_count > 0)));
  const governmentRows = government.filter(row => matches(row.case_no) && (!quarter || governmentServiceQuarter(row) === quarter)
    && (status === 'service_pending' ? !row.service_end_confirmed : status === 'service_confirmed' ? row.service_end_confirmed : status === 'history' ? row.net_allocated_ntd > 0 : true));
  const knownTotal = (values: (number | null)[]) => values.reduce<number | null>((sum, amount) => amount === null ? sum : (sum ?? 0) + amount, null);
  const estimatedTotal = knownTotal(governmentRows.map(row => row.estimated_subsidy_amount_ntd));
  const outstandingTotal = knownTotal(governmentRows.map(row => row.outstanding_amount_ntd));
  const receivedTotal = governmentRows.reduce((sum, row) => sum + row.net_allocated_ntd, 0);
  const advanceRows = advances.filter(row => matches(`${row.case_no} ${row.client_name}`));
  return <section className="finance-workspace finance-collection" aria-label="收款清單">
    <div className="finance-section-heading"><div><h2>收款</h2><p>客戶款項、政府補助與墊款回收，在同一處追蹤。</p></div><button type="button" className="finance-reload-btn" onClick={() => setRefresh(value => value + 1)}>重新整理</button></div>
    <div className="finance-filter-bar">
      <label>收款來源<select className="finance-select" value={source} onChange={event => { setSource(event.target.value as typeof source); setStatus('all'); setSearch(''); setQuarter(''); }}><option value="client">客戶收款</option><option value="government">政府補助</option></select></label>
      <label>狀態<select className="finance-select" value={status} onChange={event => setStatus(event.target.value)}><option value="all">全部</option>{source === 'government' ? <><option value="service_pending">待確認服務結束</option><option value="service_confirmed">已確認服務結束</option></> : <option value="unpaid">待收款</option>}<option value="history">已收款</option>{source === 'government' && <option value="recovery">工會墊款與回收紀錄</option>}</select></label>
      {source === 'government' && status !== 'recovery' && <label>服務歸屬季度<select className="finance-select" value={quarter} onChange={event => setQuarter(event.target.value)}><option value="">全部季度</option>{[...new Set(government.map(governmentServiceQuarter).filter((value): value is string => value !== null))].sort().map(value => <option key={value} value={value}>{value}</option>)}</select></label>}
      <label className="finance-search">搜尋<input className="finance-input" value={search} maxLength={100} onChange={event => setSearch(event.target.value)} placeholder={source === 'client' || status === 'recovery' ? '姓名或案件編號' : '案件編號'} /></label>
    </div>
    {loading ? <p className="finance-state" role="status">正在查詢收款資料…</p> : error ? <p className="finance-state error" role="alert">{error}</p> : source === 'client' ? <>
      <div className="finance-inline-summary"><span>{clientRows.length} 件</span><span>已建帳務待收 <strong>{financeMoney(clientRows.reduce((sum, row) => sum + (row.open_receivable_amount_ntd ?? 0), 0))}</strong></span>{clientRows.some(row => row.open_receivable_amount_ntd === null) && <span>尚未建帳務的案件未計入合計</span>}</div>
      <div className="finance-table-container"><table className="finance-table"><thead><tr><th>客戶／案件</th><th>目前應收</th><th>歷史入帳</th><th>操作</th></tr></thead><tbody>{clientRows.map(row => <tr key={row.case_no}><td><strong>{row.name}</strong><small className="finance-secondary">{row.case_no}</small></td><td>{financeMoney(row.open_receivable_amount_ntd)}</td><td>{row.ledger_entry_count ? '可查看歷史紀錄' : '尚無入帳紀錄'}</td><td className="finance-row-actions"><button type="button" onClick={() => onOpenCase(row.case_no)}>收款明細</button><button type="button" onClick={() => onOpenSubsidy(row.case_no)}>案件補助明細</button></td></tr>)}</tbody></table></div>
      {!clientRows.length && <p className="finance-state">沒有符合條件的客戶收款。</p>}
    </> : status === 'recovery' ? <>
      <div className="finance-inline-summary"><span>{advanceRows.length} 筆墊款</span><span>待核對與回收 {advanceRows.filter(row => row.status !== 'recovered').length} 筆</span></div>
      <div className="finance-table-container"><table className="finance-table"><thead><tr><th>客戶／案件</th><th>原墊款</th><th>狀態</th><th>操作</th></tr></thead><tbody>{advanceRows.map(row => <tr key={row.advance_id}><td><strong>{row.client_name}</strong><small className="finance-secondary">{row.case_no}</small></td><td>{financeMoney(row.advance_amount_ntd)}</td><td>{{ ready: '可銷帳', waiting_receipt: '待政府入款', recovered: '已銷帳', review_required: '待核對' }[row.status]}</td><td className="finance-row-actions"><button type="button" onClick={() => onOpenSubsidy(row.case_no)}>案件補助明細</button></td></tr>)}</tbody></table></div>
      {!advanceRows.length && <p className="finance-state">目前沒有正式工會墊款。</p>}
    </> : <>
      <div className="finance-inline-summary"><span>{governmentRows.length} 件</span><span>預估補助小計 <strong>{financeMoney(estimatedTotal)}</strong></span><span>已核准待收小計 <strong>{financeMoney(outstandingTotal)}</strong></span><span>政府已入款 <strong>{receivedTotal > 0 ? financeMoney(receivedTotal) : '尚無入款'}</strong></span></div>
      <div className="finance-table-container"><table className="finance-table"><thead><tr><th>案件／季度</th><th>服務結束確認</th><th>預估補助金額</th><th>已核准待收款</th><th>已入款</th><th>操作</th></tr></thead><tbody>{governmentRows.map(row => <tr key={row.case_no}><td>{row.case_no}<small className="finance-secondary">{governmentServiceQuarter(row) ?? '季度待確認'}</small></td><td>{serviceEndLabel(row)}{row.service_end_confirmed && <small className="finance-secondary">{row.service_end_date}</small>}</td><td>{financeMoney(row.estimated_subsidy_amount_ntd)}{row.estimate_unavailable_reason && <small className="finance-secondary">{subsidyEstimateReasons[row.estimate_unavailable_reason]}</small>}</td><td>{financeMoney(row.outstanding_amount_ntd)}</td><td>{row.net_allocated_ntd > 0 ? financeMoney(row.net_allocated_ntd) : '尚未入款'}</td><td className="finance-row-actions"><button type="button" onClick={() => onOpenSubsidy(row.case_no)}>案件補助明細</button></td></tr>)}</tbody></table></div>
      <p className="subsidy-refund-note">預估補助與已核准待收款分開計算；資料不足的案件顯示待確認，不計入小計。服務結束須以正式確認紀錄為準。</p>
      {!governmentRows.length && <p className="finance-state">沒有符合條件的政府補助案件。</p>}
    </>}
  </section>;
}
