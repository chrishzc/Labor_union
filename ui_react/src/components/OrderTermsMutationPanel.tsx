/**
 * File: OrderTermsMutationPanel.tsx
 * Description: 訂單條款預覽與套用面板，支援常用班次快捷與30分鐘時段下拉並自動計算時數。
 */

import { useEffect, useRef, useState, type FC } from 'react';
import {
  orderTermsMutationClient,
  type OrderTermsPreview,
  type OrderTermsReceipt,
  type OrderTermsApplyPayload,
} from '../api/orders/order_terms_mutation_client';
import { schedulePrecisionClient, type SchedulePrecisionRequest } from '../api/scheduling/schedule_precision_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { OrderTerms } from '../api/orders/order_query_schemas';

interface OrderTermsMutationPanelProps {
  caseNo: string;
  query: OrderTerms;
  onObserved?: () => void;
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

export const COMMON_SHIFT_PRESETS = [
  { label: '4h 上午 (09:00~13:00)', startTime: '09:00', endTime: '13:00', endDayOffset: '0' as const },
  { label: '4h 下午 (14:00~18:00)', startTime: '14:00', endTime: '18:00', endDayOffset: '0' as const },
  { label: '8h 早班 (08:00~16:00)', startTime: '08:00', endTime: '16:00', endDayOffset: '0' as const },
  { label: '8h (09:00~17:00)', startTime: '09:00', endTime: '17:00', endDayOffset: '0' as const },
] as const;

export const STANDARD_TIME_OPTIONS: readonly string[] = Array.from({ length: 48 }, (_, i) => {
  const h = String(Math.floor(i / 2)).padStart(2, '0');
  const m = i % 2 === 0 ? '00' : '30';
  return `${h}:${m}`;
});

export function getTimeOptions(currentValue?: string): readonly string[] {
  if (!currentValue || !/^\d{2}:\d{2}$/.test(currentValue)) {
    return STANDARD_TIME_OPTIONS;
  }
  if (STANDARD_TIME_OPTIONS.includes(currentValue)) {
    return STANDARD_TIME_OPTIONS;
  }
  return [...STANDARD_TIME_OPTIONS, currentValue].sort();
}

export function calculateDailyServiceHours(
  startTime: string,
  endTime: string,
  endDayOffset: '0' | '1',
): number | null {
  if (!/^\d{2}:\d{2}$/.test(startTime) || !/^\d{2}:\d{2}$/.test(endTime)) {
    return null;
  }
  const [startH, startM] = startTime.split(':').map(Number);
  const [endH, endM] = endTime.split(':').map(Number);
  if (
    startH < 0 || startH > 23 || startM < 0 || startM > 59 ||
    endH < 0 || endH > 23 || endM < 0 || endM > 59
  ) {
    return null;
  }
  const startMinutes = startH * 60 + startM;
  let endMinutes = endH * 60 + endM;
  if (endDayOffset === '1') {
    endMinutes += 24 * 60;
  }
  const diffMinutes = endMinutes - startMinutes;
  if (diffMinutes <= 0) {
    return null;
  }
  const hours = diffMinutes / 60;
  return Number.isInteger(hours * 2) && hours > 0 && hours <= 24 ? hours : null;
}

export function validateServiceTimeWindow(
  startTime: string,
  endTime: string,
  endDayOffset: '0' | '1',
): string | null {
  if (!startTime || !endTime) return null;
  if (!/^\d{2}:\d{2}$/.test(startTime) || !/^\d{2}:\d{2}$/.test(endTime)) {
    return '服務時段格式須為 HH:MM。';
  }
  const [startH, startM] = startTime.split(':').map(Number);
  const [endH, endM] = endTime.split(':').map(Number);
  if (
    startH < 0 || startH > 23 || startM < 0 || startM > 59 ||
    endH < 0 || endH > 23 || endM < 0 || endM > 59
  ) {
    return '服務時段時間數值無效。';
  }
  const startMinutes = startH * 60 + startM;
  let endMinutes = endH * 60 + endM;
  if (endDayOffset === '1') {
    endMinutes += 24 * 60;
  }
  const diffMinutes = endMinutes - startMinutes;
  if (diffMinutes <= 0) {
    return '每日結束時間須晚於開始時間；若為跨日服務，請將「結束日偏移」設為隔日。';
  }
  if (diffMinutes > 24 * 60) {
    return '單日服務時數不可超過 24 小時。';
  }
  if (diffMinutes % 30 !== 0) {
    return `每日服務時數須以 0.5 小時為單位（目前計算為 ${(diffMinutes / 60).toFixed(2)} 小時）。`;
  }
  return null;
}

function draftFromQuery(query: OrderTerms): OrderTermsDraft {
  const startTime = query.terms.service_time.start_time?.slice(0, 5) ?? '';
  const endTime = query.terms.service_time.end_time?.slice(0, 5) ?? '';
  const endDayOffset = query.terms.service_time.end_day_offset === 1 ? '1' : '0';

  return {
    plannedStartDate: query.terms.planned_start_date,
    serviceDays: String(query.terms.service_days),
    serviceHoursPerDay: String(query.terms.service_hours_per_day),
    requiresCooking: query.terms.requires_cooking === null
      ? ''
      : query.terms.requires_cooking ? 'yes' : 'no',
    floorFeeNtd: String(query.terms.floor_fee_ntd),
    startTime,
    endTime,
    endDayOffset,
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
  if (code === 'scheduling_segments_required') {
    return '目前排班資料不完整，無法安全調整既有排班；本次未儲存任何變更。';
  }
  if (code === 'confirmed_service_dates_reconfirmation_required') {
    return '本案已有正式服務日期；變更服務天數前，請在本面板精算完整替代日期並填寫人員分配；本次未儲存任何變更。';
  }
  if (code === 'scheduling_reallocation_required') return '請填寫每個既有指派的新服務天數，合計須等於新合約天數，再重新檢查。';
  if (code === 'service_data_locked') return '服務條件已鎖定，本次未儲存；請保留已完成服務與帳務歷史。';
  if (code === 'service_started_replacement_blocked') return '本案已開始服務，不能由此替換完整日期；請由承辦人確認保留已履行服務的調整方案。本次未儲存。';
  if (code === 'replacement_service_date_outside_selectable_range') return '替代日期超出可選期間，請重新精算日期並核對計畫開始日。';
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

export const OrderTermsMutationPanel: FC<OrderTermsMutationPanelProps> = ({ caseNo, query, onObserved }) => {
  const [draft, setDraft] = useState<OrderTermsDraft>(() => draftFromQuery(query));
  const [preview, setPreview] = useState<OrderTermsPreview | null>(null);
  const [receipt, setReceipt] = useState<OrderTermsReceipt | null>(null);
  const [readback, setReadback] = useState<OrderTerms | null>(null);
  const [reason, setReason] = useState('');
  const [replacementDates, setReplacementDates] = useState<string[] | null>(null);
  const [serviceMode, setServiceMode] = useState<SchedulePrecisionRequest['service_mode'] | ''>('');
  const [allocations, setAllocations] = useState<Record<number, string>>({});
  const [status, setStatus] = useState<'idle' | 'previewing' | 'applying' | 'calculating' | 'reading'>('idle');
  const [error, setError] = useState<string | null>(null);
  const submittedTarget = useRef<OrderTermsApplyPayload | null>(null);
  const pendingCommand = useRef<{ payload: OrderTermsApplyPayload; key: string } | null>(null);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const mounted = useRef(false);
  const activeCase = useRef(caseNo);
  activeCase.current = caseNo;
  const previewGeneration = useRef(0);
  const previewAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      previewGeneration.current += 1;
      previewAbort.current?.abort();
      previewAbort.current = null;
    };
  }, []);
  const currentQuery = readback ?? query;
  const queryRevision = [
    caseNo,
    query.order_version,
    query.scheduling_version,
    query.scheduling_generation,
    query.client_finance_version,
    query.payroll_version,
  ].join(':');
  const observedRevision = readback === null ? null : [
    readback.case_no,
    readback.order_version,
    readback.scheduling_version,
    readback.scheduling_generation,
    readback.client_finance_version,
    readback.payroll_version,
  ].join(':');
  const previousQueryRevision = useRef(queryRevision);

  useEffect(() => {
    if (previousQueryRevision.current === queryRevision) return;
    const sameCase = previousQueryRevision.current.split(':')[0] === caseNo;
    if (sameCase && (pendingCommand.current || (receipt && !readback))) return;
    previousQueryRevision.current = queryRevision;
    previewGeneration.current += 1;
    previewAbort.current?.abort();
    previewAbort.current = null;
    if (queryRevision === observedRevision) return;
    pendingCommand.current = null;
    submittedTarget.current = null;
    setOutcomeUnknown(false);
    setServiceMode('');
    setReplacementDates(null);
    setAllocations({});
    setDraft(draftFromQuery(query));
    setPreview(null);
    setReceipt(null);
    setReadback(null);
    setReason('');
    setError(null);
    setStatus('idle');
  }, [caseNo, query, queryRevision, observedRevision, receipt, readback]);

  const needsReplacement = Number(draft.serviceDays) !== currentQuery.terms.service_days
    && ((currentQuery.confirmed_service_dates?.length ?? 0) > 0 || (currentQuery.assignments?.length ?? 0) > 0);

  const updateDraft = <K extends keyof OrderTermsDraft>(key: K, value: OrderTermsDraft[K]) => {
    setReplacementDates(null);
    setDraft((current) => {
      const next = { ...current, [key]: value };
      if (key === 'startTime' || key === 'endTime' || key === 'endDayOffset') {
        const calculated = calculateDailyServiceHours(next.startTime, next.endTime, next.endDayOffset);
        if (calculated !== null) {
          next.serviceHoursPerDay = String(calculated);
        } else if (next.startTime && next.endTime) {
          next.serviceHoursPerDay = '';
        }
      }
      return next;
    });
    setPreview(null);
    setReceipt(null);
    setError(null);
  };

  const isPresetActive = (preset: typeof COMMON_SHIFT_PRESETS[number]) => (
    draft.startTime === preset.startTime
    && draft.endTime === preset.endTime
    && draft.endDayOffset === preset.endDayOffset
  );

  const applyPreset = (preset: typeof COMMON_SHIFT_PRESETS[number]) => {
    setDraft((current) => {
      const calculated = calculateDailyServiceHours(preset.startTime, preset.endTime, preset.endDayOffset);
      return {
        ...current,
        startTime: preset.startTime,
        endTime: preset.endTime,
        endDayOffset: preset.endDayOffset,
        serviceHoursPerDay: calculated !== null ? String(calculated) : current.serviceHoursPerDay,
      };
    });
    setPreview(null);
    setReceipt(null);
    setError(null);
  };

  const serviceTimeUnchanged = draft.startTime === (currentQuery.terms.service_time.start_time?.slice(0, 5) ?? '')
    && draft.endTime === (currentQuery.terms.service_time.end_time?.slice(0, 5) ?? '')
    && Number(draft.endDayOffset) === (currentQuery.terms.service_time.end_day_offset ?? 0);

  const proposedTermsPayload = () => ({
    ...(needsReplacement && replacementDates ? {
      replacement_service_dates: replacementDates,
      replacement_allocations: (currentQuery.assignments ?? []).map((assignment) => ({
        assignment_id: assignment.assignment_id,
        service_days: Number(allocations[assignment.assignment_id] ?? ''),
      })),
    } : {}),
    proposed_terms: {
      planned_start_date: draft.plannedStartDate,
      service_days: Number(draft.serviceDays),
      service_hours_per_day: Number(draft.serviceHoursPerDay),
      requires_cooking: draft.requiresCooking === ''
        ? null
        : draft.requiresCooking === 'yes',
      floor_fee_ntd: Number(draft.floorFeeNtd),
      service_time: serviceTimeUnchanged ? currentQuery.terms.service_time : {
        start_time: draft.startTime ? timeWithSeconds(draft.startTime) : null,
        end_time: draft.endTime ? timeWithSeconds(draft.endTime) : null,
        end_day_offset: draft.startTime && draft.endTime ? Number(draft.endDayOffset) : null,
      },
    },
  });

  const timeValidationError = validateServiceTimeWindow(draft.startTime, draft.endTime, draft.endDayOffset);

  const draftReady = /^\d{4}-\d{2}-\d{2}$/.test(draft.plannedStartDate)
    && Number.isInteger(Number(draft.serviceDays))
    && Number(draft.serviceDays) > 0
    && Number.isInteger(Number(draft.serviceHoursPerDay) * 2)
    && Number(draft.serviceHoursPerDay) > 0
    && Number.isInteger(Number(draft.floorFeeNtd))
    && Number(draft.floorFeeNtd) >= 0
    && ((!draft.startTime && !draft.endTime)
      || (/^\d{2}:\d{2}$/.test(draft.startTime) && /^\d{2}:\d{2}$/.test(draft.endTime)))
    && timeValidationError === null;
  const replacementReady = !needsReplacement || (replacementDates?.length === Number(draft.serviceDays)
    && (currentQuery.assignments?.length ? currentQuery.assignments.every((a) => Number.isInteger(Number(allocations[a.assignment_id])) && Number(allocations[a.assignment_id]) > 0)
      && currentQuery.assignments.reduce((sum, a) => sum + Number(allocations[a.assignment_id]), 0) === Number(draft.serviceDays) : true));
  const locked = currentQuery.service_data_locked || status !== 'idle' || (receipt !== null && readback === null) || outcomeUnknown;

  const calculateReplacement = async () => {
    if (!serviceMode || !draftReady || locked) return;
    const generation = ++previewGeneration.current;
    const isCurrent = () => mounted.current && generation === previewGeneration.current;
    setStatus('calculating'); setError(null); setPreview(null); setReplacementDates(null);
    try {
      const result = await schedulePrecisionClient.calculate({ case_no: caseNo,
        actual_start_date: draft.plannedStartDate, target_service_days: Number(draft.serviceDays), service_mode: serviceMode });
      if (!isCurrent()) return;
      setReplacementDates(result.day_by_day.filter((day) => day.is_work_day).map((day) => day.date));
    } catch (caught) { if (isCurrent()) setError(errorMessage(caught, '替代日期精算失敗。')); }
    finally { if (isCurrent()) setStatus('idle'); }
  };

  const observeReceipt = async (nextReceipt: OrderTermsReceipt) => {
    setStatus('reading'); setError(null);
    try {
      const refreshed = await orderTermsMutationClient.query(caseNo);
      if (!mounted.current || activeCase.current !== caseNo) return;
      if (refreshed.case_no !== caseNo || refreshed.order_version < nextReceipt.order_version
        || refreshed.scheduling_version < nextReceipt.scheduling_version
        || refreshed.client_finance_version < nextReceipt.client_finance_version
        || refreshed.payroll_version < nextReceipt.payroll_version) throw new Error('條款回讀案件識別或版本與收據不一致。');
      const target = submittedTarget.current;
      if (target && refreshed.order_version === nextReceipt.order_version) {
        const expected = target.proposed_terms;
        const termsDiffer = Object.entries(expected).some(([key, value]) => key === 'service_time'
          ? Object.entries(value as Record<string, unknown>).some(([part, item]) => refreshed.terms.service_time[part as keyof typeof refreshed.terms.service_time] !== item)
          : refreshed.terms[key as keyof typeof expected] !== value);
        const datesDiffer = target.replacement_service_dates
          && JSON.stringify(refreshed.confirmed_service_dates) !== JSON.stringify(target.replacement_service_dates);
        if (termsDiffer || datesDiffer) throw new Error('正式讀回內容與已提交條款／日期不一致。');
      }
      setReadback(refreshed); setDraft(draftFromQuery(refreshed)); setReplacementDates(null);
      if (mounted.current) onObserved?.();
    } catch (caught) { if (mounted.current && activeCase.current === caseNo) setError(`條款已套用，但正式回讀失敗：${errorMessage(caught, '無法重新取得訂單條款。')}`); }
    finally { if (mounted.current && activeCase.current === caseNo) setStatus('idle'); }
  };

  const previewTerms = async () => {
    if (!draftReady || !replacementReady || locked) return;
    const generation = ++previewGeneration.current;
    previewAbort.current?.abort();
    const controller = new AbortController();
    previewAbort.current = controller;
    const isCurrentPreview = () => (
      mounted.current
      && previewGeneration.current === generation
      && previewAbort.current === controller
    );
    setStatus('previewing');
    setError(null);
    setReceipt(null);
    try {
      const nextPreview = await orderTermsMutationClient.preview(
        caseNo,
        proposedTermsPayload(),
        { signal: controller.signal },
      );
      if (!isCurrentPreview()) return;
      setPreview(nextPreview);
    } catch (caught) {
      if (!isCurrentPreview() || controller.signal.aborted) return;
      setPreview(null);
      setError(conflictMessage(caught) ?? errorMessage(caught, '無法檢查訂單條款變更影響。'));
    } finally {
      if (isCurrentPreview()) {
        previewAbort.current = null;
        setStatus('idle');
      }
    }
  };

  const applyTerms = async () => {
    if (!preview || !reason.trim() || currentQuery.service_data_locked) return;
    setStatus('applying');
    setError(null);
    setReadback(null);
    try {
      if (pendingCommand.current === null) pendingCommand.current = {
        payload: {
          ...proposedTermsPayload(),
          expected_order_version: preview.order_version,
          expected_scheduling_version: preview.scheduling_version,
          expected_client_finance_version: preview.client_finance_version,
          expected_payroll_version: preview.payroll_version,
          preview_fingerprint: preview.preview_fingerprint,
          reason: reason.trim(),
        },
        key: `orders-terms-ui-${caseNo}-${crypto.randomUUID()}`,
      };
      const command = pendingCommand.current;
      submittedTarget.current = command.payload;
      const nextReceipt = await orderTermsMutationClient.apply(caseNo, command.payload, { idempotencyKey: command.key });
      if (!mounted.current || activeCase.current !== caseNo) return;
      pendingCommand.current = null; setOutcomeUnknown(false);
      setReceipt(nextReceipt);
      setPreview(null);
      setReason('');
      await observeReceipt(nextReceipt);
    } catch (caught) {
      if (!mounted.current || activeCase.current !== caseNo) return;
      const conflict = conflictMessage(caught) ?? (caught instanceof ApiHttpError && [400, 401, 403, 404, 409, 422].includes(caught.status)
        ? '本次條款未通過檢查，請核對目前資料、帳務限制及登入權限後重新檢查。' : null);
      if (conflict) {
        pendingCommand.current = null; setOutcomeUnknown(false);
        setPreview(null);
        setReason('');
        setError(conflict);
      } else {
        setOutcomeUnknown(true);
        setError(`送出結果尚未確認，請重播同一筆提交以取得結果：${errorMessage(caught, '無法確認套用訂單條款。')}`);
      }
    } finally {
      if (mounted.current && activeCase.current === caseNo) setStatus('idle');
    }
  };

  return (
    <section className="order-v2-drawer-section" aria-labelledby="order-v2-terms-mutation-heading">
      <h3 id="order-v2-terms-mutation-heading">進件條款預覽與套用</h3>
      <p className="order-v2-drawer-note">尚未建立正式服務日期時，可先修正進件條款；已有日期或排班且需改天數時，請在下方精算替代日期並填寫人員分配，一次確認保存。檢查時不會修改訂單。</p>
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
          <input
            aria-label="Beta 每日服務時數"
            type="number"
            min="1"
            max="24"
            step="0.5"
            value={draft.serviceHoursPerDay}
            readOnly
            disabled={locked}
            title="由每日開始時間、結束時間與結束日偏移自動計算"
          />
        </label>
        <label>下廚料理需求
          <select aria-label="Beta 下廚料理需求" value={draft.requiresCooking} disabled={locked} onChange={(event) => updateDraft('requiresCooking', event.target.value as OrderTermsDraft['requiresCooking'])}>
            <option value="">尚未確認（可先保留）</option>
            <option value="yes">需要下廚</option>
            <option value="no">不需下廚</option>
          </select>
        </label>
        <label>樓層加給（NTD）
          <input aria-label="Beta 樓層加給" type="number" min="0" value={draft.floorFeeNtd} disabled={locked} onChange={(event) => updateDraft('floorFeeNtd', event.target.value)} />
        </label>
        <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '6px', padding: '10px 12px', background: '#faf6f0', borderRadius: '8px', border: '1px solid #ebdcd0', marginTop: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '6px' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#6d4c3d' }}>常用班次快捷填入：</span>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {COMMON_SHIFT_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  disabled={locked}
                  className="btn-secondary-action"
                  style={{
                    fontSize: '0.78rem',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    background: isPresetActive(preset) ? '#fed7aa' : '#ffffff',
                    border: '1px solid #d4c5b9',
                    color: '#431407',
                    fontWeight: isPresetActive(preset) ? 600 : 400,
                    cursor: locked ? 'not-allowed' : 'pointer',
                  }}
                  onClick={() => applyPreset(preset)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <label>每日開始時間
          <select
            aria-label="Beta 每日開始時間"
            value={draft.startTime}
            disabled={locked}
            onChange={(event) => updateDraft('startTime', event.target.value)}
          >
            <option value="">請選擇開始時間</option>
            {getTimeOptions(draft.startTime).map((time) => (
              <option key={time} value={time}>{time}</option>
            ))}
          </select>
        </label>
        <label>每日結束時間
          <select
            aria-label="Beta 每日結束時間"
            value={draft.endTime}
            disabled={locked}
            onChange={(event) => updateDraft('endTime', event.target.value)}
          >
            <option value="">請選擇結束時間</option>
            {getTimeOptions(draft.endTime).map((time) => (
              <option key={time} value={time}>{time}</option>
            ))}
          </select>
        </label>
        <label>結束日偏移
          <select aria-label="Beta 結束日偏移" value={draft.endDayOffset} disabled={locked} onChange={(event) => updateDraft('endDayOffset', event.target.value as OrderTermsDraft['endDayOffset'])}>
            <option value="0">同日</option>
            <option value="1">隔日</option>
          </select>
        </label>
      </div>

      {needsReplacement && <fieldset disabled={locked}>
        <legend>新天數的替代服務安排</legend>
        <label>替代日期排休方式<select aria-label="替代日期排休方式" value={serviceMode} onChange={(event) => { setServiceMode(event.target.value as typeof serviceMode); setReplacementDates(null); setPreview(null); }}>
          <option value="">請選擇排休方式</option>
          {(['休周六', '休周日', '週休2日', '連續服務'] as const).map((mode) => <option key={mode}>{mode}</option>)}
        </select></label>
        <button type="button" disabled={!serviceMode || !draftReady} onClick={() => void calculateReplacement()}>精算替代日期</button>
        {replacementDates && <p>替代服務日期（{replacementDates.length} 天）：{replacementDates.join('、')}</p>}
        {(currentQuery.assignments ?? []).map((assignment) => <label key={assignment.assignment_id}>人員 {assignment.staff_id}（原 {assignment.service_days} 天）的新服務天數
          <input aria-label={`指派 ${assignment.assignment_id} 新服務天數`} type="number" min="1" value={allocations[assignment.assignment_id] ?? ''} onChange={(event) => { setAllocations((current) => ({ ...current, [assignment.assignment_id]: event.target.value })); setPreview(null); }} />
        </label>)}
        <p>依原指派順序分配上述日期，合計須等於新合約天數；不會自動分配。日期與條款將同時保存。</p>
      </fieldset>}

      {timeValidationError && (
        <p className="order-v2-drawer-error" role="status" style={{ marginTop: '6px' }}>{timeValidationError}</p>
      )}

      <div className="order-v2-drawer-actions" style={{ marginTop: '12px' }}>
        <button type="button" disabled={locked || !draftReady || !replacementReady} onClick={() => void previewTerms()}>
          {status === 'previewing' ? '正在檢查條款變更…' : '檢查訂單條款變更'}
        </button>
      </div>

      {preview && (
        <div style={{ marginTop: '12px' }}>
          <strong>條款變更前後</strong>
          <p>服務天數：{preview.before.service_days} 天 → {preview.after.service_days} 天</p>
          {preview.before.service_hours_per_day !== preview.after.service_hours_per_day && (
            <p>每日時數：{preview.before.service_hours_per_day} 小時 → {preview.after.service_hours_per_day} 小時</p>
          )}
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

      {outcomeUnknown && <button type="button" disabled={status !== 'idle'} onClick={() => void applyTerms()}>重播同一筆條款提交</button>}
      {receipt && readback && (
        <p role="status">條款已套用並完成正式回讀；Order version {readback.order_version}，合約服務 {readback.terms.service_days} 日。</p>
      )}
      {receipt && !readback && (
        <div><p role="status">條款已提交、尚未確認正式讀回；Order version {receipt.order_version}。</p>
          <button type="button" disabled={status !== 'idle'} onClick={() => void observeReceipt(receipt)}>重新讀取已提交條款</button></div>
      )}
      {error && <p className="order-v2-drawer-error" role="alert">{error}</p>}
    </section>
  );
};

export default OrderTermsMutationPanel;
