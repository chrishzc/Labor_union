/**
 * File: ReportsPage.tsx
 * Description: 顯示季度與年度補助報表真實GET，weekly與全部XLSX控制保持停用。
 */
import React, { useEffect, useRef, useState } from 'react';
import './ReportsPage.css';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { adaptSubsidyReport } from '../adapters/reports/subsidy_report_query_adapter';

type ReportsTab = 'weekly-summary' | 'subsidy' | 'weekly-active';
type ReportKind = 'quarterly' | 'annual';
type ReportState = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: ReturnType<typeof adaptSubsidyReport> } | { kind: 'empty' } | { kind: 'error'; message: string };

function currentPeriod() {
  const now = new Date();
  return { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
}

function UnavailableSheet({ title, exportId }: { title: string; exportId: string }) {
  return <section className="reports-unavailable"><h2>{title}</h2><p>後端尚未提供approved typed authority；本頁不使用前端樣本補值。</p><button data-control-id={exportId} disabled>匯出（未開放）</button></section>;
}

export const ReportsPage: React.FC = () => {
  const period = currentPeriod();
  const [activeTab, setActiveTab] = useState<ReportsTab>('subsidy');
  const [reportKind, setReportKind] = useState<ReportKind>('quarterly');
  const [year, setYear] = useState(period.year);
  const [quarter, setQuarter] = useState(period.quarter);
  const [state, setState] = useState<ReportState>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);
  const sequenceRef = useRef(0);

  useEffect(() => () => controllerRef.current?.abort(), []);
  useEffect(() => {
    controllerRef.current?.abort();
    if (activeTab !== 'subsidy') { setState({ kind: 'idle' }); return; }
    const controller = new AbortController();
    controllerRef.current = controller;
    const sequence = ++sequenceRef.current;
    setState({ kind: 'loading' });
    const query = reportKind === 'quarterly'
      ? { kind: 'quarterly' as const, applicationYear: year, quarter }
      : { kind: 'annual' as const, applicationYear: year };
    void subsidyReportQueryClient.query(query, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted || sequence !== sequenceRef.current) return;
        setState(result.total_row_count === 0 ? { kind: 'empty' } : { kind: 'ready', data: adaptSubsidyReport(result) });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || sequence !== sequenceRef.current) return;
        setState({ kind: 'error', message: error instanceof Error ? error.message : '補助報表查詢失敗' });
      });
  }, [activeTab, reportKind, year, quarter, reload]);

  return <div data-surface-id="reports.page">
    <header className="page-header-banner reports-page-header"><div><h1 className="page-title">📊 工會業務與補助報表</h1><p className="page-subtitle">季度／年度補助核銷採server-redacted typed view；weekly報表尚未開放。</p></div><button data-control-id="reports.export.full-workbook" disabled>📥 匯出完整Excel週報（未開放）</button></header>
    <nav className="reports-sheet-tabs" aria-label="報表工作區">
      <button data-surface-id="reports.tab.weekly-summary" className={activeTab==='weekly-summary'?'active':''} onClick={() => setActiveTab('weekly-summary')}>📅 週報案件受理總表</button>
      <button data-surface-id="reports.tab.subsidy" className={activeTab==='subsidy'?'active':''} onClick={() => setActiveTab('subsidy')}>🏛️ 補助季度／年度核銷</button>
      <button data-surface-id="reports.tab.weekly-active" className={activeTab==='weekly-active'?'active':''} onClick={() => setActiveTab('weekly-active')}>📊 每週服務中與工時</button>
    </nav>

    {activeTab==='weekly-summary' && <UnavailableSheet title="週報案件受理總表" exportId="reports.export.weekly-summary" />}
    {activeTab==='weekly-active' && <UnavailableSheet title="每週服務中與工時說明" exportId="reports.export.weekly-active" />}
    {activeTab==='subsidy' && <main className="reports-workspace">
      <div className="reports-toolbar"><div><h2>Government Subsidy Reconciliation</h2><p>所有金額、時數、天數與aggregate直接顯示server值。</p></div><label>檢視<select value={reportKind} onChange={(event) => setReportKind(event.target.value as ReportKind)}><option value="quarterly">季度</option><option value="annual">年度</option></select></label><label>年度<input type="number" min="1912" value={year} onChange={(event) => setYear(Number(event.target.value))} /></label>{reportKind==='quarterly' && <label>季度<select value={quarter} onChange={(event) => setQuarter(Number(event.target.value))}>{[1,2,3,4].map((value) => <option key={value} value={value}>Q{value}</option>)}</select></label>}<button onClick={() => setReload((value) => value + 1)}>重新載入</button><button data-control-id={reportKind==='quarterly'?'reports.export.quarterly-xlsx':'reports.export.annual-xlsx'} disabled>匯出XLSX（未開放）</button></div>
      {state.kind==='loading' && <div className="reports-state" role="status">正在載入補助報表…</div>}
      {state.kind==='empty' && <div className="reports-state">此期間沒有server report rows。</div>}
      {state.kind==='error' && <div className="reports-state error" role="alert">{state.message}</div>}
      {state.kind==='ready' && <>
        <section className="reports-kpi-grid" data-surface-id="reports.subsidy.kpis"><article><span>期間</span><strong>{state.data.kind==='quarterly'?`${state.data.year} Q${state.data.quarter}`:`${state.data.year} 年度`}</strong></article><article><span>總筆數</span><strong>{state.data.totalRows}</strong></article><article><span>補助總額</span><strong>{state.data.totalAmount}</strong></article><article><span>Source revision</span><strong>{state.data.revision}</strong></article></section>
        <div className="reports-meta">Generated at {state.data.generatedAt}</div>
        {state.data.partitions.map((partition) => <section key={partition.kind} className="reports-partition"><div className="reports-partition-heading"><h3>{partition.kind==='general'?'一般市民':'補助市民'}</h3><span>{partition.rowCount}筆｜{partition.totalAmount}</span></div>{partition.rows.length===0?<p>此partition沒有資料。</p>:<div className="reports-table-container"><table className="reports-table"><thead><tr><th>序號</th><th>案件</th><th>資格</th><th>服務期間</th><th>補助時數／天數</th><th>服務天數</th><th>單價</th><th>補助額</th><th>雇主／人員</th><th>身分／地址</th></tr></thead><tbody>{partition.rows.map((row) => <tr key={`${partition.kind}-${row.serial}-${row.caseNo}`}><td>{row.serial}</td><td>{row.caseNo}</td><td>{row.eligibility}</td><td>{row.serviceRange}</td><td>{row.subsidyHours}／{row.subsidyDays}</td><td>{row.serviceDays}</td><td>{row.unitPrice}</td><td>{row.amount}</td><td>{row.employer}／{row.staff}</td><td>{row.identity}／{row.address}</td></tr>)}</tbody></table></div>}</section>)}
      </>}
    </main>}
  </div>;
};

export default ReportsPage;
