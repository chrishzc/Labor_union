import { useEffect, useRef, useState } from 'react';
import type {
  HistoricalArrangementPreviewView,
  HistoricalArrangementSegmentPayload,
  ServiceDateConfirmationQueryView,
} from '../api/orders/order_mutation_schemas';
import { ordersMutationClient } from '../api/orders/order_mutation_client';

interface Props {
  caseNo: string;
  dates: ServiceDateConfirmationQueryView;
  onObserved: (query: ServiceDateConfirmationQueryView) => void;
}

function explicitSegments(
  dates: ServiceDateConfirmationQueryView,
  allocation: Record<string, number>,
): HistoricalArrangementSegmentPayload[] {
  if (dates.current_dates.length === 0) throw new Error('請先確認正式服務日期。');
  const segments: HistoricalArrangementSegmentPayload[] = [];
  for (const day of dates.current_dates) {
    const staffId = dates.bound_staff.length === 1
      ? dates.bound_staff[0].staff_id
      : allocation[day];
    if (!staffId) throw new Error('請明確指定每個正式服務日的月嫂。');
    const previous = segments.at(-1);
    if (previous?.staff_id === staffId) previous.service_dates.push(day);
    else segments.push({ staff_id: staffId, service_dates: [day] });
  }
  if (segments.length !== dates.bound_staff.length
    || new Set(segments.map((segment) => segment.staff_id)).size !== dates.bound_staff.length) {
    throw new Error('每位既定月嫂須擁有一段連續服務日，不可交錯或遺漏。');
  }
  return segments;
}

export function HistoricalRestartArrangementPanel({ caseNo, dates, onObserved }: Props) {
  const [allocation, setAllocation] = useState<Record<string, number>>({});
  const [preview, setPreview] = useState<HistoricalArrangementPreviewView | null>(null);
  const [reason, setReason] = useState('依已確認服務日期建立歷史案件正式安排');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const operationKey = useRef<string | null>(null);

  useEffect(() => {
    setAllocation({});
    setPreview(null);
    setError(null);
    setStatus(null);
    operationKey.current = null;
  }, [caseNo, dates.current_version, dates.scheduling_version]);

  const previewArrangement = async () => {
    if (busy) return;
    setBusy(true); setError(null); setStatus(null); setPreview(null);
    try {
      const segments = explicitSegments(dates, allocation);
      const result = await ordersMutationClient.previewHistoricalArrangement(caseNo, segments);
      if (result.case_no !== caseNo || result.confirmed_version !== dates.current_version) {
        throw new Error('正式日期或案件版本已變更，請重新讀取。');
      }
      operationKey.current = null;
      setPreview(result);
      setStatus('正式安排已預覽；請核對月嫂、區間與日期後建立。');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '正式安排預覽失敗。');
    } finally {
      setBusy(false);
    }
  };

  const applyArrangement = async () => {
    if (busy || preview === null) return;
    setBusy(true); setError(null); setStatus(null);
    try {
      const segments = explicitSegments(dates, allocation);
      const key = operationKey.current ?? crypto.randomUUID();
      operationKey.current = key;
      const receipt = await ordersMutationClient.applyHistoricalArrangement(
        caseNo,
        {
          segments,
          expected_order_version: preview.order_version,
          expected_scheduling_version: preview.scheduling_version,
          expected_confirmed_version: preview.confirmed_version,
          preview_fingerprint: preview.preview_fingerprint,
          reason,
        },
        { idempotencyKey: key },
      );
      if (receipt.case_no !== caseNo || receipt.preview_fingerprint !== preview.preview_fingerprint) {
        throw new Error('正式安排收據與預覽不符，請人工查核。');
      }
      const observed = await ordersMutationClient.getServiceDates(caseNo);
      if (observed.case_no !== caseNo || observed.arrangement_pending
        || observed.scheduling_version !== receipt.scheduling_version
        || observed.current_version !== preview.confirmed_version) {
        throw new Error('正式安排已寫入，但目前狀態未能完整回讀；請查閱目前排班，不要建立新操作。');
      }
      setStatus(`正式安排已建立並回讀：${receipt.assignment_ids.length} 段。`);
      setPreview(null);
      operationKey.current = null;
      onObserved(observed);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '正式安排結果未確認；請使用原操作重試或重新讀取。');
    } finally {
      setBusy(false);
    }
  };

  return <section aria-label="歷史訂單建立正式安排" className="order-v2-inline-notice">
    <h3>建立正式安排</h3>
    <p>服務日期已確認，但排班與費率快照尚未建立。請核對每位既定月嫂的連續服務日，再單獨建立正式安排。</p>
    {dates.bound_staff.length > 1 && <div role="group" aria-label="逐日指定月嫂">
      {dates.current_dates.map((day) => <label key={day}>{day}
        <select
          aria-label={`${day} 月嫂`}
          value={allocation[day] ?? ''}
          disabled={busy || operationKey.current !== null}
          onChange={(event) => {
            setAllocation((current) => ({ ...current, [day]: Number(event.target.value) }));
            setPreview(null); setStatus(null);
          }}
        >
          <option value="">請指定</option>
          {dates.bound_staff.map((staff) => <option key={staff.staff_id} value={staff.staff_id}>{staff.staff_name}</option>)}
        </select>
      </label>)}
    </div>}
    <button type="button" disabled={busy || operationKey.current !== null} onClick={() => void previewArrangement()}>預覽正式安排</button>
    {preview && <div>
      <p>預覽結果：</p>
      <ul>{preview.segments.map((segment) => <li key={segment.staff_id}>
        {dates.bound_staff.find((staff) => staff.staff_id === segment.staff_id)?.staff_name ?? segment.staff_id}
        ：{segment.assigned_start_date} 至 {segment.assigned_end_date}，{segment.service_dates.length} 個服務日
      </li>)}</ul>
      <label>建立原因
        <input value={reason} maxLength={500} disabled={busy || operationKey.current !== null}
          onChange={(event) => setReason(event.target.value)} />
      </label>
      <button type="button" disabled={busy || !reason.trim()} onClick={() => void applyArrangement()}>
        {operationKey.current ? '以原操作確認結果' : '建立正式安排'}
      </button>
    </div>}
    {error && <p role="alert">{error}</p>}
    {status && <p role="status">{status}</p>}
  </section>;
}
