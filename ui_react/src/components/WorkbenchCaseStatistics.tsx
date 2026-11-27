/**
 * File: WorkbenchCaseStatistics.tsx
 * Description: 待辦看板案件統計元件：唯讀查詢三大補助資格六欄與非市民狀態統計。
 */
import './WorkbenchCaseStatistics.css';
import { useCallback, useEffect, useState } from 'react';
import { useAdminOperationsViews, useOperationsQuery, viewTimestamp } from '../pages/admin_operations_view_cache';
import { caseStatisticsQueryClient } from '../api/reports/weekly_operations_report_query_client';

const QUALIFICATION_LABELS = [
  '一般市民符合', '一般市民不符合',
  '補助市民符合', '補助市民不符合',
  '原住民符合', '原住民不符合',
];
const STATUS_LABELS = ['待補件', '洽談中', '訂單成立', '服務中', '訂單取消'] as const;
const APPLICATION_STATUS_FIELDS = [
  ['訂單成立', 'order_established_count'], ['洽談中', 'negotiating_count'],
  ['取消', 'cancelled_count'], ['審核不符合', 'review_rejected_count'],
] as const;
const currentYear = () => Number(new Intl.DateTimeFormat('en', { timeZone: 'Asia/Taipei', year: 'numeric' }).format(new Date()));
const displayCount = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString('zh-TW');

type WorkbenchViewCache = ReturnType<typeof useAdminOperationsViews>['workbench'];

export function WorkbenchCaseStatistics({ refreshKey = 0, caseCategory = 'subsidy', viewCache }: {
  refreshKey?: number;
  caseCategory?: 'subsidy' | 'non_citizen';
  viewCache?: WorkbenchViewCache;
}) {
  const views = useAdminOperationsViews();
  const cache = viewCache ?? views.workbench;
  const nonCitizen = caseCategory === 'non_citizen';
  const titleId = `workbench-statistics-title-${caseCategory}`;
  const [year, setYear] = useState(() => cache.statisticsPeriods.get(caseCategory)?.year ?? currentYear());
  const [quarter, setQuarter] = useState(() => cache.statisticsPeriods.get(caseCategory)?.quarter ?? 0);
  const [month, setMonth] = useState(() => cache.statisticsPeriods.get(caseCategory)?.month ?? 0);
  const [availableYears, setAvailableYears] = useState<number[]>(() => [year]);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    cache.statisticsPeriods.set(caseCategory, { year, quarter, month });
  }, [cache, caseCategory, year, quarter, month]);

  const readStatistics = useCallback((signal: AbortSignal) =>
    caseStatisticsQueryClient.query(year, quarter || null, month || null, { signal, caseCategory }),
  [year, quarter, month, caseCategory]);
  const stats = useOperationsQuery({
    cache: cache.statistics,
    queryKey: JSON.stringify([caseCategory, year, quarter, month]),
    read: readStatistics,
    refreshKey: refreshKey + retryKey,
  });
  const data = stats.snapshot?.data ?? null;
  const loading = stats.status.kind === 'loading';
  const failed = stats.status.kind === 'failed';
  useEffect(() => { if (data) setAvailableYears(data.available_years); }, [data]);

  const firstMonth = month || (quarter ? (quarter - 1) * 3 + 1 : 1);
  const lastMonth = month || (quarter ? quarter * 3 : 12);
  const selectedData = data?.year === year && data.quarter === (quarter || null) && data.month === (month || null) ? data : null;
  const summary = selectedData?.summary;
  const counts = [
    summary?.general_eligible_count, summary?.general_ineligible_count,
    summary?.subsidized_eligible_count, summary?.subsidized_ineligible_count,
    summary?.indigenous_eligible_count, summary?.indigenous_ineligible_count,
  ];
  const endDay = new Date(year, lastMonth, 0).getDate();
  const period = `${year}/${String(firstMonth).padStart(2, '0')}/01－${year}/${String(lastMonth).padStart(2, '0')}/${endDay}`;
  const months = Array.from({ length: 12 }, (_, index) => index + 1)
    .filter((value) => !quarter || Math.ceil(value / 3) === quarter);

  return (
    <section className="workbench-statistics" aria-labelledby={titleId} aria-busy={loading} tabIndex={0}>
      <div className="workbench-statistics-heading">
        <div>
          <div className="workbench-statistics-title-line">
            <h2 id={titleId}>{nonCitizen ? '非市民案件統計' : '案件受理統計'}</h2>
            <span className="workbench-statistics-state" aria-live="polite">
              {loading && (data ? '更新中…' : '查詢中…')}
              {failed && <>
                {stats.snapshot && <span>顯示 {viewTimestamp(stats.snapshot.updatedAt)} 的統計。</span>}
                <button type="button" onClick={() => setRetryKey(value => value + 1)}>統計讀取失敗・重試</button>
              </>}
              {!loading && !failed && summary && ((!nonCitizen && summary.unclassified_qualification_count > 0) || summary.other_status_count > 0) &&
                <span title={`資格尚未分類 ${summary.unclassified_qualification_count} 件；其他或缺值狀態 ${summary.other_status_count} 件，均已納入案件總數。`}>部分資料待確認</span>}
            </span>
          </div>
          <div className="workbench-statistics-period"><span>{period}{nonCitizen && '・依工會核准建案日（僅計有可追溯核准日的正式案件）'}</span></div>
        </div>
        <div className="workbench-statistics-filters" role="group" aria-label="統計期間篩選">
          <label>年度<select aria-label={nonCitizen ? '非市民年度' : '年度'} value={year} onChange={(event) => setYear(Number(event.target.value))}>
            {availableYears.map((value) => <option key={value} value={value}>{value} 年</option>)}
          </select></label>
          <label>季度<select aria-label={nonCitizen ? '非市民季度' : '季度'} value={quarter} onChange={(event) => { setQuarter(Number(event.target.value)); setMonth(0); }}>
            <option value={0}>全年</option>
            {[1, 2, 3, 4].map((value) => <option key={value} value={value}>第{['一', '二', '三', '四'][value - 1]}季</option>)}
          </select></label>
          <label>月份<select aria-label={nonCitizen ? '非市民月份' : '月份'} value={month} onChange={(event) => setMonth(Number(event.target.value))}>
            <option value={0}>{quarter ? '整季' : '全月'}</option>
            {months.map((value) => <option key={value} value={value}>{value} 月</option>)}
          </select></label>
        </div>
      </div>

      <div className="workbench-statistics-overview" aria-live="polite">
        <div className="workbench-statistics-total"><span>{nonCitizen ? '期間核准建案' : '平台案件申請數'}</span><strong>{displayCount(summary?.application_count)}</strong></div>
        <div className="workbench-statistics-annual"><span>年度累計</span><strong>{displayCount(selectedData?.annual_application_count)}</strong></div>
      </div>

      {!nonCitizen && <div className="workbench-statistics-group">
        <div className="workbench-statistics-qualifications">
          {['市民案件審核', '社福案件審核', '原住民案件審核'].map((group, groupIndex) => <div key={group}>
            <h3>{group}</h3>
            <dl className="workbench-statistics-grid qualifications">
              {QUALIFICATION_LABELS.slice(groupIndex * 2, groupIndex * 2 + 2).map((label, index) =>
                <div key={label}><dt>{label}</dt><dd>{displayCount(counts[groupIndex * 2 + index])}</dd></div>)}
            </dl>
          </div>)}
        </div>
      </div>}
      <div className="workbench-statistics-group">
        {!nonCitizen && <h3>申請案件狀況</h3>}
        <dl className={`workbench-statistics-grid statuses${nonCitizen ? '' : ' application-statuses'}`}>
          {nonCitizen
            ? STATUS_LABELS.map((label) => <div key={label}><dt>{label}</dt><dd>{displayCount(summary?.order_status_counts[label])}</dd></div>)
            : APPLICATION_STATUS_FIELDS.map(([label, field]) => <div key={label}><dt>{label}</dt><dd>{displayCount(summary?.[field])}</dd></div>)}
        </dl>
      </div>
    </section>
  );
}
