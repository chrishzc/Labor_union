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
function paymentStageLabel(stage: ClientPaymentStage): string {
  return ({ deposit: '訂金', first: '第一期', second: '第二期', adjustment: '調整款' })[stage];
}
function obligationTypeLabel(type: 'adjustment' | 'refund' | 'subsidy_return'): string {
  return type === 'adjustment' ? '調整款' : type === 'refund' ? '一般退款' : '補助退還';
}
function settlementErrorMessage(error: unknown): string {
  const typed = error instanceof ClientSettlementRemediationError ? error : null;
  const code = typed?.code.toUpperCase() ?? '';
  if (typed?.status === 401 || code.includes('UNAUTHENTICATED')) return '登入狀態已失效，請重新登入後再操作。';
  if (typed?.status === 403 || code.includes('FORBIDDEN')) return '目前帳號沒有處理這筆客戶帳務的權限。';
  if (typed?.status === 404 || code.includes('NOT_FOUND')) return '找不到這筆客戶帳務資料，請返回清單重新查詢。';
  if (typed?.status === 409 || code.includes('STALE') || code.includes('CONFLICT')) return '案件資料已變更，請重新查詢並再次預覽。';
  if (typed?.status === 422 || code.includes('INVALID') || code.includes('BLOCK')) return '所選義務或銀行流水未通過檢核，請調整選擇後再預覽。';
  if (typed?.retryable) return '結果尚未確認；請先重新查詢，再安全重試原操作。';
  return '客戶帳務目前無法完成，請稍後再試。';
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
      if (!remaining.length) { setNotice('重新查詢後已無這類逾期未清義務，提醒可解除。'); await onResolved?.(); }
    } catch (caught) { setQuery(null); setError(settlementErrorMessage(caught)); }
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
    } catch (caught) { setError(settlementErrorMessage(caught)); setPreview(null); }
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
      setNotice((current) => current ?? '本次核銷已重新查詢確認；若仍有其他同類逾期義務，提醒會保留。');
    } catch (caught) {
      const typed = caught instanceof ClientSettlementRemediationError ? caught : null;
      setUnknownOutcome(Boolean(typed?.retryable)); setError(settlementErrorMessage(caught));
    } finally { setBusy(null); }
  };

  if (!query) return <section aria-label={`${title(target.kind)}人工處理`}><h3>{title(target.kind)}人工處理</h3>{busy === 'query' && <p role="status">正在讀取客戶帳務資料…</p>}{error && <div role="alert">{error}</div>}<button type="button" disabled={busy !== null} onClick={() => void reload(true)}>重新查詢</button></section>;
  return <section aria-label={`${title(target.kind)}人工處理`} data-surface-id="client-settlement-remediation" style={{ border: '1px solid #fed7aa', borderRadius: 12, padding: 16, marginTop: 12 }}>
    <h3>{title(target.kind)}人工處理</h3><p>案件：{query.case_no}｜帳務資料日期：{query.as_of}</p>
    <p><strong>解除條件：</strong>這類逾期義務餘額全部歸零；電話、LINE 或追蹤狀態都不能代替正式核銷。</p>
    <details><summary>技術詳情與資料來源</summary><p>帳務版本：{query.account_version}</p></details>
    {target.kind === 'receivable' && <label>核銷期別 <select value={stage} disabled={busy !== null} onChange={(event) => { setStage(event.target.value as ClientPaymentStage); setObligationIds([]); invalidate(); }}><option value="deposit">訂金</option><option value="first">第一期</option><option value="second">第二期</option><option value="adjustment">調整款</option></select></label>}
    <fieldset disabled={busy !== null}><legend>具體逾期義務</legend>{visibleObligations.map((item, index) => <div key={item.obligation_identity}><label style={{ display: 'block' }}><input type="checkbox" checked={obligationIds.includes(item.obligation_identity)} onChange={() => toggleObligation(item.obligation_identity)} /> 第 {index + 1} 筆｜{'payment_stage' in item ? paymentStageLabel(item.payment_stage) : obligationTypeLabel(item.obligation_type)}｜到期 {item.due_date}｜NT$ {item.amount_due_ntd.toLocaleString('zh-TW')}</label><details><summary>義務技術詳情</summary><p>義務識別：{item.obligation_identity}</p></details></div>)}{!visibleObligations.length && <p>目前沒有此分支的逾期義務。</p>}</fieldset>
    <fieldset disabled={busy !== null}><legend>可核對的銀行流水</legend>{banks.map((item, index) => <div key={item.finance_import_row_id}><label style={{ display: 'block' }}><input type="checkbox" checked={bankIds.includes(item.finance_import_row_id)} onChange={() => toggleBank(item.finance_import_row_id)} /> 第 {index + 1} 筆｜{item.transaction_date}｜NT$ {item.amount_ntd.toLocaleString('zh-TW')}</label><details><summary>銀行流水技術詳情</summary><p>來源資料列：{item.finance_import_row_id}</p></details></div>)}{!banks.length && <p role="alert">尚無符合方向、分類、對方帳戶與未核銷條件的銀行流水；提醒保留。</p>}</fieldset>
    <label style={{ display: 'block' }}>人工核對理由<textarea value={reason} disabled={busy !== null} maxLength={500} onChange={(event) => { setReason(event.target.value); invalidate(); }} /></label>
    <button type="button" disabled={busy !== null || !obligationIds.length || !bankIds.length} onClick={() => void previewAction()}>{busy === 'preview' ? '檢查中…' : '檢查核銷影響'}</button>
    {preview && <div data-surface-id="client-settlement-preview"><p>預覽核銷金額：NT$ {previewAmount(preview).toLocaleString('zh-TW')}</p><label><input type="checkbox" checked={confirmed} disabled={busy !== null} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對案件、逾期義務、銀行流水與預覽結果，確認套用此核銷。</label><button type="button" disabled={!confirmed || !reason.trim() || busy !== null} onClick={() => void applyAction()}>確認並套用</button></div>}
    {unknownOutcome && <div role="alert">套用結果尚未確認；原操作已保留，不會建立第二筆操作。<button type="button" disabled={busy !== null} onClick={() => void reload(false)}>重新查詢結果</button>{preview && <button type="button" disabled={busy !== null} onClick={() => void applyAction()}>安全重試原操作</button>}</div>}
    {notice && <div role="status">{notice}</div>}{error && <div role="alert">{error}</div>}
  </section>;
};
