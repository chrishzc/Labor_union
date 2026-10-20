import { useEffect, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { createStaffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import type { StaffDirectorySummary } from '../api/staff_directory/staff_directory_schemas';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';
import type { ServiceBeforeReplacementScenario } from '../api/orders/service_before_replacement_client';
import { ClientRegistryReplacementCandidates } from './ClientRegistryReplacementCandidates';
import { OrderActualStartPanel } from './OrderActualStartPanel';
import { staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';

interface Props {
  caseNo: string;
  revision: object;
  disabled: boolean;
  onCommitted: () => Promise<void>;
  onStateChange: (state: { dirty: boolean; busy: boolean }) => void;
  onOpenServiceArrangement?: (recalculateDates: boolean) => void;
}

export function ClientRegistryServiceStaff({ caseNo, revision, disabled, onCommitted, onStateChange, onOpenServiceArrangement }: Props) {
  const [plan, setPlan] = useState<AssignmentPlan | null>(null);
  const [historicalOrder, setHistoricalOrder] = useState<boolean | null>(null);
  const [people, setPeople] = useState<Record<number, StaffDirectorySummary>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nameError, setNameError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [replacementScenario, setReplacementScenario] = useState<ServiceBeforeReplacementScenario>();
  const [choosing, setChoosing] = useState(false);
  const [correctingStart, setCorrectingStart] = useState(false);
  const [startState, setStartState] = useState({ dirty: false, busy: false });
  const [startNotice, setStartNotice] = useState('');
  const [recalculateDates, setRecalculateDates] = useState(false);
  const [replacementState, setReplacementState] = useState({ dirty: false, busy: false });
  const [candidateState, setCandidateState] = useState({ dirty: false, busy: false });
  useEffect(() => {
    onStateChange({ dirty: replacementState.dirty || candidateState.dirty || startState.dirty, busy: replacementState.busy || candidateState.busy || startState.busy });
  }, [replacementState, candidateState, startState, onStateChange]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setPlan(null); setPeople({}); setLoading(true); setError(''); setNameError(false);
    void (async () => {
      try {
        const order = await ordersQueryClient.getOrderDetail(caseNo, { signal: controller.signal });
        if (order.case_no !== caseNo) throw new Error('服務月嫂資料的案件編號不一致。');
        if (!active) return;
        const isHistorical = ['歷史訂單－未服務', '歷史訂單－服務中', '歷史訂單－服務完成', '歷史訂單－帳務完成'].includes(order.order_status);
        setHistoricalOrder(isHistorical);
        const current = await ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal });
        if (current.case_no !== caseNo) throw new Error('服務月嫂資料的案件編號不一致。');
        if (!active) return;
        setPlan(current);
        if (current.assignments.length > 0) setReplacementScenario((previous) => previous ?? 'R-04');
        const ids = [...new Set(current.assignments.map(segment => segment.staff_id))];
        const results = await Promise.allSettled(ids.map(async (staffId) => {
          const page = await createStaffDirectoryClient().queryPage({ staffId }, { signal: controller.signal });
          const person = page.items.find((item) => item.id === staffId);
          if (!person) throw new Error('月嫂名冊未回傳此人員。');
          return person;
        }));
        if (!active) return;
        setPeople(Object.fromEntries(results.flatMap((result) => result.status === 'fulfilled' ? [[result.value.id, result.value]] : [])));
        setNameError(results.some((result) => result.status === 'rejected'));
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : '服務月嫂資料讀取失敗。');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; controller.abort(); };
  }, [caseNo, revision, retry]);

  return <section className="registry-editor" aria-label="服務安排與月嫂">
    <h3>服務安排與月嫂</h3>
    <small>{historicalOrder ? '已保存的歷史服務指派' : '目前正式指派'}</small>
    {loading && <p role="status">正在讀取服務月嫂…</p>}
    {error && <p role="alert">服務月嫂資料暫時無法讀取：{error}</p>}
    {plan && (plan.assignments.length === 0 ? <p>尚未建立正式指派。</p> : <div className="registry-staff-segments">{plan.assignments.map((segment) => {
      const person = people[segment.staff_id];
      return <dl className="registry-information-fields" key={segment.assignment_id ?? `${segment.sequence}-${segment.staff_id}`} aria-label={`第 ${segment.sequence} 段服務月嫂`}>
        <div><dt>月嫂姓名</dt><dd>{person ? staffDisplayLabel(person.union_no, person.name ?? '姓名未設定') : '月嫂資料待確認'}</dd></div>
        <div><dt>公會編號</dt><dd>{person?.union_no ?? '未登錄'}</dd></div>
        <div><dt>服務期間</dt><dd>{segment.assigned_start_date} ～ {segment.assigned_end_date}</dd></div>
        <div><dt>正式服務天數</dt><dd>{segment.official_service_dates.length > 0 ? `${segment.official_service_dates.length} 天` : '未建立逐日排班'}</dd></div>
      </dl>;
    })}</div>)}
    {nameError && <p role="alert">部分月嫂姓名或公會編號無法讀取，目前保留服務指派資料。</p>}
    {(error || nameError) && <button type="button" disabled={loading} onClick={() => setRetry((value) => value + 1)}>重新讀取服務月嫂</button>}
    {historicalOrder === false && <><section className="registry-start-correction" aria-label="實際開始日更正">
      {!correctingStart && <button type="button" disabled={disabled || replacementState.busy || candidateState.busy || loading} onClick={() => setCorrectingStart(true)}>更正實際開始日</button>}
      {correctingStart && <><fieldset className="registry-terms-fieldset" disabled={disabled || replacementState.busy || candidateState.busy}>
        <OrderActualStartPanel key={caseNo} caseNo={caseNo} autoLoad staffNames={Object.fromEntries(Object.entries(people).map(([id, person]) => [id, staffDisplayLabel(person.union_no, person.name ?? '姓名未設定')]))} onEditStateChange={setStartState} onObserved={operation => {
          setRecalculateDates(operation === 'date_only');
          setStartNotice(operation === 'reschedule' ? '實際開始日與各段排班已一併更新，請前往服務安排核對調整結果。' : '實際開始日已儲存，請前往服務安排重新確認日期表。');
          setRetry(value => value + 1); void onCommitted();
        }} />
      </fieldset><button type="button" disabled={startState.busy} onClick={() => { if (!startState.dirty || window.confirm('放棄尚未儲存的開始日調整？')) { setCorrectingStart(false); setStartState({ dirty: false, busy: false }); } }}>收合開始日更正</button></>}
      {startNotice && <p role="status">{startNotice}</p>}
      <a aria-disabled={startState.busy || startState.dirty || replacementState.busy || candidateState.busy || undefined} onClick={event => {
        if (startState.busy || startState.dirty || replacementState.busy || candidateState.busy) { event.preventDefault(); return; }
        if (onOpenServiceArrangement) { event.preventDefault(); onOpenServiceArrangement(recalculateDates); }
      }} href={`#order-workbench-v2?case=${encodeURIComponent(caseNo)}&work=service&from=clients${recalculateDates ? '&recalculate=1' : ''}`}>前往本案服務安排確認 →</a>
    </section>
    <p className="registry-section-note">服務前可辦理更換；已有服務紀錄時，改由請假代班處理。更換後須重新確認人選及服務安排。</p>
    <fieldset className="registry-terms-fieldset" disabled={disabled || candidateState.busy || startState.busy || startState.dirty || loading}>
      <ServiceBeforeReplacementActions caseNo={caseNo} initialScenario={replacementScenario} hideScenarioPicker={replacementScenario !== undefined} completionLabel="已登記更換，請選擇接任月嫂" onEditStateChange={setReplacementState} onCommitted={async () => {
        setChoosing(true);
        setRetry((value) => value + 1);
        await onCommitted();
      }} onSubstitutionReferral={() => { window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`; }} />
    </fieldset>
    {!choosing && plan?.assignments.length === 0 && <button type="button" disabled={disabled || replacementState.busy} onClick={() => setChoosing(true)}>選擇接任月嫂</button>}
    {choosing && <ClientRegistryReplacementCandidates caseNo={caseNo} disabled={disabled || replacementState.busy} onObserved={onCommitted} onStateChange={setCandidateState} />}
    </>}
  </section>;
}
