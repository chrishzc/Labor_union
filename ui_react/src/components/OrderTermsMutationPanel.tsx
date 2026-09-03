import { useEffect, useRef, useState, type FC } from 'react';
import {
  orderTermsMutationClient,
  type OrderTermsPreview,
  type OrderTermsReceipt,
} from '../api/orders/order_terms_mutation_client';
import type { OrderTerms } from '../api/orders/order_query_schemas';

interface OrderTermsMutationPanelProps {
  caseNo: string;
  query: OrderTerms;
}

interface OrderTermsDraft {
  plannedStartDate: string;
  serviceDays: string;
  serviceHoursPerDay: string;
  requiresCooking: '' | 'yes' | 'no';
  floorFeeNtd: string;
  startTime: string;
  endTime: string;
  endDayOffset: '0' | '1';
}

function draftFromQuery(query: OrderTerms): OrderTermsDraft {
  return {
    plannedStartDate: query.terms.planned_start_date,
    serviceDays: String(query.terms.service_days),
    serviceHoursPerDay: String(query.terms.service_hours_per_day),
    requiresCooking: query.terms.requires_cooking === null
      ? ''
      : query.terms.requires_cooking ? 'yes' : 'no',
    floorFeeNtd: String(query.terms.floor_fee_ntd),
    startTime: query.terms.service_time.start_time?.slice(0, 5) ?? '',
    endTime: query.terms.service_time.end_time?.slice(0, 5) ?? '',
    endDayOffset: query.terms.service_time.end_day_offset === 1 ? '1' : '0',
  };
}

const timeWithSeconds = (value: string) => value.length === 5 ? `${value}:00` : value;

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message.trim() : fallback;
}

function conflictMessage(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('code' in error)) return null;
  const code = (error as { code?: unknown }).code;
  if (typeof code !== 'string') return null;
  if (code === 'stale_preview') {
    return '預覽已過期：正式資料已變更，請重新檢查條款變更後再套用。';
  }
  if (
    code.endsWith('_version_conflict')
    || code === 'client_finance_candidate_stale'
    || code === 'scheduling_lock_set_stale'
  ) {
    return '版本已變更：正式資料已更新，請重新檢查條款變更後再套用。';
  }
  return null;
}

export const OrderTermsMutationPanel: FC<OrderTermsMutationPanelProps> = ({ caseNo, query }) => {
  const [draft, setDraft] = useState<OrderTermsDraft>(() => draftFromQuery(query));
  const [preview, setPreview] = useState<OrderTermsPreview | null>(null);
  const [receipt, setReceipt] = useState<OrderTermsReceipt | null>(null);
  const [readback, setReadback] = useState<OrderTerms | null>(null);
  const [reason, setReason] = useState('');
  const [status, setStatus] = useState<'idle' | 'previewing' | 'applying'>('idle');
  const [error, setError] = useState<string | null>(null);
  const currentQuery = readback ?? query;
  const queryRevision = [
    caseNo,
    query.order_version,
    query.scheduling_version,
    query.scheduling_generation,
    query.client_finance_version,
    query.payroll_version,
  ].join(':');
  const previousQueryRevision = useRef(queryRevision);

  useEffect(() => {
    if (previousQueryRevision.current === queryRevision) return;
    previousQueryRevision.current = queryRevision;
    setDraft(draftFromQuery(query));
    setPreview(null);
    setReceipt(null);
    setReadback(null);
    setReason('');
    setError(null);
    setStatus('idle');
  }, [query, queryRevision]);

  const updateDraft = <K extends keyof OrderTermsDraft>(key: K, value: OrderTermsDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
    setPreview(null);
    setReceipt(null);
    setError(null);
  };

  const proposedTermsPayload = () => ({
    proposed_terms: {
      planned_start_date: draft.plannedStartDate,
      service_days: Number(draft.serviceDays),
      service_hours_per_day: Number(draft.serviceHoursPerDay),
      requires_cooking: draft.requiresCooking === 'yes',
      floor_fee_ntd: Number(draft.floorFeeNtd),
      service_time: {
        start_time: timeWithSeconds(draft.startTime),
        end_time: timeWithSeconds(draft.endTime),
        end_day_offset: Number(draft.endDayOffset),
      },
    },
  });

  const draftReady = /^\d{4}-\d{2}-\d{2}$/.test(draft.plannedStartDate)
    && Number.isInteger(Number(draft.serviceDays))
    && Number(draft.serviceDays) > 0
    && Number.isInteger(Number(draft.serviceHoursPerDay))
    && Number(draft.serviceHoursPerDay) > 0
    && draft.requiresCooking !== ''
    && Number.isInteger(Number(draft.floorFeeNtd))
    && Number(draft.floorFeeNtd) >= 0
    && /^\d{2}:\d{2}$/.test(draft.startTime)
    && /^\d{2}:\d{2}$/.test(draft.endTime);
  const locked = currentQuery.service_data_locked || status !== 'idle';

  const previewTerms = async () => {
    if (!draftReady || currentQuery.service_data_locked) return;
    setStatus('previewing');
    setError(null);
    setReceipt(null);
    try {
      setPreview(await orderTermsMutationClient.preview(caseNo, proposedTermsPayload()));
    } catch (caught) {
      setPreview(null);
      setError(errorMessage(caught, '無法檢查訂單條款變更影響。'));
    } finally {
      setStatus('idle');
    }
  };

  const applyTerms = async () => {
    if (!preview || !reason.trim() || currentQuery.service_data_locked) return;
    setStatus('applying');
    setError(null);
    try {
      const nextReceipt = await orderTermsMutationClient.apply(
        caseNo,
        {
          ...proposedTermsPayload(),
          expected_order_version: preview.order_version,
          expected_scheduling_version: preview.scheduling_version,
          expected_client_finance_version: preview.client_finance_version,
          expected_payroll_version: preview.payroll_version,
          preview_fingerprint: preview.preview_fingerprint,
          reason: reason.trim(),
        },
        { idempotencyKey: `orders-terms-ui-${caseNo}-${crypto.randomUUID()}` },
      );
      setReceipt(nextReceipt);
      setPreview(null);
      setReason('');
      try {
        const refreshed = await orderTermsMutationClient.query(caseNo);
        setReadback(refreshed);
        setDraft(draftFromQuery(refreshed));
      } catch (caught) {
        setError(`條款已套用，但正式回讀失敗：${errorMessage(caught, '無法重新取得訂單條款。')}`);
      }
    } catch (caught) {
      const conflict = conflictMessage(caught);
      if (conflict) {
        setPreview(null);
        setReason('');
        setError(conflict);
      } else {
        setError(errorMessage(caught, '無法確認套用訂單條款。'));
      }
    } finally {
      setStatus('idle');
    }
  };

  return (
    <section className="order-v2-drawer-section" aria-labelledby="order-v2-terms-mutation-heading">
      <h3 id="order-v2-terms-mutation-heading">進件條款預覽與套用</h3>
      <p className="order-v2-drawer-note">沿用既有 Orders Terms Preview／Apply；預覽不寫入，套用使用預覽版本與 fingerprint，並要求人工變更原因。</p>
      {currentQuery.service_data_locked && (
        <p className="order-v2-drawer-error" role="status">此案件的服務條件已鎖定，依既有規則不可再變更條款。</p>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
        <label>計畫服務開始日
          <input aria-label="Beta 計畫服務開始日" type="date" value={draft.plannedStartDate} disabled={locked} onChange={(event) => updateDraft('plannedStartDate', event.target.value)} />
        </label>
        <label>服務天數
          <input aria-label="Beta 服務天數" type="number" min="1" value={draft.serviceDays} disabled={locked} onChange={(event) => updateDraft('serviceDays', event.target.value)} />
        </label>
        <label>每日服務時數
          <input aria-label="Beta 每日服務時數" type="number" min="1" value={draft.serviceHoursPerDay} disabled={locked} onChange={(event) => updateDraft('serviceHoursPerDay', event.target.value)} />
        </label>
        <label>下廚料理需求
          <select aria-label="Beta 下廚料理需求" value={draft.requiresCooking} disabled={locked} onChange={(event) => updateDraft('requiresCooking', event.target.value as OrderTermsDraft['requiresCooking'])}>
            <option value="">請明確選擇</option>
            <option value="yes">需要下廚</option>
            <option value="no">不需下廚</option>
          </select>
        </label>
        <label>樓層加給（NTD）
          <input aria-label="Beta 樓層加給" type="number" min="0" value={draft.floorFeeNtd} disabled={locked} onChange={(event) => updateDraft('floorFeeNtd', event.target.value)} />
        </label>
        <label>每日開始時間
          <input aria-label="Beta 每日開始時間" type="time" value={draft.startTime} disabled={locked} onChange={(event) => updateDraft('startTime', event.target.value)} />
        </label>
        <label>每日結束時間
          <input aria-label="Beta 每日結束時間" type="time" value={draft.endTime} disabled={locked} onChange={(event) => updateDraft('endTime', event.target.value)} />
        </label>
        <label>結束日偏移
          <select aria-label="Beta 結束日偏移" value={draft.endDayOffset} disabled={locked} onChange={(event) => updateDraft('endDayOffset', event.target.value as OrderTermsDraft['endDayOffset'])}>
            <option value="0">同日</option>
            <option value="1">隔日</option>
          </select>
        </label>
      </div>

      <div className="order-v2-drawer-actions" style={{ marginTop: '12px' }}>
        <button type="button" disabled={locked || !draftReady} onClick={() => void previewTerms()}>
          {status === 'previewing' ? '正在檢查條款變更…' : '檢查訂單條款變更'}
        </button>
      </div>

      {preview && (
        <div style={{ marginTop: '12px' }}>
          <strong>條款變更前後</strong>
          <p>服務天數：{preview.before.service_days} 天 → {preview.after.service_days} 天</p>
          <p>時段：{preview.before.service_time.start_time}～{preview.before.service_time.end_time} → {preview.after.service_time.start_time}～{preview.after.service_time.end_time}</p>
          <p>版本：Order {preview.order_version} · Scheduling {preview.scheduling_version} · Client Finance {preview.client_finance_version} · Payroll {preview.payroll_version}</p>
          <label>變更原因（稽核必填）
            <textarea aria-label="Beta 條款變更原因" rows={2} maxLength={500} value={reason} disabled={locked} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="order-v2-drawer-actions" style={{ marginTop: '8px' }}>
            <button type="button" disabled={locked || reason.trim().length === 0} onClick={() => void applyTerms()}>
              {status === 'applying' ? '條款套用中…' : '確認套用訂單條款'}
            </button>
          </div>
        </div>
      )}

      {receipt && readback && (
        <p role="status">條款已套用並完成正式回讀；Order version {readback.order_version}，合約服務 {readback.terms.service_days} 日。</p>
      )}
      {receipt && !readback && (
        <p role="status">條款已套用；Order version {receipt.order_version}，正式服務日 {receipt.official_service_day_count} 天。</p>
      )}
      {error && <p className="order-v2-drawer-error" role="alert">{error}</p>}
    </section>
  );
};

export default OrderTermsMutationPanel;
