/**
 * File: ClientSettlementRemediationWorkbench.tsx
 * Description: 客戶應收、一般退款與補助退還的 bounded owner Q/P/A 工作台。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  clientSettlementRemediationClient,
  ClientSettlementRemediationError,
  type ClientSettlementRemediationClient,
  type ClientSettlementOptions,
} from '../api/client_finance/client_settlement_remediation_client';
import type {
  ClientPayablePreview, ClientPaymentStage, ClientReceiptPreview, ClientSettlementQuery,
} from '../api/client_finance/client_settlement_remediation_schemas';
import type { ClientSettlementTarget } from '../adapters/anomalies/client_settlement_target';

interface Props {
  target: ClientSettlementTarget;
  onResolved?: () => void | Promise<void>;
  client?: ClientSettlementRemediationClient;
  requestOptions?: ClientSettlementOptions;
}
type Preview = { kind: 'receivable'; value: ClientReceiptPreview } | { kind: 'payable'; value: ClientPayablePreview };

function title(kind: ClientSettlementTarget['kind']): string {
  return kind === 'receivable' ? '逾期客戶應收' : kind === 'refund' ? '逾期客戶退款／調整應付' : '逾期客戶補助退還';
}
function commandId(prefix: string): string { return `${prefix}-${crypto.randomUUID()}`; }
function previewAmount(preview: Preview): number {
  return preview.kind === 'receivable'
    ? preview.value.candidate.obligation_total.amount
    : preview.value.candidate.amount.amount;
}

export const ClientSettlementRemediationWorkbench: React.FC<Props> = ({
  target, onResolved, client = clientSettlementRemediationClient, requestOptions = {},
}) => {
  const [query, setQuery] = useState<ClientSettlementQuery | null>(null);
  const [stage, setStage] = useState<ClientPaymentStage>('deposit');
  const [obligationIds, setObligationIds] = useState<string[]>([]);
  const [bankIds, setBankIds] = useState<number[]>([]);
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState<'query' | 'preview' | 'apply' | null>('query');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [unknownOutcome, setUnknownOutcome] = useState(false);
  const command = useRef<{ fingerprint: string; idempotencyKey: string; correlationId: string } | null>(null);

  const obligations = useMemo(() => {
    if (!query) return [];
    if (target.kind === 'receivable') return query.receivable_obligations;
    return target.kind === 'refund' ? query.refund_obligations : query.subsidy_return_obligations;
  }, [query, target.kind]);
  const banks = useMemo(() => {
    if (!query) return [];
    if (target.kind === 'receivable') return query.incoming_bank_facts;
    return target.kind === 'refund' ? query.refund_bank_facts : query.subsidy_return_bank_facts;
  }, [query, target.kind]);
  const visibleObligations = target.kind === 'receivable'
    ? obligations.filter((item) => 'payment_stage' in item && item.payment_stage === stage)
    : obligations;

  const invalidate = () => { setPreview(null); setConfirmed(false); setNotice(null); setUnknownOutcome(false); command.current = null; };
  const reload = async (enforceBoundVersion = false) => {
    setBusy('query'); setError(null);
    try {
      const fresh = await client.query(target.caseNo, requestOptions);
      if (enforceBoundVersion && fresh.account_version !== target.accountVersion) {
        throw new ClientSettlementRemediationError('client_finance_candidate_stale', '帳務版本已改變，請刷新異常清單後重新進入。');
      }
      setQuery(fresh);
      const remaining = target.kind === 'receivable' ? fresh.receivable_obligations : target.kind === 'refund' ? fresh.refund_obligations : fresh.subsidy_return_obligations;
      if (!remaining.length) { setNotice('根據 Client Finance current root，此碼已無逾期未清義務，異常可解除。'); await onResolved?.(); }
    } catch (caught) { setQuery(null); setError(caught instanceof Error ? caught.message : '無法取得 Client Finance 根事實。'); }
    finally { setBusy(null); }
  };

  useEffect(() => { setObligationIds([]); setBankIds([]); setReason(''); invalidate(); void reload(true); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [target.caseNo, target.kind, target.accountVersion]);

  const toggleObligation = (value: string) => { setObligationIds((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]); invalidate(); };
  const toggleBank = (value: number) => { setBankIds((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]); invalidate(); };
  const previewAction = async () => {
    if (!query || !obligationIds.length || !bankIds.length) return;
    setBusy('preview'); setError(null); setNotice(null);
    try {
      if (target.kind === 'receivable') {
        const value = await client.previewReceipt(target.caseNo, { payment_stage: stage, finance_import_row_ids: bankIds, obligation_identities: obligationIds }, requestOptions);
        if (value.account_version !== query.account_version) throw new ClientSettlementRemediationError('client_finance_candidate_stale', 'Preview 版本與 Query 不一致。');
        setPreview({ kind: 'receivable', value });
      } else {
        const value = await client.previewPayable(target.caseNo, target.kind, { finance_import_row_ids: bankIds, obligation_identities: obligationIds, allow_partial_refund_recovery: false }, requestOptions);
        if (value.account_version !== query.account_version) throw new ClientSettlementRemediationError('client_finance_candidate_stale', 'Preview 版本與 Query 不一致。');
        setPreview({ kind: 'payable', value });
      }
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Preview 失敗。'); setPreview(null); }
    finally { setBusy(null); }
  };
  const applyAction = async () => {
    if (!query || !preview || !confirmed || !reason.trim()) return;
    setBusy('apply'); setError(null); setNotice(null);
    const fingerprint = preview.value.preview_fingerprint;
    if (!command.current || command.current.fingerprint !== fingerprint) command.current = { fingerprint, idempotencyKey: commandId('client-settlement-apply'), correlationId: commandId('client-settlement-command') };
    try {
      if (target.kind === 'receivable' && preview.kind === 'receivable') {
        await client.applyReceipt(target.caseNo, { payment_stage: stage, finance_import_row_ids: bankIds, obligation_identities: obligationIds, expected_account_version: preview.value.account_version, preview_fingerprint: fingerprint, reason: reason.trim() }, { ...requestOptions, idempotencyKey: command.current.idempotencyKey, correlationId: command.current.correlationId });
      } else if (target.kind !== 'receivable' && preview.kind === 'payable') {
        await client.applyPayable(target.caseNo, target.kind, { finance_import_row_ids: bankIds, obligation_identities: obligationIds, allow_partial_refund_recovery: false, expected_account_version: preview.value.account_version, preview_fingerprint: fingerprint, reason: reason.trim() }, { ...requestOptions, idempotencyKey: command.current.idempotencyKey, correlationId: command.current.correlationId });
      } else throw new ClientSettlementRemediationError('CLIENT_SETTLEMENT_BRANCH_MISMATCH', '異常分支與 Preview 不一致。');
      setUnknownOutcome(false); setObligationIds([]); setBankIds([]); setPreview(null); setConfirmed(false);
      await reload(false);
      setNotice((current) => current ?? '本次核銷已回讀；若仍有其他同碼逾期義務，異常會保留。');
    } catch (caught) {
      const typed = caught instanceof ClientSettlementRemediationError ? caught : null;
      setUnknownOutcome(Boolean(typed?.retryable)); setError(caught instanceof Error ? caught.message : 'Apply 失敗。');
    } finally { setBusy(null); }
  };

  if (!query) return <section aria-label={`${title(target.kind)}人工處理`}><h3>{title(target.kind)}人工處理</h3>{busy === 'query' && <p role="status">正在讀取 Client Finance 根事實…</p>}{error && <div role="alert">{error}</div>}<button type="button" disabled={busy !== null} onClick={() => void reload(true)}>重新讀取</button></section>;
  return <section aria-label={`${title(target.kind)}人工處理`} data-surface-id="client-settlement-remediation" style={{ border: '1px solid #fed7aa', borderRadius: 12, padding: 16, marginTop: 12 }}>
    <h3>{title(target.kind)}人工處理</h3><p>案件：{query.case_no}｜根事實日：{query.as_of}｜版本：{query.account_version}</p>
    <p><strong>解除條件：</strong>本碼所有逾期義務餘額歸零；電話、LINE、receipt 或追蹤狀態都不能代替。</p>
    {target.kind === 'receivable' && <label>核銷期別 <select value={stage} disabled={busy !== null} onChange={(event) => { setStage(event.target.value as ClientPaymentStage); setObligationIds([]); invalidate(); }}><option value="deposit">訂金</option><option value="first">第一期</option><option value="second">第二期</option><option value="adjustment">調整款</option></select></label>}
    <fieldset disabled={busy !== null}><legend>具體逾期義務</legend>{visibleObligations.map((item) => <label key={item.obligation_identity} style={{ display: 'block' }}><input type="checkbox" checked={obligationIds.includes(item.obligation_identity)} onChange={() => toggleObligation(item.obligation_identity)} /> {item.obligation_identity}｜{'payment_stage' in item ? item.payment_stage : item.obligation_type}｜到期 {item.due_date}｜NT$ {item.amount_due_ntd.toLocaleString('zh-TW')}</label>)}{!visibleObligations.length && <p>目前沒有此分支的逾期義務。</p>}</fieldset>
    <fieldset disabled={busy !== null}><legend>Canonical 銀行流水</legend>{banks.map((item) => <label key={item.finance_import_row_id} style={{ display: 'block' }}><input type="checkbox" checked={bankIds.includes(item.finance_import_row_id)} onChange={() => toggleBank(item.finance_import_row_id)} /> #{item.finance_import_row_id}｜{item.transaction_date}｜NT$ {item.amount_ntd.toLocaleString('zh-TW')}</label>)}{!banks.length && <p role="alert">尚無符合方向、分類、對方帳戶與未核銷條件的銀行流水；異常保留。</p>}</fieldset>
    <label style={{ display: 'block' }}>人工核對理由<textarea value={reason} disabled={busy !== null} maxLength={500} onChange={(event) => { setReason(event.target.value); invalidate(); }} /></label>
    <button type="button" disabled={busy !== null || !obligationIds.length || !bankIds.length} onClick={() => void previewAction()}>{busy === 'preview' ? '檢查中…' : '檢查核銷影響'}</button>
    {preview && <div data-surface-id="client-settlement-preview"><p>Preview 金額：NT$ {previewAmount(preview).toLocaleString('zh-TW')}</p><label><input type="checkbox" checked={confirmed} disabled={busy !== null} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對 owner Query 與規則書，確認套用此核銷。</label><button type="button" disabled={!confirmed || !reason.trim() || busy !== null} onClick={() => void applyAction()}>確認並套用</button></div>}
    {unknownOutcome && <div role="alert">Apply 結果未知；不得產生新命令。<button type="button" disabled={busy !== null} onClick={() => void reload(false)}>以 owner root 調和結果</button>{preview && <button type="button" disabled={busy !== null} onClick={() => void applyAction()}>使用原 Idempotency-Key 安全重試</button>}</div>}
    {notice && <div role="status">{notice}</div>}{error && <div role="alert">{error}</div>}
  </section>;
};
