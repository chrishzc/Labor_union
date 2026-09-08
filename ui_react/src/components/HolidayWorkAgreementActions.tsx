/**
 * File: HolidayWorkAgreementActions.tsx
 * Description: 留存目前媒合方案的國定假日雙方協調結果，不把人工登錄宣稱為 LINE 回覆。
 */
import React, { useState } from 'react';
import {
  matchingPlanCommunicationClient,
  type HolidayWorkAgreementPreview,
  type HolidayWorkParticipantDecision,
} from '../api/scheduling/matching_plan_communication_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';

interface PlanSegment {
  segmentId: number;
  sequence: number;
  staffId: number;
}

interface HolidayWorkAgreementActionsProps {
  caseNo: string;
  planId: number;
  segments: readonly PlanSegment[];
  onCommitted: () => Promise<void>;
}

type Decision = 'accepted' | 'declined';

export const HolidayWorkAgreementActions: React.FC<HolidayWorkAgreementActionsProps> = ({
  caseNo,
  planId,
  segments,
  onCommitted,
}) => {
  const [holidayDate, setHolidayDate] = useState('');
  const [reason, setReason] = useState('');
  const [customerDecision, setCustomerDecision] = useState<Decision>('accepted');
  const [caregiverDecisions, setCaregiverDecisions] = useState<Record<number, Decision>>({});
  const [preview, setPreview] = useState<HolidayWorkAgreementPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearPreview = () => {
    setPreview(null);
    setConfirmed(false);
    setNotice(null);
  };

  const participantDecisions = (): HolidayWorkParticipantDecision[] => [
    { participant_role: 'customer', segment_id: null, decision: customerDecision },
    ...segments.map((segment) => ({
      participant_role: 'caregiver' as const,
      segment_id: segment.segmentId,
      decision: caregiverDecisions[segment.segmentId] ?? 'accepted',
    })),
  ];

  const runPreview = async () => {
    setBusy('preview');
    setError(null);
    setNotice(null);
    try {
      const [activePlan, contactState] = await Promise.all([
        waitingDepositLockClient.queryPlan(caseNo),
        matchingPlanCommunicationClient.queryContactState(caseNo, planId),
      ]);
      if (
        activePlan.planId !== planId
        || activePlan.status !== 'proposed'
        || activePlan.planVersion === undefined
        || contactState.plan.id !== planId
        || contactState.plan.status !== 'proposed'
      ) {
        throw new Error('目前方案已變更，請重新載入後再協調國定假日上班。');
      }
      setPreview(await matchingPlanCommunicationClient.previewHolidayWorkAgreement(
        caseNo,
        planId,
        activePlan.planVersion,
        holidayDate,
        participantDecisions(),
        reason,
      ));
      setConfirmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法檢查國定假日上班協議。');
    } finally {
      setBusy(null);
    }
  };

  const runApply = async () => {
    if (!preview) return;
    setBusy('apply');
    setError(null);
    try {
      const receipt = await matchingPlanCommunicationClient.applyHolidayWorkAgreement(preview, reason);
      setNotice(receipt.agreement_status === 'accepted'
        ? '雙方協議已留存；這一天會在目前方案版本下列為可工作的國定假日。'
        : '協調結果已留存；未取得全體同意，這一天仍維持休假。');
      setPreview(null);
      setConfirmed(false);
      await onCommitted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法留存國定假日上班協議。');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div data-surface-id="orders.matching.holiday-work-agreement" style={{ display: 'grid', gap: '8px', marginTop: '12px', padding: '12px', border: '1px solid #ead8d1', borderRadius: '10px' }}>
      <strong style={{ fontSize: '0.88rem', color: '#1e1b19' }}>國定假日上班雙方協調</strong>
      <p style={{ margin: 0, color: '#74593f', fontSize: '0.78rem', lineHeight: 1.5 }}>
        預設休假。僅當客戶與目前方案內每一位月嫂都對同一日期表示同意，才會列為服務日；這是人工協調紀錄，不代表 LINE 已送達或回覆。
      </p>
      <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
        國定假日日期
        <input aria-label="國定假日上班協議日期" type="date" value={holidayDate} disabled={busy !== null} onChange={(event) => { setHolidayDate(event.target.value); clearPreview(); }} />
      </label>
      <fieldset disabled={busy !== null} style={{ display: 'grid', gap: '6px', border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontSize: '0.82rem', color: '#57423b' }}>協調結果</legend>
        <label><input aria-label="客戶國定假日上班同意" type="checkbox" checked={customerDecision === 'accepted'} onChange={(event) => { setCustomerDecision(event.target.checked ? 'accepted' : 'declined'); clearPreview(); }} />客戶同意上班</label>
        {segments.map((segment) => (
          <label key={segment.segmentId}><input aria-label={`月嫂 ${segment.staffId} 國定假日上班同意`} type="checkbox" checked={(caregiverDecisions[segment.segmentId] ?? 'accepted') === 'accepted'} onChange={(event) => { setCaregiverDecisions((current) => ({ ...current, [segment.segmentId]: event.target.checked ? 'accepted' : 'declined' })); clearPreview(); }} />月嫂 #{segment.staffId}（第 {segment.sequence} 段）同意上班</label>
        ))}
      </fieldset>
      <label style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#57423b' }}>
        可稽核的協調依據
        <textarea aria-label="國定假日上班協調依據" rows={2} maxLength={500} value={reason} disabled={busy !== null} placeholder="記錄電話、現場或紙本協調的時間與可核對依據" onChange={(event) => { setReason(event.target.value); clearPreview(); }} />
      </label>
      <button type="button" className="matching-action-btn-sm" data-control-id="orders.matching.holiday-work.preview" disabled={busy !== null || !holidayDate || reason.trim().length === 0} onClick={() => void runPreview()}>
        {busy === 'preview' ? '正在檢查目前方案與協調結果…' : '檢查國定假日上班協議'}
      </button>
      {preview && (
        <div style={{ display: 'grid', gap: '6px', fontSize: '0.78rem', color: '#57423b' }}>
          <span>{preview.agreement_status === 'accepted' ? '全體已同意；可留存為該方案版本的上班日。' : '有人未同意；可留存協調結果，但此日仍會維持休假。'}</span>
          <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核對目前方案、日期、客戶及所有月嫂的協調結果</label>
          <button type="button" className="orders-load-more-btn" data-control-id="orders.matching.holiday-work.apply" disabled={busy !== null || !confirmed} onClick={() => void runApply()}>
            {busy === 'apply' ? '正在留存協調結果…' : '確認留存國定假日協調結果'}
          </button>
        </div>
      )}
      {notice && <span role="status" style={{ color: '#166534', fontSize: '0.78rem' }}>{notice}</span>}
      {error && <span role="alert" style={{ color: '#991b1b', fontSize: '0.78rem' }}>{error}</span>}
    </div>
  );
};
