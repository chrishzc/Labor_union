import './WorkbenchCaseStatistics.css';
/** 待辦看板案件統計：唯讀查詢 Reporting，統計期間不影響下方待辦清單。 */
import { useEffect, useState } from 'react';
import { caseStatisticsQueryClient } from '../api/reports/weekly_operations_report_query_client';
import type { CaseStatisticsData } from '../api/reports/weekly_operations_report_schemas';

const QUALIFICATION_LABELS = ['一般市民符合', '一般市民不符合', '補助市民符合', '補助市民不符合'];
const STATUS_LABELS = ['待補件', '洽談中', '訂單成立', '服務中', '訂單完成', '訂單取消'] as const;
const currentYear = () => Number(new Intl.DateTimeFormat('en', { timeZone: 'Asia/Taipei', year: 'numeric' }).format(new Date()));
const displayCount = (value: number | null | undefined) => value == null ? '—' : value.toLocaleString('zh-TW');

export function WorkbenchCaseStatistics({ refreshKey = 0, caseCategory = 'subsidy' }: { refreshKey?: number; caseCategory?: 'subsidy' | 'non_citizen' }) {
  const nonCitizen = caseCategory === 'non_citizen';
  const titleId = `workbench-statistics-title-${caseCategory}`;
  const [year, setYear] = useState(currentYear);
  const [quarter, setQuarter] = useState(0);
  const [month, setMonth] = useState(0);
  const [availableYears, setAvailableYears] = useState<number[]>(() => [currentYear()]);
  const [data, setData] = useState<CaseStatisticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setLoading(true);
    setFailed(false);
    void caseStatisticsQueryClient.query(year, quarter || null, month || null, { signal: controller.signal, caseCategory })
      .then((result) => {
        if (controller.signal.aborted) return;
        setData(result);
        setAvailableYears(result.available_years);
      })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [year, quarter, month, refreshKey, retryKey, caseCategory]);

  const firstMonth = month || (quarter ? (quarter - 1) * 3 + 1 : 1);
  const lastMonth = month || (quarter ? quarter * 3 : 12);
  const selectedData = data?.year === year && data.quarter === (quarter || null) && data.month === (month || null) ? data : null;
  const summary = selectedData?.summary;
  const counts = [summary?.general_eligible_count, summary?.general_ineligible_count, summary?.subsidized_eligible_count, summary?.subsidized_ineligible_count];
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
              {loading && '查詢中…'}
              {failed && <button type="button" onClick={() => setRetryKey((value) => value + 1)}>統計讀取失敗・重試</button>}
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
        <div className="workbench-statistics-total"><span>{nonCitizen ? '期間核准建案' : '期間匯入'}</span><strong>{displayCount(summary?.application_count)}</strong></div>
        <div className="workbench-statistics-annual"><span>年度累計</span><strong>{displayCount(selectedData?.annual_application_count)}</strong></div>
      </div>

      {!nonCitizen && <div className="workbench-statistics-group">
        <dl className="workbench-statistics-grid qualifications">
          {QUALIFICATION_LABELS.map((label, index) => <div key={label}><dt>{label}</dt><dd>{displayCount(counts[index])}</dd></div>)}
        </dl>
      </div>}
      <div className="workbench-statistics-group">
        <dl className="workbench-statistics-grid statuses">
          {STATUS_LABELS.map((label) => <div key={label}><dt>{label}</dt><dd>{displayCount(summary?.order_status_counts[label])}</dd></div>)}
        </dl>
      </div>
    </section>
  );
}
