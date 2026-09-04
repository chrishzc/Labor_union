/**
 * File: OfficialHolidayCsvImportPanel.tsx
 * Description: 提供政府年度辦公日曆 CSV 的人工上傳、預覽與既有 Holiday Preview → Apply orchestration。
 */

import React, { useMemo, useState } from 'react';
import {
  applyHolidayFlow,
  holidayFlowStore,
  previewHolidayFlow,
  queryHolidayFlow,
  resolveHolidayMachineState,
  setHolidayDraft,
  type HolidayApplyRequest,
  type HolidayPreviewRequest,
  type HolidayRow,
} from '../adapters/scheduling/holiday_flow_adapter';
import {
  parseOfficialHolidayCsv,
  type OfficialHolidayCsvRow,
} from '../adapters/scheduling/official_holiday_csv_import';

interface OfficialHolidayCsvImportPanelProps {
  readonly disabled: boolean;
  readonly onHorizonChange: (fromDate: string, toDate: string) => void;
}

interface HolidayImportPreview {
  readonly fileName: string;
  readonly year: number;
  readonly importable: readonly OfficialHolidayCsvRow[];
  readonly skipped: readonly OfficialHolidayCsvRow[];
}

interface HolidayImportSummary {
  readonly successCount: number;
  readonly skippedCount: number;
  readonly failedDates: readonly string[];
}

function annualRange(year: number): { fromDate: string; toDate: string } {
  return { fromDate: `${year}-01-01`, toDate: `${year}-12-31` };
}

function classifyRows(
  rows: readonly OfficialHolidayCsvRow[],
  existing: readonly HolidayRow[],
): Pick<HolidayImportPreview, 'importable' | 'skipped'> {
  const matching = new Set(
    existing.map((row) => `${row.holiday_date}\u0000${row.holiday_name}`),
  );
  const skipped = rows.filter((row) => matching.has(`${row.holidayDate}\u0000${row.holidayName}`));
  const skippedKeys = new Set(skipped.map((row) => `${row.holidayDate}\u0000${row.holidayName}`));
  return {
    importable: rows.filter((row) => !skippedKeys.has(`${row.holidayDate}\u0000${row.holidayName}`)),
    skipped,
  };
}

export const OfficialHolidayCsvImportPanel: React.FC<OfficialHolidayCsvImportPanelProps> = ({
  disabled,
  onHorizonChange,
}) => {
  const [preview, setPreview] = useState<HolidayImportPreview | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<HolidayImportSummary | null>(null);

  const previewRows = useMemo(() => (
    preview ? [...preview.skipped.map((row) => ({ ...row, status: 'skipped' as const })), ...preview.importable.map((row) => ({ ...row, status: 'importable' as const }))]
      .sort((left, right) => left.holidayDate.localeCompare(right.holidayDate)) : []
  ), [preview]);

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const file = input.files?.[0] ?? null;
    input.value = '';
    setPreview(null);
    setSummary(null);
    setError(null);
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('請選擇 .csv 檔案；未執行任何國定假日變更。');
      return;
    }

    setLoadingFile(true);
    try {
      const parsed = parseOfficialHolidayCsv(await file.text());
      const { fromDate, toDate } = annualRange(parsed.year);
      onHorizonChange(fromDate, toDate);
      const calendar = await queryHolidayFlow({ from_date: fromDate, to_date: toDate });
      const classified = classifyRows(parsed.holidays, calendar.holidays);
      setPreview({
        fileName: file.name,
        year: parsed.year,
        ...classified,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '官方辦公日曆 CSV 解析失敗；未執行任何國定假日變更。');
    } finally {
      setLoadingFile(false);
    }
  };

  const confirmImport = async () => {
    if (!preview || importing || disabled) return;
    const { fromDate, toDate } = annualRange(preview.year);
    const failedDates: string[] = [];
    let successCount = 0;
    setImporting(true);
    setError(null);
    setSummary(null);

    try {
      for (let index = 0; index < preview.importable.length; index += 1) {
        const row = preview.importable[index];
        const request: HolidayPreviewRequest = {
          action: 'upsert',
          holiday_date: row.holidayDate,
          holiday_name: row.holidayName,
          is_double_pay_default: false,
          from_date: fromDate,
          to_date: toDate,
        };
        try {
          setHolidayDraft(request);
          const result = await previewHolidayFlow(request);
          const applyRequest: HolidayApplyRequest = {
            ...request,
            expected_calendar_version: result.command.expected_calendar_version,
            preview_fingerprint: result.preview_fingerprint,
            reason: `由官方辦公日曆 CSV ${preview.fileName} 匯入 ${row.holidayDate}`,
          };
          await applyHolidayFlow(applyRequest);
          successCount += 1;
        } catch {
          failedDates.push(row.holidayDate);
          const state = resolveHolidayMachineState(holidayFlowStore.get());
          if (state.type === 'outcome_unknown' || state.type === 'observation_failed') {
            preview.importable.slice(index + 1).forEach((remaining) => failedDates.push(remaining.holidayDate));
            break;
          }
        }
      }

      await queryHolidayFlow({ from_date: fromDate, to_date: toDate });
      setSummary({
        successCount,
        skippedCount: preview.skipped.length,
        failedDates,
      });
    } catch (caught) {
      setError(caught instanceof Error
        ? `匯入流程已停止：${caught.message}`
        : '匯入流程已停止，且最後重新查詢失敗。');
    } finally {
      setImporting(false);
    }
  };

  const locked = disabled || loadingFile || importing;

  return (
    <section aria-label="官方年度國定假日 CSV 匯入" style={{ display: 'grid', gap: '12px', padding: '16px 18px', background: '#fffaf8', border: '1.5px solid #fed7aa', borderRadius: '12px' }}>
      <div>
        <h3 style={{ margin: '0 0 6px', fontSize: '1rem', color: '#9a3412' }}>官方年度辦公日曆 CSV 匯入</h3>
        <p style={{ margin: 0, fontSize: '0.86rem', color: '#74593f' }}>
          先從政府官方頁面下載年度 CSV，再於此選擇檔案。系統不會自動連線或同步政府網站。
        </p>
      </div>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <a href="https://data.gov.tw/dataset/14718" target="_blank" rel="noreferrer">前往政府資料開放平臺下載年度 CSV</a>
        <a href="https://www.dgpa.gov.tw/informationlist?uid=41" target="_blank" rel="noreferrer">行政院人事行政總處辦公日曆公告</a>
      </div>

      <label style={{ display: 'grid', gap: '6px', maxWidth: '420px', fontSize: '0.86rem', fontWeight: 700, color: '#57423b' }}>
        選擇官方辦公日曆 CSV
        <input
          aria-label="選擇官方辦公日曆 CSV"
          type="file"
          accept=".csv,text/csv"
          disabled={locked}
          onChange={(event) => void handleFile(event)}
        />
      </label>

      {loadingFile && <p role="status" style={{ margin: 0 }}>正在解析 CSV 並查詢該年度既有國定假日…</p>}
      {error && <p role="alert" className="holiday-policy-notice error" style={{ margin: 0 }}>{error}</p>}

      {preview && (
        <section aria-label="官方 CSV 待匯入預覽" style={{ display: 'grid', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', fontSize: '0.86rem' }}>
            <span>來源檔名：<strong>{preview.fileName}</strong></span>
            <span>資料年度：<strong>{preview.year}</strong></span>
            <span>可匯入：<strong>{preview.importable.length}</strong></span>
            <span>已存在略過：<strong>{preview.skipped.length}</strong></span>
          </div>
          {previewRows.length === 0 ? (
            <p className="holiday-policy-notice" style={{ margin: 0 }}>此 CSV 沒有帶備註的放假日可匯入。</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: '22px' }}>
              {previewRows.map((row) => (
                <li key={`${row.holidayDate}-${row.holidayName}`}>
                  {row.holidayDate}｜{row.holidayName}｜{row.status === 'skipped' ? '已存在，略過' : '待匯入'}
                </li>
              ))}
            </ul>
          )}
          <button type="button" disabled={locked} onClick={() => void confirmImport()}>
            {importing ? '匯入中…' : '確認匯入官方國定假日'}
          </button>
        </section>
      )}

      {summary && (
        <p role="status" style={{ margin: 0 }}>
          匯入完成：成功 {summary.successCount} 筆、略過 {summary.skippedCount} 筆、失敗 {summary.failedDates.length} 筆
          {summary.failedDates.length > 0 ? `；失敗日期：${summary.failedDates.join('、')}` : '。'}
        </p>
      )}
    </section>
  );
};

export default OfficialHolidayCsvImportPanel;
