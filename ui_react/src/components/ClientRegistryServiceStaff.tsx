import { useEffect, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { AssignmentPlan } from '../api/orders/order_query_schemas';
import { createStaffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import type { StaffDirectorySummary } from '../api/staff_directory/staff_directory_schemas';
import { ServiceBeforeReplacementActions } from './ServiceBeforeReplacementActions';
import type { ServiceBeforeReplacementScenario } from '../api/orders/service_before_replacement_client';
import { ClientRegistryReplacementCandidates } from './ClientRegistryReplacementCandidates';

interface Props {
  caseNo: string;
  revision: object;
  disabled: boolean;
  onCommitted: () => Promise<void>;
  onStateChange: (state: { dirty: boolean; busy: boolean }) => void;
}

export function ClientRegistryServiceStaff({ caseNo, revision, disabled, onCommitted, onStateChange }: Props) {
  const [plan, setPlan] = useState<AssignmentPlan | null>(null);
  const [people, setPeople] = useState<Record<number, StaffDirectorySummary>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [nameError, setNameError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [replacementScenario, setReplacementScenario] = useState<ServiceBeforeReplacementScenario>();
  const [choosing, setChoosing] = useState(false);
  const [replacementState, setReplacementState] = useState({ dirty: false, busy: false });
  const [candidateState, setCandidateState] = useState({ dirty: false, busy: false });
  useEffect(() => {
    onStateChange({ dirty: replacementState.dirty || candidateState.dirty, busy: replacementState.busy || candidateState.busy });
  }, [replacementState, candidateState, onStateChange]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setPlan(null); setPeople({}); setLoading(true); setError(''); setNameError(false);
    void (async () => {
      try {
        const current = await ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal });
        if (current.case_no !== caseNo) throw new Error('服務月嫂資料的案件編號不一致。');
        if (!active) return;
        setPlan(current);
        if (current.assignments.length > 0) setReplacementScenario((previous) => previous ?? 'R-04');
        const ids = [...new Set(current.assignments.map((segment) => segment.staff_id))];
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

  return <section className="registry-editor" aria-label="服務月嫂">
    <h3>服務月嫂</h3>
    <small>目前正式指派</small>
    {loading && <p role="status">正在讀取服務月嫂…</p>}
    {error && <p role="alert">服務月嫂資料暫時無法讀取：{error}</p>}
    {plan && (plan.assignments.length === 0 ? <p>尚未建立正式指派。</p> : <div className="registry-staff-segments">{plan.assignments.map((segment) => {
      const person = people[segment.staff_id];
      return <dl className="registry-information-fields" key={segment.assignment_id ?? `${segment.sequence}-${segment.staff_id}`} aria-label={`第 ${segment.sequence} 段服務月嫂`}>
        <div><dt>月嫂姓名</dt><dd>{person?.name ?? `月嫂 #${segment.staff_id}`}</dd></div>
        <div><dt>公會編號</dt><dd>{person?.union_no ?? '未登錄'}</dd></div>
        <div><dt>服務期間</dt><dd>{segment.assigned_start_date} ～ {segment.assigned_end_date}</dd></div>
        <div><dt>正式服務天數</dt><dd>{segment.official_service_dates.length} 天</dd></div>
      </dl>;
    })}</div>)}
    {nameError && <p role="alert">部分月嫂姓名或公會編號無法讀取，目前保留正式指派資料。</p>}
    {(error || nameError) && <button type="button" disabled={loading} onClick={() => setRetry((value) => value + 1)}>重新讀取服務月嫂</button>}
    <p className="registry-section-note">服務前可辦理更換；已有服務紀錄時，改由請假代班處理。更換後須重新確認人選及服務安排。</p>
    <fieldset className="registry-terms-fieldset" disabled={disabled || candidateState.busy || loading}>
      <ServiceBeforeReplacementActions caseNo={caseNo} initialScenario={replacementScenario} hideScenarioPicker={replacementScenario !== undefined} completionLabel="已登記更換，請選擇接任月嫂" onEditStateChange={setReplacementState} onCommitted={async () => {
        setChoosing(true);
        setRetry((value) => value + 1);
        await onCommitted();
      }} onSubstitutionReferral={() => { window.location.hash = `#scheduling?tab=leave_sub&case_no=${encodeURIComponent(caseNo)}`; }} />
    </fieldset>
    {!choosing && plan?.assignments.length === 0 && <button type="button" disabled={disabled || replacementState.busy} onClick={() => setChoosing(true)}>選擇接任月嫂</button>}
    {choosing && <ClientRegistryReplacementCandidates caseNo={caseNo} disabled={disabled || replacementState.busy} onObserved={onCommitted} onStateChange={setCandidateState} />}
  </section>;
}
