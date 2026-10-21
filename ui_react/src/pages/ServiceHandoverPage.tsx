import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { OrderDetail, AssignmentPlan } from '../api/orders/order_query_schemas';
import { loadAllStaffDirectoryPages, staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import type { StaffDirectorySummary } from '../api/staff_directory/staff_directory_schemas';
import type { LeaveSubstitutionAssignment, LeaveSubstitutionPreviewRequest } from '../api/scheduling/leave_substitution_schemas';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import { leaveSubstitutionFlowStore } from '../adapters/scheduling/leave_substitution_flow_store';
import { applyLeaveSubstitutionFlow, previewLeaveSubstitutionFlow, queryLeaveSubstitutionFlow,
  retryLeaveSubstitutionApplyFlow, retryLeaveSubstitutionObservationFlow,
  setLeaveSubstitutionDraft } from '../adapters/scheduling/leave_substitution_flow_adapter';
import { useUnsavedDraft } from '../components/UnsavedChanges';
import { parseServiceHandoverLink } from '../adapters/scheduling/service_handover_navigation';
import './ServiceHandoverPage.css';

const lockedStatuses = new Set(['apply_pending', 'outcome_unknown', 'receipt_received', 'requery_loading', 'observation_failed']);
const money = (value: number) => `NT$ ${value.toLocaleString('zh-TW')}`;
const dateLabel = (value: string) => value.replaceAll('-', '/');
const errorMessage = (caught: unknown) => caught instanceof Error ? caught.message : '資料暫時無法取得，請重新查詢。';
const blockers: Record<string, string> = {
  handover_paid_adjustment_review_required: '原月嫂有已付款的獨立調整款，請先至本案帳務核對，再辦理換人。',
  handover_adjustment_review_required: '原調整款超過換人後的服務應付，請先至本案帳務核對。',
  handover_recovery_adjustment_required: '這次安排需要調整既有追償，請先至本案帳務核對。',
  handover_obligation_lineage_ambiguous: '原應付紀錄的承接關係不唯一，請先核對本案帳務。',
  payroll_adjustment_owner_ambiguous: '原調整款無法唯一承接給原月嫂，請先核對本案帳務。',
  assignment_limit_exceeded: '交接後會超過四段有效服務安排，請先核對既有分段。',
  client_finance_bootstrap_required: '本案客戶帳務尚未建立，請先完成帳務建置。',
  payroll_bootstrap_required: '本案月嫂帳務尚未建立，請先完成帳務建置。',
  handover_historical_payment_review_required: '本案有歷史付款或結清證據，請先由本案帳務核對換人後應付。',
  handover_paid_history_review_required: '付款歷史與月嫂應付紀錄不一致，請先核對本案帳務。',
  payroll_rate_snapshot_mismatch: '月嫂的薪資費率紀錄不一致，請先核對本案帳務。',
  payroll_special_pay_lineage_mismatch: '雙薪約定與薪資紀錄不一致，請先核對本案帳務。',
  invalid_payroll_facts: '月嫂帳務資料無法一致銜接，請先核對本案帳務。',
};

export function ServiceHandoverPage() {
  const link = parseServiceHandoverLink(window.location.hash);
  if (!link) return <main className="service-handover-page"><h1>無法開啟服務中換人</h1><p role="alert">缺少有效的案件或原服務指派，請從原案件的服務安排重新開啟。</p><a href="#order-workbench-v2">返回代辦看板</a></main>;
  return <HandoverWorkspace key={`${link.caseNo}:${link.assignmentId}`} {...link} />;
}

function HandoverWorkspace({ caseNo, assignmentId: linkedAssignmentId }: { caseNo: string; assignmentId: number | null }) {
  const initial = useRef((() => {
    const saved = leaveSubstitutionFlowStore.get(caseNo);
    return saved && (lockedStatuses.has(saved.status) || (saved.previewRequest?.handover_date
      && saved.previewRequest.original_assignment_id === linkedAssignmentId)) ? saved : undefined;
  })());
  const [, refreshFlow] = useState(0);
  useEffect(() => leaveSubstitutionFlowStore.subscribe(() => refreshFlow(value => value + 1)), []);
  const flow = leaveSubstitutionFlowStore.get(caseNo);
  const pending = flow !== undefined && lockedStatuses.has(flow.status);
  const pendingTemporary = pending && !flow?.previewRequest?.handover_date;
  const [context, setContext] = useState<{ detail: OrderDetail; plan: AssignmentPlan; staff: StaffDirectorySummary[] } | null>(null);
  const [assignments, setAssignments] = useState<readonly LeaveSubstitutionAssignment[]>(initial.current?.assignments ?? []);
  const [assignmentId, setAssignmentId] = useState<number | null>(initial.current?.previewRequest?.handover_date
    ? initial.current.previewRequest.original_assignment_id : linkedAssignmentId);
  const [handoverDate, setHandoverDate] = useState(initial.current?.previewRequest?.handover_date ?? '');
  const [successorId, setSuccessorId] = useState<number | null>(initial.current?.previewRequest?.handover_date
    ? initial.current.previewRequest.items[0]?.substitute_staff_id ?? null : null);
  const [reason, setReason] = useState(initial.current?.applyRequest?.reason ?? '');
  const finished = flow?.status === 'observed' && handoverDate !== ''
    && flow.previewRequest?.handover_date === handoverDate
    && flow.previewRequest.original_assignment_id === assignmentId;
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const running = useRef(false);
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const returnHref = `#order-workbench-v2?case=${encodeURIComponent(caseNo)}&work=service`;
  const financeHref = `#finance?tab=staff-payables&case_no=${encodeURIComponent(caseNo)}&from=workbench`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError(null);
    const existing = leaveSubstitutionFlowStore.get(caseNo);
    const keep = existing !== undefined && (lockedStatuses.has(existing.status)
      || (existing.status === 'observed' && existing.previewRequest?.handover_date && initial.current === existing));
    void Promise.all([
      ordersQueryClient.getOrderDetail(caseNo, { signal: controller.signal }),
      ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal }),
      loadAllStaffDirectoryPages(staffDirectoryClient.queryPage.bind(staffDirectoryClient), { pageSize: 200 }, { signal: controller.signal }),
      keep ? Promise.resolve(existing.assignments ?? []) : queryLeaveSubstitutionFlow(caseNo, { signal: controller.signal }),
    ]).then(([detail, plan, staff, rows]) => {
      if (controller.signal.aborted) return;
      if (detail.case_no !== caseNo || plan.case_no !== caseNo) throw new Error('取得的資料與本案不一致，請從原案件重新開啟。');
      setContext({ detail, plan, staff: staff.items.sort(compareStaffUnionNumbers) }); setAssignments(rows);
      setAssignmentId(value => value ?? (rows.length === 1 ? rows[0].assignment_id : null));
    }).catch(caught => { if (!controller.signal.aborted) setLoadError(errorMessage(caught)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, revision]);

  useEffect(() => {
    if (flow?.status === 'observed' && !flow.previewRequest?.handover_date) setRevision(value => value + 1);
  }, [flow?.status, flow?.previewRequest?.handover_date]);

  const source = assignments.find(item => item.assignment_id === assignmentId);
  const previewRequest = useMemo<LeaveSubstitutionPreviewRequest | null>(() => {
    if (!source || !handoverDate || successorId === null || handoverDate < today || successorId === source.staff_id) return null;
    const days = source.official_schedules.filter(day => day.work_date >= handoverDate);
    if (!days.length) return null;
    return { original_assignment_id: source.assignment_id, handover_date: handoverDate,
      items: days.map(day => ({ original_schedule_id: day.schedule_id, work_date: day.work_date,
        resolution_type: 'substitute', substitute_staff_id: successorId, is_double_pay: day.is_double_pay ?? false })),
      leave_request_id: null, expected_leave_request_version: null };
  }, [source, handoverDate, successorId, today]);

  useEffect(() => {
    if (!previewRequest || loading || pending || finished || !context?.plan.service_started
      || leaveSubstitutionFlowStore.get(caseNo)?.status === 'stale') return;
    const controller = new AbortController();
    setOperationError(null);
    setLeaveSubstitutionDraft(caseNo, previewRequest);
    const timeout = window.setTimeout(() => {
      void previewLeaveSubstitutionFlow(caseNo, { signal: controller.signal }).catch(caught => {
        if (!controller.signal.aborted) setOperationError(errorMessage(caught));
      });
    }, 200);
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [caseNo, previewRequest, loading, pending, finished, context?.plan.service_started]);

  const matchesDraft = flow?.previewRequest?.handover_date === handoverDate
    && flow?.previewRequest?.original_assignment_id === assignmentId
    && flow?.previewRequest?.items[0]?.substitute_staff_id === successorId;
  const preview = matchesDraft ? flow?.preview : null;
  const accounting = preview?.accounting;
  const ready = !loading && !loadError && context?.plan.service_started && !pending && !finished && !saving && flow?.status === 'preview_ready'
    && matchesDraft && previewRequest !== null && preview?.apply_readiness.status === 'ready' && accounting != null;
  useUnsavedDraft('服務中換人', { '原月嫂服務段': assignmentId, '交接日期': handoverDate, '接任月嫂': successorId, '原因': reason }, {
    enabled: !finished, busy: pending || saving, resetKey: finished,
  });

  const submit = useCallback(async (retry: 'apply' | 'observe' | null = null) => {
    if (running.current) return;
    running.current = true; setSaving(true); setOperationError(null);
    try {
      if (retry === 'apply') await retryLeaveSubstitutionApplyFlow(caseNo);
      else if (retry === 'observe') await retryLeaveSubstitutionObservationFlow(caseNo);
      else {
        if (!ready || !previewRequest || !preview) return;
        await applyLeaveSubstitutionFlow(caseNo, { ...previewRequest,
          expected_order_version: preview.order_version, expected_scheduling_version: preview.scheduling_version,
          expected_client_finance_version: preview.client_finance_version, expected_payroll_version: preview.payroll_version,
          preview_fingerprint: preview.preview_fingerprint, reason: reason.trim() });
      }
    } catch (caught) { setOperationError(errorMessage(caught)); }
    finally { running.current = false; setSaving(false); }
  }, [caseNo, ready, previewRequest, preview, reason]);
  const label = (id: number) => {
    const person = context?.staff.find(item => item.id === id);
    return person ? staffDisplayLabel(person.union_no, person.name ?? '姓名未設定') : '月嫂資料尚未取得';
  };
  const refresh = () => { setOperationError(null); setRevision(value => value + 1); };

  return <main className="service-handover-page">
    <a className="handover-back" href={returnHref}>← 返回本案服務安排</a>
    <header className="handover-heading"><div><p className="handover-eyebrow">服務安排 ／ 人員交接</p><h1>服務中換人</h1>
      <p>從交接日起，由新月嫂接續原月嫂的剩餘服務。</p></div><div><span className="handover-case-badge">{caseNo}</span><button className="handover-refresh" type="button" disabled={loading || pending || saving || finished} onClick={refresh}>重新查詢本案</button></div></header>
    <section className="handover-case-summary" aria-label="本案服務摘要">
      <div><small>客戶</small><strong>{context?.detail.client_name ?? '讀取中…'}</strong></div>
      <div><small>約定服務</small><strong>{context ? `${context.detail.service_days} 日 · 每日 ${context.detail.service_hours_per_day} 小時` : '讀取中…'}</strong></div>
      <div><small>原服務月嫂</small><strong>{source ? label(source.staff_id) : '請選擇原服務段'}</strong></div>
      <div><small>原服務期間</small><strong>{source ? `${dateLabel(source.assigned_start_date)} — ${dateLabel(source.assigned_end_date)}` : '尚未選擇'}</strong></div>
    </section>
    {loading && <p role="status">正在取得本案排班與月嫂資料…</p>}
    {loadError && <div role="alert" className="handover-alert">{loadError}<button type="button" disabled={pending} onClick={refresh}>重新查詢最新資料</button></div>}
    {pendingTemporary && <p role="status" className="handover-alert">本案有一筆臨時代班尚待確認，請先查核原操作結果，再辦理服務中換人。</p>}
    {!loading && !pending && !finished && !source && assignments.length > 0 && <p role="alert" className="handover-alert">原服務指派已變更，請重新選擇這次要交接的服務段。</p>}
    {!loading && !loadError && assignments.length === 0 && <p role="status">本案目前沒有可交接的正式服務指派，請返回本案核對服務安排。</p>}
    {!loading && context && !context.plan.service_started && !pending && !finished && <div role="alert" className="handover-alert">本案尚未開始服務，請由原案件辦理服務前更換月嫂。<a href={returnHref}>返回本案</a></div>}
    {finished && <section role="status" className="handover-success"><h2>換人安排已儲存</h2><p>已取得正式收據並重新讀取排班；原服務與付款紀錄已保留。請依原付款日接續帳務處理。</p><a href={returnHref}>返回本案服務安排 →</a></section>}
    {!finished && <>
      <section className="handover-card" aria-labelledby="handover-arrangement-title"><div className="handover-section-title"><span>01</span><div><h2 id="handover-arrangement-title">交接安排</h2><p>含交接日，只調整這位原月嫂剩餘的正式服務日。</p></div></div>
        <fieldset disabled={loading || pending || saving || !context?.plan.service_started} className="handover-fields">
          {(assignments.length > 1 || (assignments.length > 0 && !source)) && <label>原月嫂服務段<select value={source ? assignmentId ?? '' : ''} onChange={event => setAssignmentId(Number(event.target.value) || null)}><option value="">請選擇原服務段</option>{assignments.map(item => <option key={item.assignment_id} value={item.assignment_id}>{label(item.staff_id)} · {item.assigned_start_date} 至 {item.assigned_end_date}</option>)}</select></label>}
          <label>交接日期<input type="date" min={today} max={source?.assigned_end_date} value={handoverDate} onChange={event => setHandoverDate(event.target.value)} /><small>此日期起的剩餘服務交由接任月嫂。</small></label>
          <label>接任月嫂<select value={successorId ?? ''} onChange={event => setSuccessorId(Number(event.target.value) || null)}><option value="">請選擇接任月嫂</option>{context?.staff.filter(item => item.id !== source?.staff_id).map(item => <option key={item.id} value={item.id}>{staffDisplayLabel(item.union_no, item.name ?? '姓名未設定')}</option>)}</select><small>儲存前會檢查正式服務日期與檔期。</small></label>
          <label className="handover-reason">換人原因／備註 <span>選填</span><textarea rows={2} maxLength={500} value={reason} onChange={event => setReason(event.target.value)} placeholder="例如原月嫂因個人因素無法接續服務" /></label>
        </fieldset>
        {handoverDate && handoverDate < today && <p role="alert">交接日期不能早於今天，已服務日期需由原服務更正流程處理。</p>}
        {source && handoverDate >= today && !source.official_schedules.some(day => day.work_date >= handoverDate) && <p role="alert">交接日之後已沒有這位月嫂的正式服務日。</p>}
      </section>
      <section className="handover-card" aria-labelledby="handover-dates-title"><div className="handover-section-title"><span>02</span><div><h2 id="handover-dates-title">服務日期如何銜接</h2><p>依正式服務日顯示；已服務與其他月嫂的日期一併保留。</p></div></div>
        {preview ? <div className="handover-date-grid">{preview.assignments.map(item => <article key={item.candidate_key}><h3>{label(item.staff_id)}{item.staff_id === successorId && <em>接任</em>}</h3><p>{dateLabel(item.assigned_start_date)} — {dateLabel(item.assigned_end_date)} · {item.official_service_dates.length} 日</p><div className="handover-date-chips">{item.official_service_dates.map(day => <span key={day}>{dateLabel(day)}</span>)}</div></article>)}</div>
          : <p className="handover-empty">選擇交接日期與接任月嫂後，自動檢查服務銜接。</p>}
      </section>
      <section className="handover-card" aria-labelledby="handover-money-title"><div className="handover-section-title"><span>03</span><div><h2 id="handover-money-title">月嫂帳務影響</h2><p>原付款紀錄保留，依各自服務計算應付；換人儲存不代表付款。</p></div></div>
        {accounting ? <div className="handover-money-grid">{accounting.staff.map(item => <article className="handover-money-person" key={item.staff_id}><h3>{label(item.staff_id)}{item.staff_id === successorId && <em>接任</em>}</h3>
          <table><caption className="sr-only">{label(item.staff_id)}的帳務前後比較</caption><thead><tr><th scope="col">項目</th><th scope="col">換人前</th><th scope="col">換人後</th></tr></thead><tbody>
            {([['服務薪資', 'salary_ntd'], ['樓層費', 'floor_fee_ntd'], ['既有調整款', 'adjustment_ntd'], ['應付合計', 'total_ntd']] as const).map(([title, key]) => <tr key={key}><th scope="row">{title}</th><td>{money(item.before[key])}</td><td>{money(item.after[key])}</td></tr>)}
          </tbody></table><dl><div><dt>已付淨額（付款／退回）</dt><dd>{money(item.paid_net_ntd)}</dd></div><div className="handover-payable"><dt>換人後尚待付款</dt><dd>{money(item.payable_after_ntd)}</dd></div><div><dt>本次新增追償</dt><dd>{money(item.recovery_increase_ntd)}</dd></div><div><dt>追償未收回合計</dt><dd>{money(item.recovery_after_ntd)}</dd></div><div><dt>原付款日</dt><dd>{item.payment_due_date ? dateLabel(item.payment_due_date) : '尚未形成'}</dd></div></dl>
          {item.recovery_increase_ntd > 0 && <p className="handover-recovery-note">將建立獨立追償，不抵扣接任月嫂薪資。</p>}
        </article>)}</div> : <p className="handover-empty">完成交接安排後，顯示薪資、既有調整款與實付差額。無法確認的帳務不會以零元帶入。</p>}
      </section>
      <section className="handover-card" aria-labelledby="handover-client-title"><div className="handover-section-title"><span>04</span><div><h2 id="handover-client-title">客戶帳款影響</h2><p>依本案正式帳務核對應收差額。</p></div></div>{accounting ? <dl className="handover-client-money"><div><dt>原應收合計</dt><dd>{money(accounting.client.before_ntd)}</dd></div><div><dt>換人後應收</dt><dd>{money(accounting.client.after_ntd)}</dd></div><div><dt>本次差額</dt><dd>{money(accounting.client.difference_ntd)}</dd></div><div><dt>已核銷淨額</dt><dd>{money(accounting.client.settled_ntd)}</dd></div></dl> : <p className="handover-empty">等待正式帳務檢查。</p>}</section>
      {flow?.status === 'preview_loading' && <p role="status">正在核對檔期、日期與帳務影響…</p>}
      {preview?.apply_readiness.blockers.length ? <div role="alert" className="handover-alert"><strong>目前需要先處理以下事項</strong><ul>{preview.apply_readiness.blockers.map(code => <li key={code}>{blockers[code] ?? '本案服務或帳務資料目前無法確認，請先核對原案件後重新查詢。'}</li>)}</ul><a href={financeHref}>查看本案帳務 →</a></div> : null}
      {(operationError || flow?.error) && <div role="alert" className="handover-alert"><p>{operationError ?? flow?.error?.message}</p>{flow?.status === 'stale' && <button type="button" onClick={refresh}>重新查詢最新資料</button>}</div>}
      <footer className="handover-save-bar"><div><strong>{pendingTemporary ? '正在確認既有臨時代班' : pending ? '正在確認這筆換人操作' : '核對交接日期與帳務後即可儲存'}</strong><p>保留原服務與付款歷史，依原付款日辦理。</p></div>
        {flow?.status === 'outcome_unknown' ? <button type="button" disabled={saving} onClick={() => void submit('apply')}>{pendingTemporary ? '確認既有代班結果' : '再次確認變更結果'}</button>
          : flow?.status === 'observation_failed' ? <button type="button" disabled={saving} onClick={() => void submit('observe')}>重新讀取已儲存安排</button>
          : <button type="button" disabled={!ready} onClick={() => void submit()}>{saving || flow?.status === 'apply_pending' ? '正在儲存…' : '儲存換人安排'}</button>}
      </footer>
    </>}
  </main>;
}
