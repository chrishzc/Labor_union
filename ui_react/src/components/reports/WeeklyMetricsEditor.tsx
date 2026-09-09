/**
 * File: WeeklyMetricsEditor.tsx
 * Description: 依查詢期間涵蓋的週一至週日週次，編輯該週推廣次數與詢問人次。
 */
import React, { useEffect, useState } from 'react';
import {
  weeklyReportMetricsClient,
  type WeeklyReportMetric,
} from '../../api/reports/weekly_report_metrics_client';

interface WeeklyMetricsEditorProps {
  metrics: WeeklyReportMetric[];
  onSaved: () => void;
}

type Draft = { promotion: string; inquiry: string };

function draftOf(metric: WeeklyReportMetric): Draft {
  return {
    promotion: metric.promotion_count === null ? '' : String(metric.promotion_count),
    inquiry: metric.inquiry_count === null ? '' : String(metric.inquiry_count),
  };
}

function nullableCount(value: string): number | null {
  return value.trim() === '' ? null : Number(value);
}

export const WeeklyMetricsEditor: React.FC<WeeklyMetricsEditorProps> = ({ metrics, onSaved }) => {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [savingWeek, setSavingWeek] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setDrafts(Object.fromEntries(metrics.map((metric) => [metric.week_start_date, draftOf(metric)])));
  }, [metrics]);

  const change = (week: string, field: keyof Draft, value: string) => {
    setMessage(null);
    setDrafts((current) => ({
      ...current,
      [week]: { ...(current[week] ?? { promotion: '', inquiry: '' }), [field]: value },
    }));
  };

  const save = async (metric: WeeklyReportMetric) => {
    const draft = drafts[metric.week_start_date] ?? draftOf(metric);
    setSavingWeek(metric.week_start_date);
    setMessage(null);
    try {
      await weeklyReportMetricsClient.save(metric.week_start_date, {
        promotion_count: nullableCount(draft.promotion),
        inquiry_count: nullableCount(draft.inquiry),
      });
      setMessage(`${metric.week_start_date}～${metric.week_end_date} 已儲存。`);
      onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '每週數值儲存失敗。');
    } finally {
      setSavingWeek(null);
    }
  };

  return <section className="reports-metrics-editor" aria-labelledby="weekly-metrics-title">
    <div>
      <h2 id="weekly-metrics-title">每週推廣與詢問數值</h2>
      <p>每列固定為星期一至星期日；留白代表尚未登錄，0 代表本週實際為零。</p>
    </div>
    <div className="reports-metrics-grid">
      {metrics.map((metric) => {
        const draft = drafts[metric.week_start_date] ?? draftOf(metric);
        return <fieldset key={metric.week_start_date} disabled={savingWeek !== null}>
          <legend>{metric.week_start_date}～{metric.week_end_date}</legend>
          <label>推廣次數<input type="number" min="0" step="1" value={draft.promotion} onChange={(event) => change(metric.week_start_date, 'promotion', event.target.value)} /></label>
          <label>詢問人次<input type="number" min="0" step="1" value={draft.inquiry} onChange={(event) => change(metric.week_start_date, 'inquiry', event.target.value)} /></label>
          <button type="button" onClick={() => void save(metric)}>{savingWeek === metric.week_start_date ? '儲存中…' : '儲存此週'}</button>
        </fieldset>;
      })}
    </div>
    {message && <p className="reports-metrics-message" role="status">{message}</p>}
  </section>;
};
