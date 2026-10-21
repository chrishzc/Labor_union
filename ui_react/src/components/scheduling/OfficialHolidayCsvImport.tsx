import { useUnsavedDraft } from '../UnsavedChanges';
/**
 * File: OfficialHolidayCsvImport.tsx
 * Description: Manual upload UI for the official government office-calendar CSV.
 */
import { useEffect, useRef, useState } from 'react';
import {
  applyHolidayFlow,
  holidayFlowStore,
  previewHolidayFlow,
  queryHolidayFlow,
  retryHolidayApplyFlow,
  retryHolidayObservationFlow,
  setHolidayDraft,
} from '../../adapters/scheduling/holiday_flow_adapter';
import {
  importOfficialHolidayCandidates,
  parseOfficialHolidayCsv,
  planOfficialHolidayImport,
  type OfficialHolidayCsvSuccess,
  type OfficialHolidayImportSummary,
} from '../../adapters/scheduling/official_holiday_csv';

interface OfficialHolidayCsvImportProps {
  readonly disabled?: boolean;
  readonly onImported?: (year: number) => void;
}

interface PreparedImport {
  readonly fileName: string;
  readonly parsed: OfficialHolidayCsvSuccess;
}

const importOperations = {
  query: queryHolidayFlow,
  preview: previewHolidayFlow,
  apply: applyHolidayFlow,
  setDraft: (request: Parameters<typeof setHolidayDraft>[0]) => {
    setHolidayDraft(request);
  },
};

export function OfficialHolidayCsvImport({ disabled = false, onImported }: OfficialHolidayCsvImportProps) {
  const [prepared, setPrepared] = useState<PreparedImport | null>(null);
  const [summary, setSummary] = useState<OfficialHolidayImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingFile, setLoadingFile] = useState(false);
  const [importing, setImporting] = useState(false);
  const [reason, setReason] = useState('');
  const submittingRef = useRef(false);
  const [, setStoreRevision] = useState(0);
  useEffect(() => holidayFlowStore.subscribe(() => setStoreRevision(value => value + 1)), []);
  const flowStatus = holidayFlowStore.get()?.status;
  const unresolved = flowStatus === 'outcome_unknown' || flowStatus === 'observation_failed';

  useUnsavedDraft('官方假日匯入', { '待匯入檔案': prepared?.fileName ?? '', '原因': reason }, { baseline: { '待匯入檔案': '', '原因': '' }, enabled: !summary, busy: importing });
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
      setPrepared({
        fileName: file.name,
        parsed,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '無法讀取或查詢國定假日資料。');
    } finally {
      setLoadingFile(false);
    }
  };

  const saveImport = async () => {
    if (!prepared || importing || unresolved || submittingRef.current) return;
    submittingRef.current = true;
    setImporting(true);
    setSummary(null);
    setError(null);
    try {
      const calendar = await importOperations.query({
        from_date: `${prepared.parsed.year}-01-01`,
        to_date: `${prepared.parsed.year}-12-31`,
      });
      const plan = planOfficialHolidayImport(prepared.parsed, calendar);
      const result = await importOfficialHolidayCandidates(
        plan.pending,
        prepared.parsed.year,
        plan.existingSkipCount,
        importOperations,
        reason.trim(),
      );
      setSummary(result);
      onImported?.(prepared.parsed.year);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '匯入後無法完成最終查詢。');
    } finally {
      submittingRef.current = false;
      setImporting(false);
    }
  };

  const retryResult = async () => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setImporting(true);
    setError(null);
    try {
      if (flowStatus === 'outcome_unknown') await retryHolidayApplyFlow();
      else if (flowStatus === 'observation_failed') await retryHolidayObservationFlow();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '匯入結果尚待確認。');
    } finally {
      submittingRef.current = false;
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
      </div>

      <p style={{ margin: 0 }}>
        請下載一般版 CSV，不要使用檔名含「_Google行事曆專用」的檔案（含修正版）；該版本欄位不同，無法匯入。
      </p>

      <label style={{ display: 'grid', gap: '6px', maxWidth: '520px' }}>
        選擇政府官方 CSV
        <input
          aria-label="選擇政府官方國定假日 CSV"
          type="file"
          accept=".csv,text/csv"
          disabled={disabled || loadingFile || importing || unresolved}
          onChange={(event) => {
            void selectFile(event.target.files?.[0] ?? null);
          }}
        />
      </label>

      {loadingFile && <p role="status">正在解析 CSV…</p>}
      {error && <p role="alert" style={{ color: '#b91c1c' }}>{error}</p>}

      {prepared && (
        <section aria-label="國定假日 CSV 匯入設定" style={{ display: 'grid', gap: '8px' }}>
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
            <span>檔案：{prepared.fileName}</span>
            <span>年度：{prepared.parsed.year}</span>
            <span>假日：{prepared.parsed.holidays.length}</span>
          </div>
          <label>
            匯入原因（選填）
            <input aria-label="國定假日 CSV 匯入原因" value={reason} maxLength={500} disabled={disabled || importing || unresolved} onChange={event => setReason(event.target.value)} />
          </label>
          <button
            type="button"
            data-control-id="scheduling.holiday.official-csv-import.apply"
            disabled={disabled || importing || unresolved || prepared.parsed.holidays.length === 0}
            onClick={() => { void saveImport(); }}
          >
            {importing ? '匯入中…' : '匯入國定假日'}
          </button>
        </section>
      )}

      {unresolved && (
        <div role="status">
          <p>本次變更結果尚待確認；確認後可繼續匯入剩餘日期。</p>
          <button type="button" disabled={importing} onClick={() => void retryResult()}>
            {flowStatus === 'observation_failed' ? '重新查詢匯入結果' : '再次確認匯入結果'}
          </button>
        </div>
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
