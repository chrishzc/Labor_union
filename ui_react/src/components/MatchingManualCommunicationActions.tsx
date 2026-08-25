/**
 * File: MatchingManualCommunicationActions.tsx
 * Description: 以 Preview、確認與 Apply 留存媒合資訊及客戶履歷的人工送達證據。
 */
import React, { useState } from 'react';
import {
  candidateContactPoolClient,
  type ManualCandidateInformationPreview,
  type ManualMatchingConfirmationMethod,
} from '../api/scheduling/candidate_contact_pool_client';
import {
  matchingPlanCommunicationClient,
  type ManualCustomerProfilesPreview,
} from '../api/scheduling/matching_plan_communication_client';

const METHOD_LABELS: Record<ManualMatchingConfirmationMethod, string> = {
  phone: '電話',
  in_person: '現場',
  paper: '紙本',
  other: '其他可稽核方式',
};

interface CandidateManualInformationProps {
  caseNo: string;
  candidateId: number;
  infoType: 1 | 2;
  disabledReason: string | null;
  onCommitted: () => Promise<void>;
}

export const CandidateManualInformationActions: React.FC<CandidateManualInformationProps> = ({
  caseNo,
  candidateId,
  infoType,
  disabledReason,
  onCommitted,
}) => {
  const [method, setMethod] = useState<ManualMatchingConfirmationMethod>('phone');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<ManualCandidateInformationPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resetPreview = () => {
    setPreview(null);
    setConfirmed(false);
    setNotice(null);
  };

  const runPreview = async () => {
    setBusy('preview');
    setError(null);
    setNotice(null);
    try {
      setPreview(await candidateContactPoolClient.previewManualInformation(
        caseNo, candidateId, infoType, method, reason,
      ));
      setConfirmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法檢查人工資訊確認影響。');
    } finally {
      setBusy(null);
    }
  };

  const runApply = async () => {
    if (!preview) return;
    setBusy('apply');
    setError(null);
    try {
      await candidateContactPoolClient.applyManualInformation(preview);
      setNotice('人工確認紀錄已留存。');
      setPreview(null);
      setConfirmed(false);
      await onCommitted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法留存人工資訊確認。');
    } finally {
      setBusy(null);
    }
  };

  if (disabledReason) return null;
  return (
    <div style={{ display: 'grid', gap: '7px', marginTop: '8px', paddingTop: '8px', borderTop: '1px dashed #d8c1b8' }}>
      <strong style={{ fontSize: '0.8rem' }}>非 LINE 人工確認</strong>
      <select
        aria-label={`資訊-${infoType} 人工確認方式`}
        value={method}
        disabled={busy !== null}
        onChange={(event) => { setMethod(event.target.value as ManualMatchingConfirmationMethod); resetPreview(); }}
      >
        {Object.entries(METHOD_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input
        aria-label={`資訊-${infoType} 人工確認依據`}
        value={reason}
        maxLength={500}
        disabled={busy !== null}
        placeholder="記錄實際說明方式、時間或可核對依據"
        onChange={(event) => { setReason(event.target.value); resetPreview(); }}
      />
      <button
        type="button"
        className="matching-action-btn-sm"
        data-control-id={`orders.candidate-info-${infoType}.manual-preview`}
        disabled={busy !== null || reason.trim().length === 0}
        onClick={() => void runPreview()}
      >
        {busy === 'preview' ? '正在檢查人工確認…' : '檢查人工已提供資訊的影響'}
      </button>
      {preview && (
        <div style={{ display: 'grid', gap: '6px', fontSize: '0.78rem', color: '#57423b' }}>
          <span>候選 Staff #{preview.staff_id}／目前聯繫狀態已核對</span>
          <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核對候選人、資訊類型與實際確認依據</label>
          <button
            type="button"
            className="orders-load-more-btn"
            data-control-id={`orders.candidate-info-${infoType}.manual-apply`}
            disabled={busy !== null || !confirmed}
            onClick={() => void runApply()}
          >
            {busy === 'apply' ? '正在留存人工確認…' : '確認留存人工資訊證據'}
          </button>
        </div>
      )}
      {notice && <span role="status" style={{ color: '#166534', fontSize: '0.78rem' }}>{notice}</span>}
      {error && <span role="alert" style={{ color: '#991b1b', fontSize: '0.78rem' }}>{error}</span>}
    </div>
  );
};

interface CustomerProfilesManualProps {
  caseNo: string;
  planId: number;
  currentStatus: string | null;
  onCommitted: () => Promise<void>;
}

export const CustomerProfilesManualActions: React.FC<CustomerProfilesManualProps> = ({
  caseNo,
  planId,
  currentStatus,
  onCommitted,
}) => {
  const [method, setMethod] = useState<ManualMatchingConfirmationMethod>('phone');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<ManualCustomerProfilesPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resetPreview = () => {
    setPreview(null);
    setConfirmed(false);
    setNotice(null);
  };

  const runPreview = async () => {
    setBusy('preview');
    setError(null);
    try {
      const contactState = await matchingPlanCommunicationClient.queryContactState(caseNo, planId);
      setPreview(await matchingPlanCommunicationClient.previewManualCustomerProfiles(
        caseNo,
        planId,
        contactState.plan.communication_version,
        method,
        reason,
      ));
      setConfirmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法檢查客戶履歷人工送達影響。');
    } finally {
      setBusy(null);
    }
  };

  const runApply = async () => {
    if (!preview) return;
    setBusy('apply');
    setError(null);
    try {
      await matchingPlanCommunicationClient.applyManualCustomerProfiles(preview);
      setNotice('客戶履歷人工送達紀錄已留存。');
      setPreview(null);
      setConfirmed(false);
      await onCommitted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '無法留存客戶履歷人工送達記錄。');
    } finally {
      setBusy(null);
    }
  };

  if (currentStatus !== null) {
    return (
      <div style={{ display: 'grid', gap: '4px' }}>
        <span role="status" style={{ color: '#166534', fontSize: '0.8rem' }}>履歷傳達根事實：{currentStatus}</span>
        {notice && <span role="status" style={{ color: '#166534', fontSize: '0.78rem' }}>{notice}</span>}
      </div>
    );
  }
  return (
    <div style={{ display: 'grid', gap: '8px', marginTop: '10px', paddingTop: '10px', borderTop: '1px dashed #d8c1b8' }}>
      <strong style={{ fontSize: '0.82rem' }}>非 LINE 人工送達履歷</strong>
      <select aria-label="履歷人工送達方式" value={method} disabled={busy !== null} onChange={(event) => { setMethod(event.target.value as ManualMatchingConfirmationMethod); resetPreview(); }}>
        {Object.entries(METHOD_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <input aria-label="履歷人工送達依據" value={reason} maxLength={500} disabled={busy !== null} placeholder="記錄實際提供履歷的時間、方式或可核對依據" onChange={(event) => { setReason(event.target.value); resetPreview(); }} />
      <button type="button" className="matching-action-btn-sm" data-control-id="orders.customer-profiles.manual-preview" disabled={busy !== null || reason.trim().length === 0} onClick={() => void runPreview()}>
        {busy === 'preview' ? '正在檢查履歷送達影響…' : '檢查人工已送達履歷的影響'}
      </button>
      {preview && <div style={{ display: 'grid', gap: '6px', fontSize: '0.78rem', color: '#57423b' }}>
        <span>方案 #{preview.plan_id}／{preview.segment_ids.length} 位月嫂履歷已核對</span>
        <label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核對正式方案、履歷對象與實際送達依據</label>
        <button type="button" className="orders-load-more-btn" data-control-id="orders.customer-profiles.manual-apply" disabled={busy !== null || !confirmed} onClick={() => void runApply()}>
          {busy === 'apply' ? '正在留存履歷送達記錄…' : '確認留存人工履歷送達證據'}
        </button>
      </div>}
      {notice && <span role="status" style={{ color: '#166534', fontSize: '0.78rem' }}>{notice}</span>}
      {error && <span role="alert" style={{ color: '#991b1b', fontSize: '0.78rem' }}>{error}</span>}
    </div>
  );
};
