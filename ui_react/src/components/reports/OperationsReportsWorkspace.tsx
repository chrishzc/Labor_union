import { staffDisplayLabel } from '../../adapters/staff/staff_directory_adapter';
/**
 * File: OperationsReportsWorkspace.tsx
 * Description: 沿用既有週報及補助欄位與 XLSX，提供營運及帳務唯一補助入口兩種既定畫面。
 */
import React, { useEffect, useRef, useState } from 'react';
import '../../pages/ReportsPage.css';
import { WorkbenchCaseStatistics } from '../WorkbenchCaseStatistics';
import { subsidyReportQueryClient } from '../../api/reports/subsidy_report_query_client';
import { subsidyReportExportClient } from '../../api/reports/subsidy_report_export_client';
import {
  weeklyOperationsReportQueryClient,
} from '../../api/reports/weekly_operations_report_query_client';
import { weeklyOperationsReportExportClient } from '../../api/reports/weekly_operations_report_export_client';
import { adaptSubsidyReport } from '../../adapters/reports/subsidy_report_query_adapter';
import {
  adaptWeeklyOperationsReport,
  displayWeeklyMetric,
  displayWeeklyValue,
} from '../../adapters/reports/weekly_operations_report_adapter';
import { WeeklyOperationsReportError } from '../../api/reports/weekly_operations_report_errors';
import { WeeklyMetricsEditor } from './WeeklyMetricsEditor';

type ReportKind = 'weekly' | 'quarterly' | 'annual';
type WeeklyTab = 'cases' | 'subsidy' | 'service';
type ReportState =
  | { kind: 'idle' | 'loading' }
  | { kind: 'weekly-ready'; data: ReturnType<typeof adaptWeeklyOperationsReport> }
  | { kind: 'subsidy-ready'; data: ReturnType<typeof adaptSubsidyReport> }
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
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  const startDate = date.toISOString().slice(0, 10);
  date.setUTCDate(date.getUTCDate() + 6);
  return { startDate, endDate: date.toISOString().slice(0, 10) };
}

type SubsidyPartitions = ReturnType<typeof adaptSubsidyReport>['partitions'];
type WeeklyView = ReturnType<typeof adaptWeeklyOperationsReport>;
type WeeklySubsidyPartitions = WeeklyView['subsidy']['partitions'];

function annualSubsidyPeriod(endDate: string): string {
  const year = endDate.slice(0, 4);
  return `${year}-01-01～${year}-12-31`;
}

const SubsidyPartitionsView: React.FC<{
  partitions: SubsidyPartitions | WeeklySubsidyPartitions;
  kind?: 'weekly' | 'quarterly' | 'annual';
  onCase?: (caseNo: string) => void;
}> = ({ partitions, kind = 'weekly', onCase }) => <>
  {partitions.map((partition) => <section key={partition.kind} className="reports-partition">
    <div className="reports-partition-heading">
      <h3>{partition.kind === 'general' ? '一般市民' : '補助市民'}</h3>
      <span>{partition.rowCount}筆｜{partition.totalAmount}</span>
    </div>
    {partition.rows.length === 0 ? <p>此類別目前沒有資料。</p> : <div className="reports-table-container" tabIndex={0} role="region" aria-label={`${partition.kind === 'general' ? '一般市民' : '補助市民'}補助明細，可左右捲動`}>
      {kind === 'quarterly' ? <table className="reports-table" aria-label={`${partition.kind === 'general' ? '一般市民' : '補助市民'}季度補助明細`}>
        <thead><tr><th>序號</th><th>市府訂單號碼</th><th>補助資格</th><th>服務開始</th><th>服務結束</th><th>補助時數</th><th>補助天數</th><th>服務天數</th><th>補助款金額</th><th>單價</th><th>雇主</th><th>服務人員</th><th>身分證字號</th><th>地址</th><th>簽領</th></tr></thead>
        <tbody>{partition.rows.map((row) => <tr key={`${partition.kind}-${row.serial}-${row.caseNo}`}>
          <td>{row.serial}</td><td><ReportCase caseNo={row.caseNo} onCase={onCase} /></td><td>{row.eligibility}</td><td>{row.serviceStart}</td><td>{row.serviceEnd}</td>
          <td>{row.subsidyHours}</td><td>{row.subsidyDays}</td><td>{row.serviceDays}</td><td>{row.amount}</td><td>{row.unitPrice}</td>
          <td>{row.employer}</td><td>{row.staff}</td><td>{row.identity}</td><td>{row.address}</td><td />
        </tr>)}</tbody>
      </table> : kind === 'annual' ? <table className="reports-table" aria-label={`${partition.kind === 'general' ? '一般市民' : '補助市民'}年度補助明細`}>
        <thead><tr><th>序號</th><th>市府訂單號碼</th><th>補助資格</th><th>服務開始</th><th>服務結束</th><th>服務天數</th><th>補助款金額</th><th>單價</th><th>雇主</th><th>服務人員</th></tr></thead>
        <tbody>{partition.rows.map((row) => <tr key={`${partition.kind}-${row.serial}-${row.caseNo}`}>
          <td>{row.serial}</td><td><ReportCase caseNo={row.caseNo} onCase={onCase} /></td><td>{row.eligibility}</td><td>{row.serviceStart}</td><td>{row.serviceEnd}</td>
          <td>{row.serviceDays}</td><td>{row.amount}</td><td>{row.unitPrice}</td><td>{row.employer}</td><td>{row.staff}</td>
        </tr>)}</tbody>
      </table> : <table className="reports-table" aria-label={`${partition.kind === 'general' ? '一般市民' : '補助市民'}補助案件統計明細`}>
        <thead><tr><th>序號</th><th>案件編號</th><th>年度與身分</th><th>年度接案</th><th>訂單號碼</th><th>起日</th><th>訖日</th><th>補助時數</th><th>補助天數</th><th>備註</th><th>補助款金額</th><th>單價</th><th>結案/核銷</th><th>年度季度</th></tr></thead>
        <tbody>{partition.rows.map((row) => {
          if (!('annualIdentity' in row)) throw new Error('Weekly subsidy row is missing workbook fields.');
          return <tr key={`${partition.kind}-${row.serial}-${row.caseNo}`}>
            <td>{row.serial}</td><td>{row.caseNo}</td><td>{row.annualIdentity}</td><td>{row.annualEntry}</td><td><ReportCase caseNo={row.caseNo} onCase={onCase} /></td>
            <td>{row.serviceStart}</td><td>{row.serviceEnd}</td><td>{row.subsidyHours}</td><td>{row.subsidyDays}</td>
            <td>{row.notes}</td><td>{row.amount}</td><td>{row.unitPrice}</td><td>{row.reconciliationStatus}</td><td>{row.claimPeriodLabel}</td>
          </tr>;
        })}</tbody>
      </table>}
    </div>}
  </section>)}
</>;

const WeeklyCaseTotalsRow: React.FC<{
  total: NonNullable<WeeklyView['annualTotals']>[number];
}> = ({ total }) => {
  const label = total.month === null
    ? `${total.year - 1911}年度累計`
    : `${total.year - 1911}年${total.month}月小計`;
  const counts: [string, number | null][] = [
    ['推廣次數', total.promotion_count],
    ['詢問人次', total.inquiry_count],
    ['平台案件申請數', total.application_count],
    ['一般市民符合', total.general_eligible_count],
    ['一般市民不符合', total.general_ineligible_count],
    ['補助市民符合', total.subsidized_eligible_count],
    ['補助市民不符合', total.subsidized_ineligible_count],
    ['訂單成立', total.order_established_count],
    ['洽談中', total.negotiating_count],
    ['取消', total.cancelled_count],
    ['審核不符合', total.review_rejected_count],
  ];
  return <tr aria-label={label}>
    <th scope="row" colSpan={5}>{label}<br /><small>{total.start_date}～{total.end_date}</small></th>
    {counts.map(([name, value], index) => {
      const text = value === null && index < 2 ? '未完整登錄' : displayWeeklyMetric(value);
      return <td key={name} aria-label={`${name}：${text}`}>{text}</td>;
    })}
    <td colSpan={7} />
  </tr>;
};

const WeeklyCasesView: React.FC<{ report: WeeklyView }> = ({ report }) => {
  const metrics = new Map(report.weeklyMetrics.map((metric) => [metric.week_start_date, metric]));
  const rowsByWeek = new Map<string | null, typeof report.caseRows>();
  report.caseRows.forEach((row) => {
    rowsByWeek.set(row.week_start_date, [...(rowsByWeek.get(row.week_start_date) ?? []), row]);
  });
  const weeks = [...new Set([
    ...metrics.keys(),
    ...report.caseRows.flatMap((row) => row.week_start_date === null ? [] : [row.week_start_date]),
  ])].sort();
  const caseRows = (rows: typeof report.caseRows, week: string | null) => {
    const metric = week ? metrics.get(week) : undefined;
    const label = week ? `${week} ~ ${metric?.week_end_date ?? rows[0]?.week_end_date ?? ''}` : '日期未登錄';
    const group = rows.length ? rows : [null];
    return group.map((row, index) => <tr key={row?.case_no ?? week ?? 'undated'}
      aria-label={index === 0 ? `週次 ${week ?? '日期未登錄'}` : `案件 ${row?.case_no}`}>
      <td title={row?.case_no}>{row?.serial_number ?? ''}</td>
      <td>{row?.month_label ?? ''}</td><td>{row?.application_date_roc ?? ''}</td>
      {index === 0 && <td rowSpan={group.length}>{label}</td>}
      <td>{row?.applicant_name ?? ''}</td>
      {index === 0 && <>
        <td rowSpan={group.length} aria-label={`推廣次數：${displayWeeklyMetric(metric?.promotion_count ?? null)}`}>{displayWeeklyMetric(metric?.promotion_count ?? null)}</td>
        <td rowSpan={group.length} aria-label={`詢問人次：${displayWeeklyMetric(metric?.inquiry_count ?? null)}`}>{displayWeeklyMetric(metric?.inquiry_count ?? null)}</td>
      </>}
      <td>{row ? 1 : ''}</td>
      {(['general_eligible', 'general_ineligible', 'subsidized_eligible', 'subsidized_ineligible',
        'order_established', 'negotiating', 'cancelled', 'review_rejected'] as const)
        .map((field) => <td key={field}>{row?.[field] || ''}</td>)}
      <td>{row ? displayWeeklyValue(row.service_days) : ''}</td>
      <td>{row ? displayWeeklyValue(row.service_hours_per_day) : ''}</td>
      <td>{row ? displayWeeklyValue(row.planned_start_date) : ''}</td>
      <td>{row ? displayWeeklyValue(row.planned_end_date) : ''}</td>
      <td>{row?.service_status ?? ''}</td><td>{row?.district ?? ''}</td><td>{row?.notes ?? ''}</td>
    </tr>);
  };

  return <>
    <section className="reports-kpi-grid reports-weekly-kpis" data-surface-id="reports.weekly.case-kpis">
      <article><span>案件申請</span><strong>{displayWeeklyMetric(report.summary.application_count)}</strong></article>
      <article><span>一般符合</span><strong>{displayWeeklyMetric(report.summary.general_eligible_count)}</strong></article>
      <article><span>補助符合</span><strong>{displayWeeklyMetric(report.summary.subsidized_eligible_count)}</strong></article>
      <article><span>不符合（待分流）</span><strong>{displayWeeklyMetric(report.summary.rejection_unpartitioned_count)}</strong></article>
      <article><span>已成立訂單</span><strong>{displayWeeklyMetric(report.summary.order_established_count)}</strong></article>
      <article><span>資料不完整</span><strong>{displayWeeklyMetric(report.summary.incomplete_count)}</strong></article>
    </section>
    {report.caseRows.length === 0 && <div className="reports-state">此期間沒有案件受理資料。</div>}
    <div className="reports-table-container" tabIndex={0} role="region" aria-label="案件受理資料，可左右捲動">
      <table className="reports-table reports-case-table" aria-label="週報案件受理總表">
        <caption>{report.totalsAvailable ? '整週按星期一歸月。月小計為查詢期間內的週資料，年度案件累計由 1 月 1 日計至迄日。HCM 審核不符合優先列入審核不符合，每案最多計入一個狀況欄。訂單成立含服務中與完成，審核缺值保留待確認。' : '目前顯示舊版週報資料，年度累計與月小計尚未提供。'}</caption>
        <thead>
          <tr>
            <th rowSpan={2} scope="col">平台序號</th><th rowSpan={2} colSpan={2} scope="colgroup">年度月份</th>
            <th rowSpan={2} scope="col">週報週數</th><th rowSpan={2} scope="col">申請人</th>
            <th rowSpan={2} scope="col">推廣次數</th><th rowSpan={2} scope="col">詢問人次</th>
            <th rowSpan={2} scope="col">平台案件申請數</th>
            <th colSpan={2} scope="colgroup">市民案件審核</th><th colSpan={2} scope="colgroup">社福案件審核</th>
            <th colSpan={4} scope="colgroup">申請案件狀況</th>
            {['服務天數', '每日服務時數', '預計服務開始日期', '預計服務結束日期', '服務狀況', '區域', '備註']
              .map((label) => <th key={label} rowSpan={2} scope="col">{label}</th>)}
          </tr>
          <tr>{['一般市民符合', '一般市民不符合', '補助市民符合', '補助市民不符合', '訂單成立', '洽談中', '取消', '審核不符合']
            .map((label) => <th key={label} scope="col">{label}</th>)}</tr>
        </thead>
        <tbody>
          {report.annualTotals?.map((total) => <WeeklyCaseTotalsRow key={`year-${total.year}`} total={total} />)}
          {weeks.map((week, index) => {
            const rows = rowsByWeek.get(week) ?? [];
            const monthKey = week.slice(0, 7);
            const lastWeekOfMonth = weeks[index + 1]?.slice(0, 7) !== monthKey;
            const subtotal = lastWeekOfMonth ? report.monthlySubtotals?.find((total) =>
              `${total.year}-${String(total.month).padStart(2, '0')}` === monthKey) : undefined;
            return <React.Fragment key={week}>
              {caseRows(rows, week)}
              {subtotal && <WeeklyCaseTotalsRow total={subtotal} />}
            </React.Fragment>;
          })}
          {rowsByWeek.has(null) && <>
            {caseRows(rowsByWeek.get(null) ?? [], null)}
          </>}
        </tbody>
      </table>
    </div>
  </>;
};

const WeeklySubsidyView: React.FC<{ report: WeeklyView; onCase?: (caseNo: string) => void }> = ({ report, onCase }) => <>
  <section className="reports-kpi-grid" data-surface-id="reports.weekly.subsidy-kpis">
    <article><span>統計範圍</span><strong>{annualSubsidyPeriod(report.period.end_date)}</strong></article>
    <article><span>報表筆數</span><strong>{report.subsidy.totalRows}</strong><small>報表列數不代表銀行款項已核銷</small></article>
    <article><span>補助總額</span><strong>{report.subsidy.totalAmount}</strong></article>
    <article><span>報表期間</span><strong>{report.period.period_label}</strong></article>
  </section>
  <SubsidyPartitionsView partitions={report.subsidy.partitions} onCase={onCase} />
</>;

function serviceWeekNumber(weekStartDate: string): string {
  const [, month, day] = weekStartDate.split('-').map(Number);
  return `${month}-${Math.ceil(day / 7)}`;
}

function serviceDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number);
  return `${year}/${month}/${day}`;
}

const WeeklyServiceView: React.FC<{ report: WeeklyView }> = ({ report }) => {
  if (report.serviceRows.length === 0) {
    return <div className="reports-state">此期間服務工時無資料。</div>;
  }

  const groups = new Map<string, typeof report.serviceRows>();
  report.serviceRows.forEach((row) => {
    const key = `${row.period_start_date}|${row.period_end_date}`;
    groups.set(key, [...(groups.get(key) ?? []), row]);
  });

  const hasIncompleteRows = report.serviceRows.some((row) => row.data_quality_codes.length > 0);
  return <div className="reports-table-container reports-service-tables" tabIndex={0} role="region" aria-label="服務工時資料，可左右捲動">
    {hasIncompleteRows && <p role="status">部分服務安排缺少每日時數或服務期間；已保留可得明細，無法計算欄位留空。</p>}
    {[...groups.entries()].map(([key, rows]) => <table className="reports-table reports-service-table" key={key}>
      <thead><tr><th>週數</th><th>序號</th><th>市府案號</th><th>雇主</th><th>服務人員</th><th>每週起始日</th><th>每週結束日</th><th>服務時數</th><th>每週工作日數</th><th>每週工時</th><th>結案</th></tr></thead>
      <tbody>{rows.map((row, idx) => <tr key={`${row.assignment_id}-${row.period_start_date}`}>
        {idx === 0 && <td rowSpan={rows.length} className="reports-service-week">{serviceWeekNumber(row.period_start_date)}</td>}
        <td>{idx + 1}</td><td>{row.case_no}</td><td>{row.client_name}</td><td>{staffDisplayLabel(row.staff_union_no, row.staff_name)}</td>
        <td>{serviceDate(row.period_start_date)}</td><td>{serviceDate(row.period_end_date)}</td>
        <td>{row.service_hours_per_day ?? ''}</td><td>{row.weekly_work_days}</td><td>{row.weekly_hours ?? ''}</td>
        <td>{row.completed ? '結案' : ''}</td>
      </tr>)}</tbody>
    </table>)}
  </div>;
};

function ReportCase({caseNo,onCase}: {caseNo: string; onCase?: (caseNo: string) => void}) {
  return onCase ? <button type="button" className="reports-case-link" aria-label={'開啟案件 '+caseNo} onClick={() => onCase(caseNo)}>{caseNo}</button> : <>{caseNo}</>;
}

export const OperationsReportsWorkspace: React.FC<{ mode: 'operations' | 'subsidy'; onCase?: (caseNo: string) => void; revision?: number }> = ({mode, onCase, revision = 0}) => {
  const subsidyOnly = mode === 'subsidy';
  const period = currentPeriod();
  const [reportKind, setReportKind] = useState<ReportKind>('weekly');
  const [weeklyTab, setWeeklyTab] = useState<WeeklyTab>(subsidyOnly ? 'subsidy' : 'cases');
  const initialReportPeriod = currentTaipeiReportPeriod();
  const [startDate, setStartDate] = useState(initialReportPeriod.startDate);
  const [endDate, setEndDate] = useState(initialReportPeriod.endDate);
  const [dateDraft, setDateDraft] = useState(initialReportPeriod);
  const [year, setYear] = useState(period.year);
  const [quarter, setQuarter] = useState(period.quarter);
  const [state, setState] = useState<ReportState>({ kind: 'idle' });
  const [reload, setReload] = useState(0);
  const [exportState, setExportState] = useState<'idle' | 'loading' | 'success' | { error: string }>('idle');
  const controllerRef = useRef<AbortController | null>(null);
  const exportControllerRef = useRef<AbortController | null>(null);
  const sequenceRef = useRef(0);
  const exportSequenceRef = useRef(0);

  const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number(value.slice(0,4)) >= 1912 && Number(value.slice(0,4)) <= 9999 && !Number.isNaN(Date.parse(value+'T00:00:00Z')) && new Date(value+'T00:00:00Z').toISOString().slice(0,10) === value;
  const validRange = validDate(dateDraft.startDate) && validDate(dateDraft.endDate) && dateDraft.startDate <= dateDraft.endDate;
  const validYear = Number.isInteger(year) && year >= 1912 && year <= 9999;
  const draftPending = reportKind === 'weekly' && (dateDraft.startDate !== startDate || dateDraft.endDate !== endDate);
  const validQuery = reportKind === 'weekly' ? validRange : validYear;
  const readyToExport = validQuery && !draftPending && (state.kind === 'subsidy-ready' || state.kind === 'weekly-ready' && state.data.totalsAvailable);

  const clearExportState = () => {
    exportControllerRef.current?.abort();
    exportSequenceRef.current += 1;
    setExportState('idle');
  };

  const changeReportKind = (next: ReportKind) => {
    if (next === reportKind) return;
    clearExportState();
    setState({kind: 'loading'});
    setReportKind(next);
  };

  const changeDateRange = (nextStartDate: string, nextEndDate: string) => {
    if (!validDate(nextStartDate) || !validDate(nextEndDate) || nextStartDate > nextEndDate) return;
    if (nextStartDate === startDate && nextEndDate === endDate) return;
    clearExportState();
    setState({ kind: 'loading' });
    setStartDate(nextStartDate);
    setEndDate(nextEndDate);
  };

  const changeYear = (next: number) => {
    if (next === year) return;
    clearExportState();
    setState({kind: 'loading'});
    setYear(next);
  };

  const changeQuarter = (next: number) => {
    if (next === quarter) return;
    clearExportState();
    setState({kind: 'loading'});
    setQuarter(next);
  };

  const reloadReport = () => {
    clearExportState();
    if (!validQuery || draftPending) return;
    setState({kind: 'loading'});
    setReload((value) => value + 1);
  };

  useEffect(() => {
    controllerRef.current?.abort();
    clearExportState();
    if (reportKind !== 'weekly' && !validYear) return;
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
            setState({ kind: 'weekly-ready', data });
          } else if ('total_row_count' in result) {
            setState({ kind: 'subsidy-ready', data: adaptSubsidyReport(result) });
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
  }, [reportKind, startDate, endDate, year, quarter, reload, revision]);

  useEffect(() => () => exportControllerRef.current?.abort(), []);

  const downloadXlsx = async () => {
    if (!readyToExport) return;
    exportControllerRef.current?.abort();
    const controller = new AbortController();
    exportControllerRef.current = controller;
    const sequence = ++exportSequenceRef.current;
    setExportState('loading');
    try {
      const artifact = reportKind === 'weekly'
        ? await weeklyOperationsReportExportClient.download(
          startDate,
          endDate,
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
    } catch (error) {
      if (!controller.signal.aborted && sequence === exportSequenceRef.current) {
        setExportState({ error: error instanceof WeeklyOperationsReportError
          && error.code === 'WEEKLY_REPORT_EXPORT_VERSION_MISMATCH'
          ? error.message : '報表匯出失敗，請重試。' });
      }
    }
  };

  const exportControlId = reportKind === 'weekly'
    ? 'reports.export.full-workbook'
    : reportKind === 'quarterly'
      ? 'reports.export.quarterly-xlsx'
      : 'reports.export.annual-xlsx';

  return <div data-surface-id={subsidyOnly ? "finance.subsidy-reports" : "reports.page"}>
    {!subsidyOnly && <details className="reports-workspace"><summary>非市民案件統計</summary><WorkbenchCaseStatistics caseCategory="non_citizen" /></details>}
    <section className="reports-unified-entry"><div><strong>{subsidyOnly ? "政府補助清單｜報表與匯出" : "補助報表已集中至帳務工作台"}</strong><p>{subsidyOnly ? "沿用營運週報既有報表與 Excel；點案件編號開啟原案件抽屜處理安排及核銷。" : "週報補助統計、季度與年度補助，統一由政府補助清單查詢與匯出。"}</p></div>{!subsidyOnly && <a href="#finance?tab=government-list">前往政府補助清單 →</a>}</section>
    <section className="reports-workspace" aria-label={subsidyOnly ? "政府補助報表查詢工作區" : "營運報表查詢工作區"}>
      <div className="reports-toolbar">
        <div>
          <h2>{subsidyOnly ? '補助報表與匯出' : '工會營運報表'}</h2>
          <p>{reportKind === 'weekly' ? subsidyOnly ? '補助案件統計範圍為迄日所屬完整年度；完整 Excel 保留原三張工作表。' : '可自選含首尾的日期範圍，下載內容固定包含三個工作表。' : '沿用既有季度／年度報表欄位與 XLSX。'}</p>
        </div>
        {subsidyOnly && <label>報表範圍
          <select aria-label="報表範圍" value={reportKind} onChange={(event) => changeReportKind(event.target.value as ReportKind)}>
            <option value="weekly">週報補助統計</option><option value="quarterly">季度補助</option><option value="annual">年度補助</option>
          </select>
        </label>}
        {reportKind === 'weekly' ? <><label>起日
          <input type="date" value={dateDraft.startDate} onChange={(event) => {clearExportState(); setDateDraft(value => ({...value,startDate:event.target.value}));}} onBlur={() => changeDateRange(dateDraft.startDate, dateDraft.endDate)} onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }} />
        </label><label>迄日
          <input type="date" value={dateDraft.endDate} onChange={(event) => {clearExportState(); setDateDraft(value => ({...value,endDate:event.target.value}));}} onBlur={() => changeDateRange(dateDraft.startDate, dateDraft.endDate)} onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }} />
        </label></> : <label>年度
          <input aria-label="年度" type="number" min="1912" value={year} onChange={(event) => changeYear(Number(event.target.value))} />
        </label>}
        {reportKind === 'quarterly' && <label>季度
          <select aria-label="季度" value={quarter} onChange={(event) => changeQuarter(Number(event.target.value))}>
            {[1, 2, 3, 4].map((value) => <option key={value} value={value}>Q{value}</option>)}
          </select>
        </label>}
        <button type="button" disabled={!validQuery || draftPending} onClick={reloadReport}>重新載入</button>
        <button type="button" data-control-id={exportControlId} disabled={exportState === 'loading' || !readyToExport} onClick={() => void downloadXlsx()}>
          {exportState === 'loading' ? '正在產生 XLSX…' : reportKind === 'weekly' ? '下載營運報表 XLSX' : '匯出 XLSX'}
        </button>
      </div>

      {!validQuery && <div className="reports-state error" role="alert">請輸入有效年度及日期範圍，起日不可晚於迄日。</div>}
      {draftPending && validQuery && <p className="reports-meta" role="status">日期尚未套用，請完成輸入並離開日期欄位。</p>}
      {!subsidyOnly && reportKind === 'weekly' && <nav className="reports-sheet-tabs" role="tablist" aria-label="營運報表分頁">
        {([
          ['cases', '週報案件受理總表'],
          ['service', '每週服務中與工時'],
        ] as const).map(([tab, label]) => <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={weeklyTab === tab}
          className={weeklyTab === tab ? 'active' : ''}
          onClick={() => setWeeklyTab(tab)}
        >{label}</button>)}
      </nav>}

      {!subsidyOnly && reportKind === 'weekly' && state.kind === 'weekly-ready' && <WeeklyMetricsEditor
        metrics={state.data.weeklyMetrics}
        onSaved={reloadReport}
      />}

      {exportState === 'success' && <div className="reports-state" role="status">XLSX 已產生並開始下載。</div>}
      {typeof exportState === 'object' && <div className="reports-state error" role="alert">{exportState.error}</div>}
      {state.kind === 'loading' && validQuery && <div className="reports-state" role="status">正在載入報表…</div>}
      {state.kind === 'error' && <div className="reports-state error" role="alert">
        <span>{state.message}</span><button type="button" onClick={reloadReport}>重試</button>
      </div>}

      {state.kind === 'weekly-ready' && <>
        {!state.data.totalsAvailable && <div className="reports-state" role="status">
          週報 API 尚未更新至新版統計；目前保留原有週資料，年度累計、月小計及新版 XLSX 暫不提供。後端更新後請重新載入。
        </div>}
        {weeklyTab === 'cases' && <WeeklyCasesView report={state.data} />}
        {weeklyTab === 'subsidy' && <WeeklySubsidyView report={state.data} onCase={onCase} />}
        {weeklyTab === 'service' && <WeeklyServiceView report={state.data} />}
      </>}

      {state.kind === 'subsidy-ready' && <>
        <section className="reports-kpi-grid" data-surface-id="reports.subsidy.kpis">
          <article><span>期間</span><strong>{state.data.kind === 'quarterly' ? `${state.data.year} Q${state.data.quarter}` : `${state.data.year} 年度`}</strong></article>
          <article><span>總筆數</span><strong>{state.data.totalRows}</strong></article>
          <article><span>補助總額</span><strong>{state.data.totalAmount}</strong></article>
        </section>
        <div className="reports-meta">報表產生時間：{state.data.generatedAt}</div>
        <SubsidyPartitionsView partitions={state.data.partitions} kind={state.data.kind} onCase={onCase} />
      </>}

      <div className="reports-export-format"><strong>{reportKind === 'weekly' ? '完整營運報表保留原三張工作表' : '沿用既有補助 Excel 欄位'}</strong><p>{reportKind === 'weekly' ? '週報案件受理總表 ／ 補助案件統計表 ／ 每周服務中說明' : reportKind === 'quarterly' ? '依所選年度及季度查詢與匯出；報表金額與工會實際收付款分開。' : '依所選年度查詢與匯出；報表金額與工會實際收付款分開。'}</p></div>
    </section>
  </div>;
};
