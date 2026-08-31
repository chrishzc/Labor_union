/**
 * File: ClientOverRefundRecoveryWorkbench.tsx
 * Description: 客戶退款超額追償的 bounded owner workbench；只以 Query／Preview／Apply 與 root readback 決定畫面。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  clientOverRefundRecoveryClient,
  type ClientOverRefundRecoveryClient,
} from '../api/client_finance/client_over_refund_recovery_client';
import {
  mapClientOverRefundRecoveryError,
} from '../api/client_finance/client_over_refund_recovery_errors';
import type {
  ClientOverRefundRecoveryAdjustmentPreview,
  ClientOverRefundRecoveryMatchedPreviewRequest,
  ClientOverRefundRecoveryMatchingPreview,
  ClientOverRefundRecoveryMatchingPreviewRequest,
  ClientOverRefundRecoveryPreview,
  ClientOverRefundRecoveryQuery,
  ClientOverRefundRecoveryReceipt,
} from '../api/client_finance/client_over_refund_recovery_schemas';

export interface ClientOverRefundRecoveryWorkbenchProps {
  caseNo: string;
  recoveryIdentity: string;
  /** Optional owner-provided target; it is never inferred from an anomaly snapshot. */
  initialFinanceImportRowId?: number;
  client?: ClientOverRefundRecoveryClient;
  onCommitted?: (query: ClientOverRefundRecoveryQuery) => void;
}

type Action = 'matching' | 'collection' | 'adjustment';
type Preview = ClientOverRefundRecoveryMatchingPreview | ClientOverRefundRecoveryPreview | ClientOverRefundRecoveryAdjustmentPreview;

function commandId(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return `${prefix}-${globalThis.crypto.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
function displayError(error: unknown): string {
  const typed = mapClientOverRefundRecoveryError(error);
  if (typed.code === 'CLIENT_RECOVERY_TIMEOUT' || typed.retryable) return '結果尚未確認；系統正在重新讀取最新追償資料，請勿重複送出。';
  if (typed.code === 'client_finance_candidate_stale' || typed.code === 'client_over_refund_recovery_candidate_stale') return '追償資料已變更，請重新查詢並檢查處理影響。';
  return '客戶追償目前無法完成，異常仍會保留；請確認資料後再試。';
}
function terminal(query: ClientOverRefundRecoveryQuery): boolean {
  return query.remaining_amount_ntd === 0 && (query.status === 'recovered' || query.status === 'adjusted');
}
function recoveryStatusLabel(status: ClientOverRefundRecoveryQuery['status']): string {
  const labels: Record<ClientOverRefundRecoveryQuery['status'], string> = {
    open: '待處理',
    partially_recovered: '部分收回',
    recovered: '已收回',
    adjusted: '已完成授權調整',
  };
  return labels[status];
}

export const ClientOverRefundRecoveryWorkbench: React.FC<ClientOverRefundRecoveryWorkbenchProps> = ({
  caseNo,
  recoveryIdentity,
  initialFinanceImportRowId,
  client = clientOverRefundRecoveryClient,
  onCommitted,
}) => {
  const [query, setQuery] = useState<ClientOverRefundRecoveryQuery | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<Action>('matching');
  const [rowId, setRowId] = useState(initialFinanceImportRowId ? String(initialFinanceImportRowId) : '');
  const [matchingIdentity, setMatchingIdentity] = useState('');
  const [matchingVersion, setMatchingVersion] = useState('');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [evidence, setEvidence] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requestSequence = useRef(0);
  const onCommittedRef = useRef(onCommitted);
  const applyCommand = useRef<{ previewFingerprint: string; idempotencyKey: string; correlationId: string } | null>(null);

  useEffect(() => { onCommittedRef.current = onCommitted; }, [onCommitted]);

  const readOwner = useCallback(async (): Promise<ClientOverRefundRecoveryQuery | null> => {
    const sequence = ++requestSequence.current;
    setLoading(true); setQueryError(null);
    try {
      const next = await client.query(caseNo, recoveryIdentity);
      if (sequence !== requestSequence.current) return null;
      setQuery(next); onCommittedRef.current?.(next); return next;
    } catch (caught) {
      if (sequence === requestSequence.current) setQueryError(displayError(caught));
      return null;
    } finally { if (sequence === requestSequence.current) setLoading(false); }
  }, [caseNo, client, recoveryIdentity]);

  useEffect(() => { void readOwner(); return () => { requestSequence.current += 1; }; }, [readOwner]);
  useEffect(() => {
    const first = query?.current_matchings[0];
    if (query && first) {
      setAction('collection');
      setMatchingIdentity(first.matching_identity);
      setMatchingVersion(String(first.matching_version));
    } else if (query) setAction('matching');
  }, [query]);

  const key = useMemo(() => JSON.stringify({ action, rowId, matchingIdentity, matchingVersion, amount, reason, evidence, recoveryVersion: query?.recovery_version, accountVersion: query?.account_version }), [action, rowId, matchingIdentity, matchingVersion, amount, reason, evidence, query?.recovery_version, query?.account_version]);
  const previewCurrent = preview !== null && previewKey === key;
  const rowNumber = Number(rowId);
  const amountNumber = Number(amount);
  const validRow = Number.isInteger(rowNumber) && rowNumber > 0;
  const validAmount = Number.isInteger(amountNumber) && amountNumber > 0;
  const canPreview = !busy && !!query && !terminal(query) && !!reason.trim() && !!evidence.trim() && (action === 'adjustment' ? validAmount : validRow) && (action !== 'collection' || (!!matchingIdentity.trim() && Number.isInteger(Number(matchingVersion)) && Number(matchingVersion) > 0));

  const previewAction = async () => {
    if (!canPreview || !query) return;
    setBusy(true); setError(null); setNotice(null); setPreview(null); setPreviewKey(null);
    try {
      let next: Preview;
      if (action === 'matching') {
        const request: ClientOverRefundRecoveryMatchingPreviewRequest = { recovery_identity: recoveryIdentity, finance_import_row_id: rowNumber, evidence_reference: evidence.trim() };
        next = await client.previewMatching(caseNo, request);
      } else if (action === 'collection') {
        const request: ClientOverRefundRecoveryMatchedPreviewRequest = { recovery_identity: recoveryIdentity, finance_import_row_id: rowNumber, matching_identity: matchingIdentity.trim(), matching_version: Number(matchingVersion), evidence_reference: evidence.trim() };
        next = await client.previewCollection(caseNo, request);
      } else {
        next = await client.previewAdjustment(caseNo, { recovery_identity: recoveryIdentity, adjustment_amount_ntd: amountNumber, evidence_reference: evidence.trim() });
      }
      setPreview(next); setPreviewKey(key);
    } catch (caught) { setError(displayError(caught)); }
    finally { setBusy(false); }
  };

  const applyAction = async () => {
    if (!previewCurrent || !query || busy) return;
    setBusy(true); setError(null); setNotice(null);
    const fingerprint = (preview as { preview_fingerprint: string }).preview_fingerprint;
    if (applyCommand.current?.previewFingerprint !== fingerprint) {
      applyCommand.current = { previewFingerprint: fingerprint, idempotencyKey: commandId(`client-recovery-${action}`), correlationId: commandId('client-recovery-command') };
    }
    const options = { idempotencyKey: applyCommand.current.idempotencyKey, correlationId: applyCommand.current.correlationId };
    try {
      let receipt: ClientOverRefundRecoveryReceipt | unknown;
      if (action === 'matching') {
        const p = preview as ClientOverRefundRecoveryMatchingPreview;
        receipt = await client.applyMatching(caseNo, { recovery_identity: recoveryIdentity, finance_import_row_id: rowNumber, evidence_reference: evidence.trim(), expected_recovery_version: p.recovery_version, expected_account_version: p.account_version, preview_fingerprint: p.preview_fingerprint, reason: reason.trim() }, options);
      } else if (action === 'collection') {
        const p = preview as ClientOverRefundRecoveryPreview;
        receipt = await client.applyCollection(caseNo, { recovery_identity: recoveryIdentity, finance_import_row_id: rowNumber, matching_identity: matchingIdentity.trim(), matching_version: Number(matchingVersion), evidence_reference: evidence.trim(), expected_recovery_version: p.recovery_version, expected_account_version: p.account_version, preview_fingerprint: p.preview_fingerprint, reason: reason.trim() }, options);
      } else {
        const p = preview as ClientOverRefundRecoveryAdjustmentPreview;
        receipt = await client.applyAdjustment(caseNo, { recovery_identity: recoveryIdentity, adjustment_amount_ntd: amountNumber, evidence_reference: evidence.trim(), expected_recovery_version: p.recovery_version, expected_account_version: p.account_version, preview_fingerprint: p.preview_fingerprint, reason: reason.trim() }, options);
      }
      const fresh = await readOwner();
      if (fresh && terminal(fresh)) setNotice('已重新確認追償餘額歸零且完成處理，異常可解除。');
      else if (fresh) setNotice(action === 'matching' ? '配對已記錄；配對本身不解除異常，請再完成收款或授權調整。' : `處理已記錄；目前仍有 ${fresh.remaining_amount_ntd.toLocaleString()} 元待處理。`);
      void receipt;
      setPreview(null); setPreviewKey(null);
      applyCommand.current = null;
    } catch (caught) {
      const fresh = await readOwner();
      if (fresh && terminal(fresh)) setNotice('結果已由最新追償資料確認完成，異常可解除。');
      else setError(displayError(caught));
    } finally { setBusy(false); }
  };

  const invalidate = (setter: (value: string) => void) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => { setter(event.target.value); setPreview(null); setPreviewKey(null); applyCommand.current = null; setNotice(null); };
  if (loading && !query) return <section aria-label="客戶退款超額追償處理"><p>正在讀取最新客戶追償資料…</p></section>;
  if (queryError && !query) return <section aria-label="客戶退款超額追償處理"><p role="alert">{queryError}</p><button type="button" onClick={() => void readOwner()}>重新查詢</button></section>;
  if (!query) return null;
  if (terminal(query)) return <section aria-label="客戶退款超額追償處理"><h3>客戶退款超額追償已解除</h3><p>目前餘額：0 元｜狀態：{recoveryStatusLabel(query.status)}</p></section>;

  return <section aria-label="客戶退款超額追償處理" data-recovery-status={query.status}>
    <h3>客戶退款超額追償</h3>
    <p>案件：{query.case_no}</p>
    <p>目前餘額：{query.remaining_amount_ntd.toLocaleString()} 元｜狀態：{recoveryStatusLabel(query.status)}</p>
    <p>完成條件：追償餘額歸零，且款項已收回或授權調整已完成；只有建立配對不會解除異常。</p>
    <div role="group" aria-label="處置方式">
      <button type="button" aria-pressed={action === 'matching'} onClick={() => { setAction('matching'); setPreview(null); setPreviewKey(null); applyCommand.current = null; }}>建立入款配對</button>
      {query.current_matchings.length > 0 && <button type="button" aria-pressed={action === 'collection'} onClick={() => { setAction('collection'); setPreview(null); setPreviewKey(null); applyCommand.current = null; }}>核銷已配對入款</button>}
      <button type="button" aria-pressed={action === 'adjustment'} onClick={() => { setAction('adjustment'); setPreview(null); setPreviewKey(null); applyCommand.current = null; }}>授權人工調整</button>
    </div>
    {action !== 'adjustment' && <label>入款流水紀錄編號<input inputMode="numeric" value={rowId} onChange={invalidate(setRowId)} /></label>}
    {action === 'collection' && <details><summary>技術操作欄位</summary><label>配對識別值<input value={matchingIdentity} onChange={invalidate(setMatchingIdentity)} /></label><label>配對資料版本<input inputMode="numeric" value={matchingVersion} onChange={invalidate(setMatchingVersion)} /></label></details>}
    {action === 'adjustment' && <label>調整金額（元）<input inputMode="numeric" value={amount} onChange={invalidate(setAmount)} /></label>}
    <label>處理原因（必填）<textarea value={reason} onChange={invalidate(setReason)} /></label>
    <label>佐證紀錄（必填，可填電話／紙本紀錄索引）<input value={evidence} onChange={invalidate(setEvidence)} /></label>
    <div><button type="button" onClick={() => void previewAction()} disabled={!canPreview}>{busy ? '處理中…' : '預覽處理影響'}</button><button type="button" onClick={() => void applyAction()} disabled={!previewCurrent || busy}>確認套用</button></div>
    {previewCurrent && <p role="status">處理影響已確認；正式套用前仍會重新讀取並鎖定最新追償資料。</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    {queryError && <p role="alert">{queryError}</p>}
  </section>;
};
