import { useUnsavedDraft } from './UnsavedChanges';
import { compareStaffUnionNumbers } from '../adapters/staff/staff_directory_adapter';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { candidateContactPoolClient, type CandidateContactPool } from '../api/scheduling/candidate_contact_pool_client';
import { waitingDepositLockClient, type ActiveWaitingDepositPlan } from '../api/scheduling/waiting_deposit_lock_client';
import { matchingPlanCommunicationClient, type FormalPlanContactState } from '../api/scheduling/matching_plan_communication_client';
import { matchingCandidateWorkflowClient } from '../api/scheduling/matching_candidate_workflow_client';
import { sessionClient } from '../api/auth/session_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { orderMutationFlowStore, type RecommendationReplacementFlowState } from '../adapters/orders/order_mutation_flow_store';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';
import type { ServiceBeforeReplacementApplyResult } from '../api/orders/service_before_replacement_client';

type Props = { caseNo: string; plan: ActiveWaitingDepositPlan; contact: FormalPlanContactState; onClose: () => void;
  onObserved: () => void; onReplacementStarted: () => Promise<void>; onOpenCandidates?: () => void; onEditStateChange: (state: { dirty: boolean; busy: boolean }) => void };
const subscribe = (listener: () => void) => orderMutationFlowStore.subscribe(listener);
const failure = (error: unknown) => error instanceof Error ? error.message : '換人操作暫時無法完成。';

/** Recommendation replacement never rewrites an effective assignment; each existing owner operation keeps its own receipt. */
export function OrderRecommendationReplacementPanel({ caseNo, plan, contact, onClose, onObserved, onReplacementStarted, onOpenCandidates, onEditStateChange }: Props) {
  const flow = useSyncExternalStore(subscribe, () => orderMutationFlowStore.getRecommendationReplacement(caseNo));
  const staffIdentity = useStaffIdentityLabels();
  const [source, setSource] = useState<{ pool: CandidateContactPool; assigned: boolean; started: boolean } | null>(null);
  const [retry, setRetry] = useState(0);
  const [segmentIndex, setSegmentIndex] = useState(0);
  const [staffId, setStaffId] = useState(0);
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<RecommendationReplacementFlowState['command'] | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replacementReceipt, setReplacementReceipt] = useState<ServiceBeforeReplacementApplyResult | null>(null);
  const running = useRef(false);
  const segments = [...(plan.segments ?? [])].sort((a, b) => a.sequence - b.sequence);
  const selectedSegment = segments[segmentIndex];
  const eligible = source?.pool.candidates.filter(candidate => candidate.status === 'active' && candidate.willingness === 'willing'
    && !segments.some(segment => segment.staffId === candidate.staff_id)
    && selectedSegment && candidate.service_start_date <= selectedSegment.assignedStartDate
    && candidate.service_end_date >= selectedSegment.assignedEndDate) ?? [];
  useEffect(() => {
    const controller = new AbortController();
    setSource(null); setError(null);
    void Promise.all([ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal }), candidateContactPoolClient.query(caseNo, { signal: controller.signal })])
      .then(([assignment, pool]) => {
        if (controller.signal.aborted) return;
        if (assignment.case_no !== caseNo || pool.case_no !== caseNo) throw new Error('換人查詢案件識別不一致。');
        setSource({ pool, assigned: assignment.assignments.length > 0, started: assignment.service_started });
      }).catch(caught => { if (!controller.signal.aborted) setError(failure(caught)); });
    return () => controller.abort();
  }, [caseNo, retry]);
  useEffect(() => { if (!source?.assigned && !source?.started) onEditStateChange({ dirty: reason.trim().length > 0, busy: busy || flow !== undefined }); }, [reason, busy, flow, onEditStateChange, source]);
  useEffect(() => () => onEditStateChange({ dirty: false, busy: false }), [onEditStateChange]);

  const inspect = async () => {
    if (running.current || !eligible.some(candidate => candidate.staff_id === staffId) || !reason.trim()) return;
    running.current = true; setBusy(true); setError(null); setPreview(null);
    try {
      const [freshPlan, freshContact, assignment, pool] = await Promise.all([
        waitingDepositLockClient.queryPlan(caseNo), matchingPlanCommunicationClient.queryContactState(caseNo, plan.planId),
        ordersQueryClient.getAssignmentPlan(caseNo), candidateContactPoolClient.query(caseNo),
      ]);
      if (assignment.service_started || assignment.assignments.length) throw new Error('本案已有正式指派，請重新查詢並接續正式換人或代班。');
      if (freshPlan.planId !== plan.planId || freshContact.plan.id !== plan.planId || freshContact.plan.communication_version !== contact.plan.communication_version) throw new Error('推薦進度已變更，請更新狀態後再換人。');
      const freshSegments = [...(freshPlan.segments ?? [])].sort((a, b) => a.sequence - b.sequence);
      if (JSON.stringify(freshSegments) !== JSON.stringify(segments)) throw new Error('推薦人員或日期已變更，請更新後再選擇。');
      const target = pool.candidates.find(candidate => candidate.staff_id === staffId && candidate.status === 'active' && candidate.willingness === 'willing');
      if (!target || !selectedSegment || target.service_start_date > selectedSegment.assignedStartDate || target.service_end_date < selectedSegment.assignedEndDate) throw new Error('接任月嫂的意願或服務期間已變更，請重新查詢。');
      const release = freshPlan.activeLockId === null ? null : await waitingDepositLockClient.previewRelease(caseNo, plan.planId, freshPlan.activeLockId);
      if (release && (!release.apply_allowed || release.case_no !== caseNo || release.plan_id !== plan.planId || release.lock_id !== freshPlan.activeLockId)) throw new Error('目前不能釋放檔期，請先確認訂金、正式服務與檔期狀態。');
      const actor = sessionClient.getUser()?.username.trim();
      if (!actor) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
      setPreview({ caseNo, planId: plan.planId, expectedVersion: freshContact.plan.communication_version, actor, reason: reason.trim(), lockId: freshPlan.activeLockId, originalPlan: freshPlan, originalContact: freshContact,
        releaseFingerprint: release?.preview_fingerprint ?? null,
        releaseKey: `recommendation-release-${crypto.randomUUID()}`, cancelKey: `recommendation-cancel-${crypto.randomUUID()}`, createKey: `recommendation-create-${crypto.randomUUID()}`,
        asOf: new Date().toISOString().slice(0, 10), segments: freshSegments.map((segment, index) => ({ staff_id: index === segmentIndex ? staffId : segment.staffId, start_date: segment.assignedStartDate, end_date: segment.assignedEndDate })) });
      setConfirmed(false);
    } catch (caught) { setError(failure(caught)); }
    finally { running.current = false; setBusy(false); }
  };
  const persist = (value: RecommendationReplacementFlowState) => { orderMutationFlowStore.setRecommendationReplacement(caseNo, value); return value; };
  const cancelOriginal = async (value: RecommendationReplacementFlowState) => {
    if (running.current) return;
    running.current = true; setBusy(true); setError(null);
    let current = persist(value);
    try {
      const command = current.command;
      if (sessionClient.getUser()?.username.trim() !== command.actor) throw new Error('請以原操作帳號確認換人結果。');
      if (!current.released && command.lockId !== null) {
        const receipt = await waitingDepositLockClient.release(caseNo, command.planId, command.lockId, command.releaseFingerprint!, command.reason, command.releaseKey, command.actor);
        if (receipt.case_no !== caseNo || receipt.plan_id !== command.planId || receipt.lock_id !== command.lockId || receipt.lock_status !== 'released') throw new Error('檔期釋放回條識別不一致，請確認原操作結果。');
        current = persist({ ...current, released: true, stage: 'cancel', error: null });
      }
      if (!current.cancelled) {
        current = persist({ ...current, stage: 'cancel' });
        const receipt = await matchingPlanCommunicationClient.cancelRecommendation(caseNo, command.planId, command.expectedVersion, command.reason, command.cancelKey, command.actor);
        current = persist({ ...current, cancelled: true, cancellationEventId: receipt.event_id, stage: 'ready', error: null });
      }
      try {
        await waitingDepositLockClient.queryPlan(caseNo);
        throw new Error('目前又有其他有效推薦方案，請確認原操作結果後再接續。');
      } catch (caught) { if (!(caught instanceof ApiHttpError && caught.status === 404)) throw caught; }
      persist({ ...current, stage: 'ready', error: null });
    } catch (caught) {
      const message = failure(caught); setError(message);
      if (!current.released && !current.cancelled && caught instanceof ApiHttpError && caught.status >= 400 && caught.status < 500 && ![408, 429].includes(caught.status)) {
        orderMutationFlowStore.clearRecommendationReplacement(caseNo); setPreview(null); setConfirmed(false);
      } else persist({ ...current, error: message });
    } finally { running.current = false; setBusy(false); }
  };
  const createSuccessor = async (value: RecommendationReplacementFlowState) => {
    if (running.current || !value.cancelled) return;
    running.current = true; setBusy(true); setError(null);
    let current = persist({ ...value, stage: value.receipt ? 'observe' : 'create', error: null });
    try {
      const command = { caseNo, actor: value.command.actor, asOf: value.command.asOf, key: value.command.createKey, segments: value.command.segments };
      if (sessionClient.getUser()?.username.trim() !== command.actor) throw new Error('請以原操作帳號接續新推薦。');
      let receipt = current.receipt;
      if (!receipt) {
        try { receipt = await matchingCandidateWorkflowClient.queryMatchingPlanReceipt(command); }
        catch (caught) {
          if (!(caught instanceof ApiHttpError && caught.status === 404)) throw caught;
          receipt = command.segments.length === 1 ? await matchingCandidateWorkflowClient.createSingleCaregiverPlan(command) : await matchingCandidateWorkflowClient.createMatchingPlan(command);
        }
        current = persist({ ...current, receipt, stage: 'observe' });
      }
      if (receipt.case_no !== caseNo || receipt.actor !== command.actor || receipt.event_key !== command.key || receipt.as_of !== command.asOf
        || receipt.segments.length !== command.segments.length || receipt.segments.some((segment, index) => segment.staff_id !== command.segments[index].staff_id || segment.assigned_start_date !== command.segments[index].start_date || segment.assigned_end_date !== command.segments[index].end_date)) throw new Error('新推薦回條與原操作不一致，請重新讀取原結果。');
      const observed = await waitingDepositLockClient.queryPlan(caseNo);
      if (observed.planId !== receipt.plan_id || (observed.planVersion ?? -1) < receipt.version || observed.segments?.length !== command.segments.length
        || [...observed.segments].sort((a, b) => a.sequence - b.sequence).some((segment, index) => segment.staffId !== command.segments[index].staff_id || segment.assignedStartDate !== command.segments[index].start_date || segment.assignedEndDate !== command.segments[index].end_date)) throw new Error('新推薦已建立，但回讀尚未確認原人員與日期，請重新讀取。');
      orderMutationFlowStore.clearRecommendationReplacement(caseNo); onObserved();
    } catch (caught) {
      const message = failure(caught); setError(message);
      persist({ ...current, error: message, stage: !current.receipt && caught instanceof ApiHttpError && caught.status === 409 && caught.code === 'matching_plan_staff_occupancy_conflict' ? 'reselect' : current.stage });
    }
    finally { running.current = false; setBusy(false); }
  };
  const reselectSuccessor = async (value: RecommendationReplacementFlowState) => {
    if (running.current || value.stage !== 'reselect') return;
    running.current = true; setBusy(true); setError(null);
    try {
      const command = { caseNo, actor: value.command.actor, asOf: value.command.asOf, key: value.command.createKey, segments: value.command.segments };
      if (sessionClient.getUser()?.username.trim() !== command.actor) throw new Error('請以原操作帳號確認換人結果。');
      try {
        const receipt = await matchingCandidateWorkflowClient.queryMatchingPlanReceipt(command);
        persist({ ...value, receipt, stage: 'observe', error: null });
        return;
      } catch (caught) { if (!(caught instanceof ApiHttpError && caught.status === 404)) throw caught; }
      try {
        await waitingDepositLockClient.queryPlan(caseNo);
        throw new Error('本案已有其他有效推薦，請先確認目前推薦狀態。');
      } catch (caught) { if (!(caught instanceof ApiHttpError && caught.status === 404)) throw caught; }
      await onReplacementStarted();
      orderMutationFlowStore.clearRecommendationReplacement(caseNo);
    } catch (caught) { const message = failure(caught); setError(message); persist({ ...value, error: message }); }
    finally { running.current = false; setBusy(false); }
  };
  useUnsavedDraft('更換推薦月嫂', { '照護段': segmentIndex, '月嫂': staffId, '原因': reason }, { busy: busy || flow !== undefined, resetKey: replacementReceipt });

  if (source?.started) return <section className="formal-recommendation-inline-form"><h4>本案已有實際服務</h4><p>請由請假代班安排接續人員，保留原月嫂的服務與薪資紀錄。</p><a href={`#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`}>前往請假代班 →</a></section>;
  const continueReplacement = async (result: ServiceBeforeReplacementApplyResult) => {
    setReplacementReceipt(result); setError(null); setBusy(true);
    try {
      if (result.readback.case_no !== caseNo || !['applied', 'replayed'].includes(result.status)) throw new Error('換人回條與本案不一致，請重新確認原操作結果。');
      await onReplacementStarted();
    } catch (caught) { setError(failure(caught)); }
    finally { setBusy(false); }
  };
  if (source?.assigned) return <>
    <ServiceBeforeReplacementActions caseNo={caseNo} initialScenario="R-04" hideScenarioPicker onEditStateChange={onEditStateChange} onCommitted={continueReplacement} onSubstitutionReferral={() => { window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`; }} />
    {error && replacementReceipt && <div role="alert"><p>{error}</p><button type="button" disabled={busy} onClick={() => void continueReplacement(replacementReceipt)}>重新讀取換人後的推薦進度</button></div>}
  </>;
  return <section className="formal-recommendation-inline-form" aria-label="更換月嫂">
    <header className="formal-recommendation-summary"><h4>更換月嫂</h4>{!flow && <button type="button" disabled={busy} onClick={onClose}>取消</button>}</header>
    {!source && !error && <p role="status">正在確認本案指派與可接任人選…</p>}
    {error && <div role="alert">{error}{!flow && !source && <button type="button" onClick={() => setRetry(value => value + 1)}>重新查詢</button>}</div>}
    {flow ? <>
      {flow.stage === 'reselect' ? <><p>新推薦因檔期衝突未能建立。原推薦與回覆紀錄已保留；請改選月嫂，或調整服務日期後重新查詢。</p><button type="button" disabled={busy} onClick={() => void reselectSuccessor(flow)}>返回改選月嫂</button></>
        : flow.stage === 'ready' && !flow.error ? <><p>換人已啟動，原推薦與回覆紀錄已保留。請接續建立新推薦，再交由客戶確認。</p><button className="formal-recommendation-primary" type="button" disabled={busy} onClick={() => void createSuccessor(flow)}>建立新推薦並交客戶確認</button></>
        : <><p>原操作結果尚需確認；保留原人員、日期及操作編號，不重複建立新操作。</p><button type="button" disabled={busy} onClick={() => void (flow.cancelled && flow.stage !== 'ready' ? createSuccessor(flow) : cancelOriginal(flow))}>{flow.stage === 'observe' ? '重新讀取新推薦結果' : '重新確認原換人操作'}</button></>}
    </> : source && <>
      {preview ? <><h4>確認換人影響</h4><p>只更換選定段落的人員，其餘服務日期保留。</p><ul><li>原推薦、意願及客戶回覆紀錄保留。</li><li>新推薦需重新取得客戶確認。</li>{preview.lockId !== null && <li>先依正式流程釋放原檔期，再重新確認契約與服務安排。</li>}</ul><label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />我已確認換人原因及影響</label><div className="formal-recommendation-actions"><button className="formal-recommendation-primary" type="button" disabled={busy || !confirmed} onClick={() => void cancelOriginal({ command: preview, stage: preview.lockId === null ? 'cancel' : 'release', released: false, cancelled: false, cancellationEventId: null, receipt: null, error: null })}>確認啟動換人</button><button type="button" disabled={busy} onClick={() => setPreview(null)}>返回修改</button></div></>
        : <>
          {segments.length > 1 && <label>要更換的服務段落<select value={segmentIndex} disabled={busy} onChange={event => { setSegmentIndex(Number(event.target.value)); setStaffId(0); }}>{segments.map((segment, index) => ({ segment, index })).sort((a, b) => staffIdentity.compare(a.segment.staffId, b.segment.staffId)).map(({ segment, index }) => <option key={segment.segmentId} value={index}>第 {index + 1} 段・{staffIdentity.label(segment.staffId, contact.segments.find(item => item.segment_id === segment.segmentId)?.staff_name, contact.segments.find(item => item.segment_id === segment.segmentId)?.staff_union_no)}</option>)}</select></label>}
          <fieldset aria-label="選擇新月嫂"><legend>選擇新月嫂</legend>{[...eligible].sort((a, b) => compareStaffUnionNumbers({ id: a.staff_id, unionNo: a.staff_union_no }, { id: b.staff_id, unionNo: b.staff_union_no })).map(candidate => <label key={candidate.id} className="formal-recommendation-replacement-option"><input type="radio" name={`replacement-${caseNo}`} value={candidate.staff_id} checked={staffId === candidate.staff_id} disabled={busy} onChange={() => setStaffId(candidate.staff_id)} /><span><strong>{staffIdentity.label(candidate.staff_id, candidate.staff_name, candidate.staff_union_no)}</strong><small>{candidate.service_start_date} ～ {candidate.service_end_date}</small></span><span>已願意承接</span></label>)}{eligible.length === 0 && <p>目前沒有符合此段期間、且已願意承接的新月嫂。請先到「尋找月嫂與詢問意願」新增並確認人選。{onOpenCandidates && <button type="button" disabled={busy} onClick={onOpenCandidates}>前往尋找月嫂與詢問意願</button>}</p>}</fieldset>
          <label>換人原因（必填）<textarea value={reason} maxLength={255} disabled={busy} onChange={event => setReason(event.target.value)} placeholder="請填寫客戶要求或月嫂通知內容" /></label><button className="formal-recommendation-primary" type="button" disabled={busy || !staffId || !reason.trim()} onClick={() => void inspect()}>檢查換人影響</button>
        </>}
    </>}
  </section>;
}
