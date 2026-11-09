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
import type { FinanceBankTransaction } from '../api/finance_import/finance_import_query_schemas';

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
  bankSource?: Pick<FinanceBankTransaction, 'transaction_date' | 'amount_ntd' | 'reference' | 'counterparty_name'>;
  requiresFundingSplit?: boolean;
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
  bankSource,
  requiresFundingSplit = false,
  confirmPreview = false,
  onBusyChange,
  client = staffPayoutRemediationClient,
  requestOptions = EMPTY_REQUEST_OPTIONS,
  pollIntervalMs = 500,
  maxPollAttempts = 60,
}) => {
  const [query, setQuery] = useState<StaffPayablesQuery | null>(null);
  const [rowIdsText, setRowIdsText] = useState('');
  const [differenceMode, setDifferenceMode] = useState<'' | 'underpayment' | 'overpayment' | 'subsidy_split'>('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<StaffPayoutPreview | null>(null);
  const [previewRemainingBefore, setPreviewRemainingBefore] = useState(0);
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
  const remainingTotal = obligations.reduce((sum, item) => sum + item.balance_ntd, 0);
  const needsConfirmation = confirmPreview || differenceMode === 'subsidy_split';
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
      if (selected.differenceMode === 'subsidy_split' && !value.subsidy_split) throw new StaffPayoutRemediationError('STAFF_PAYOUT_SCHEMA_MISMATCH', '方案一預覽缺少正式補助分配。');
      if (!previewMatchesTarget(value, target, query)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_PREVIEW_IDENTITY_MISMATCH', 'Preview 未回傳同一 Staff 與原義務。');
      setPreviewRemainingBefore(remainingTotal);
      setPreview(value);
      if (!needsConfirmation) await runApply(value);
    } catch (caught) { setError(displayError(caught,sourceBank)); }
    finally { if (mounted.current) setBusy(null); }
  };

  const readbackAfterSuccess = async (): Promise<void> => {
    const fresh = await loadQuery(true);
    onPosted?.();
    const current = activeObligations(fresh, target);
    if (!targetSettled(fresh, target)) {
      if (differenceMode === 'subsidy_split') {
        const subsidy = current.flatMap(item => item.funding_portions ?? []).find(p => p.funding_kind === 'subsidy');
        setNotice(`補助方案一已保存，自備款已核銷；剩餘補助待付 NT$ ${subsidy?.remaining_ntd?.toLocaleString('zh-TW') ?? '待確認'}，待台新補助款核銷後結清。`);
        return;
      }
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
          <strong>核銷結果：</strong>只核對既有銀行出款資料，不會發動銀行匯款。完成後重新讀取待付餘額；方案一依自備款、補助款分別核銷，兩部分清償後才整筆結清。
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
              <div className="finance-recon-obligation-item is-selected-item" aria-label="銀行出款明細">
                <input type="checkbox" checked disabled readOnly aria-label="納入銀行款" />
                <div className="finance-recon-ob-info">
                  <div className="finance-recon-ob-name">
                    <strong>{sourceBank === 'sinopac' ? '永豐銀行' : sourceBank === 'taishin' ? '台新銀行' : '銀行出款'}</strong>
                    <small>交易日：{bankSource?.transaction_date ?? '未提供'}</small>
                    <small>收款對象：{bankSource?.counterparty_name ?? '未提供'}</small>
                    <small style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>交易摘要：{bankSource?.reference || '未提供'}</small>
                    <strong>銀行實付：{bankSource ? `NT$ ${bankSource.amount_ntd.toLocaleString('zh-TW')}` : '待確認'}</strong>
                  </div>
                </div>
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
              <span>{financeImportRowId !== undefined && bankSource ? `銀行實付合計：NT$ ${bankSource.amount_ntd.toLocaleString('zh-TW')}` : `已指定流水：${parseRowIds(rowIdsText)?.length ?? 0} 筆`}</span>
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
                      {obligation.funding_portions?.map(portion => <small key={portion.funding_kind}>
                        {portion.funding_kind === 'client' ? '自備款（永豐）' : '補助款（台新）'}：應付 NT$ {portion.amount_ntd.toLocaleString('zh-TW')} · 待付 NT$ {(portion.remaining_ntd === null ? '待確認' : portion.remaining_ntd.toLocaleString('zh-TW'))} · {portion.due_date ?? '未設定撥款日'}
                      </small>)}
                      {!!obligation.funding_portions?.length && <small>方案一分別核銷：永豐核銷自備款，剩餘補助由台新轉付；兩部分完成後才結清。</small>}
                      {!obligation.funding_portions?.length && sourceBank === 'sinopac' && <small>若本案為補助方案一，可在下方核銷方式選擇「補助方案一：核銷自備款，補助款保留待付」預覽確認。</small>}
                      {requiresFundingSplit && !obligation.funding_portions?.length && sourceBank !== 'sinopac' && <small>補助分配待確認，請先由原永豐自備款核對或案件帳務確認來源。</small>}
                    </div>
                    <div className="finance-recon-ob-meta" style={{ display: 'grid', gap: 2 }}>
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
                  <option value="">足額核銷本次款項（含 100 元內手續費）</option>
                  <option value="underpayment">付款不足，先核銷實付</option>
                  <option value="overpayment">付款超額，另列追收</option>
                  {sourceBank === 'sinopac' && <option value="subsidy_split">補助方案一：核銷自備款，補助款保留待付</option>}
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
            <p>內扣手續費：待預覽確認。符合條件的 0～100 元差額由收款方負擔；補助待付款另列，不列為手續費。</p>
            {differenceMode === 'subsidy_split' && <p>確認後會一併保存補助方案一、核銷本次自備款，並保留補助待付；請先預覽本案正式金額。</p>}
            <div className="finance-recon-action-row">
              <button
                type="button"
                className="finance-btn-primary finance-btn-lg"
                disabled={!selection() || busy !== null || unknownOutcome || accepted !== null}
                onClick={() => void runPreview()}
              >
                {needsConfirmation ? '預覽核銷' : '儲存核銷'}
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
            <p>內扣手續費：{payoutCandidate.transfer_fee ? `NT$ ${payoutCandidate.transfer_fee.amount.toLocaleString('zh-TW')}` : '未提供，待確認'}</p>
            {preview.subsidy_split && <div aria-label="補助方案一核銷預覽">
              <p>月嫂總應付：NT$ {preview.subsidy_split.total_ntd.toLocaleString('zh-TW')}</p>
              <p>正式補助款：NT$ {preview.subsidy_split.subsidy_ntd.toLocaleString('zh-TW')}</p>
              <p>本次自備款待付：NT$ {preview.subsidy_split.client_remaining_ntd.toLocaleString('zh-TW')} · 撥款日 {preview.subsidy_split.client_due_date ?? '未設定'}</p>
              <p>補助款保留待付：NT$ {preview.subsidy_split.subsidy_remaining_ntd.toLocaleString('zh-TW')} · 撥款日 {preview.subsidy_split.subsidy_due_date ?? '未設定'}</p>
              <p>確認時一併保存補助方案一，補助款後續由台新轉付月嫂。</p>
            </div>}
            <p>核銷後剩餘待付：NT$ {Math.max(0, previewRemainingBefore - payoutCandidate.allocations.reduce((sum, item) => sum + item.amount.amount, 0)).toLocaleString('zh-TW')}</p>
            {sourceBank === 'sinopac' && obligations.some(item => item.funding_portions?.some(p => p.funding_kind === 'subsidy' && p.remaining_ntd !== null && p.remaining_ntd > 0)) &&
              <p>剩餘補助待付：NT$ {obligations.reduce((sum, item) => sum + (item.funding_portions?.filter(p => p.funding_kind === 'subsidy').reduce((total, p) => total + (p.remaining_ntd ?? 0), 0) ?? 0), 0).toLocaleString('zh-TW')}，由方案一補助款經台新轉付，本次不結清補助部分。</p>}
            {needsConfirmation && preview && !accepted && !unknownOutcome && (
              <div className="finance-recon-confirm-row">
                <button
                  type="button"
                  className="finance-btn-primary finance-btn-lg"
                  disabled={busy !== null}
                  onClick={() => void runApply(preview)}
                >
                  {preview.subsidy_split ? '確認方案一並核銷' : '確認核銷'}
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
            所選應付款目前已無待付餘額，請核對已核銷紀錄。
          </div>
        )}
      </div>
    </section>
  );
};
