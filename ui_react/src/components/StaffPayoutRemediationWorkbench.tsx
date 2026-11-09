import { useUnsavedDraft } from './UnsavedChanges';
/**
 * File: StaffPayoutRemediationWorkbench.tsx
 * Description: PAYOUT-001 的人工核銷工作台，僅以 Job terminal 與 fresh owner readback 解除異常。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  createStaffPayoutRemediationCommand,
  staffPayoutRemediationClient,
  type StaffPayoutRemediationClient,
  type StaffPayoutRemediationOptions,
  type StaffPayoutSelection,
} from '../api/staff_payables/staff_payout_remediation_client';
import {
  type StaffPayoutJob,
  type StaffPayoutJobAccepted,
  type StaffPayoutPreview,
} from '../api/staff_payables/staff_payout_remediation_schemas';
import { StaffPayoutRemediationError, staffPayoutBlockerMessage } from '../api/staff_payables/staff_payout_remediation_errors';
import type { StaffPayablesQuery } from '../api/staff_payables/staff_payables_query_schemas';

export interface StaffPayoutRemediationTarget {
  staffId: number;
  obligationIdentity: string;
  obligationIdentities?: readonly string[];
}

export interface StaffPayoutRemediationWorkbenchProps {
  target: StaffPayoutRemediationTarget;
  onResolved?: () => void | Promise<void>;
  onPosted?: () => void;
  financeImportRowId?: number;
  sourceBank?: 'sinopac' | 'taishin';
  confirmPreview?: boolean;
  onBusyChange?: (busy: boolean) => void;
  client?: StaffPayoutRemediationClient;
  requestOptions?: StaffPayoutRemediationOptions;
  pollIntervalMs?: number;
  maxPollAttempts?: number;
}

type Busy = 'query' | 'preview' | 'apply' | 'poll' | 'reconcile' | null;
const EMPTY_REQUEST_OPTIONS: StaffPayoutRemediationOptions = {};

function parseRowIds(value: string): number[] | null {
  const parts = value.trim().split(/[\s,]+/).filter(Boolean);
  if (!parts.length) return null;
  const parsed = parts.map((part) => {
    if (!/^[1-9][0-9]*$/.test(part)) return null;
    const id = Number(part);
    return Number.isSafeInteger(id) && id > 0 ? id : null;
  });
  if (parsed.some((item) => item === null)) return null;
  const values = parsed as number[];
  return new Set(values).size === values.length ? values : null;
}

function activeObligations(query: StaffPayablesQuery | null, target: StaffPayoutRemediationTarget) {
  const ids = target.obligationIdentities ?? [target.obligationIdentity];
  return query?.obligations.filter((item) => ids.includes(item.obligation_identity)) ?? [];
}
function targetPresent(query: StaffPayablesQuery, target: StaffPayoutRemediationTarget) {
  return activeObligations(query, target).length === (target.obligationIdentities ?? [target.obligationIdentity]).length;
}
function targetSettled(query: StaffPayablesQuery, target: StaffPayoutRemediationTarget) {
  return targetPresent(query, target) && activeObligations(query, target).every((item) => item.balance_ntd === 0 && item.payout_status === 'completed');
}

function displayError(error: unknown, sourceBank?: string): string {
  if (error instanceof StaffPayoutRemediationError) {
    const blocker = staffPayoutBlockerMessage(error.code,sourceBank);
    if (blocker) return blocker;
    if (error.code.toLowerCase().includes('stale')) return '應付款資料已更新，請重新查詢後再檢查核銷影響。';
    if (error.code === 'STAFF_PAYOUT_SCHEMA_MISMATCH') return '應付款核銷資料目前不完整，已停止操作。';
    if (['STAFF_PAYOUT_TIMEOUT', 'STAFF_PAYOUT_NETWORK', 'STAFF_PAYOUT_ABORTED', 'STAFF_PAYOUT_UNKNOWN', 'STAFF_PAYOUT_JOB_TIMEOUT'].includes(error.code)) {
      return '核銷結果目前無法安全確認；請使用原操作重新查詢或安全重試。';
    }
    return '應付款核銷目前無法完成，異常仍會保留；請重新整理後再試。';
  }
  return '應付款核銷目前無法完成，異常仍會保留；請重新整理後再試。';
}

function isStaleApplyError(error: unknown): boolean {
  return error instanceof StaffPayoutRemediationError
    && error.code.toLowerCase().includes('stale');
}

function isUnknownApplyOutcome(error: unknown): boolean {
  return error instanceof StaffPayoutRemediationError
    && ['STAFF_PAYOUT_TIMEOUT', 'STAFF_PAYOUT_NETWORK', 'STAFF_PAYOUT_ABORTED', 'STAFF_PAYOUT_UNKNOWN'].includes(error.code);
}

function terminalMessage(job: StaffPayoutJob, sourceBank?: string): string {
  if (job.status === 'failed') {
    if (job.outcome?.kind === 'failure') {
      const blocker = staffPayoutBlockerMessage(job.outcome.error.code,sourceBank);
      if (blocker) return blocker;
      if (job.outcome.error.code.toLowerCase().includes('stale')) return '應付款資料已更新，請重新查詢後再檢查核銷影響。';
    }
    return '核銷處理未完成，未留存可顯示的具體阻擋原因；請重新查詢帳務資料。';
  }
  if (job.status === 'cancelled') return '背景核銷已取消；異常仍保留。';
  return '背景核銷尚未完成；異常仍保留。';
}

function payoutStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    payable: '待付款',
    partially_paid: '部分付款',
    completed: '已結清',
    overdue: '逾期待處理',
  };
  return labels[status] ?? '待確認';
}

function jobStatusLabel(status: StaffPayoutJob['status']): string {
  const labels: Record<StaffPayoutJob['status'], string> = {
    queued: '等待處理',
    running: '處理中',
    succeeded: '處理完成，正在核對應付款',
    failed: '處理未完成',
    cancelled: '已取消',
  };
  return labels[status];
}

function waitForPoll(ms: number): Promise<void> {
  return new Promise((resolve) => { window.setTimeout(resolve, ms); });
}

function previewMatchesTarget(preview: StaffPayoutPreview, target: StaffPayoutRemediationTarget, query: StaffPayablesQuery): boolean {
  if (preview.staff_payables_version !== query.staff_payables_version) return false;
  if (preview.candidate.staff_id !== target.staffId || !('allocations' in preview.candidate)) return false;
  const obligations = new Set(preview.candidate.allocations.map((item) => item.obligation_identity));
  return obligations.size > 0 && [...obligations].every((id) => (target.obligationIdentities ?? [target.obligationIdentity]).includes(id));
}

export const StaffPayoutRemediationWorkbench: React.FC<StaffPayoutRemediationWorkbenchProps> = ({
  target,
  onResolved,
  onPosted,
  financeImportRowId,
  sourceBank,
  confirmPreview = false,
  onBusyChange,
  client = staffPayoutRemediationClient,
  requestOptions = EMPTY_REQUEST_OPTIONS,
  pollIntervalMs = 500,
  maxPollAttempts = 60,
}) => {
  const [query, setQuery] = useState<StaffPayablesQuery | null>(null);
  const [rowIdsText, setRowIdsText] = useState('');
  const [differenceMode, setDifferenceMode] = useState<'' | 'underpayment' | 'overpayment'>('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<StaffPayoutPreview | null>(null);
  const [job, setJob] = useState<StaffPayoutJob | null>(null);
  const [accepted, setAccepted] = useState<StaffPayoutJobAccepted | null>(null);
  const [busy, setBusy] = useState<Busy>('query');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [unknownOutcome, setUnknownOutcome] = useState(false);
  const command = useRef<{ fingerprint: string; value: ReturnType<typeof createStaffPayoutRemediationCommand> } | null>(null);
  const generation = useRef(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current += 1; };
  }, []);

  const loadQuery = useCallback(async (resolveOnSettled = false): Promise<StaffPayablesQuery> => {
    const current = ++generation.current;
    setBusy('query');
    setError(null);
    try {
      const fresh = await client.query(target.staffId, requestOptions);
      if (!targetPresent(fresh, target)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_OWNER_MISMATCH', 'owner Query 找不到原異常義務。');
      if (current === generation.current && mounted.current) {
        setQuery(fresh);
        if (resolveOnSettled && targetSettled(fresh, target)) {
          setNotice('已重新確認應付款結清。');
          await onResolved?.();
        }
      }
      return fresh;
    } finally {
      if (mounted.current && current === generation.current) setBusy(null);
    }
  }, [client, onResolved, requestOptions, target]);

  useEffect(() => {
    generation.current += 1;
    setQuery(null); setPreview(null); setJob(null); setAccepted(null);
    setRowIdsText(financeImportRowId === undefined ? '' : String(financeImportRowId)); setDifferenceMode(''); setReason(''); setError(null); setNotice(null); setUnknownOutcome(false); command.current = null;
    const current = generation.current;
    void client.query(target.staffId, requestOptions).then((fresh) => {
      if (!targetPresent(fresh, target)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_OWNER_MISMATCH', 'owner Query 找不到原異常義務。');
      if (current === generation.current && mounted.current) { setQuery(fresh); setBusy(null); }
    }).catch((caught: unknown) => {
      if (current === generation.current && mounted.current) { setBusy(null); setError(displayError(caught,sourceBank)); }
    });
    return () => { generation.current += 1; };
  }, [client, requestOptions, target, financeImportRowId, sourceBank]);

  const invalidatePreview = () => { setPreview(null); setNotice(null); command.current = null; };
  const obligations = activeObligations(query, target);
  const obligation = obligations[0] ?? null;
  const active = obligations.some((item) => item.balance_ntd > 0 && item.payout_status !== 'completed');
  const payoutCandidate = preview && 'allocations' in preview.candidate ? preview.candidate : null;
  const selection = (): StaffPayoutSelection | null => {
    const financeImportRowIds = parseRowIds(rowIdsText);
    if (!financeImportRowIds || !active || (financeImportRowId !== undefined && (financeImportRowIds.length !== 1 || financeImportRowIds[0] !== financeImportRowId))) return null;
    return { financeImportRowIds, obligationIdentities: obligations.filter((item) => item.balance_ntd > 0).map((item) => item.obligation_identity), ...(differenceMode ? { differenceMode } : {}) };
  };
  const runPreview = async () => {
    const selected = selection();
    if (!selected || !query || busy !== null || unknownOutcome) return;
    setBusy('preview'); setError(null); setNotice(null); setPreview(null);
    try {
      const value = await client.preview(selected, requestOptions);
      if (!previewMatchesTarget(value, target, query)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_PREVIEW_IDENTITY_MISMATCH', 'Preview 未回傳同一 Staff 與原義務。');
      setPreview(value);
      if (!confirmPreview) await runApply(value);
    } catch (caught) { setError(displayError(caught,sourceBank)); }
    finally { if (mounted.current) setBusy(null); }
  };

  const readbackAfterSuccess = async (): Promise<void> => {
    const fresh = await loadQuery(true);
    onPosted?.();
    const current = activeObligations(fresh, target);
    if (!targetSettled(fresh, target)) {
      setNotice(`最新應付款仍未結清（餘額 NT$ ${current.reduce((sum, item) => sum + item.balance_ntd, 0).toLocaleString('zh-TW')}、狀態 ${current.map((item) => payoutStatusLabel(item.payout_status)).join('／')}）；異常仍會保留。`);
      return;
    }
    setNotice('已重新確認應付款餘額歸零且完成結清，異常可解除。');
  };

  const retryOwnerQuery = async (): Promise<void> => {
    try {
      await loadQuery(false);
    } catch (caught) {
      if (mounted.current) setError(displayError(caught,sourceBank));
    }
  };

  const pollToTerminal = async (jobId: string): Promise<void> => {
    setBusy('poll'); setError(null); setUnknownOutcome(false);
    let latest: StaffPayoutJob | null = null;
    for (let attempt = 0; attempt < maxPollAttempts; attempt += 1) {
      latest = await client.queryJob(jobId, requestOptions);
      if (mounted.current) setJob(latest);
      if (latest.status === 'succeeded' || latest.status === 'failed' || latest.status === 'cancelled') break;
      if (attempt + 1 < maxPollAttempts && pollIntervalMs > 0) await waitForPoll(pollIntervalMs);
    }
    if (!latest || (latest.status !== 'succeeded' && latest.status !== 'failed' && latest.status !== 'cancelled')) {
      throw new StaffPayoutRemediationError('STAFF_PAYOUT_JOB_TIMEOUT', 'Job 在期限內沒有 terminal 結果。', true);
    }
    if (latest.status !== 'succeeded') {
      setPreview(null); setAccepted(null); command.current = null; setNotice(terminalMessage(latest,sourceBank));
      return;
    }
    if (latest.outcome?.kind !== 'success' || latest.outcome.result_reference !== `staff_payout:${target.staffId}`) {
      throw new StaffPayoutRemediationError('STAFF_PAYOUT_JOB_RESULT_MISMATCH', 'Job 成功結果未指向同一 Staff Payables root。');
    }
    await readbackAfterSuccess();
  };

  const runApply = async (checked: StaffPayoutPreview | null = preview) => {
    const preview = checked;
    const selected = selection();
    if (!selected || !preview || (unknownOutcome && accepted !== null)) return;
    setBusy('apply'); setError(null); setNotice(null);
    const fingerprint = preview.preview_fingerprint;
    if (!command.current || command.current.fingerprint !== fingerprint) command.current = { fingerprint, value: createStaffPayoutRemediationCommand() };
    let next: StaffPayoutJobAccepted;
    try {
      next = await client.apply(preview, selected, reason, command.current.value, requestOptions);
    } catch (caught) {
      if (isUnknownApplyOutcome(caught)) {
        setUnknownOutcome(true);
        setError(displayError(caught,sourceBank));
      } else {
        setUnknownOutcome(false); setPreview(null); setJob(null); setAccepted(null); command.current = null;
        if (isStaleApplyError(caught)) {
          try {
            await loadQuery(false);
            setNotice('應付款資料已更新；請依最新餘額重新檢查核銷影響。');
          } catch (queryError) {
            setError(displayError(queryError,sourceBank));
          }
        } else {
          setError(displayError(caught,sourceBank));
        }
      }
      if (mounted.current) setBusy(null);
      return;
    }
    setAccepted(next);
    try {
      await pollToTerminal(next.job_id);
    } catch (caught) {
      setUnknownOutcome(true);
      setError(displayError(caught,sourceBank));
    } finally { if (mounted.current) setBusy(null); }
  };

  const reconcile = async () => {
    if (!accepted || busy !== null) return;
    try { await pollToTerminal(accepted.job_id); }
    catch (caught) { setUnknownOutcome(true); setError(displayError(caught,sourceBank)); }
    finally { if (mounted.current) setBusy(null); }
  };
  const continueRemaining = () => {
    if (busy !== null || unknownOutcome || job?.status !== 'succeeded' || !active) return;
    setAccepted(null); setJob(null); setPreview(null); setRowIdsText(''); setDifferenceMode(''); setReason(''); setNotice(null); setError(null); command.current = null;
  };
  useEffect(() => { onBusyChange?.(busy !== null || unknownOutcome); return () => onBusyChange?.(false); }, [busy, unknownOutcome, onBusyChange]);
  useUnsavedDraft('月嫂付款核銷', { '銀行交易資料列': rowIdsText, '核銷方式': differenceMode, '原因': reason }, { busy: busy !== null || unknownOutcome || (accepted !== null && !['succeeded', 'failed', 'cancelled'].includes(job?.status ?? '')), resetKey: busy === null && !unknownOutcome && job?.status === 'succeeded' ? job : null, save: runPreview, discard: () => { setRowIdsText(''); setDifferenceMode(''); setReason(''); invalidatePreview(); } });


  if (!query) return (
    <section className="case-accounting-card finance-advanced-reconciliation-card" aria-label="月嫂付款核銷">
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行出款與月嫂應付款對核</h3>
          <span className="finance-tag-imported">月嫂款項沖銷</span>
        </div>
        <button type="button" className="finance-btn-secondary" disabled={busy !== null} onClick={() => void retryOwnerQuery()}>
          重新讀取
        </button>
      </div>
      {busy === 'query' && <p role="status">正在讀取最新應付款資料…</p>}
      {error && <div role="alert">{error}</div>}
    </section>
  );

  return (
    <section
      className="case-accounting-card finance-advanced-reconciliation-card"
      aria-label="月嫂付款核銷"
      data-surface-id="staff-payout-remediation"
    >
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行出款與月嫂應付款對核</h3>
          <span className="finance-tag-imported">月嫂款項沖銷</span>
        </div>
        <button
          type="button"
          className="finance-btn-secondary"
          disabled={busy !== null}
          onClick={() => void retryOwnerQuery()}
        >
          重新讀取
        </button>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>💡 作用說明：</strong>銀行對帳單已辨識到本案的月嫂款項出款（如下左側）。請確認要將此筆款項<strong>沖抵哪一筆應付款項</strong>（如下右側）。核對確認後，系統將正式記錄實付並更新應付款狀態。
        <span style={{ display: 'block', marginTop: '4px', fontSize: '0.8rem', color: '#6b5f54' }}>
          <strong>解除條件：</strong>只核對既有銀行入帳資料，不會發動銀行匯款。核銷處理完成後，系統仍會重新確認此筆應付款已結清。
        </span>
      </div>

      <p style={{ display: 'none' }}>服務人員：已指定{obligation ? `｜案件 ${obligation.case_no}` : ''}</p>

      {error && <div role="alert">{error}</div>}
      {notice && <div role="status">{notice}</div>}

      <div className="finance-recon-deck">
        <div className="finance-recon-deck-grid">
          {/* 左側：銀行出款流水 */}
          <div className="finance-recon-col finance-recon-col-bank">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 1</span>
              <h4>銀行已出款項（來源流水）</h4>
            </div>
            {financeImportRowId !== undefined ? (
              <div className="finance-table-container">
                <table className="finance-table finance-recon-table">
                  <thead>
                    <tr>
                      <th>納入</th>
                      <th>銀行來源</th>
                      <th>流水編號</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="is-selected-row">
                      <td>
                        <input type="checkbox" checked disabled readOnly aria-label="納入銀行款" />
                      </td>
                      <td>
                        <span>{sourceBank === 'sinopac' ? '永豐銀行' : sourceBank === 'taishin' ? '台新銀行' : '銀行出款'}</span>
                      </td>
                      <td>
                        <small className="finance-mono-sub">bank:{financeImportRowId}</small>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ padding: '8px 0' }}>
                <label style={{ display: 'grid', gap: 4 }}>
                  <span style={{ fontSize: '0.84rem', fontWeight: 600 }}>銀行流水紀錄編號（可用逗號或空白分隔）</span>
                  <input
                    aria-label="銀行流水紀錄編號"
                    inputMode="numeric"
                    value={rowIdsText}
                    disabled={busy !== null || unknownOutcome || accepted !== null || !active}
                    onChange={(event) => { setRowIdsText(event.target.value); invalidatePreview(); }}
                    style={{ padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6 }}
                  />
                </label>
              </div>
            )}
            <div className="finance-recon-col-summary">
              <span>{financeImportRowId !== undefined ? '使用已選取的銀行流水。' : `已指定流水：${parseRowIds(rowIdsText)?.length ?? 0} 筆`}</span>
            </div>
          </div>

          {/* 中間箭頭 */}
          <div className="finance-recon-arrow-divider" aria-hidden="true">
            <span className="finance-recon-arrow-icon">➔</span>
            <small>沖抵核銷</small>
          </div>

          {/* 右側：月嫂應付款項 */}
          <div className="finance-recon-col finance-recon-col-target">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 2</span>
              <h4>預計沖抵月嫂應付款（核銷目標）</h4>
            </div>
            <div className="finance-recon-obligations-list">
              {obligations.map((obligation) => (
                <div
                  key={obligation.obligation_identity}
                  data-surface-id="staff-payout-obligation"
                  className="finance-recon-obligation-item is-selected-item"
                >
                  <input type="checkbox" checked disabled readOnly aria-label={`核銷款項 ${obligation.obligation_identity}`} />
                  <div className="finance-recon-ob-info">
                    <div className="finance-recon-ob-name">
                      <strong>案件 {obligation.case_no} 應付款</strong>
                      <small>{obligation.due_date ? `到期日：${obligation.due_date}` : '未設定到期日'} · 狀態 {payoutStatusLabel(obligation.payout_status)}</small>
                    </div>
                    <div className="finance-recon-ob-meta" style={{ display: 'grid', gap: 2, textAlign: 'right' }}>
                      <span>應付 NT$ {obligation.amount_due_ntd.toLocaleString('zh-TW')}</span>
                      <span>餘額 NT$ {obligation.balance_ntd.toLocaleString('zh-TW')}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="finance-recon-col-summary">
              <span>應付待付合計：<strong>NT$ {obligations.reduce((sum, item) => sum + item.balance_ntd, 0).toLocaleString('zh-TW')}</strong></span>
            </div>
          </div>
        </div>

        {/* 試算與決策條 */}
        <div className="finance-recon-calculation-bar">
          <fieldset
            disabled={busy !== null || unknownOutcome || accepted !== null || !active}
            style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 10 }}
          >
            <legend style={{ display: 'none' }}>既有銀行入帳資料</legend>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <label style={{ flex: 1, minWidth: 200 }}>
                <span style={{ display: 'block', fontSize: '0.84rem', fontWeight: 600, marginBottom: 4 }}>核銷方式</span>
                <select
                  aria-label="核銷方式"
                  value={differenceMode}
                  onChange={(event) => { setDifferenceMode(event.target.value as typeof differenceMode); invalidatePreview(); }}
                  style={{ width: '100%', padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6 }}
                >
                  <option value="">足額核銷剩餘款</option>
                  <option value="underpayment">付款不足，先核銷實付</option>
                  <option value="overpayment">付款超額，另列追收</option>
                </select>
              </label>
              <label style={{ flex: 2, minWidth: 260 }}>
                <span style={{ display: 'block', fontSize: '0.84rem', fontWeight: 600, marginBottom: 4 }}>人工核對理由（選填）</span>
                <textarea
                  aria-label="人工核對理由"
                  maxLength={500}
                  value={reason}
                  onChange={(event) => { setReason(event.target.value); invalidatePreview(); }}
                  placeholder="備註核對原因"
                  style={{ width: '100%', padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6, minHeight: '38px', resize: 'vertical' }}
                />
              </label>
            </div>
            <div className="finance-recon-action-row">
              <button
                type="button"
                className="finance-btn-primary finance-btn-lg"
                disabled={!selection() || busy !== null || unknownOutcome || accepted !== null}
                onClick={() => void runPreview()}
              >
                {confirmPreview ? '預覽核銷' : '儲存核銷'}
              </button>
            </div>
          </fieldset>
        </div>

        {/* 預覽與確認核銷結果 */}
        {preview && payoutCandidate && (
          <div className="finance-scope-note finance-recon-preview-box" data-surface-id="staff-payout-remediation-preview">
            <div className="finance-recon-preview-header">
              <h5>本次核銷資料</h5>
              <span>銀行總額 NT$ {payoutCandidate.bank_total.amount.toLocaleString('zh-TW')}｜應付款總額 NT$ {payoutCandidate.obligation_total.amount.toLocaleString('zh-TW')}</span>
            </div>
            {confirmPreview && preview && !accepted && !unknownOutcome && (
              <div className="finance-recon-confirm-row">
                <button
                  type="button"
                  className="finance-btn-primary finance-btn-lg"
                  disabled={busy !== null}
                  onClick={() => void runApply(preview)}
                >
                  確認核銷
                </button>
              </div>
            )}
          </div>
        )}

        {accepted && (
          <div data-surface-id="staff-payout-job" className="finance-scope-note finance-recon-preview-box">
            <p>核銷已受理，正在處理並重新確認應付款狀態。</p>
            {job && <p>處理狀態：{jobStatusLabel(job.status)}</p>}
            {(unknownOutcome || (job !== null && (job.status === 'queued' || job.status === 'running' || job.status === 'succeeded'))) && (
              <button type="button" className="finance-btn-secondary" disabled={busy !== null} onClick={() => void reconcile()}>
                重新查詢核銷結果
              </button>
            )}
          </div>
        )}

        {accepted && job?.status === 'succeeded' && !unknownOutcome && active && financeImportRowId === undefined && (
          <button type="button" className="finance-btn-primary" disabled={busy !== null} onClick={continueRemaining}>
            繼續核銷剩餘款
          </button>
        )}
        {accepted && job?.status === 'succeeded' && active && financeImportRowId !== undefined && (
          <p role="status">剩餘款繼續待付；請由補款流水接續核銷。</p>
        )}

        {unknownOutcome && !accepted && (
          <div role="alert" className="finance-scope-note" style={{ borderColor: '#dc2626' }}>
            核銷結果目前無法安全確認，禁止產生新操作。
            <button type="button" className="finance-btn-secondary" disabled={busy !== null} onClick={() => void runApply()}>
              使用原操作安全重試
            </button>
          </div>
        )}

        {!active && !accepted && (
          <div role="status" className="finance-state">
            目前應付款已非逾期待處理；系統會依最新應付款資料判斷是否解除異常。
          </div>
        )}
      </div>
    </section>
  );
};
