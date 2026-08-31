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
import { StaffPayoutRemediationError } from '../api/staff_payables/staff_payout_remediation_errors';
import type { StaffPayablesQuery } from '../api/staff_payables/staff_payables_query_schemas';

export interface StaffPayoutRemediationTarget {
  staffId: number;
  obligationIdentity: string;
}

export interface StaffPayoutRemediationWorkbenchProps {
  target: StaffPayoutRemediationTarget;
  onResolved?: () => void | Promise<void>;
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

function activeObligation(query: StaffPayablesQuery | null, target: StaffPayoutRemediationTarget) {
  return query?.obligations.find((item) => item.obligation_identity === target.obligationIdentity) ?? null;
}

function displayError(error: unknown): string {
  if (error instanceof StaffPayoutRemediationError) {
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

function terminalMessage(job: StaffPayoutJob): string {
  if (job.status === 'failed') return '核銷處理未完成，異常仍會保留；請確認資料後再試。';
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
  return obligations.has(target.obligationIdentity);
}

export const StaffPayoutRemediationWorkbench: React.FC<StaffPayoutRemediationWorkbenchProps> = ({
  target,
  onResolved,
  client = staffPayoutRemediationClient,
  requestOptions = EMPTY_REQUEST_OPTIONS,
  pollIntervalMs = 500,
  maxPollAttempts = 60,
}) => {
  const [query, setQuery] = useState<StaffPayablesQuery | null>(null);
  const [rowIdsText, setRowIdsText] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<StaffPayoutPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
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
      const obligation = activeObligation(fresh, target);
      if (!obligation) throw new StaffPayoutRemediationError('STAFF_PAYOUT_OWNER_MISMATCH', 'owner Query 找不到原異常義務。');
      if (current === generation.current && mounted.current) {
        setQuery(fresh);
        if (resolveOnSettled && obligation.balance_ntd === 0 && obligation.payout_status === 'completed') {
          setNotice('已重新確認原逾期應付款結清。');
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
    setQuery(null); setPreview(null); setConfirmed(false); setJob(null); setAccepted(null);
    setRowIdsText(''); setReason(''); setError(null); setNotice(null); setUnknownOutcome(false); command.current = null;
    const current = generation.current;
    void client.query(target.staffId, requestOptions).then((fresh) => {
      const obligation = activeObligation(fresh, target);
      if (!obligation) throw new StaffPayoutRemediationError('STAFF_PAYOUT_OWNER_MISMATCH', 'owner Query 找不到原異常義務。');
      if (current === generation.current && mounted.current) { setQuery(fresh); setBusy(null); }
    }).catch((caught: unknown) => {
      if (current === generation.current && mounted.current) { setBusy(null); setError(displayError(caught)); }
    });
    return () => { generation.current += 1; };
  }, [client, requestOptions, target]);

  const invalidatePreview = () => { setPreview(null); setConfirmed(false); setNotice(null); command.current = null; };
  const obligation = activeObligation(query, target);
  const active = obligation !== null && obligation.balance_ntd > 0 && obligation.payout_status !== 'completed';
  const payoutCandidate = preview && 'allocations' in preview.candidate ? preview.candidate : null;
  const selection = (): StaffPayoutSelection | null => {
    const financeImportRowIds = parseRowIds(rowIdsText);
    if (!financeImportRowIds || !active) return null;
    return { financeImportRowIds, obligationIdentities: [target.obligationIdentity] };
  };
  const runPreview = async () => {
    const selected = selection();
    if (!selected || !query || busy !== null || unknownOutcome) return;
    setBusy('preview'); setError(null); setNotice(null); setPreview(null); setConfirmed(false);
    try {
      const value = await client.preview(selected, requestOptions);
      if (!previewMatchesTarget(value, target, query)) throw new StaffPayoutRemediationError('STAFF_PAYOUT_PREVIEW_IDENTITY_MISMATCH', 'Preview 未回傳同一 Staff 與原義務。');
      setPreview(value);
    } catch (caught) { setError(displayError(caught)); }
    finally { if (mounted.current) setBusy(null); }
  };

  const readbackAfterSuccess = async (): Promise<void> => {
    const fresh = await loadQuery(true);
    const current = activeObligation(fresh, target);
    if (!current || current.balance_ntd !== 0 || current.payout_status !== 'completed') {
      setNotice(`最新應付款仍未結清（餘額 NT$ ${(current?.balance_ntd ?? 0).toLocaleString('zh-TW')}、狀態 ${payoutStatusLabel(current?.payout_status ?? '')}）；異常仍會保留。`);
      return;
    }
    setNotice('已重新確認原逾期應付款餘額歸零且完成結清，異常可解除。');
  };

  const retryOwnerQuery = async (): Promise<void> => {
    try {
      await loadQuery(false);
    } catch (caught) {
      if (mounted.current) setError(displayError(caught));
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
      setPreview(null); setConfirmed(false); setAccepted(null); command.current = null; setNotice(terminalMessage(latest));
      return;
    }
    if (latest.outcome?.kind !== 'success' || latest.outcome.result_reference !== `staff_payout:${target.staffId}`) {
      throw new StaffPayoutRemediationError('STAFF_PAYOUT_JOB_RESULT_MISMATCH', 'Job 成功結果未指向同一 Staff Payables root。');
    }
    await readbackAfterSuccess();
  };

  const runApply = async () => {
    const selected = selection();
    if (!selected || !preview || !confirmed || !reason.trim() || busy !== null || (unknownOutcome && accepted !== null)) return;
    setBusy('apply'); setError(null); setNotice(null);
    const fingerprint = preview.preview_fingerprint;
    if (!command.current || command.current.fingerprint !== fingerprint) command.current = { fingerprint, value: createStaffPayoutRemediationCommand() };
    let next: StaffPayoutJobAccepted;
    try {
      next = await client.apply(preview, selected, reason, command.current.value, requestOptions);
    } catch (caught) {
      if (isUnknownApplyOutcome(caught)) {
        setUnknownOutcome(true);
        setError(displayError(caught));
      } else {
        setUnknownOutcome(false); setPreview(null); setConfirmed(false); setJob(null); setAccepted(null); command.current = null;
        if (isStaleApplyError(caught)) {
          try {
            await loadQuery(false);
            setNotice('應付款資料已更新；請依最新餘額重新檢查核銷影響。');
          } catch (queryError) {
            setError(displayError(queryError));
          }
        } else {
          setError(displayError(caught));
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
      setError(displayError(caught));
    } finally { if (mounted.current) setBusy(null); }
  };

  const reconcile = async () => {
    if (!accepted || busy !== null) return;
    try { await pollToTerminal(accepted.job_id); }
    catch (caught) { setUnknownOutcome(true); setError(displayError(caught)); }
    finally { if (mounted.current) setBusy(null); }
  };

  if (!query) return <section aria-label="逾期月嫂應付款人工核銷"><h3>逾期月嫂應付款人工核銷</h3>{busy === 'query' && <p role="status">正在讀取最新應付款資料…</p>}{error && <div role="alert">{error}</div>}<button type="button" disabled={busy !== null} onClick={() => void retryOwnerQuery()}>重新讀取</button></section>;

  return <section aria-label="逾期月嫂應付款人工核銷" data-surface-id="staff-payout-remediation" style={{ display: 'grid', gap: 12, border: '1px solid #dec0b6', borderRadius: 12, padding: 16, background: '#fffaf8' }}>
    <header><h3 style={{ margin: 0 }}>逾期月嫂應付款人工核銷</h3><p>服務人員：已指定{obligation ? `｜案件 ${obligation.case_no}` : ''}</p></header>
    <p><strong>解除條件：</strong>只核對既有銀行入帳資料，不會發動銀行匯款。核銷處理完成後，系統仍會重新確認此筆應付款已結清。</p>
    {obligation && <div data-surface-id="staff-payout-obligation"><strong>原逾期應付款</strong><p>到期 {obligation.due_date ?? '未設定'}｜應付 NT$ {obligation.amount_due_ntd.toLocaleString('zh-TW')}｜餘額 NT$ {obligation.balance_ntd.toLocaleString('zh-TW')}｜狀態 {payoutStatusLabel(obligation.payout_status)}</p></div>}
    {error && <div role="alert">{error}</div>}{notice && <div role="status">{notice}</div>}
    <fieldset disabled={busy !== null || unknownOutcome || accepted !== null || !active} style={{ display: 'grid', gap: 8 }}><legend>既有銀行入帳資料</legend><label>銀行流水紀錄編號（可用逗號或空白分隔）<input aria-label="銀行流水紀錄編號" inputMode="numeric" value={rowIdsText} onChange={(event) => { setRowIdsText(event.target.value); invalidatePreview(); }} /></label><label>人工核對理由<textarea aria-label="人工核對理由" maxLength={500} value={reason} onChange={(event) => { setReason(event.target.value); invalidatePreview(); }} /></label><button type="button" disabled={!selection() || !reason.trim()} onClick={() => void runPreview()}>檢查核銷影響</button></fieldset>
    {preview && payoutCandidate && <div data-surface-id="staff-payout-remediation-preview" style={{ border: '1px solid #b7d8d1', padding: 10, borderRadius: 8 }}><strong>核銷影響已確認，尚未寫入</strong><p>銀行總額 NT$ {payoutCandidate.bank_total.amount.toLocaleString('zh-TW')}｜應付款總額 NT$ {payoutCandidate.obligation_total.amount.toLocaleString('zh-TW')}</p><label><input type="checkbox" aria-label="確認核銷影響" checked={confirmed} disabled={busy !== null || accepted !== null} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對規則、原應付款與銀行入帳資料，確認套用。</label><button type="button" disabled={!confirmed || !reason.trim() || busy !== null || accepted !== null} onClick={() => void runApply()}>確認並提交核銷</button></div>}
    {accepted && <div data-surface-id="staff-payout-job"><p>核銷已受理，正在處理並重新確認應付款狀態。</p>{job && <p>處理狀態：{jobStatusLabel(job.status)}</p>}{(unknownOutcome || (job !== null && (job.status === 'queued' || job.status === 'running' || job.status === 'succeeded'))) && <button type="button" disabled={busy !== null} onClick={() => void reconcile()}>重新查詢核銷結果</button>}</div>}
    {unknownOutcome && !accepted && <div role="alert">核銷結果目前無法安全確認，禁止產生新操作。<button type="button" disabled={busy !== null} onClick={() => void runApply()}>使用原操作安全重試</button></div>}
    {!active && !accepted && <div role="status">目前應付款已非逾期待處理；系統會依最新應付款資料判斷是否解除異常。</div>}
  </section>;
};
