import React, { useEffect, useRef, useState } from 'react';

import {
  caseArchitectureBootstrapClient,
  type CaseArchitectureBootstrapPreview,
  type CaseArchitectureBootstrapStatus,
} from '../api/case_import/case_architecture_bootstrap_client';
import {
  intakeBlockerMessage,
  intakeRepairErrorMessage,
  orderIntakeCompletionClient,
  type IntakeTermsPreview,
} from '../api/orders/order_intake_completion_client';

const reason = '補建既有案件缺少的 Client Finance、Payroll 與 Scheduling 初始資料';
const termsReason = '補齊既有歷史案件的約定服務開始日與服務天數';
const key = () => `case-bootstrap-repair-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;

const blockerMessage = (code: string) => ({
  missing_start_date: '請先補齊約定服務開始日，再建立案件初始資料。',
  case_architecture_bootstrap_partial: '案件已有部分初始資料，為避免覆寫既有資料，請由系統管理員檢查。',
}[code] ?? `目前無法補建（${code}）。`);

export const CaseArchitectureBootstrapRepairPanel: React.FC<{
  caseNo: string;
  onCompleted: () => void | Promise<void>;
}> = ({ caseNo, onCompleted }) => {
  const [status, setStatus] = useState<CaseArchitectureBootstrapStatus | null>(null);
  const [preview, setPreview] = useState<CaseArchitectureBootstrapPreview | null>(null);
  const [termsPreview, setTermsPreview] = useState<IntakeTermsPreview | null>(null);
  const [startDate, setStartDate] = useState('');
  const [serviceDays, setServiceDays] = useState('');
  const [busy, setBusy] = useState<'status' | 'terms-preview' | 'terms-apply' | 'preview' | 'apply' | null>('status');
  const [message, setMessage] = useState<string | null>(null);
  const idempotencyKey = useRef(key());
  const termsIdempotencyKey = useRef(`historical-terms-repair-${key()}`);

  useEffect(() => {
    let active = true;
    idempotencyKey.current = key();
    termsIdempotencyKey.current = `historical-terms-repair-${key()}`;
    setStatus(null);
    setPreview(null);
    setTermsPreview(null);
    setBusy('status');
    setMessage(null);
    void caseArchitectureBootstrapClient.status(caseNo)
      .then(async (value) => {
        if (!active) return;
        setStatus(value);
        if (value.domain_blockers.includes('missing_start_date')) {
          const completion = await orderIntakeCompletionClient.previewCompletion(caseNo);
          if (!active) return;
          setStartDate(completion.current_start_date ?? '');
          setServiceDays(completion.current_service_days ? String(completion.current_service_days) : '');
        }
      })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : '無法讀取案件初始資料狀態。'); })
      .finally(() => { if (active) setBusy(null); });
    return () => { active = false; };
  }, [caseNo]);

  const runTermsPreview = async () => {
    setBusy('terms-preview');
    setMessage(null);
    setTermsPreview(null);
    try {
      setTermsPreview(await orderIntakeCompletionClient.previewTerms(
        caseNo, startDate, Number(serviceDays),
      ));
    } catch (error) {
      setMessage(intakeRepairErrorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const applyTerms = async () => {
    if (!termsPreview) return;
    setBusy('terms-apply');
    setMessage(null);
    try {
      await orderIntakeCompletionClient.applyTerms(
        caseNo, termsPreview, termsReason, termsIdempotencyKey.current,
      );
      const refreshed = await caseArchitectureBootstrapClient.status(caseNo);
      setStatus(refreshed);
      setTermsPreview(null);
      setMessage('約定服務資料已補齊，現在可以檢查案件初始資料補建內容。');
    } catch (error) {
      setMessage(intakeRepairErrorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const runPreview = async () => {
    if (!status?.recommendation) return;
    setBusy('preview');
    setMessage(null);
    try {
      setPreview(await caseArchitectureBootstrapClient.preview(caseNo, status.recommendation));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '案件初始資料預覽失敗。');
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    if (!status?.recommendation || !preview) return;
    setBusy('apply');
    setMessage(null);
    try {
      await caseArchitectureBootstrapClient.apply(
        caseNo, status.recommendation, preview, reason, idempotencyKey.current,
      );
      setMessage('案件初始資料已建立，正在重新讀取訂單條件與客戶帳務。');
      await onCompleted();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '案件初始資料建立失敗；可使用相同預覽安全重試。');
    } finally {
      setBusy(null);
    }
  };

  return <div className="registry-bootstrap-repair" aria-label="案件初始資料修復" style={{ borderTop: '1px solid #fed7aa', marginTop: '12px', paddingTop: '12px', display: 'grid', gap: '8px' }}>
    <strong>缺少案件初始資料</strong>
    <p style={{ margin: 0 }}>這不是排班格式問題；既有案件尚未建立 Client Finance、Payroll 與 Scheduling 初始根資料。</p>
    {busy === 'status' && <p role="status">正在檢查可補建資料…</p>}
    {status?.ready && <p role="status">初始資料已存在，請重新讀取案件。</p>}
    {status && status.domain_blockers.filter((blocker) => blocker !== 'missing_start_date').length > 0 && <ul>{status.domain_blockers.filter((blocker) => blocker !== 'missing_start_date').map((blocker) => <li key={blocker}>{blockerMessage(blocker)}</li>)}</ul>}
    {status?.domain_blockers.includes('missing_start_date') && <div style={{ display: 'grid', gap: '8px' }}>
      <p style={{ margin: 0 }}>{blockerMessage('missing_start_date')}</p>
      <label>約定服務開始日<input type="date" value={startDate} onChange={(event) => { setStartDate(event.target.value); setTermsPreview(null); }} /></label>
      <label>服務天數<input type="number" min="1" step="1" value={serviceDays} onChange={(event) => { setServiceDays(event.target.value); setTermsPreview(null); }} /></label>
      <button type="button" disabled={busy !== null || !startDate || Number(serviceDays) <= 0} onClick={() => void runTermsPreview()}>
        {busy === 'terms-preview' ? '正在檢查約定服務資料…' : '檢查約定服務資料'}
      </button>
      {termsPreview && <div style={{ display: 'grid', gap: '6px' }}>
        <span>將設定約定服務開始日 {termsPreview.after_start_date}，服務天數 {termsPreview.after_service_days} 天。</span>
        {termsPreview.blockers.length > 0 && <ul>{termsPreview.blockers.map((blocker) => <li key={blocker}>{intakeBlockerMessage(blocker)}</li>)}</ul>}
        <button type="button" disabled={busy !== null || !termsPreview.apply_allowed} onClick={() => void applyTerms()}>
          {busy === 'terms-apply' ? '正在套用約定服務資料…' : '確認套用約定服務資料'}
        </button>
      </div>}
    </div>}
    {status?.recommendation && !preview && <button type="button" disabled={busy !== null} onClick={() => void runPreview()}>
      {busy === 'preview' ? '正在產生補建預覽…' : '檢查初始資料補建內容'}
    </button>}
    {preview && <div style={{ display: 'grid', gap: '6px' }}>
      <span>客戶時薪：{preview.client_hourly_rate_ntd} 元；月嫂政策：{preview.payroll_policy_kind}／{preview.payroll_hourly_rate_ntd} 元。</span>
      <button type="button" disabled={busy !== null} onClick={() => void apply()}>
        {busy === 'apply' ? '正在建立初始資料…' : '確認建立案件初始資料'}
      </button>
    </div>}
    {message && <p role="status">{message}</p>}
  </div>;
};

export default CaseArchitectureBootstrapRepairPanel;
