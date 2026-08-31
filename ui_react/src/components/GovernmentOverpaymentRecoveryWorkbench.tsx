/**
 * File: GovernmentOverpaymentRecoveryWorkbench.tsx
 * Description: GOVSUB-006 的 bounded Query／Preview／Confirm／Apply／owner readback 工作區。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import type { AnomalyDetailView } from '../api/anomalies/anomaly_detail_schemas';
import {
  governmentOverpaymentRecoveryClient,
  GovernmentOverpaymentRecoveryError,
  type GovernmentOverpaymentRecoveryOptions,
} from '../api/government_subsidy/government_overpayment_recovery_client';
import type {
  GovernmentOverpaymentDisposition,
  GovernmentOverpaymentDispositionPreviewRequest,
  GovernmentOverpaymentPreview,
  GovernmentOverpaymentQuery,
  GovernmentOverpaymentReceipt,
} from '../api/government_subsidy/government_overpayment_recovery_schemas';

interface Props {
  overpaymentIdentity: string;
  anomalyFingerprint: string;
  onResolved?: (fingerprint: string) => GovernmentOverpaymentRefreshResult | Promise<GovernmentOverpaymentRefreshResult>;
  client?: typeof governmentOverpaymentRecoveryClient;
  anomalyClient?: Pick<typeof anomalyDetailClient, 'queryAnomalyDetail'>;
  requestOptions?: GovernmentOverpaymentRecoveryOptions;
}

export interface GovernmentOverpaymentRefreshResult {
  succeeded: boolean;
  originalFingerprintPresent: boolean;
}

type WorkStatus = 'loading' | 'ready' | 'previewing' | 'applying' | 'failed' | 'completed';
type TargetAmounts = Record<number, string>;

function errorMessage(error: unknown): string {
  const typed = error instanceof GovernmentOverpaymentRecoveryError ? error : null;
  const code = typed?.code.toUpperCase() ?? '';
  if (typed?.status === 401 || code.includes('UNAUTHENTICATED')) return '登入狀態已失效，請重新登入後再操作。';
  if (typed?.status === 403 || code.includes('FORBIDDEN')) return '目前帳號沒有處理政府溢撥的權限。';
  if (typed?.status === 404 || code.includes('NOT_FOUND')) return '找不到這筆政府溢撥資料，請返回清單重新查詢。';
  if (typed?.status === 409 || /(stale|conflict|version)/i.test(code)) return '資料已變更，請重新查詢並再次檢查處置影響。';
  if (typed?.status === 422 || code.includes('INVALID') || code.includes('BLOCK')) return '所選處置未通過檢核，請依畫面提示調整後再試。';
  if (typed?.retryable) return '結果尚未確認；請先重新查詢，再安全確認原操作。';
  return '政府溢撥目前無法處理，請稍後再試。';
}

function statusLabel(status: GovernmentOverpaymentQuery['status']): string {
  return ({
    pending_review: '待人工判定',
    offset_reserved: '抵扣處理中',
    offset_applied: '抵扣已完成',
    return_payable: '已建立政府退還款',
    partially_returned: '政府退還款部分完成',
    returned: '政府退還款已完成',
  })[status];
}

function dispositionLabel(disposition: GovernmentOverpaymentDisposition): string {
  return disposition === 'offset' ? '抵扣合法補助標的' : '建立政府退還款';
}

function blockerLabel(blocker: string): string {
  return blocker === 'government_subsidy_recipient_account_missing'
    ? '政府退款帳戶尚未準備完成'
    : '必要資料尚未準備完成';
}

function applyOutcomeUnknown(error: unknown): boolean {
  return error instanceof GovernmentOverpaymentRecoveryError
    && ['GOVERNMENT_OVERPAYMENT_TIMEOUT', 'GOVERNMENT_OVERPAYMENT_NETWORK', 'GOVERNMENT_OVERPAYMENT_ABORTED', 'GOVERNMENT_OVERPAYMENT_UNKNOWN'].includes(error.code);
}

function staleApplyOutcome(error: unknown): boolean {
  return error instanceof GovernmentOverpaymentRecoveryError
    && /(stale|conflict|version)/i.test(error.code);
}

function terminalPredicate(query: GovernmentOverpaymentQuery): boolean {
  return query.status !== 'pending_review';
}

function anomalyPredicateCleared(detail: AnomalyDetailView, fingerprint: string): boolean {
  return detail.summary.fingerprint === fingerprint
    && detail.summary.definition_code === 'GOVSUB-006'
    && detail.summary.predicate_active === false;
}

export const GovernmentOverpaymentRecoveryWorkbench: React.FC<Props> = ({
  overpaymentIdentity,
  anomalyFingerprint,
  onResolved,
  client = governmentOverpaymentRecoveryClient,
  anomalyClient = anomalyDetailClient,
  requestOptions = {},
}) => {
  const [query, setQuery] = useState<GovernmentOverpaymentQuery | null>(null);
  const [disposition, setDisposition] = useState<GovernmentOverpaymentDisposition>('offset');
  const [targetAmounts, setTargetAmounts] = useState<TargetAmounts>({});
  const [dueDate, setDueDate] = useState('');
  const [reason, setReason] = useState('');
  const [evidence, setEvidence] = useState('');
  const [preview, setPreview] = useState<GovernmentOverpaymentPreview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [receipt, setReceipt] = useState<GovernmentOverpaymentReceipt | null>(null);
  const [readback, setReadback] = useState<GovernmentOverpaymentQuery | null>(null);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [readbackUnavailable, setReadbackUnavailable] = useState(false);
  const [needsRecheck, setNeedsRecheck] = useState(false);
  const [staleOwnerRefreshRequired, setStaleOwnerRefreshRequired] = useState(false);
  const [completionVerified, setCompletionVerified] = useState(false);
  const [status, setStatus] = useState<WorkStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const idempotencyKeys = useRef(new Map<string, string>());

  const reload = async () => {
    setStatus('loading');
    setError(null);
    setPreview(null);
    setConfirmed(false);
    setReceipt(null);
    setReadback(null);
    setOutcomeUnknown(false);
    setReadbackUnavailable(false);
    setNeedsRecheck(false);
    setStaleOwnerRefreshRequired(false);
    setCompletionVerified(false);
    try {
      const result = await client.query(overpaymentIdentity, requestOptions);
      setQuery(result);
      setStatus('ready');
    } catch (caught) {
      setQuery(null);
      setStatus('failed');
      setError(errorMessage(caught));
    }
  };

  useEffect(() => {
    void reload();
    // The owner identity is the only query key; options are request-scoped inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overpaymentIdentity]);

  const targets = useMemo(() => {
    if (!query) return [];
    return query.offset_targets
      .map((target) => ({
        claim_item_id: target.claim_item_id,
        amount_ntd: Number(targetAmounts[target.claim_item_id] ?? 0),
      }))
      .filter((target) => Number.isInteger(target.amount_ntd) && target.amount_ntd > 0);
  }, [query, targetAmounts]);

  const request = useMemo<GovernmentOverpaymentDispositionPreviewRequest | null>(() => {
    if (!query || !evidence.trim()) return null;
    if (disposition === 'offset') {
      if (!targets.length) return null;
      return {
        overpayment_identity: query.overpayment_identity,
        disposition,
        targets,
        due_date: null,
        evidence_reference: evidence.trim(),
      };
    }
    if (!dueDate) return null;
    return {
      overpayment_identity: query.overpayment_identity,
      disposition,
      targets: [],
      due_date: dueDate,
      evidence_reference: evidence.trim(),
    };
  }, [query, disposition, targets, dueDate, evidence]);

  const updateInput = <T,>(setter: React.Dispatch<React.SetStateAction<T>>, value: T) => {
    setter(value);
    setPreview(null);
    setConfirmed(false);
    setReceipt(null);
    setReadback(null);
    setOutcomeUnknown(false);
    setReadbackUnavailable(false);
    setNeedsRecheck(false);
  };

  const previewDisposition = async () => {
    if (!request || !query) return;
    setStatus('previewing');
    setError(null);
    setPreview(null);
    setConfirmed(false);
    try {
      const result = await client.preview(request, requestOptions);
      if (result.overpayment_version !== query.overpayment_version) throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_PREVIEW_VERSION_MISMATCH', 'Preview 版本與 Query 不一致。');
      setPreview(result);
      setStatus('ready');
    } catch (caught) {
      setStatus('failed');
      setError(errorMessage(caught));
    }
  };

  const observeCompletion = async (ownerQuery?: GovernmentOverpaymentQuery): Promise<boolean> => {
    const freshOwner = ownerQuery ?? await client.query(overpaymentIdentity, requestOptions);
    if (freshOwner.overpayment_identity !== overpaymentIdentity) {
      throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_IDENTITY_MISMATCH', 'owner readback identity 與原命令不一致。');
    }
    setReadback(freshOwner);
    setQuery(freshOwner);
    if (!terminalPredicate(freshOwner)) {
      setCompletionVerified(false);
      setNeedsRecheck(true);
      setStatus('ready');
      return false;
    }

    if (!/^[0-9a-f]{64}$/.test(anomalyFingerprint)) {
      throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_ANOMALY_FINGERPRINT_INVALID', '缺少原異常 exact fingerprint，無法確認解除。');
    }
    const anomaly = await anomalyClient.queryAnomalyDetail({ fingerprint: anomalyFingerprint });
    if (!anomalyPredicateCleared(anomaly, anomalyFingerprint)) {
      setCompletionVerified(false);
      setNeedsRecheck(true);
      setStatus('ready');
      setError('政府溢撥已完成處置，但最新問題清單尚未確認解除；提醒仍保留。');
      return false;
    }

    // The active list is the final visible surface. Do not mark this workbench
    // completed until its owner has successfully asked the page to refresh it.
    const refresh = await onResolved?.(anomalyFingerprint);
    if (!refresh || !refresh.succeeded || refresh.originalFingerprintPresent) {
      setCompletionVerified(false);
      setNeedsRecheck(true);
      setStatus('ready');
      setError(refresh?.originalFingerprintPresent
        ? '處置資料已更新，但最新問題清單仍包含這筆提醒；提醒仍保留。'
        : '處置資料已更新，但最新問題清單查詢未成功；提醒仍保留。');
      return false;
    }
    setCompletionVerified(true);
    setNeedsRecheck(false);
    setStatus('completed');
    return true;
  };

  const applyDisposition = async () => {
    if (!request || !preview || !confirmed || !reason.trim() || !query) return;
    setStatus('applying');
    setError(null);
    const identity = JSON.stringify({ ...request, reason: reason.trim(), preview: preview.preview_fingerprint });
    const idempotencyKey = idempotencyKeys.current.get(identity) ?? `ui-government-overpayment-${crypto.randomUUID()}`;
    idempotencyKeys.current.set(identity, idempotencyKey);
    let applyReceiptReceived = false;
    try {
      const result = await client.apply({
        ...request,
        expected_overpayment_version: preview.overpayment_version,
        preview_fingerprint: preview.preview_fingerprint,
        reason: reason.trim(),
      }, {
        ...requestOptions,
        idempotencyKey,
        correlationId: `government-overpayment-apply-${crypto.randomUUID()}`,
      });
      setReceipt(result);
      applyReceiptReceived = true;
      setOutcomeUnknown(false);
      setReadbackUnavailable(false);
      await observeCompletion();
    } catch (caught) {
      if (staleApplyOutcome(caught)) {
        setPreview(null);
        setConfirmed(false);
        setReceipt(null);
        setOutcomeUnknown(false);
        setReadbackUnavailable(false);
        setNeedsRecheck(false);
        setCompletionVerified(false);
        setStaleOwnerRefreshRequired(true);
        setError('資料已變更；正在重新查詢最新資料，請重新檢查處置影響。');
        try {
          const freshOwner = await client.query(overpaymentIdentity, requestOptions);
          if (freshOwner.overpayment_identity !== overpaymentIdentity) {
            throw new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_IDENTITY_MISMATCH', 'owner readback identity 與原命令不一致。');
          }
          setQuery(freshOwner);
          setReadback(freshOwner);
          setStaleOwnerRefreshRequired(false);
          setStatus('ready');
          setError('資料已更新；舊 Preview 已清除，請重新檢查處置影響後再套用。');
        } catch (readbackError) {
          setStatus('failed');
          setError(`資料已更新，但最新資料查詢失敗；請重新查詢後再檢查處置影響。${errorMessage(readbackError)}`);
        }
        return;
      }
      setStatus('failed');
      setOutcomeUnknown(!applyReceiptReceived && applyOutcomeUnknown(caught));
      setReadbackUnavailable(applyReceiptReceived);
      setError(errorMessage(caught));
    }
  };

  const reconcileOutcome = async () => {
    if ((!outcomeUnknown && !readbackUnavailable && !needsRecheck) || !query) return;
    setStatus('applying');
    setError(null);
    try {
      const completed = await observeCompletion();
      if (completed) {
        setOutcomeUnknown(false);
        setReadbackUnavailable(false);
        setNeedsRecheck(false);
      } else if (receipt) {
        setOutcomeUnknown(false);
        setReadbackUnavailable(false);
        setNeedsRecheck(true);
      } else {
        // A timeout with a still-pending owner root remains unresolved. Keep
        // the reconcile affordance, but never call Apply again.
        setOutcomeUnknown(true);
      }
    } catch (caught) {
      setStatus('failed');
      setOutcomeUnknown(!receipt);
      setReadbackUnavailable(Boolean(receipt));
      setError(errorMessage(caught));
    }
  };

  const canOffset = query?.available_actions.includes('offset') ?? false;
  const canReturn = (query?.available_actions.includes('return') && query.return_recipient.ready) ?? false;
  const busy = status === 'loading' || status === 'previewing' || status === 'applying';
  const commandLocked = receipt !== null || outcomeUnknown || readbackUnavailable || needsRecheck || completionVerified || staleOwnerRefreshRequired;
  const effectiveReadback = readback ?? query;

  if (status === 'loading' && !query) return <section aria-label="政府溢撥處置" data-surface-id="government-overpayment-recovery-loading">正在讀取政府溢撥資料…</section>;
  if (!query) return <section aria-label="政府溢撥處置" data-surface-id="government-overpayment-recovery-error"><div role="alert">{error ?? '政府溢撥資料無法讀取。'}</div><button type="button" onClick={() => void reload()}>重新查詢</button></section>;

  return (
    <section aria-label="政府溢撥人工處置" data-surface-id="government-overpayment-recovery-workbench" style={{ border: '1px solid #fed7aa', borderRadius: 12, padding: 16, marginTop: 12 }}>
      <h3 style={{ marginTop: 0 }}>政府溢撥人工處置</h3>
      <div data-surface-id="government-overpayment-recovery-root-evidence">
        <div>目前狀態：<strong>{statusLabel(query.status)}</strong></div>
        <div>目前剩餘：<strong>{query.remaining_amount_ntd.toLocaleString('zh-TW')} 元</strong></div>
        <details><summary>技術詳情與資料來源</summary><div>資料版本：{query.overpayment_version}</div><div>來源：{query.source_bank_fact_reference}／{query.source_transaction_reference}</div></details>
        {query.blockers.length > 0 && <div role="alert">阻擋原因：{query.blockers.map(blockerLabel).join('、')}</div>}
      </div>

      {status === 'completed' && completionVerified ? (
        <div role="status" style={{ color: '#166534', fontWeight: 700, marginTop: 12 }}>處置已完成，重新查詢也確認這筆提醒已從最新問題清單解除。</div>
      ) : terminalPredicate(query) && !receipt ? (
        <div role="status" style={{ color: '#166534', fontWeight: 700, marginTop: 12 }}>政府溢撥已離開待人工判定狀態，最新資料已重新查詢確認。</div>
      ) : (
        <>
          <fieldset disabled={busy || commandLocked} style={{ border: 0, padding: 0, margin: '14px 0' }}>
            <legend>選擇合法處置</legend>
            <label><input type="radio" name={`government-overpayment-disposition-${query.overpayment_identity}`} checked={disposition === 'offset'} disabled={!canOffset} onChange={() => updateInput<GovernmentOverpaymentDisposition>(setDisposition, 'offset')} /> 抵扣已核准且仍有 outstanding 的補助標的</label>
            <label style={{ marginLeft: 16 }}><input type="radio" name={`government-overpayment-disposition-${query.overpayment_identity}`} checked={disposition === 'return'} disabled={!canReturn} onChange={() => updateInput<GovernmentOverpaymentDisposition>(setDisposition, 'return')} /> 建立退還政府應付</label>
          </fieldset>

          {disposition === 'offset' && canOffset && <div>
            <div style={{ fontWeight: 700 }}>可抵扣的已核准補助標的</div>
            {query.offset_targets.length === 0 ? <div role="alert">目前沒有合法抵扣標的，不能猜測未來案件。</div> : query.offset_targets.map((target) => (
              <label key={target.claim_item_id} style={{ display: 'block', marginTop: 8 }}>
                {target.claim_item_id}／批次 {target.claim_batch_id}（最多 {target.outstanding_amount_ntd.toLocaleString('zh-TW')} 元）
                <input aria-label={`抵扣標的 ${target.claim_item_id} 金額`} type="number" min="1" max={target.outstanding_amount_ntd} step="1" value={targetAmounts[target.claim_item_id] ?? ''} disabled={busy || commandLocked} onChange={(event) => updateInput(setTargetAmounts, { ...targetAmounts, [target.claim_item_id]: event.target.value })} />
              </label>
            ))}
          </div>}

          {disposition === 'return' && canReturn && <label style={{ display: 'block', marginTop: 12 }}>退款應付日期
            <input aria-label="退款應付日期" type="date" value={dueDate} disabled={busy || commandLocked} onChange={(event) => updateInput(setDueDate, event.target.value)} />
            {!query.return_recipient.ready && <div role="alert">退款對象不可用：{query.return_recipient.blockers.join('、') || '政府退款帳戶未準備完成。'}</div>}
            {query.return_recipient.ready && <div>退款對象：{query.return_recipient.agency_name}／{query.return_recipient.bank_code}／{query.return_recipient.account_display}</div>}
          </label>}

          <label style={{ display: 'block', marginTop: 12 }}>處置證據（獨立欄位）
            <input aria-label="處置證據" type="text" maxLength={500} value={evidence} disabled={busy || commandLocked} onChange={(event) => updateInput(setEvidence, event.target.value)} />
          </label>
          <label style={{ display: 'block', marginTop: 8 }}>人工處置原因
            <textarea aria-label="人工處置原因" rows={2} maxLength={500} value={reason} disabled={busy || commandLocked} onChange={(event) => updateInput(setReason, event.target.value)} />
          </label>
          <button type="button" style={{ marginTop: 12 }} disabled={!request || !reason.trim() || busy || commandLocked} onClick={() => void previewDisposition()}>{status === 'previewing' ? '正在檢查處置影響…' : '檢查處置影響'}</button>

          {preview && <div style={{ background: '#fff7ed', borderRadius: 8, padding: 12, marginTop: 12 }} data-surface-id="government-overpayment-recovery-preview">
            <div>預計處置：{dispositionLabel(preview.disposition_kind)}，{preview.disposition_amount_ntd.toLocaleString('zh-TW')} 元</div>
            <div>套用後狀態：{statusLabel(preview.resulting_status)}；剩餘 {preview.remaining_after_ntd.toLocaleString('zh-TW')} 元</div>
            <label style={{ display: 'block', marginTop: 8 }}><input type="checkbox" checked={confirmed} disabled={busy || commandLocked} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對目前金額、合法標的、證據與預覽結果，確認執行此處置。</label>
            <button type="button" style={{ marginTop: 8 }} disabled={!confirmed || !reason.trim() || busy || commandLocked} onClick={() => void applyDisposition()}>{status === 'applying' ? '處置套用中…' : '確認套用處置'}</button>
          </div>}
        </>
      )}

      {receipt && <div data-surface-id="government-overpayment-recovery-receipt" style={{ marginTop: 12 }}>處置已受理，正在重新查詢最新資料與問題清單。</div>}
      {outcomeUnknown && <div role="alert" style={{ marginTop: 12 }}>套用結果尚未確認；原操作已保留，系統只會重新查詢，不會再次送出處置。<button type="button" disabled={busy} onClick={() => void reconcileOutcome()}>重新查詢並安全確認結果</button></div>}
      {readbackUnavailable && <div role="alert" style={{ marginTop: 12 }}>處置已受理，但最新資料或問題清單暫時無法確認；提醒仍保留。<button type="button" disabled={busy} onClick={() => void reconcileOutcome()}>重新查詢結果</button></div>}
      {staleOwnerRefreshRequired && <div role="alert" style={{ marginTop: 12 }}>資料版本已更新；舊預覽已清除，請取得最新資料後重新檢查處置影響。<button type="button" disabled={busy} onClick={() => void reload()}>重新查詢最新資料</button></div>}
      {needsRecheck && !outcomeUnknown && !readbackUnavailable && !completionVerified && <div role="alert" style={{ marginTop: 12 }}>處置已受理，但最新資料與問題清單尚未完成雙重確認；提醒仍保留。<button type="button" disabled={busy} onClick={() => void reconcileOutcome()}>重新查詢結果</button></div>}
      {effectiveReadback && receipt && <div role="status" data-surface-id="government-overpayment-recovery-readback" style={{ marginTop: 8, color: completionVerified ? '#166534' : '#92400e', fontWeight: 700 }}>
        最新狀態：{statusLabel(effectiveReadback.status)}；剩餘 {effectiveReadback.remaining_amount_ntd.toLocaleString('zh-TW')} 元。{completionVerified ? '最新問題清單已確認解除這筆提醒。' : '最新資料與問題清單尚未完成雙重確認，提醒保留。'}
      </div>}
      {error && <div role="alert" style={{ color: '#b91c1c', marginTop: 8 }}>{error}</div>}
    </section>
  );
};
