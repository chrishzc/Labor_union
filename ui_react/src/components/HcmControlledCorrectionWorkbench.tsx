/** In-page HCM full-workbook correction for one canonical review identity. */
import React, { useState } from 'react';
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
  const [message, setMessage] = useState<string | null>(null);

  const selectFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setPreview(null);
    setMessage(null);
    if (!file) { setSnapshot(null); return; }
    try { setSnapshot(await HcmWorkbookSnapshot.fromFile(file)); }
    catch (error) { setSnapshot(null); setMessage(error instanceof Error ? error.message : '無法讀取修正版。'); }
  };

  const previewCorrection = async () => {
    if (!snapshot || busy) return;
    setBusy(true); setMessage(null);
    try { setPreview(await hcmResubmissionClient.preview(snapshot, reviewIdentity)); }
    catch (error) { setMessage(error instanceof Error ? error.message : '修正預覽失敗。'); }
    finally { setBusy(false); }
  };

  const applyCorrection = async () => {
    if (!snapshot || !preview || !reason.trim() || busy) return;
    setBusy(true); setMessage(null);
    try {
      await hcmResubmissionClient.apply(snapshot, preview, reason.trim());
      onApplied();
    } catch (error) { setMessage(error instanceof Error ? error.message : '修正套用失敗。'); }
    finally { setBusy(false); }
  };

  return (
    <section className="import-workbench-card" data-surface-id="imports.hcm-correction.workbench">
      <div className="import-card-header"><div className="import-card-title-group"><h2>修正案件 {caseNo}</h2><p>{displayMessage}</p></div></div>
      <p className="import-description">請選擇包含本案件的完整 HCM 修正版。系統會先預覽，且只會更新這項異常對應的欄位。</p>
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="選擇 HCM 修正版" disabled={busy} onChange={(event) => void selectFile(event)} />
      <button type="button" className="import-preview-btn" disabled={!snapshot || busy} onClick={() => void previewCorrection()}>{busy && !preview ? '預覽中…' : '預覽修正'}</button>
      {preview && <div className="import-preview-result" role="status"><strong>只會修正：{preview.source_field}</strong><p>案件 {preview.case_no}；套用前仍會重新確認資料版本。</p></div>}
      {preview && <label>修正原因<input value={reason} maxLength={500} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>}
      {preview && <button type="button" className="import-apply-btn" disabled={busy || !reason.trim()} onClick={() => void applyCorrection()}>{busy ? '套用中…' : '確認套用修正'}</button>}
      <button type="button" disabled={busy} onClick={onCancel}>取消</button>
      {message && <div className="import-error" role="alert">{message}</div>}
    </section>
  );
};

export default HcmControlledCorrectionWorkbench;
