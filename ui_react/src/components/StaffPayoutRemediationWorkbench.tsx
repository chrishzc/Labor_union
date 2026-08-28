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
    if (error.code.includes('STALE')) return '根事實版本已變更，請重新查詢後再 Preview。';
    if (error.code === 'STAFF_PAYOUT_SCHEMA_MISMATCH') return 'PAYOUT 回應契約不完整，已停止操作。';
    return `${error.code}：${error.message}`;
  }
  return error instanceof Error ? error.message : 'PAYOUT 核銷失敗，異常仍保留。';
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
  if (job.status === 'failed') return `背景核銷失敗：${job.outcome?.kind === 'failure' ? job.outcome.error.message : '未提供錯誤原因'}；異常仍保留。`;
  if (job.status === 'cancelled') return '背景核銷已取消；異常仍保留。';
  return '背景核銷尚未完成；異常仍保留。';
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
          setNotice('fresh Staff Payables root 已確認原義務結清。');
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
      setNotice(`owner root 仍未結清（餘額 NT$ ${(current?.balance_ntd ?? 0).toLocaleString('zh-TW')}、狀態 ${current?.payout_status ?? 'unknown'}）；異常保留。`);
      return;
    }
    setNotice('owner root 已確認原逾期義務 balance=0 且 completed，異常可解除。');
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
            setNotice('Staff Payables 根事實已更新；請依最新餘額重新 Preview。');
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

  if (!query) return <section aria-label="逾期月嫂應付款人工核銷"><h3>逾期月嫂應付款人工核銷</h3>{busy === 'query' && <p role="status">正在讀取 Staff Payables 根事實…</p>}{error && <div role="alert">{error}</div>}<button type="button" disabled={busy !== null} onClick={() => void retryOwnerQuery()}>重新讀取</button></section>;

  return <section aria-label="逾期月嫂應付款人工核銷" data-surface-id="staff-payout-remediation" style={{ display: 'grid', gap: 12, border: '1px solid #dec0b6', borderRadius: 12, padding: 16, background: '#fffaf8' }}>
    <header><h3 style={{ margin: 0 }}>逾期月嫂應付款人工核銷</h3><p>Staff #{query.staff_id}｜義務 {target.obligationIdentity}｜版本 {query.staff_payables_version}</p></header>
    <p><strong>解除條件：</strong>只核銷既有 canonical Finance Import 銀行事實；不會發動銀行匯款。Job 成功不是解除條件，必須 fresh owner root 證明 balance=0 且 completed。</p>
    {obligation && <div data-surface-id="staff-payout-obligation"><strong>原逾期義務</strong><p>案件 {obligation.case_no}｜到期 {obligation.due_date ?? '未設定'}｜應付 NT$ {obligation.amount_due_ntd.toLocaleString('zh-TW')}｜餘額 NT$ {obligation.balance_ntd.toLocaleString('zh-TW')}｜狀態 {obligation.payout_status}</p></div>}
    {error && <div role="alert">{error}</div>}{notice && <div role="status">{notice}</div>}
    <fieldset disabled={busy !== null || unknownOutcome || accepted !== null || !active} style={{ display: 'grid', gap: 8 }}><legend>既有銀行事實</legend><label>Finance Import row IDs（可用逗號或空白分隔）<input aria-label="Finance Import row IDs" inputMode="numeric" value={rowIdsText} onChange={(event) => { setRowIdsText(event.target.value); invalidatePreview(); }} /></label><label>人工核對理由<textarea aria-label="人工核對理由" maxLength={500} value={reason} onChange={(event) => { setReason(event.target.value); invalidatePreview(); }} /></label><button type="button" disabled={!selection() || !reason.trim()} onClick={() => void runPreview()}>Preview 核銷（零寫入）</button></fieldset>
    {preview && payoutCandidate && <div data-surface-id="staff-payout-remediation-preview" style={{ border: '1px solid #b7d8d1', padding: 10, borderRadius: 8 }}><strong>Preview 已完成，尚未寫入</strong><p>銀行總額 NT$ {payoutCandidate.bank_total.amount.toLocaleString('zh-TW')}｜義務總額 NT$ {payoutCandidate.obligation_total.amount.toLocaleString('zh-TW')}</p><label><input type="checkbox" aria-label="確認核銷 Preview" checked={confirmed} disabled={busy !== null || accepted !== null} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對規則書、原義務與 canonical 銀行事實，確認套用。</label><button type="button" disabled={!confirmed || !reason.trim() || busy !== null || accepted !== null} onClick={() => void runApply()}>確認並 Apply</button></div>}
    {accepted && <div data-surface-id="staff-payout-job"><p>Apply 已接受，Job：{accepted.job_id}。正在等待 terminal 並重新讀取 owner root。</p>{job && <p>Job 狀態：{job.status}</p>}{(unknownOutcome || (job !== null && (job.status === 'queued' || job.status === 'running' || job.status === 'succeeded'))) && <button type="button" disabled={busy !== null} onClick={() => void reconcile()}>重新查詢原 Job／owner root</button>}</div>}
    {unknownOutcome && !accepted && <div role="alert">Apply 結果未明，禁止產生新命令。<button type="button" disabled={busy !== null} onClick={() => void runApply()}>使用原 Idempotency-Key 安全重試 Apply</button></div>}
    {!active && !accepted && <div role="status">目前義務已非逾期 active；本工作台不會以 tracking 狀態代替 root readback。</div>}
  </section>;
};
