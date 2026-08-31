/**
 * File: StaffOverpaymentRecoveryActions.tsx
 * Description: Staff overpayment recovery 的 owner Query／matching／collection／adjustment 工作台。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createStaffOverpaymentRecoveryCommandIdentity,
  staffOverpaymentRecoveryClient,
  type StaffOverpaymentRecoveryAdjustmentInput,
  type StaffOverpaymentRecoveryCollectionInput,
  type StaffOverpaymentRecoveryMatchingInput,
  type StaffOverpaymentRecoveryCommand,
} from '../api/staff_payables/staff_overpayment_recovery_client';
import {
  type StaffOverpaymentRecoveryAdjustmentPreview,
  type StaffOverpaymentRecoveryCollectionPreview,
  type StaffOverpaymentRecoveryMatchingPreview,
  type StaffOverpaymentRecoveryQuery,
} from '../api/staff_payables/staff_overpayment_recovery_schemas';
import { StaffOverpaymentRecoveryError } from '../api/staff_payables/staff_overpayment_recovery_errors';
import { ApiNetworkError, ApiTimeoutError } from '../api/shared/typed_errors';

export interface StaffOverpaymentRecoveryActionsProps {
  staffId: number;
  recoveryIdentity: string;
  /** Optional numeric bank-row binding from the anomaly owner context. It is never editable for collection. */
  initialFinanceImportRowId?: number;
  onCommitted?: () => Promise<void> | void;
}

type PreviewState =
  | { kind: 'matching'; value: StaffOverpaymentRecoveryMatchingPreview }
  | { kind: 'collection'; value: StaffOverpaymentRecoveryCollectionPreview }
  | { kind: 'adjustment'; value: StaffOverpaymentRecoveryAdjustmentPreview };

type Operation = 'query' | 'preview' | 'apply' | 'reconcile';

function displayError(error: unknown): string {
  if (error instanceof StaffOverpaymentRecoveryError) {
    if (error.code === 'STAFF_RECOVERY_SCHEMA_MISMATCH') return '追償資料目前不完整，已停止操作。';
    if (error.code === 'STAFF_RECOVERY_OWNER_MISMATCH' || error.code.includes('OWNER_MISMATCH')) return '追償資料與目前處理對象不一致，已停止操作。';
    if (error.code.includes('STALE')) return '追償資料已變更，請重新查詢後再檢查處理影響。';
    return '月嫂超額付款追償目前無法完成，異常仍會保留；請確認資料後再試。';
  }
  return '月嫂超額付款追償目前無法完成，異常仍會保留；請重新查詢後再試。';
}

function recoveryStatusLabel(status: StaffOverpaymentRecoveryQuery['status']): string {
  const labels: Record<StaffOverpaymentRecoveryQuery['status'], string> = {
    open: '待處理',
    partially_recovered: '部分收回',
    recovered: '已收回',
    adjusted: '已完成授權調整',
  };
  return labels[status];
}

function isOutcomeUnknown(error: unknown): boolean {
  return error instanceof ApiTimeoutError || error instanceof ApiNetworkError
    || (error instanceof StaffOverpaymentRecoveryError && error.retryable);
}

function positiveRowId(value: string): number | null {
  const normalized = value.trim();
  if (!/^[1-9][0-9]*$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function commandFor(identities: Map<string, StaffOverpaymentRecoveryCommand>, kind: string): StaffOverpaymentRecoveryCommand {
  const existing = identities.get(kind);
  if (existing) return existing;
  const identity = createStaffOverpaymentRecoveryCommandIdentity(kind);
  identities.set(kind, identity);
  return identity;
}

export function StaffOverpaymentRecoveryActions({
  staffId,
  recoveryIdentity,
  initialFinanceImportRowId,
  onCommitted,
}: StaffOverpaymentRecoveryActionsProps) {
  const [query, setQuery] = useState<StaffOverpaymentRecoveryQuery | null>(null);
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [rowIdText, setRowIdText] = useState(initialFinanceImportRowId?.toString() ?? '');
  const [reason, setReason] = useState('');
  const [evidenceReference, setEvidenceReference] = useState('');
  const [operation, setOperation] = useState<Operation>('query');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const requestGeneration = useRef(0);
  const identities = useRef(new Map<string, StaffOverpaymentRecoveryCommand>());

  const loadQuery = useCallback(async (signal?: AbortSignal): Promise<StaffOverpaymentRecoveryQuery> => {
    const generation = ++requestGeneration.current;
    setOperation('query');
    const value = await staffOverpaymentRecoveryClient.query(staffId, recoveryIdentity, { signal });
    if (generation === requestGeneration.current) {
      setQuery(value);
      setPreview(null);
      setOutcomeUnknown(false);
    }
    return value;
  }, [recoveryIdentity, staffId]);

  useEffect(() => {
    const controller = new AbortController();
    identities.current.clear();
    setQuery(null);
    setPreview(null);
    setError(null);
    setNotice(null);
    setRowIdText(initialFinanceImportRowId?.toString() ?? '');
    void loadQuery(controller.signal).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setOperation('query');
        setError(displayError(cause));
      }
    });
    return () => {
      requestGeneration.current += 1;
      controller.abort();
    };
  }, [initialFinanceImportRowId, loadQuery]);

  const invalidatePreview = () => {
    setPreview(null);
    setNotice(null);
  };

  const inputReady = reason.trim().length > 0 && evidenceReference.trim().length > 0;
  const active = query !== null && (query.status === 'open' || query.status === 'partially_recovered') && query.remaining_amount_ntd > 0;
  const uniqueMatching = query?.matchings.length === 1 ? query.matchings[0] : null;
  const multipleMatchings = (query?.matchings.length ?? 0) > 1;
  const collectionRowId = initialFinanceImportRowId ?? positiveRowId(rowIdText);
  const collectionReady = uniqueMatching !== null && collectionRowId !== null && inputReady && active;
  const matchingReady = query !== null && query.matchings.length === 0 && positiveRowId(rowIdText) !== null && inputReady && active;
  const adjustmentReady = query !== null && query.matchings.length === 0 && inputReady && active;
  const busy = operation !== 'query' && operation !== 'reconcile';

  const runPreview = async (kind: 'matching' | 'collection' | 'adjustment') => {
    if (!query || !active || !inputReady || busy) return;
    setError(null);
    setNotice(null);
    setOperation('preview');
    try {
      if (kind === 'matching') {
        const id = positiveRowId(rowIdText);
        if (query.matchings.length !== 0 || id === null) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_BANK_ROW_INVALID', '請提供正確的銀行流水編號。');
        const input: StaffOverpaymentRecoveryMatchingInput = { recovery_identity: recoveryIdentity, finance_import_row_id: id, evidence_reference: evidenceReference };
        setPreview({ kind, value: await staffOverpaymentRecoveryClient.previewMatching(input) });
      } else if (kind === 'collection') {
        if (multipleMatchings || uniqueMatching === null || collectionRowId === null) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_MATCHING_AMBIGUOUS', 'current matching 不唯一或缺少 owner bank binding，已停止操作。');
        const input: StaffOverpaymentRecoveryCollectionInput = { recovery_identity: recoveryIdentity, finance_import_row_id: collectionRowId, matching_identity: uniqueMatching.matching_identity, matching_version: uniqueMatching.matching_version, evidence_reference: evidenceReference };
        setPreview({ kind, value: await staffOverpaymentRecoveryClient.previewCollection(input) });
      } else {
        const input: StaffOverpaymentRecoveryAdjustmentInput = { recovery_identity: recoveryIdentity, adjustment_amount_ntd: query.remaining_amount_ntd, evidence_reference: evidenceReference };
        setPreview({ kind, value: await staffOverpaymentRecoveryClient.previewAdjustment(input) });
      }
    } catch (cause) {
      setPreview(null);
      setError(displayError(cause));
    } finally {
      setOperation('query');
    }
  };

  const runApply = async () => {
    if (!query || !preview || !inputReady || busy) return;
    setError(null);
    setNotice(null);
    setOperation('apply');
    try {
      let terminal = false;
      if (preview.kind === 'matching') {
        const id = positiveRowId(rowIdText);
        if (id === null) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_BANK_ROW_INVALID', '銀行流水編號已失效，請重新 Preview。');
        await staffOverpaymentRecoveryClient.applyMatching(preview.value, { recovery_identity: recoveryIdentity, finance_import_row_id: id, evidence_reference: evidenceReference, reason }, commandFor(identities.current, 'matching-apply'));
      } else if (preview.kind === 'collection') {
        if (multipleMatchings || uniqueMatching === null || collectionRowId === null) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_MATCHING_AMBIGUOUS', 'current matching 已不唯一，請重新查詢。');
        await staffOverpaymentRecoveryClient.applyCollection(preview.value, { recovery_identity: recoveryIdentity, finance_import_row_id: collectionRowId, matching_identity: uniqueMatching.matching_identity, matching_version: uniqueMatching.matching_version, evidence_reference: evidenceReference, reason }, commandFor(identities.current, 'collection-apply'));
        terminal = true;
      } else {
        if (preview.value.adjustment_amount_ntd !== query.remaining_amount_ntd) throw new StaffOverpaymentRecoveryError('STAFF_RECOVERY_AMOUNT_STALE', 'remaining 已變更，不能套用舊 adjustment。');
        await staffOverpaymentRecoveryClient.applyAdjustment(preview.value, { recovery_identity: recoveryIdentity, adjustment_amount_ntd: query.remaining_amount_ntd, evidence_reference: evidenceReference, reason }, commandFor(identities.current, 'adjustment-apply'));
        terminal = true;
      }
      identities.current.delete(`${preview.kind}-apply`);
      const readback = await loadQuery();
      if (terminal && (readback.status === 'recovered' || readback.status === 'adjusted') && readback.remaining_amount_ntd === 0) {
        setNotice('已重新確認追償餘額歸零且完成處理，異常可解除。');
        await onCommitted?.();
      } else if (terminal) {
        setNotice(`Staff recovery 仍在處理中，剩餘 NT$ ${readback.remaining_amount_ntd.toLocaleString('en-US')}；異常保留。`);
      } else {
        setNotice('入款配對已建立；配對本身不解除異常，請依最新追償資料繼續收款。');
      }
    } catch (cause) {
      if (isOutcomeUnknown(cause)) {
        setOutcomeUnknown(true);
        setError('操作結果目前無法安全確認，禁止重複送出；請使用原操作重新查詢。');
      } else setError(displayError(cause));
    } finally {
      setOperation('query');
    }
  };

  const reconcileUnknown = async () => {
    if (!outcomeUnknown || busy) return;
    setError(null);
    setOperation('reconcile');
    try {
      const readback = await loadQuery();
      if (readback.remaining_amount_ntd === 0 && (readback.status === 'recovered' || readback.status === 'adjusted')) {
        setNotice('已由最新追償資料確認完成，異常可解除；原操作紀錄仍會保留供稽核。');
        setOutcomeUnknown(false);
        await onCommitted?.();
      } else {
        setNotice('最新追償資料仍未完成；系統不會重複送出操作，異常仍會保留。');
      }
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setOperation('query');
    }
  };

  if (!query && !error) return <section aria-label="月嫂超額付款追償"><p role="status">正在查詢最新追償資料…</p></section>;

  return (
    <section aria-label="月嫂超額付款追償" data-control-id="staff-payables.overpayment-recovery.actions" style={{ display: 'grid', gap: 12, border: '1px solid #dec0b6', borderRadius: 12, padding: 16, background: '#fffaf8' }}>
      <header>
        <h3 style={{ margin: 0 }}>月嫂超額付款追償</h3>
        {query && <p style={{ margin: '6px 0 0' }}>目前狀態：{recoveryStatusLabel(query.status)}｜剩餘 NT$ {query.remaining_amount_ntd.toLocaleString('en-US')}</p>}
      </header>
      {error && <div role="alert" style={{ color: '#9f1239' }}>{error}</div>}
      {notice && <div role="status">{notice}</div>}
      {outcomeUnknown && <button type="button" onClick={() => void reconcileUnknown()} disabled={operation === 'reconcile'}>重新查詢原操作結果</button>}
      {query && !active && <div role="status">此筆追償已完成；只有最新追償資料確認後才可移除異常。</div>}
      {query && active && multipleMatchings && <div role="alert">目前有多筆入款配對，收款目標不唯一；請先人工整理配對資料。</div>}
      {query && active && query.matchings.length === 0 && (
        <>
          <fieldset disabled={busy || outcomeUnknown} style={{ display: 'grid', gap: 8 }}>
            <legend>配對退回入款（配對不會解除異常）</legend>
            <label>銀行流水編號<input aria-label="銀行流水編號" inputMode="numeric" value={rowIdText} onChange={(event) => { setRowIdText(event.target.value); invalidatePreview(); }} /></label>
            <button type="button" disabled={!matchingReady} onClick={() => void runPreview('matching')}>Preview 配對（零寫入）</button>
          </fieldset>
          <fieldset disabled={busy || outcomeUnknown} style={{ display: 'grid', gap: 8 }}>
            <legend>人工調整（一次精確結清）</legend>
            <p>依正式應付款規則，調整金額固定為目前剩餘追償額：NT$ {query.remaining_amount_ntd.toLocaleString('en-US')}，不可自行輸入部分金額。</p>
            <button type="button" disabled={!adjustmentReady} onClick={() => void runPreview('adjustment')}>檢查精確調整影響</button>
          </fieldset>
        </>
      )}
      {query && active && uniqueMatching && !multipleMatchings && (
        <fieldset disabled={busy || outcomeUnknown} style={{ display: 'grid', gap: 8 }}>
          <legend>核銷已配對退回入款</legend>
          <details><summary>技術操作欄位</summary><p>配對識別值：{uniqueMatching.matching_identity}（資料版本 {uniqueMatching.matching_version}）</p></details>
          {collectionRowId === null && <p role="alert">目前配對缺少可提交的銀行流水編號，已停止操作。</p>}
          {collectionRowId !== null && <p>銀行流水編號：{collectionRowId}</p>}
          <button type="button" disabled={!collectionReady} onClick={() => void runPreview('collection')}>檢查收款核銷影響</button>
        </fieldset>
      )}
      {query && active && (
        <fieldset disabled={busy || outcomeUnknown} style={{ display: 'grid', gap: 8 }}>
          <legend>人工操作說明與獨立佐證</legend>
          <label>處理理由<textarea aria-label="處理理由" value={reason} maxLength={500} onChange={(event) => { setReason(event.target.value); invalidatePreview(); }} /></label>
          <label>佐證紀錄<textarea aria-label="佐證紀錄" value={evidenceReference} maxLength={191} onChange={(event) => { setEvidenceReference(event.target.value); invalidatePreview(); }} /></label>
        </fieldset>
      )}
      {preview && (
        <div data-surface-id="staff-payables.overpayment-recovery.preview" style={{ border: '1px solid #b7d8d1', padding: 10, borderRadius: 8 }}>
          <strong>處理影響已確認（尚未寫入）</strong>
          <div>{preview.kind === 'matching' ? '只建立入款配對，不會解除異常' : preview.kind === 'collection' ? `收款後剩餘 NT$ ${preview.value.remaining_after_ntd.toLocaleString('en-US')}` : `精確調整 NT$ ${preview.value.adjustment_amount_ntd.toLocaleString('en-US')} 後結清`}</div>
          <button type="button" disabled={busy || outcomeUnknown || !inputReady} onClick={() => void runApply()}>確認並提交</button>
        </div>
      )}
    </section>
  );
}
