/**
 * File: OfficialHolidayCsvImport.tsx
 * Description: Manual upload UI for the official government office-calendar CSV.
 */
import { useState } from 'react';
import {
  applyHolidayFlow,
  previewHolidayFlow,
  queryHolidayFlow,
  setHolidayDraft,
} from '../../adapters/scheduling/holiday_flow_adapter';
import {
  importOfficialHolidayCandidates,
  parseOfficialHolidayCsv,
  planOfficialHolidayImport,
  type OfficialHolidayCsvSuccess,
  type OfficialHolidayImportPlan,
  type OfficialHolidayImportSummary,
} from '../../adapters/scheduling/official_holiday_csv';

interface OfficialHolidayCsvImportProps {
  readonly disabled?: boolean;
}

interface PreparedImport {
  readonly fileName: string;
  readonly parsed: OfficialHolidayCsvSuccess;
  readonly plan: OfficialHolidayImportPlan;
}

const importOperations = {
  query: queryHolidayFlow,
  preview: previewHolidayFlow,
  apply: applyHolidayFlow,
  setDraft: (request: Parameters<typeof setHolidayDraft>[0]) => {
    setHolidayDraft(request);
  },
};

export function OfficialHolidayCsvImport({ disabled = false }: OfficialHolidayCsvImportProps) {
  const [prepared, setPrepared] = useState<PreparedImport | null>(null);
  const [summary, setSummary] = useState<OfficialHolidayImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [importing, setImporting] = useState(false);

  const selectFile = async (file: File | null) => {
    setPrepared(null);
    setSummary(null);
    setError(null);
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('請選擇政府官方下載的 .csv 檔案。');
      return;
    }

    setLoadingFile(true);
    try {
      const parsed = parseOfficialHolidayCsv(await file.text());
      if (!parsed.ok) {
        setError(parsed.error);
        return;
      }
      const horizon = {
        from_date: `${parsed.year}-01-01`,
        to_date: `${parsed.year}-12-31`,
      };
      const calendar = await queryHolidayFlow(horizon);
      setPrepared({
        fileName: file.name,
        parsed,
        plan: planOfficialHolidayImport(parsed, calendar),
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '無法讀取或查詢國定假日資料。');
    } finally {
      setLoadingFile(false);
    }
  };

  const confirmImport = async () => {
    if (!prepared || importing || prepared.plan.pending.length === 0) return;
    setImporting(true);
    setSummary(null);
    setError(null);
    try {
      const result = await importOfficialHolidayCandidates(
        prepared.plan.pending,
        prepared.parsed.year,
        prepared.plan.existingSkipCount,
        importOperations,
      );
      setSummary(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '匯入後無法完成最終查詢。');
    } finally {
      setImporting(false);
    }
  };

  return (
    <section
      aria-label="政府官方國定假日 CSV 匯入"
      data-surface-id="scheduling.holiday.official-csv-import"
      style={{
        display: 'grid',
        gap: '12px',
        marginBottom: '18px',
        padding: '16px 18px',
        border: '1.5px solid #fed7aa',
        borderRadius: '12px',
        background: '#fffaf8',
      }}
    >
      <div>
        <strong style={{ display: 'block', color: '#9a3412' }}>年度國定假日 CSV 一鍵匯入</strong>
        <p style={{ margin: '6px 0 0' }}>
          請先從政府官方來源下載年度 CSV，再回此處選擇檔案。系統不會自動連線抓取政府資料。
        </p>
      </div>

      <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
        <a href="https://data.gov.tw/dataset/14718" target="_blank" rel="noreferrer">
          政府資料開放平臺：辦公日曆表
        </a>
        <a href="https://www.dgpa.gov.tw/informationlist?uid=41" target="_blank" rel="noreferrer">
          行政院人事行政總處：辦公日曆表
        </a>
      </div>

      <label style={{ display: 'grid', gap: '6px', maxWidth: '520px' }}>
        選擇政府官方 CSV
        <input
          aria-label="選擇政府官方國定假日 CSV"
          type="file"
          accept=".csv,text/csv"
          disabled={disabled || loadingFile || importing}
          onChange={(event) => {
            void selectFile(event.target.files?.[0] ?? null);
          }}
        />
      </label>

      {loadingFile && <p role="status">正在解析 CSV 並查詢既有國定假日…</p>}
      {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}

      {prepared && (
        <section aria-label="國定假日 CSV 匯入預覽" style={{ display: 'grid', gap: '8px' }}>
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
            <span>檔案：{prepared.fileName}</span>
            <span>年度：{prepared.parsed.year}</span>
            <span>可匯入：{prepared.plan.pending.length}</span>
            <span>已存在略過：{prepared.plan.existingSkipCount}</span>
          </div>
          {prepared.plan.pending.length > 0 ? (
            <ul style={{ margin: 0, paddingLeft: '22px' }}>
              {prepared.plan.pending.map((holiday) => (
                <li key={`${holiday.holiday_date}-${holiday.holiday_name}`}>
                  {holiday.holiday_date}　{holiday.holiday_name}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ margin: 0 }}>此 CSV 沒有需要新增的國定假日。</p>
          )}
          <button
            type="button"
            data-control-id="scheduling.holiday.official-csv-import.confirm"
            disabled={disabled || importing || prepared.plan.pending.length === 0}
            onClick={() => { void confirmImport(); }}
          >
            {importing ? '匯入中…' : '確認匯入'}
          </button>
        </section>
      )}

      {summary && (
        <section aria-label="國定假日 CSV 匯入結果" role="status">
          <strong>匯入完成</strong>
          <p>
            成功 {summary.successCount} 筆／略過 {summary.skipCount} 筆／失敗 {summary.failureCount} 筆
          </p>
          {summary.failures.length > 0 && (
            <>
              <strong>失敗日期／原因</strong>
              <ul>
                {summary.failures.map((failure, index) => (
                  <li key={`${failure.holiday_date}-${index}`}>
                    {failure.holiday_date}：{failure.reason}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </section>
  );
}
