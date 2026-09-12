/** Client Finance owner workbench for bounded historical payment evidence. */
import React, { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  historicalClientPaymentClient,
  HistoricalClientPaymentClientError,
  type HistoricalClientPaymentIntent,
  type HistoricalClientPaymentPreview,
  type HistoricalClientPaymentQuery,
  type HistoricalClientPaymentReadback,
} from '../api/client_finance/historical_client_payment_client';
import { sessionClient } from '../api/auth/session_client';
import {
  orderMutationFlowStore,
  type HistoricalClientPaymentCommand,
  type HistoricalClientPaymentFlowState,
} from '../adapters/orders/order_mutation_flow_store';

const subscribeHistoricalClientPayment = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
const sameValues = (left: readonly string[], right: readonly string[]) => left.length === right.length
  && [...left].sort().every((value, index) => value === [...right].sort()[index]);
const definitiveRejection = (error: unknown) => error instanceof HistoricalClientPaymentClientError
  && error.status !== undefined && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429;
const blockerMessages: Record<string, string> = {
  historical_client_cross_case_forbidden: '所選款項不屬於目前案件。',
  historical_client_case_not_adopted: '請先完成歷史案件資料採納。',
  historical_client_bank_reconciliation_required: '已找到銀行流水，請改用銀行流水核銷。',
  historical_client_obligation_not_found: '所選款項已不存在，請重新查詢付款資料。',
  historical_client_obligation_not_open: '所選款項已結清或取消，請重新查詢付款資料。',
  historical_client_direction_mismatch: '所選款項與付款方向不符。',
  historical_client_obligation_type_mismatch: '所選款項不適用這個付款確認方式。',
};

export const HistoricalClientPaymentWorkbench: React.FC<{ caseNo: string }> = ({ caseNo }) => {
  const [query, setQuery] = useState<HistoricalClientPaymentQuery | null>(null);
  const [direction, setDirection] = useState<HistoricalClientPaymentIntent['direction']>('receivable_from_client');
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<'paid' | 'settled'>('paid');
  const [paymentDate, setPaymentDate] = useState('');
  const [unknownReason, setUnknownReason] = useState('原始付款日期無法可靠還原');
  const [sourceAvailability, setSourceAvailability] = useState<HistoricalClientPaymentIntent['source_availability']>('missing');
  const [evidenceReference, setEvidenceReference] = useState('');
  const [reason, setReason] = useState('已核對歷史案件與所選款項');
  const [preview, setPreview] = useState<HistoricalClientPaymentPreview | null>(null);
  const [readback, setReadback] = useState<HistoricalClientPaymentReadback | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const generation = useRef(0);
  const activeCase = useRef<string | null>(null);
  const busyRef = useRef(false);
  const previewController = useRef<AbortController | null>(null);
  const queryController = useRef<AbortController | null>(null);
  const flow = useSyncExternalStore(subscribeHistoricalClientPayment, () => orderMutationFlowStore.getHistoricalClientPayment(caseNo));
  const protectedFlow = flow !== undefined;
  const isActive = (request: number) => activeCase.current === caseNo && generation.current === request;

  const load = useCallback(async () => {
    const current = ++generation.current;
    queryController.current?.abort();
    const controller = new AbortController();
    queryController.current = controller;
    previewController.current?.abort();
    previewController.current = null;
    setQuery(null); setSelected([]); setPreview(null); setConfirmed(false);
    setBusy(true); setMessage(null);
    try {
      const value = await historicalClientPaymentClient.query(caseNo, { signal: controller.signal });
      if (value.case_no !== caseNo || value.obligations.some((item) => item.case_no !== caseNo)) throw new Error('付款資料與目前案件不符。');
      if (isActive(current)) setQuery(value);
    }
    catch { if (isActive(current)) setMessage('歷史客戶付款候選目前無法取得。'); }
    finally {
      if (isActive(current)) setBusy(false);
      if (queryController.current === controller) queryController.current = null;
    }
  // isActive deliberately reads mutable request ownership.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseNo]);
  useEffect(() => {
    activeCase.current = caseNo;
    setQuery(null); setSelected([]); setPreview(null); setReadback(null); setConfirmed(false);
    void load();
    return () => {
      activeCase.current = null; generation.current += 1;
      previewController.current?.abort(); previewController.current = null;
      queryController.current?.abort(); queryController.current = null;
    };
  }, [caseNo, load]);

  const obligations = useMemo(() => query?.obligations.filter((item) => item.direction === direction && item.status === 'open') ?? [], [direction, query]);
  const invalidate = () => {
    if (previewController.current) {
      previewController.current.abort(); previewController.current = null; setBusy(false);
    }
    setPreview(null); setConfirmed(false); setReadback(null);
  };
  const intent = (): HistoricalClientPaymentIntent => ({
    case_no: caseNo, direction, confirmation_kind: confirmation, obligation_identities: selected,
    payment_date: paymentDate || null, payment_date_unknown_reason: paymentDate ? null : unknownReason.trim() || null,
    source_availability: sourceAvailability, evidence_reference: evidenceReference.trim() || null,
  });
  const receiptMatches = (command: HistoricalClientPaymentCommand, receipt: NonNullable<HistoricalClientPaymentFlowState['receipt']>) => (
    receipt.case_no === command.intent.case_no && sameValues(receipt.obligation_identities, command.intent.obligation_identities)
    && receipt.amount_snapshot_ntd === command.preview.amount_snapshot_ntd && receipt.preview_fingerprint === command.preview.preview_fingerprint
    && receipt.resulting_account_version === command.preview.account_version + 1
  );
  const readbackMatches = (command: HistoricalClientPaymentCommand, receipt: NonNullable<HistoricalClientPaymentFlowState['receipt']>, value: HistoricalClientPaymentReadback) => (
    value.case_no === command.intent.case_no && value.account_version >= receipt.resulting_account_version
    && command.preview.obligations.every((item) => value.projections.some((projection) => projection.obligation_identity === item.obligation_identity
      && projection.amount_snapshot_ntd === item.amount_due_ntd && projection.obligation_projection_version === item.projection_version))
  );
  const observe = async (state: HistoricalClientPaymentFlowState, request: number) => {
    if (state.receipt === null) throw new Error('尚未收到收據，不能只讀取結果。');
    orderMutationFlowStore.setHistoricalClientPayment(caseNo, { ...state, status: 'observing', error: null });
    const fresh = await historicalClientPaymentClient.readback(state.command.intent.case_no);
    if (!readbackMatches(state.command, state.receipt, fresh)) throw new Error('收據後回讀與原案件、義務、金額或版本不一致；只能重新讀取。');
    orderMutationFlowStore.clearHistoricalClientPayment(caseNo);
    if (!isActive(request)) return;
    setReadback(fresh); setPreview(null); setConfirmed(false);
    setMessage(fresh.owner_terminal ? '已提交並重新確認 客戶款項已全部結清。' : '已提交；尚有客戶款項未結清。');
  };
  const submit = async (command: HistoricalClientPaymentCommand, recovery: boolean) => {
    const request = generation.current;
    orderMutationFlowStore.setHistoricalClientPayment(caseNo, { status: 'applying', command, receipt: null, error: null });
    let receipt: HistoricalClientPaymentFlowState['receipt'];
    try {
      receipt = await historicalClientPaymentClient.apply(command.intent, command.preview, command.reason, command.key, { expectedActor: command.actor });
      if (!receiptMatches(command, receipt)) throw new Error('歷史客戶付款收據 identity 不一致。');
    } catch (error) {
      if (!recovery && definitiveRejection(error)) {
        orderMutationFlowStore.clearHistoricalClientPayment(caseNo);
        if (isActive(request)) setMessage(error instanceof Error ? error.message : '提交遭拒。');
      } else {
        const text = recovery ? '原歷史客戶付款結果仍未確認；請恢復權限後確認提交結果。' : '歷史客戶付款結果尚未確認；請確認提交結果。';
        orderMutationFlowStore.setHistoricalClientPayment(caseNo, { status: 'outcome_unknown', command, receipt: null, error: text });
        if (isActive(request)) setMessage(text);
      }
      return;
    }
    const received: HistoricalClientPaymentFlowState = { status: 'observation_failed', command, receipt, error: null };
    orderMutationFlowStore.setHistoricalClientPayment(caseNo, received);
    try { await observe(received, request); }
    catch (error) {
      const text = error instanceof Error ? error.message : '收據後回讀失敗；只能重新讀取。';
      const saved = orderMutationFlowStore.getHistoricalClientPayment(caseNo);
      if (saved?.receipt) orderMutationFlowStore.setHistoricalClientPayment(caseNo, { ...saved, status: 'observation_failed', error: text });
      if (isActive(request)) setMessage(text);
    }
  };
  const runPreview = async () => {
    if (protectedFlow || !selected.length) { if (!protectedFlow) setMessage('請至少選擇一筆同方向款項。'); return; }
    previewController.current?.abort();
    const controller = new AbortController();
    previewController.current = controller;
    const request = generation.current;
    const requested = intent();
    const current = () => isActive(request) && !controller.signal.aborted && previewController.current === controller;
    setBusy(true); setMessage(null); setPreview(null); setConfirmed(false);
    try {
      const value = await historicalClientPaymentClient.preview(requested, { signal: controller.signal });
      if (!current()) return;
      if (value.case_no !== requested.case_no
        || value.obligations.some((item) => item.case_no !== requested.case_no)
        || value.obligations.some((item) => !requested.obligation_identities.includes(item.obligation_identity))
        || (value.can_apply && !sameValues(value.obligations.map((item) => item.obligation_identity), requested.obligation_identities))) {
        throw new Error('預覽與目前案件或選取項目不符。');
      }
      setPreview(value);
      if (!value.can_apply) setMessage(`目前不可提交：${value.blockers.map((blocker) => blockerMessages[blocker] ?? '付款資料已變更，請重新查詢後再預覽。').join(' ') || '尚未符合提交條件'}`);
    } catch { if (current()) setMessage('預覽失敗；資料不會被修改。'); }
    finally {
      if (current()) setBusy(false);
      if (previewController.current === controller) previewController.current = null;
    }
  };
  const runApply = async () => {
    if (busyRef.current || protectedFlow || !preview?.can_apply || preview.adoption_receipt_id === null || !confirmed || !reason.trim()) return;
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    if (!actor) { setMessage('請先登入後再提交。'); return; }
    busyRef.current = true; setBusy(true); setMessage(null);
    const command: HistoricalClientPaymentCommand = { actor, intent: intent(), preview, reason: reason.trim(), key: `historical-client-${crypto.randomUUID()}` };
    try { await submit(command, false); } finally { busyRef.current = false; if (activeCase.current === caseNo) setBusy(false); }
  };
  const retryOriginal = async () => {
    if (busyRef.current || flow?.status !== 'outcome_unknown') return;
    busyRef.current = true; setBusy(true); setMessage(null);
    try { await submit(flow.command, true); } finally { busyRef.current = false; if (activeCase.current === caseNo) setBusy(false); }
  };
  const retryReadback = async () => {
    if (busyRef.current || flow?.status !== 'observation_failed' || flow.receipt === null) return;
    const request = generation.current;
    busyRef.current = true; setBusy(true); setMessage(null);
    try { await observe(flow, request); }
    catch (error) {
      const text = error instanceof Error ? error.message : '收據後回讀失敗；只能重新讀取。';
      const saved = orderMutationFlowStore.getHistoricalClientPayment(caseNo);
      if (saved?.receipt) orderMutationFlowStore.setHistoricalClientPayment(caseNo, { ...saved, status: 'observation_failed', error: text });
      if (isActive(request)) setMessage(text);
    } finally { busyRef.current = false; if (activeCase.current === caseNo) setBusy(false); }
  };

  return <section className="finance-detail-block" aria-label="歷史客戶付款人工確認">
    <h3>歷史客戶付款人工確認</h3>
    <p>只供已完成資料採納的系統啟用前案件且銀行證據缺失、歸屬不明或無法還原時使用；正常銀行候選存在時請回銀行流水核銷。</p>
    {query?.normal_bank_candidate_identities.length ? <p role="alert">已找到正常銀行候選：{query.normal_bank_candidate_identities.join('、')}。歷史人工路徑應保持阻擋。</p> : null}
    <div className="finance-filter-bar"><label>方向<select disabled={protectedFlow} value={direction} onChange={(event) => { setDirection(event.target.value as HistoricalClientPaymentIntent['direction']); setSelected([]); invalidate(); }}><option value="receivable_from_client">客戶付款給工會</option><option value="payable_to_client">工會付款給客戶</option></select></label><label>確認類型<select disabled={protectedFlow} value={confirmation} onChange={(event) => { setConfirmation(event.target.value as 'paid' | 'settled'); invalidate(); }}><option value="paid">已付款</option><option value="settled">已結清</option></select></label><label>舊來源狀態<select disabled={protectedFlow} value={sourceAvailability} onChange={(event) => { setSourceAvailability(event.target.value as HistoricalClientPaymentIntent['source_availability']); invalidate(); }}><option value="missing">缺失</option><option value="ambiguous">歸屬不明</option><option value="unrecoverable">無法可靠還原</option></select></label></div>
    {obligations.map((item) => <label key={item.obligation_identity}><input disabled={protectedFlow} type="checkbox" checked={selected.includes(item.obligation_identity)} onChange={(event) => { setSelected((values) => event.target.checked ? [...values, item.obligation_identity] : values.filter((value) => value !== item.obligation_identity)); invalidate(); }} /> {item.obligation_type}｜{item.obligation_identity}｜NT$ {item.amount_due_ntd.toLocaleString('zh-TW')}</label>)}
    {!busy && query && obligations.length === 0 ? <p>此方向目前沒有可處理的未結清款項。</p> : null}
    <div className="finance-filter-bar"><label>付款日期（不確定可留空）<input disabled={protectedFlow} type="date" value={paymentDate} onChange={(event) => { setPaymentDate(event.target.value); invalidate(); }} /></label>{!paymentDate && <label>日期未知原因<input disabled={protectedFlow} value={unknownReason} maxLength={500} onChange={(event) => { setUnknownReason(event.target.value); invalidate(); }} /></label>}<label>證據參考（選填）<input disabled={protectedFlow} value={evidenceReference} maxLength={191} onChange={(event) => { setEvidenceReference(event.target.value); invalidate(); }} /></label></div>
    <button className="finance-btn-secondary" type="button" disabled={busy || !query || protectedFlow} onClick={() => void runPreview()}>預覽歷史付款影響</button>
    {preview && <div><p>本次確認項目：{preview.obligations.map((item) => item.obligation_identity).join('、')}</p><p>金額快照：NT$ {preview.amount_snapshot_ntd.toLocaleString('zh-TW')}</p>{preview.can_apply && <><label>原因<input disabled={protectedFlow} value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} /></label><label><input disabled={protectedFlow} type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> 我已核對方向、付款人／收款人、款項與金額</label><button className="finance-btn-primary" type="button" disabled={busy || protectedFlow || !confirmed || !reason.trim()} onClick={() => void runApply()}>確認並提交</button></>}</div>}
    {readback && <p>已重新讀取付款結果：{readback.owner_terminal ? '客戶款項已結清' : '尚有款項未結清'}（版本 {readback.account_version}）</p>}
    {flow?.status === 'outcome_unknown' && <button className="finance-btn-secondary" data-control-id="historical-client-payment-reconcile-original" type="button" disabled={busy} onClick={() => void retryOriginal()}>確認提交結果</button>}
    {flow?.status === 'observation_failed' && <button className="finance-btn-secondary" data-control-id="historical-client-payment-readback-only" type="button" disabled={busy} onClick={() => void retryReadback()}>重新讀取付款結果</button>}
    {message && <p role="status">{message}</p>}
    <button className="finance-btn-secondary" type="button" disabled={busy} onClick={() => void load()}>重新查詢付款資料</button>
  </section>;
};
