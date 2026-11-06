import { useUnsavedDraft } from './UnsavedChanges';
import { useEffect, useRef, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { financeImportCorrectionClient, type FinanceImportCorrectionPreview, type FinanceImportCorrectionSelection } from '../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../api/client_finance/client_receipt_query_client';
import { StaffPayoutRemediationWorkbench, type StaffPayoutRemediationTarget } from './StaffPayoutRemediationWorkbench';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import { clientSettlementRemediationClient } from '../api/client_finance/client_settlement_remediation_client';
import { subsidyPeriodClient, type SubsidyPeriod, type SubsidyPeriodView, type GovernmentDifferenceCommand } from '../api/government_subsidy/period_reconciliation_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { ClientReceiptReconciliationPanel } from './ClientReceiptReconciliationPanel';

type CorrectionCommand = {
  preview: FinanceImportCorrectionPreview;
  selection: FinanceImportCorrectionSelection;
  identity: { idempotencyKey: string; correlationId: string };
};
const refundModes = {
  exact: '足額核銷待退款',
  partial: '退款不足，先核銷實退',
  overage: '退款超出，另列待追回款',
};

export function FinanceImportCorrectionForm({ rowIdentity, sourceLabel, staff, bankAmount, initialKind = 'client_receipt', onPosted, onBusyChange }: {
  rowIdentity: string; sourceLabel: string; staff: readonly { id: number; label: string }[];
  bankAmount?: number;
  initialKind?: 'client_receipt' | 'staff_payout' | 'client_refund' | 'client_subsidy_return' | 'government_subsidy';
  onPosted?: () => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [payoutTarget, setPayoutTarget] = useState<StaffPayoutRemediationTarget | null>(null);
  const [payoutBusy, setPayoutBusy] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [groupBusy, setGroupBusy] = useState(false);
  const bankRow = /^finance-import-row:([1-9][0-9]*)$/.exec(rowIdentity);
  const [kind, setKind] = useState(initialKind);
  const [refundMode, setRefundMode] = useState<keyof typeof refundModes>('exact');
  const [target, setTarget] = useState('');
  const [caseSearch, setCaseSearch] = useState('');
  const [cases, setCases] = useState<{ case_no: string; client_name: string }[]>([]);
  const [caseCursor, setCaseCursor] = useState<string | null>(null);
  const [caseSearching, setCaseSearching] = useState(true);
  const [caseError, setCaseError] = useState('');
  const caseRequest = useRef<AbortController | null>(null);
  const [options, setOptions] = useState<{ id: string; label: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<FinanceImportCorrectionPreview | null>(null);
  const [selection, setSelection] = useState<FinanceImportCorrectionSelection | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [identity] = useState(() => ({ idempotencyKey: `finance-correction-${crypto.randomUUID()}`, correlationId: `finance-correction-${crypto.randomUUID()}` }));
  const [retryCommand, setRetryCommand] = useState<CorrectionCommand | null>(null);
  const closeLocked = busy || payoutBusy || groupBusy || (!!retryCommand && !submitted) || (!!jobId && !completed);
  useEffect(() => { onBusyChange?.(closeLocked); return () => onBusyChange?.(false); }, [closeLocked, onBusyChange]);
  const loadCases = async (query: string, after?: string) => {
    caseRequest.current?.abort();
    const controller = new AbortController(); caseRequest.current = controller;
    setCaseSearching(true); setCaseError('');
    try {
      const page = await ordersQueryClient.getOrderSummaries({ query_text: query, page_size: 50, ...(after ? { after_case_no: after } : {}) }, { signal: controller.signal });
      if (!controller.signal.aborted) {
        setCases(items => after ? [...new Map([...items, ...page.items].map(item => [item.case_no, item])).values()] : page.items);
        setCaseCursor(page.next_cursor);
      }
    } catch { if (!controller.signal.aborted) setCaseError('案件清單載入失敗，請重新搜尋或重試。'); }
    finally { if (!controller.signal.aborted) setCaseSearching(false); }
  };
  useEffect(() => {
    if (kind === 'staff_payout' || kind === 'government_subsidy') { setCaseSearching(false); return; }
    setCases([]); setCaseCursor(null); setCaseSearching(true); setCaseError('');
    const timer = window.setTimeout(() => void loadCases(caseSearch.trim()), 250);
    return () => { window.clearTimeout(timer); caseRequest.current?.abort(); };
  }, [caseSearch, kind]);
  // 政府整期入款狀態
  const currentNow = new Date();
  const [subsidyUnit, setSubsidyUnit] = useState<SubsidyPeriod['unit']>('quarter');
  const [subsidyYear, setSubsidyYear] = useState<number>(currentNow.getFullYear());
  const [subsidyIndex, setSubsidyIndex] = useState<number>(Math.floor(currentNow.getMonth() / 3) + 1);
  const [subsidyView, setSubsidyView] = useState<SubsidyPeriodView | null>(null);
  const [subsidyLoading, setSubsidyLoading] = useState(false);
  const [subsidyError, setSubsidyError] = useState('');
  const [subsidyHandling, setSubsidyHandling] = useState<'exact' | 'partial' | 'refund_excess' | ''>('');
  const [subsidyBalanceId, setSubsidyBalanceId] = useState<string>('');
  const [subsidyConfirmed, setSubsidyConfirmed] = useState(false);

  const loadSubsidyPeriod = async () => {
    setSubsidyLoading(true); setSubsidyError(''); setSubsidyView(null);
    try {
      const data = await subsidyPeriodClient.query({
        unit: subsidyUnit,
        year: subsidyYear,
        index: subsidyIndex,
      });
      setSubsidyView(data);
      setSubsidyHandling('');
      setSubsidyBalanceId(data.balances?.find(b => b.direction === 'receivable')?.identity || '');
      setSubsidyConfirmed(false);
    } catch (err) {
      setSubsidyError(err instanceof Error ? err.message : '整期補助資料載入失敗，請確認期間後重試。');
    } finally {
      setSubsidyLoading(false);
    }
  };

  useEffect(() => {
    if (kind !== 'government_subsidy') return;
    void loadSubsidyPeriod();
  }, [kind, subsidyUnit, subsidyYear, subsidyIndex]);

  const wantedHandling = (() => {
    if (!subsidyView || bankAmount === undefined) return 'exact';
    if (subsidyView.coverage.length === 0) {
      const exp = subsidyView.total_ntd ?? 0;
      if (bankAmount === exp) return 'exact';
      return bankAmount < exp ? 'partial' : 'refund_excess';
    }
    const balance = subsidyView.balances?.find(b => b.identity === subsidyBalanceId);
    if (!balance) return 'exact';
    return bankAmount > balance.remaining_ntd ? 'refund_excess' : 'exact';
  })();

  const applySubsidyPeriod = async () => {
    if (!subsidyView || !bankRow || busy || !subsidyConfirmed) return;
    setBusy(true); setMessage(''); setSubsidyError('');
    try {
      const mode = subsidyView.coverage.length ? 'balance' : 'initial';
      const action = mode === 'initial' ? 'initial_receipt' : 'receipt';
      const handling = wantedHandling === 'exact' ? 'exact' : (subsidyHandling || wantedHandling);
      await subsidyPeriodClient.difference({
        unit: subsidyUnit,
        year: subsidyYear,
        index: subsidyIndex,
        action: action as GovernmentDifferenceCommand['action'],
        identity: mode === 'balance' ? subsidyBalanceId : '',
        amount_ntd: null,
        bank_row_id: Number(bankRow[1]),
        handling: handling as GovernmentDifferenceCommand['handling'],
        reason: reason.trim() || '銀行對帳手動核對政府入款',
        expected_version: subsidyView.version,
        key: crypto.randomUUID(),
      });
      setMessage('政府補助整期入款核銷完成！已確認核銷收據。');
      setCompleted(true);
      onPosted?.();
    } catch (err) {
      setSubsidyError(err instanceof Error ? err.message : '政府入款核銷失敗，請重新整理後重試。');
    } finally {
      setBusy(false);
    }
  };

  const invalidate = () => { setPayoutTarget(null); setPreview(null); setSelection(null); setMessage(''); setSubsidyError(''); };
  const load = async () => {
    if (retryCommand) return;
    setBusy(true); invalidate(); setOptions([]); setSelected([]);
    try {
      if (kind === 'client_receipt') {
        const data = await clientReceiptQueryClient.query(target);
        setOptions(data.obligations.map((item) => ({ id: item.obligation_identity, label: `${data.case_no} · ${{ deposit: '訂金', first: '第一期', second: '第二期', adjustment: '調整款' }[item.payment_stage] ?? item.payment_stage} · NT$ ${item.amount_due_ntd.toLocaleString()}` })));
      } else if (kind === 'client_refund' || kind === 'client_subsidy_return') {
        const data = await clientSettlementRemediationClient.query(target, { includeNotDue: true });
        const obligations = kind === 'client_refund' ? data.refund_obligations : data.subsidy_return_obligations;
        const label = kind === 'client_refund' ? '客戶退款' : '退客戶先墊補助';
        setOptions(obligations.map((item) => ({ id: item.obligation_identity, label: `${data.case_no} · ${label} · 待退 NT$ ${item.amount_due_ntd.toLocaleString()}` })));
      } else {
        const data = await staffPayablesQueryClient.query(Number(target));
        setOptions(data.obligations.filter((item) => item.balance_ntd > 0).map((item) => ({ id: item.obligation_identity, label: `${item.case_no} · 未付 NT$ ${item.balance_ntd.toLocaleString()}` })));
      }
    } catch (error) { setMessage(error instanceof Error ? error.message : '款項查詢失敗。'); }
    finally { setBusy(false); }
  };
  const review = async () => {
    if (retryCommand) return;
    setBusy(true); invalidate();
    const request: FinanceImportCorrectionSelection = { row_identity: rowIdentity, classification_type: kind,
      target_obligation_identities: selected, refund_ledger_entry_identity: null, allow_partial_refund_recovery: kind === 'client_refund' && refundMode === 'partial',
      allow_refund_overage_recovery: kind === 'client_refund' && refundMode === 'overage', allow_client_receipt_overage: false, reason: reason.trim(), evidence: [sourceLabel] };
    try {
      const result = await financeImportCorrectionClient.preview(request);
      if (result.candidate.row_identity !== rowIdentity || result.candidate.classification_type !== kind) throw new Error('更正預覽對象不一致。');
      if (!result.candidate.allocations.length || result.candidate.allocations.some((item) => !selected.includes(item.obligation_identity))) throw new Error('更正預覽包含未選取的款項。');
      setSelection(request); setPreview(result);
    } catch (error) { setMessage(error instanceof Error ? error.message : '更正預覽失敗。'); }
    finally { setBusy(false); }
  };
  const apply = async (checked?: CorrectionCommand) => {
    const command = retryCommand ?? checked ?? (preview && selection ? { preview, selection, identity } : null);
    if (!command || submitted) return;
    setBusy(true); setSubmitted(true);
    try {
      const job = await financeImportCorrectionClient.apply(command.preview, command.selection, command.identity);
      setRetryCommand(null); setJobId(job.job_id); setMessage('更正已受理，正在確認核銷結果。');
      await readOutcome(job.job_id, command.preview);
    }
    catch (error) {
      setRetryCommand(command);
      setSubmitted(false);
      setMessage(`${error instanceof Error ? error.message : '更正結果未知。'} 請使用同一個確認更正操作重新確認。`);
    }
    finally { setBusy(false); }
  };
  const readOutcome = async (selectedJob = jobId, checkedPreview = preview) => {
    if (!selectedJob || !checkedPreview) return;
    setBusy(true);
    try {
      let outcome = await financeImportCorrectionClient.queryOutcome(selectedJob);
      for (let attempt = 0; attempt < 9 && !['succeeded', 'failed', 'cancelled'].includes(outcome.status); attempt++) {
        await new Promise(resolve => setTimeout(resolve, 500));
        outcome = await financeImportCorrectionClient.queryOutcome(selectedJob);
      }
      if (outcome.status === 'succeeded') {
        if (
          !outcome.receipt
          || outcome.receipt.row_identity !== rowIdentity
          || outcome.receipt.batch_identity !== checkedPreview.candidate.batch_identity
          || outcome.receipt.preview_fingerprint !== checkedPreview.preview_fingerprint
        ) throw new Error('更正收據尚未確認，不能判定完成。');
        if (kind === 'client_refund') {
          const fresh = await clientSettlementRemediationClient.query(target, { includeNotDue: true });
          setOptions(fresh.refund_obligations.map((item) => ({ id: item.obligation_identity, label: `${fresh.case_no} · 客戶退款 · 待退 NT$ ${item.amount_due_ntd.toLocaleString()}` })));
          setSelected([]);
          const overage = checkedPreview.candidate.allow_refund_overage_recovery
            && checkedPreview.candidate.bank_amount_ntd > checkedPreview.candidate.allocations.reduce((sum, item) => sum + item.amount_ntd, 0);
          setMessage(overage ? '退款核銷完成；超退金額已另列待追回款，請至案件帳務查看。'
            : fresh.refund_obligations.length ? '退款核銷完成；已更新剩餘待退款，後續清冊只列餘額。' : '退款核銷完成；本案一般退款已退清。');
        } else setMessage('帳務更正完成，已確認核銷收據。');
        setCompleted(true); onPosted?.();
      } else { if (outcome.status === 'failed' || outcome.status === 'cancelled') setCompleted(true); setMessage(outcome.status === 'failed' || outcome.status === 'cancelled' ? '更正未完成，請重新查詢帳務資料。' : '更正仍在處理中。'); }
    } catch (error) { setMessage(error instanceof Error ? error.message : '無法讀取結果。'); }
    finally { setBusy(false); }
  };
  useUnsavedDraft('匯入帳務修正', { '款項類別': kind, '指定對象': target, '選取項目': selected, '退款核銷方式': refundModes[refundMode], '原因': reason }, { enabled: !groupOpen && (kind !== 'staff_payout' || !payoutTarget) && kind !== 'government_subsidy', busy: closeLocked, resetKey: completed, discard: () => { setSelected([]); setTarget(''); setReason(''); setRefundMode('exact'); invalidate(); } });

  return <section aria-label="銀行款項更正" className="order-case-review-note finance-correction-form">
    <p>將這筆銀行紀錄對應至正確的客戶收款、客戶退款、月嫂付款或政府整期入款。金額由後端核對，不可手動標記已付。</p>
    <fieldset disabled={busy || payoutBusy || groupOpen || submitted || retryCommand !== null}>
      <label>款項用途<select value={kind} onChange={(event) => { if (retryCommand) return; setKind(event.target.value as typeof kind); setCaseSearch(''); setRefundMode('exact'); setTarget(''); setOptions([]); setSelected([]); invalidate(); }}><option value="client_receipt">客戶收款</option><option value="client_refund">客戶退款</option><option value="client_subsidy_return">退客戶先墊補助</option><option value="staff_payout">月嫂付款</option><option value="government_subsidy">政府入款</option></select></label>
      {kind === 'government_subsidy' ? (
        <div className="government-subsidy-correction-section" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <label>彙總單位
              <select value={subsidyUnit} onChange={(e) => { setSubsidyUnit(e.target.value as typeof subsidyUnit); setSubsidyIndex(1); }}>
                <option value="month">按月（工會標準）</option>
                <option value="quarter">按季</option>
                <option value="year">按年</option>
              </select>
            </label>
            <label>年度
              <input type="number" min={2020} max={2035} style={{ width: '80px' }} value={subsidyYear} onChange={(e) => setSubsidyYear(Number(e.target.value) || subsidyYear)} />
            </label>
            {subsidyUnit !== 'year' && (
              <label>{subsidyUnit === 'month' ? '月份' : '季度'}
                <select value={subsidyIndex} onChange={(e) => setSubsidyIndex(Number(e.target.value))}>
                  {Array.from({ length: subsidyUnit === 'month' ? 12 : 4 }, (_, i) => (
                    <option key={i + 1} value={i + 1}>{subsidyUnit === 'month' ? `${i + 1} 月` : `第 ${i + 1} 季`}</option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" disabled={subsidyLoading} onClick={() => void loadSubsidyPeriod()}>
              {subsidyLoading ? '查詢中…' : '重新查詢本期補助'}
            </button>
          </div>

          {subsidyLoading && <p role="status">正在查詢政府補助整期資料…</p>}
          {subsidyError && <p role="alert" style={{ color: 'red' }}>{subsidyError}</p>}

          {subsidyView && (
            <div style={{ background: '#f8fafc', padding: '0.75rem', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <p><strong>{subsidyView.label}</strong></p>
              <p>
                本期{subsidyView.coverage.length ? '原已固定' : '目前計算'}應收：
                <strong>{financeMoney(subsidyView.coverage.length ? subsidyView.recorded_lines.reduce((n, l) => n + (l.amount_ntd ?? 0), 0) : (subsidyView.total_ntd ?? 0))}</strong>
                {' · '}銀行本筆入帳：
                <strong>{financeMoney(bankAmount ?? 0)}</strong>
              </p>

              {subsidyView.coverage.length > 0 && (
                <div>
                  {subsidyView.coverage.map(c => (
                    <p key={c.receipt_id} style={{ fontSize: '0.9em', color: '#475569' }}>
                      {c.settled === false ? '已納入本期，差額尚待處理' : '已核銷'} · {c.label} · 實收 {financeMoney(c.amount_ntd)}
                    </p>
                  ))}
                  {subsidyView.balances && subsidyView.balances.length > 0 && (
                    <label>選擇核對的差額款項
                      <select value={subsidyBalanceId} onChange={(e) => setSubsidyBalanceId(e.target.value)}>
                        <option value="">請選擇</option>
                        {subsidyView.balances.map(b => (
                          <option key={b.identity} value={b.identity}>
                            {b.kind === 'original' ? '本期原款' : `${b.case_no} 更正差額`} · 待補撥 {financeMoney(b.remaining_ntd)} · {b.status}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </div>
              )}

              {wantedHandling !== 'exact' && (
                <div style={{ margin: '0.5rem 0' }}>
                  <label>{wantedHandling === 'partial' ? '本次少撥的下一步' : '本次超撥的下一步'}
                    <select value={subsidyHandling || wantedHandling} onChange={(e) => setSubsidyHandling(e.target.value as typeof subsidyHandling)}>
                      {wantedHandling === 'partial' ? (
                        <option value="partial">先記實收，剩餘款項繼續追收補撥</option>
                      ) : (
                        <option value="refund_excess">先記實收，超撥部分列為待退回</option>
                      )}
                    </select>
                  </label>
                </div>
              )}

              {subsidyView.lines && subsidyView.lines.length > 0 && (
                <details style={{ margin: '0.5rem 0' }}>
                  <summary>檢視本期申報案件清單（{subsidyView.lines.length} 筆）</summary>
                  <ul style={{ maxHeight: '180px', overflowY: 'auto', paddingLeft: '1.25rem', margin: '0.5rem 0' }}>
                    {subsidyView.lines.map(line => (
                      <li key={line.case_no}>
                        {line.case_no} · 服務結束：{line.service_end_date} · 金額：{financeMoney(line.amount_ntd ?? 0)}
                        {line.unavailable_reason && <span style={{ color: '#eab308', marginLeft: '0.5rem' }}>（排班/計算待確認）</span>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              <label>核銷備註（選填）
                <input maxLength={500} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="例：銀行對帳手動核對政府入款" />
              </label>

              <div style={{ marginTop: '0.75rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={subsidyConfirmed} onChange={(e) => setSubsidyConfirmed(e.target.checked)} />
                  <span>我已確認整期期別、金額與處理方式無誤</span>
                </label>
              </div>

              <div style={{ marginTop: '0.75rem' }}>
                <button
                  type="button"
                  className="finance-btn-primary"
                  disabled={!subsidyConfirmed || busy || subsidyLoading}
                  onClick={() => void applySubsidyPeriod()}
                >
                  {busy ? '核銷中…' : '確認核銷本期政府入款'}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          {kind !== 'staff_payout' ? <>
            <label>搜尋案件<input type="search" maxLength={50} placeholder="輸入部分案件編號或客戶姓名" value={caseSearch} onChange={(event) => { caseRequest.current?.abort(); setCaseSearch(event.target.value); setCaseSearching(true); setCases([]); setCaseCursor(null); setTarget(''); setOptions([]); setSelected([]); invalidate(); }} /></label>
            <label>案件編號<select value={target} disabled={caseSearching} onChange={(event) => { setTarget(event.target.value); setOptions([]); setSelected([]); invalidate(); }}><option value="">請選擇案件</option>{cases.map(item => <option key={item.case_no} value={item.case_no}>{item.case_no}｜{item.client_name}</option>)}</select></label>
            {caseSearching && <p role="status">正在搜尋案件…</p>}
            {caseError && <div role="alert">{caseError}<button type="button" onClick={() => void loadCases(caseSearch.trim())}>重新載入案件</button></div>}
            {!caseSearching && !caseError && !cases.length && <p role="status">找不到符合的案件，請改用其他編號或客戶姓名搜尋。</p>}
            {caseCursor && <button type="button" disabled={caseSearching} onClick={() => void loadCases(caseSearch.trim(), caseCursor)}>載入更多案件</button>}
          </> : <label>月嫂<select aria-label="月嫂" value={target} onChange={(event) => { if (retryCommand) return; setTarget(event.target.value); setOptions([]); setSelected([]); invalidate(); }}><option value="">請選擇</option>{staff.map((person) => <option key={person.id} value={person.id}>{person.label}</option>)}</select></label>}
          <button type="button" disabled={!target.trim()} onClick={() => void load()}>查詢待核銷款項</button>
          {kind === 'client_receipt' && target && bankRow && (
            <button type="button" onClick={() => { invalidate(); setGroupOpen(true); }}>核對同案多筆入款</button>
          )}
          {options.map((item) => <label key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={() => { if (retryCommand) return; setSelected((items) => items.includes(item.id) ? items.filter((id) => id !== item.id) : [...items, item.id]); invalidate(); }} />{item.label}</label>)}
          {kind === 'staff_payout' && bankRow && <button type="button" disabled={!selected.length} onClick={() => setPayoutTarget({ staffId: Number(target), obligationIdentity: selected[0], obligationIdentities: selected })}>處理付款不足或超額</button>}
          {kind === 'client_refund' && <><label>退款核銷方式<select value={refundMode} onChange={(event) => { setRefundMode(event.target.value as keyof typeof refundModes); invalidate(); }}>{Object.entries(refundModes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>{refundMode === 'overage' && <p>銀行多退的金額會另列待追回款；原銀行支出保留全額。</p>}</>}
          <label>更正原因（選填）<input maxLength={500} value={reason} onChange={(event) => { if (retryCommand) return; setReason(event.target.value); invalidate(); }} /></label>
          <button type="button" disabled={!selected.length} onClick={() => void review()}>預覽核銷</button>
        </>
      )}
    </fieldset>
    {groupOpen && bankRow && (
      <>
        <ClientReceiptReconciliationPanel
          caseNo={target}
          requiredBankRowId={Number(bankRow[1])}
          onBusyChange={setGroupBusy}
          onChanged={() => { setGroupOpen(false); setCompleted(true); onPosted?.(); }}
        />
        <button type="button" disabled={groupBusy} onClick={() => setGroupOpen(false)}>返回單筆核對</button>
      </>
    )}
    {payoutTarget && bankRow && <div><StaffPayoutRemediationWorkbench target={payoutTarget} financeImportRowId={Number(bankRow[1])} onBusyChange={setPayoutBusy} onPosted={() => setSubmitted(true)}/><button type="button" disabled={payoutBusy} onClick={() => setPayoutTarget(null)}>關閉差額核銷</button></div>}
    {preview && <div><p>銀行金額 NT$ {preview.candidate.bank_amount_ntd.toLocaleString()}，將核銷 {preview.candidate.allocations.length} 筆款項。</p><ul>{preview.candidate.allocations.map((item) => <li key={item.obligation_identity}>{options.find((option) => option.id === item.obligation_identity)?.label ?? '待確認款項'}：本次核銷 NT$ {item.amount_ntd.toLocaleString()}</li>)}</ul></div>}
    {preview && selection && !retryCommand && !submitted && (
      <button type="button" disabled={busy} onClick={() => void apply()}>確認核銷</button>
    )}
    {retryCommand && <button type="button" disabled={busy || submitted} onClick={() => void apply()}>以原操作確認更正結果</button>}
    {jobId && <button type="button" disabled={busy} onClick={() => void readOutcome()}>重新查詢更正結果</button>}
    {message && <p role="status">{message}</p>}
  </section>;
}
