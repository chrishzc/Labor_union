/** In-page HCM full-workbook correction for one canonical review identity. */
import React, { useRef, useState } from 'react';
import { ApiHttpError } from '../api/shared/typed_errors';
import { hcmResubmissionClient } from '../api/case_import/hcm_resubmission_client';
import { HcmWorkbookSnapshot } from '../api/case_import/hcm_workbook_client';
import type { HcmResubmissionPreview } from '../api/case_import/hcm_workbook_schemas';
import '../pages/DataImportPage.css';

export interface HcmControlledCorrectionWorkbenchProps {
  caseNo: string;
  displayMessage: string;
  reviewIdentity: string;
  onCancel: () => void;
  onApplied: () => void;
}

export const HcmControlledCorrectionWorkbench: React.FC<HcmControlledCorrectionWorkbenchProps> = ({
  caseNo, displayMessage, reviewIdentity, onCancel, onApplied,
}) => {
  const [snapshot, setSnapshot] = useState<HcmWorkbookSnapshot | null>(null);
  const [preview, setPreview] = useState<HcmResubmissionPreview | null>(null);
  const [reason, setReason] = useState('修正 HCM 匯入異常');
  const [busy, setBusy] = useState(false);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [submitted, setSubmitted] = useState<number | null>(null);
  const fileReadGeneration = useRef(0);
  const [message, setMessage] = useState<string | null>(null);

  const selectFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const generation = ++fileReadGeneration.current;
    const file = event.target.files?.[0];
    setSnapshot(null);
    setPreview(null);
    setMessage(null);
    if (!file) { setSnapshot(null); return; }
    try { const value = await HcmWorkbookSnapshot.fromFile(file); if (generation === fileReadGeneration.current) setSnapshot(value); }
    catch (error) { if (generation === fileReadGeneration.current) { setSnapshot(null); setMessage(error instanceof Error ? error.message : '無法讀取修正版。'); } }
  };

  const previewCorrection = async () => {
    if (!snapshot || busy) return;
    setBusy(true); setMessage(null); setPreview(null);
    try { setPreview(await hcmResubmissionClient.preview(snapshot, reviewIdentity)); }
    catch (error) { setMessage(error instanceof Error ? error.message : '修正預覽失敗。'); }
    finally { setBusy(false); }
  };

  const observeCorrection = async (version: number) => {
    setBusy(true); setMessage(null);
    try {
      const state = await hcmResubmissionClient.query(reviewIdentity);
      if (state.case_no !== caseNo || state.review_identity !== reviewIdentity || state.review_version < version) throw new Error('修正讀回案件或版本不一致。');
      if (!state.resolved) throw new Error('目前問題尚未解除，請保留此項並重新核對。');
      onApplied();
    } catch (error) { setMessage(`修正已提交，尚未確認問題解除：${error instanceof Error ? error.message : '正式讀回失敗。'}`); }
    finally { setBusy(false); }
  };

  const applyCorrection = async () => {
    if (!snapshot || !preview || !reason.trim() || busy) return;
    setBusy(true); setMessage(null);
    try {
      const receipt = await hcmResubmissionClient.apply(snapshot, preview, reason.trim());
      setOutcomeUnknown(false);
      setSubmitted(receipt.resulting_review_version); setPreview(null);
      await observeCorrection(receipt.resulting_review_version);
    } catch (error) {
      if (error instanceof ApiHttpError && [400, 401, 403, 404, 409, 422].includes(error.status)) {
        setOutcomeUnknown(false); setPreview(null);
        setMessage(error.code === 'service_data_locked' ? '服務條件已鎖定，不能透過 HCM 更正；請保留已完成服務與帳務歷史。'
          : error.status === 409 ? '正式資料或預覽版本已變更，本次修正未套用；請重新預覽後核對。'
          : '修正未通過資料或權限檢查；請核對來源欄位及登入權限後重新預覽。');
      } else {
        setOutcomeUnknown(true); setMessage(`送出結果尚未確認；可重播同一筆提交取得結果。${error instanceof Error ? error.message : '修正套用失敗。'}`);
      }
    }
    finally { setBusy(false); }
  };

  return (
    <section className="import-workbench-card" data-surface-id="imports.hcm-correction.workbench">
      <div className="import-card-header"><div className="import-card-title-group"><h2>修正案件 {caseNo}</h2><p>{displayMessage}</p></div></div>
      <p className="import-description">請選擇包含本案件的完整 HCM 修正版。系統會先預覽，且只會更新這項異常對應的欄位。</p>
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="選擇 HCM 修正版" disabled={busy || submitted !== null || outcomeUnknown} onChange={(event) => void selectFile(event)} />
      <button type="button" className="import-preview-btn" disabled={!snapshot || busy || submitted !== null || outcomeUnknown} onClick={() => void previewCorrection()}>{busy && !preview ? '預覽中…' : '預覽修正'}</button>
      {preview && <div className="import-preview-result" role="status"><strong>只會修正：{preview.source_field}</strong><p>案件 {preview.case_no}；套用前仍會重新確認資料版本。</p></div>}
      {preview && <label>修正原因<input value={reason} maxLength={500} disabled={busy || outcomeUnknown} onChange={(event) => setReason(event.target.value)} /></label>}
      {preview && <button type="button" className="import-apply-btn" disabled={busy || !reason.trim()} onClick={() => void applyCorrection()}>{busy ? '套用中…' : outcomeUnknown ? '重播同一筆修正提交' : '確認套用修正'}</button>}
      {submitted !== null && <button type="button" disabled={busy} onClick={() => void observeCorrection(submitted)}>重新讀取修正結果</button>}
      <button type="button" disabled={busy} onClick={() => { fileReadGeneration.current += 1; setSnapshot(null); setPreview(null); onCancel(); }}>{submitted !== null ? '關閉（修正已提交）' : outcomeUnknown ? '關閉（結果尚未確認）' : '取消'}</button>
      {message && <div className="import-error" role="alert">{message}</div>}
    </section>
  );
};

export default HcmControlledCorrectionWorkbench;
