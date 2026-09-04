/**
 * File: ReportsPage.tsx
 * Description: 顯示自選期間營運報表三分頁及季度／年度補助報表，支援重載、完整 XLSX 與 stale request 防護。
 */
import React, { useEffect, useRef, useState } from 'react';
import './ReportsPage.css';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { subsidyReportExportClient } from '../api/reports/subsidy_report_export_client';
import {
  weeklyOperationsReportQueryClient,
} from '../api/reports/weekly_operations_report_query_client';
import { weeklyOperationsReportExportClient } from '../api/reports/weekly_operations_report_export_client';
import { adaptSubsidyReport } from '../adapters/reports/subsidy_report_query_adapter';
import {
  adaptWeeklyOperationsReport,
  displayWeeklyMetric,
  displayWeeklyValue,
} from '../adapters/reports/weekly_operations_report_adapter';
import { WeeklyBatchModal } from '../components/reports/WeeklyBatchModal';

type ReportKind = 'weekly' | 'quarterly' | 'annual';
type WeeklyTab = 'cases' | 'subsidy' | 'service';
type ReportState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'weekly-ready'; data: ReturnType<typeof adaptWeeklyOperationsReport> }
  | { kind: 'subsidy-ready'; data: ReturnType<typeof adaptSubsidyReport> }
  | { kind: 'empty' }
  | { kind: 'error'; message: string };

function currentPeriod() {
  const now = new Date();
  return { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
}

function currentTaipeiReportPeriod(): { startDate: string; endDate: string } {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const value = (part: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === part)?.value ?? '';
  const date = new Date(`${value('year')}-${value('month')}-${value('day')}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 3) % 7));
  const startDate = date.toISOString().slice(0, 10);
  date.setUTCDate(date.getUTCDate() + 6);
  return { startDate, endDate: date.toISOString().slice(0, 10) };
}

type SubsidyPartitions = ReturnType<typeof adaptSubsidyReport>['partitions'];

const SubsidyPartitionsView: React.FC<{ partitions: SubsidyPartitions }> = ({ partitions }) => <>
  {partitions.map((partition) => <section key={partition.kind} className="reports-partition">
    <div className="reports-partition-heading">
      <h3>{partition.kind === 'general' ? '一般市民' : '補助市民'}</h3>
      <span>{partition.rowCount}筆｜{partition.totalAmount}</span>
    </div>
    {partition.rows.length === 0 ? <p>此類別目前沒有資料。</p> : <div className="reports-table-container">
      <table className="reports-table">
        <thead><tr><th>序號</th><th>案件</th><th>資格</th><th>服務期間</th><th>補助時數／天數</th><th>服務天數</th><th>單價</th><th>補助額</th><th>雇主／人員</th><th>身分／地址</th></tr></thead>
        <tbody>{partition.rows.map((row) => <tr key={`${partition.kind}-${row.serial}-${row.caseNo}`}>
          <td>{row.serial}</td><td>{row.caseNo}</td><td>{row.eligibility}</td><td>{row.serviceRange}</td>
          <td>{row.subsidyHours}／{row.subsidyDays}</td><td>{row.serviceDays}</td><td>{row.unitPrice}</td>
          <td>{row.amount}</td><td>{row.employer}／{row.staff}</td><td>{row.identity}／{row.address}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>)}
</>;

type WeeklyView = ReturnType<typeof adaptWeeklyOperationsReport>;

const DataQualityIssues: React.FC<{ issues: WeeklyView['dataQualityIssues'] }> = ({ issues }) => (
  issues.length === 0 ? null : <aside className="reports-quality" aria-label="資料品質待補正">
    <h3>資料品質待補正</h3>
    <ul>{issues.map((issue) => <li key={`${issue.code}-${issue.field}`}>
      <strong>{issue.message}</strong><span>{issue.field}｜{issue.row_count} 筆｜{issue.code}</span>
    </li>)}</ul>
  </aside>
);

const WeeklyCasesView: React.FC<{ report: WeeklyView }> = ({ report }) => <>
  <section className="reports-kpi-grid reports-weekly-kpis" data-surface-id="reports.weekly.case-kpis">
    <article><span>推廣次數</span><strong>{displayWeeklyMetric(report.summary.promotion_count)}</strong></article>
    <article><span>詢問人次</span><strong>{displayWeeklyMetric(report.summary.inquiry_count)}</strong></article>
    <article><span>案件申請</span><strong>{displayWeeklyMetric(report.summary.application_count)}</strong></article>
    <article><span>一般符合</span><strong>{displayWeeklyMetric(report.summary.general_eligible_count)}</strong></article>
    <article><span>補助符合</span><strong>{displayWeeklyMetric(report.summary.subsidized_eligible_count)}</strong></article>
    <article><span>不符合（待分流）</span><strong>{displayWeeklyMetric(report.summary.rejection_unpartitioned_count)}</strong></article>
    <article><span>已成立訂單</span><strong>{displayWeeklyMetric(report.summary.order_established_count)}</strong></article>
    <article><span>資料不完整</span><strong>{displayWeeklyMetric(report.summary.incomplete_count)}</strong></article>
  </section>
  {report.caseRows.length === 0 ? <div className="reports-state">此期間沒有案件受理資料。</div> : <div className="reports-table-container">
    <table className="reports-table">
      <thead><tr><th>案件</th><th>申請人</th><th>申請日</th><th>身分</th><th>審核</th><th>訂單狀態</th><th>天數／每日時數</th><th>預計服務期間</th><th>區域</th><th>資料品質</th></tr></thead>
      <tbody>{report.caseRows.map((row) => <tr key={row.case_no}>
        <td>{row.case_no}</td><td>{row.applicant_name}</td><td>{displayWeeklyValue(row.application_date)}</td>
        <td>{displayWeeklyValue(row.identity_status)}</td><td>{row.reviewLabel}</td><td>{displayWeeklyValue(row.order_status)}</td>
        <td>{displayWeeklyValue(row.service_days)}／{displayWeeklyValue(row.service_hours_per_day)}</td>
        <td>{displayWeeklyValue(row.planned_start_date)}～{displayWeeklyValue(row.planned_end_date)}</td>
        <td>{displayWeeklyValue(row.district)}</td><td>{row.data_quality_codes.length ? row.data_quality_codes.join('、') : '—'}</td>
      </tr>)}</tbody>
    </table>
  </div>}
</>;

const WeeklySubsidyView: React.FC<{ report: WeeklyView }> = ({ report }) => <>
  <section className="reports-kpi-grid" data-surface-id="reports.weekly.subsidy-kpis">
    <article><span>統計範圍</span><strong>{report.period.start_date}～{report.period.end_date}</strong></article>
    <article><span>核銷筆數</span><strong>{report.subsidy.totalRows}</strong></article>
    <article><span>補助總額</span><strong>{report.subsidy.totalAmount}</strong></article>
    <article><span>報表期間</span><strong>{report.period.period_label}</strong></article>
  </section>
  <SubsidyPartitionsView partitions={report.subsidy.partitions} />
</>;

const WeeklyServiceView: React.FC<{ report: WeeklyView }> = ({ report }) => (
  report.serviceRows.length === 0 ? <div className="reports-state">此期間服務工時無資料。</div> : <div className="reports-table-container">
    <table className="reports-table">
      <thead><tr><th>序號</th><th>市府案號</th><th>雇主</th><th>服務開始</th><th>服務結束</th><th>每週起始日</th><th>每週結束日</th><th>服務時數</th><th>每周工作日數</th><th>每周工時</th><th>結案</th></tr></thead>
      <tbody>{report.serviceRows.map((row, idx) => <tr key={row.assignment_id || idx}>
        <td>{idx + 1}</td><td>{row.case_no}</td><td>{row.client_name}</td>
        <td>{displayWeeklyValue(row.service_start_date)}</td><td>{displayWeeklyValue(row.service_end_date)}</td>
        <td>{displayWeeklyValue(row.period_start_date)}</td><td>{displayWeeklyValue(row.period_end_date)}</td>
        <td>{row.service_hours_per_day}</td><td>{row.weekly_work_days}</td><td>{row.weekly_hours}</td>
        <td>{row.completed ? '結案' : '—'}</td>
      </tr>)}</tbody>
    </table>
  </div>
);

export const ReportsPage: React.FC = () => {
  const period = currentPeriod();
  const [reportKind, setReportKind] = useState<ReportKind>('weekly');
  const [weeklyTab, setWeeklyTab] = useState<WeeklyTab>('cases');
  const initialReportPeriod = currentTaipeiReportPeriod();
  const [startDate, setStartDate] = useState(initialReportPeriod.startDate);
  const [endDate, setEndDate] = useState(initialReportPeriod.endDate);
  const [year, setYear] = useState(period.year);
  const [quarter, setQuarter] = useState(period.quarter);
  const [promotionCount, setPromotionCount] = useState<string>('');
  const [inquiryCount, setInquiryCount] = useState<string>('');
  const [state, setState] = useState<ReportState>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const [isBatchModalOpen, setIsBatchModalOpen] = useState(false);
  const [exportState, setExportState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const controllerRef = useRef<AbortController | null>(null);
  const exportControllerRef = useRef<AbortController | null>(null);
  const sequenceRef = useRef(0);
  const exportSequenceRef = useRef(0);

  const clearExportState = () => {
    exportControllerRef.current?.abort();
    exportSequenceRef.current += 1;
    setExportState('idle');
  };

  const changeReportKind = (next: ReportKind) => {
    clearExportState();
    setReportKind(next);
  };

  const changeDateRange = (nextStartDate: string, nextEndDate: string) => {
    clearExportState();
    setStartDate(nextStartDate);
    setEndDate(nextEndDate);
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
      const request = reportKind === 'weekly'
        ? weeklyOperationsReportQueryClient.query(startDate, endDate, { signal: controller.signal })
        : subsidyReportQueryClient.query(
          reportKind === 'quarterly'
            ? { kind: 'quarterly', applicationYear: year, quarter }
            : { kind: 'annual', applicationYear: year },
          { signal: controller.signal },
        );
      void request
        .then((result) => {
          if (controller.signal.aborted || sequence !== sequenceRef.current) return;
          if (reportKind === 'weekly' && 'schema_version' in result) {
            const data = adaptWeeklyOperationsReport(result);
            const isEmpty = data.caseRows.length === 0 && data.serviceRows.length === 0 && data.subsidy.totalRows === 0;
            setState(isEmpty ? { kind: 'empty' } : { kind: 'weekly-ready', data });
          } else if ('total_row_count' in result) {
            setState(result.total_row_count === 0
              ? { kind: 'empty' }
              : { kind: 'subsidy-ready', data: adaptSubsidyReport(result) });
          }
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || sequence !== sequenceRef.current) return;
          setState({ kind: 'error', message: error instanceof Error ? error.message : '報表查詢失敗' });
        });
    });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [reportKind, startDate, endDate, year, quarter, reload]);

  useEffect(() => () => exportControllerRef.current?.abort(), []);

  const downloadXlsx = async () => {
    exportControllerRef.current?.abort();
    const controller = new AbortController();
    exportControllerRef.current = controller;
    const sequence = ++exportSequenceRef.current;
    setExportState('loading');
    try {
      const pCount = promotionCount.trim() !== '' ? Number(promotionCount) : null;
      const iCount = inquiryCount.trim() !== '' ? Number(inquiryCount) : null;
      const artifact = reportKind === 'weekly'
        ? await weeklyOperationsReportExportClient.download(
          startDate,
          endDate,
          {
            promotionCount: pCount,
            inquiryCount: iCount,
            annualYtd: true,
          },
          controller.signal,
        )
        : await subsidyReportExportClient.download(
          reportKind === 'quarterly'
            ? { kind: 'quarterly', applicationYear: year, quarter }
            : { kind: 'annual', applicationYear: year },
          controller.signal,
        );
      if (controller.signal.aborted || sequence !== exportSequenceRef.current) return;
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setExportState('success');
    } catch {
      if (!controller.signal.aborted && sequence === exportSequenceRef.current) setExportState('error');
    }
  };

  const exportControlId = reportKind === 'weekly'
    ? 'reports.export.full-workbook'
    : reportKind === 'quarterly'
      ? 'reports.export.quarterly-xlsx'
      : 'reports.export.annual-xlsx';

  return <div data-surface-id="reports.page">
    <header className="page-header-banner reports-page-header">
      <div>
        <h1 className="page-title">📊 工會營運與補助報表</h1>
        <p className="page-subtitle">集中查詢營運報表與政府補助核銷資料，並可下載完整工作表。</p>
      </div>
    </header>
    <section className="reports-workspace" aria-label="營運與補助報表查詢工作區">
      <div className="reports-toolbar">
        <div>
          <h2>{reportKind === 'weekly' ? '工會營運報表' : '政府補助核銷報表'}</h2>
          <p>{reportKind === 'weekly' ? '可自選含首尾的日期範圍，下載內容固定包含三個工作表。' : '保留既有季度／年度核銷查詢與 XLSX。'}</p>
        </div>
        <label>報表範圍
          <select value={reportKind} onChange={(event) => changeReportKind(event.target.value as ReportKind)}>
            <option value="weekly">營運報表</option><option value="quarterly">季度補助</option><option value="annual">年度補助</option>
          </select>
        </label>
        {reportKind === 'weekly' ? <><label>起日
          <input type="date" value={startDate} onChange={(event) => changeDateRange(event.target.value, endDate)} />
        </label><label>迄日
          <input type="date" value={endDate} onChange={(event) => changeDateRange(startDate, event.target.value)} />
        </label><label>推廣次數
          <input
            type="number"
            min="0"
            placeholder="0"
            value={promotionCount}
            onChange={(event) => setPromotionCount(event.target.value)}
          />
        </label><label>詢問人次
          <input
            type="number"
            min="0"
            placeholder="0"
            value={inquiryCount}
            onChange={(event) => setInquiryCount(event.target.value)}
          />
        </label></> : <label>年度
          <input type="number" min="1912" value={year} onChange={(event) => changeYear(Number(event.target.value))} />
        </label>}
        {reportKind === 'quarterly' && <label>季度
          <select value={quarter} onChange={(event) => changeQuarter(Number(event.target.value))}>
            {[1, 2, 3, 4].map((value) => <option key={value} value={value}>Q{value}</option>)}
          </select>
        </label>}
        <button type="button" onClick={reloadReport}>重新載入</button>
        {reportKind === 'weekly' && (
          <button
            type="button"
            style={{ background: '#f8fafc', borderColor: '#3b82f6', color: '#1d4ed8' }}
            onClick={() => setIsBatchModalOpen(true)}
          >
            📑 週報結算管理
          </button>
        )}
        <button type="button" data-control-id={exportControlId} disabled={exportState === 'loading'} onClick={() => void downloadXlsx()}>
          {exportState === 'loading' ? '正在產生 XLSX…' : reportKind === 'weekly' ? '下載營運報表 XLSX' : '匯出 XLSX'}
        </button>
      </div>

      {reportKind === 'weekly' && <nav className="reports-sheet-tabs" role="tablist" aria-label="營運報表分頁">
        {([
          ['cases', '週報案件受理總表'],
          ['subsidy', '補助案件統計表'],
          ['service', '每周服務中說明'],
        ] as const).map(([tab, label]) => <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={weeklyTab === tab}
          className={weeklyTab === tab ? 'active' : ''}
          onClick={() => setWeeklyTab(tab)}
        >{label}</button>)}
      </nav>}

      {exportState === 'success' && <div className="reports-state" role="status">XLSX 已產生並開始下載。</div>}
      {exportState === 'error' && <div className="reports-state error" role="alert">報表匯出失敗，請重試。</div>}
      {state.kind === 'loading' && <div className="reports-state" role="status">正在載入報表…</div>}
      {state.kind === 'empty' && <div className="reports-state">此期間沒有可列入報表的資料。</div>}
      {state.kind === 'error' && <div className="reports-state error" role="alert">
        <span>{state.message}</span><button type="button" onClick={reloadReport}>重試</button>
      </div>}

      {state.kind === 'weekly-ready' && <>
        {weeklyTab === 'cases' && <WeeklyCasesView report={state.data} />}
        {weeklyTab === 'subsidy' && <WeeklySubsidyView report={state.data} />}
        {weeklyTab === 'service' && <WeeklyServiceView report={state.data} />}
      </>}

      {state.kind === 'subsidy-ready' && <>
        <section className="reports-kpi-grid" data-surface-id="reports.subsidy.kpis">
          <article><span>期間</span><strong>{state.data.kind === 'quarterly' ? `${state.data.year} Q${state.data.quarter}` : `${state.data.year} 年度`}</strong></article>
          <article><span>總筆數</span><strong>{state.data.totalRows}</strong></article>
          <article><span>補助總額</span><strong>{state.data.totalAmount}</strong></article>
        </section>
        <div className="reports-meta">報表產生時間：{state.data.generatedAt}</div>
        <SubsidyPartitionsView partitions={state.data.partitions} />
      </>}

      <WeeklyBatchModal
        isOpen={isBatchModalOpen}
        onClose={() => setIsBatchModalOpen(false)}
        year={Number(startDate.slice(0, 4)) || 2026}
        onBatchClosed={reloadReport}
      />
    </section>
  </div>;
};

export default ReportsPage;