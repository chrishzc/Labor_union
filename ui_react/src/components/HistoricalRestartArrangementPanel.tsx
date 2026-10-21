import { useUnsavedDraft } from './UnsavedChanges';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
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
  onBusyChange?: (busy: boolean) => void;
}

function explicitSegments(
  dates: ServiceDateConfirmationQueryView,
  allocation: Record<string, number>,
): HistoricalArrangementSegmentPayload[] {
  if (dates.current_dates.length === 0) throw new Error('請先確認服務日期。');
  const segments: HistoricalArrangementSegmentPayload[] = [];
  for (const day of dates.current_dates) {
    const staffId = dates.bound_staff.length === 1
      ? dates.bound_staff[0].staff_id
      : allocation[day];
    if (!staffId) throw new Error('請明確指定每個服務日的月嫂。');
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

export function HistoricalRestartArrangementPanel({ caseNo, dates, onObserved, onBusyChange }: Props) {
  const staffIdentity = useStaffIdentityLabels();
  const [allocation, setAllocation] = useState<Record<string, number>>({});
  const [preview, setPreview] = useState<HistoricalArrangementPreviewView | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const operationKey = useRef<string | null>(null);

  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);

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
      setPreview(result);
      await applyArrangement(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '正式安排預覽失敗。');
    } finally {
      setBusy(false);
    }
  };

  const applyArrangement = async (preview: HistoricalArrangementPreviewView) => {
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
  useUnsavedDraft('歷史案件服務安排', { '分配天數': allocation, '原因': reason }, { busy });


  return <section aria-label="歷史訂單建立正式安排" className="order-v2-inline-notice">
    <h3>建立正式安排</h3>
    <p>服務日期已確認，但排班與費率快照尚未建立。請核對每位既定月嫂的連續服務日，再單獨建立正式安排。</p>
    <dl className="order-v2-business-summary" aria-label="待建立正式安排摘要">
      <div><dt>既定月嫂</dt><dd>{dates.bound_staff.map((staff) => staffIdentity.label(staff.staff_id, staff.staff_name)).join('、')}</dd></div>
      <div><dt>已確認服務期間</dt><dd>{dates.current_dates[0]} 至 {dates.current_dates.at(-1)}（{dates.current_dates.length} 天）</dd></div>
    </dl>
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
          {[...dates.bound_staff].sort((a, b) => staffIdentity.compare(a.staff_id, b.staff_id)).map((staff) => <option key={staff.staff_id} value={staff.staff_id}>{staffIdentity.label(staff.staff_id, staff.staff_name)}</option>)}
        </select>
      </label>)}
    </div>}
    <label>建立原因（選填）<input value={reason} maxLength={500} disabled={busy || operationKey.current !== null} onChange={event => setReason(event.target.value)} /></label>
    <button type="button" disabled={busy} onClick={() => void (operationKey.current && preview ? applyArrangement(preview) : previewArrangement())}>
      {operationKey.current ? '以原操作確認結果' : '建立正式安排'}
    </button>
    {error && <p role="alert">{error}</p>}
    {status && <p role="status">{status}</p>}
  </section>;
}
