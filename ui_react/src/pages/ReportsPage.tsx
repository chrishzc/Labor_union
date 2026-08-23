/**
 * File: ReportsPage.tsx
 * Description: 顯示季度與年度補助報表、下載 XLSX，並在查詢範圍變更時清除舊匯出狀態。
 */
import React, { useEffect, useRef, useState } from 'react';
import './ReportsPage.css';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { subsidyReportExportClient } from '../api/reports/subsidy_report_export_client';
import { adaptSubsidyReport } from '../adapters/reports/subsidy_report_query_adapter';

type ReportKind = 'quarterly' | 'annual';
type ReportState = { kind: 'idle' | 'loading' } | { kind: 'ready'; data: ReturnType<typeof adaptSubsidyReport> } | { kind: 'empty' } | { kind: 'error'; message: string };

function currentPeriod() {
  const now = new Date();
  return { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
}

export const ReportsPage: React.FC = () => {
  const period = currentPeriod();
  const [reportKind, setReportKind] = useState<ReportKind>('quarterly');
  const [year, setYear] = useState(period.year);
  const [quarter, setQuarter] = useState(period.quarter);
  const [state, setState] = useState<ReportState>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const [exportState, setExportState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const controllerRef = useRef<AbortController | null>(null);
  const sequenceRef = useRef(0);
  const exportSequenceRef = useRef(0);

  const clearExportState = () => {
    exportSequenceRef.current += 1;
    setExportState('idle');
  };

  const changeReportKind = (next: ReportKind) => {
    clearExportState();
    setReportKind(next);
  };

  const changeYear = (next: number) => {
    clearExportState();
    setYear(next);
  };

  const changeQuarter = (next: number) => {
    clearExportState();
    setQuarter(next);
  };

  const reloadReport = () => {
    clearExportState();
    setReload((value) => value + 1);
  };

  useEffect(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const sequence = ++sequenceRef.current;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
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
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [reportKind, year, quarter, reload]);

  const downloadXlsx = async () => {
    const sequence = ++exportSequenceRef.current;
    setExportState('loading');
    try {
      const query = reportKind === 'quarterly'
        ? { kind: 'quarterly' as const, applicationYear: year, quarter }
        : { kind: 'annual' as const, applicationYear: year };
      const artifact = await subsidyReportExportClient.download(query);
      if (sequence !== exportSequenceRef.current) return;
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setExportState('success');
    } catch {
      if (sequence === exportSequenceRef.current) setExportState('error');
    }
  };

  return <div data-surface-id="reports.page">
    <header className="page-header-banner reports-page-header"><div><h1 className="page-title">📊 工會補助核銷報表</h1><p className="page-subtitle">季度／年度資料採 server-redacted typed view，並由既有後端產生 XLSX。</p></div></header>
    <section className="reports-workspace" aria-label="補助報表查詢工作區">
      <div className="reports-toolbar"><div><h2>Government Subsidy Reconciliation</h2><p>所有金額、時數、天數與 aggregate 直接顯示 server 值。</p></div><label>檢視<select value={reportKind} onChange={(event) => changeReportKind(event.target.value as ReportKind)}><option value="quarterly">季度</option><option value="annual">年度</option></select></label><label>年度<input type="number" min="1912" value={year} onChange={(event) => changeYear(Number(event.target.value))} /></label>{reportKind==='quarterly' && <label>季度<select value={quarter} onChange={(event) => changeQuarter(Number(event.target.value))}>{[1,2,3,4].map((value) => <option key={value} value={value}>Q{value}</option>)}</select></label>}<button onClick={reloadReport}>重新載入</button><button data-control-id={reportKind==='quarterly'?'reports.export.quarterly-xlsx':'reports.export.annual-xlsx'} disabled={exportState==='loading'} onClick={() => void downloadXlsx()}>{exportState==='loading'?'正在產生 XLSX…':'匯出 XLSX'}</button></div>
      {exportState==='success' && <div className="reports-state" role="status">XLSX 已產生並開始下載。</div>}
      {exportState==='error' && <div className="reports-state error" role="alert">補助報表匯出失敗，請重試。</div>}
      {state.kind==='loading' && <div className="reports-state" role="status">正在載入補助報表…</div>}
      {state.kind==='empty' && <div className="reports-state">此期間沒有補助核銷資料。</div>}
      {state.kind==='error' && <div className="reports-state error" role="alert">{state.message}</div>}
      {state.kind==='ready' && <>
        <section className="reports-kpi-grid" data-surface-id="reports.subsidy.kpis"><article><span>期間</span><strong>{state.data.kind==='quarterly'?`${state.data.year} Q${state.data.quarter}`:`${state.data.year} 年度`}</strong></article><article><span>總筆數</span><strong>{state.data.totalRows}</strong></article><article><span>補助總額</span><strong>{state.data.totalAmount}</strong></article><article><span>Source revision</span><strong>{state.data.revision}</strong></article></section>
        <div className="reports-meta">Generated at {state.data.generatedAt}</div>
        {state.data.partitions.map((partition) => <section key={partition.kind} className="reports-partition"><div className="reports-partition-heading"><h3>{partition.kind==='general'?'一般市民':'補助市民'}</h3><span>{partition.rowCount}筆｜{partition.totalAmount}</span></div>{partition.rows.length===0?<p>此類別目前沒有資料。</p>:<div className="reports-table-container"><table className="reports-table"><thead><tr><th>序號</th><th>案件</th><th>資格</th><th>服務期間</th><th>補助時數／天數</th><th>服務天數</th><th>單價</th><th>補助額</th><th>雇主／人員</th><th>身分／地址</th></tr></thead><tbody>{partition.rows.map((row) => <tr key={`${partition.kind}-${row.serial}-${row.caseNo}`}><td>{row.serial}</td><td>{row.caseNo}</td><td>{row.eligibility}</td><td>{row.serviceRange}</td><td>{row.subsidyHours}／{row.subsidyDays}</td><td>{row.serviceDays}</td><td>{row.unitPrice}</td><td>{row.amount}</td><td>{row.employer}／{row.staff}</td><td>{row.identity}／{row.address}</td></tr>)}</tbody></table></div>}</section>)}
      </>}
    </section>
  </div>;
};

export default ReportsPage;
