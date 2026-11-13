import type { MatchingAvailability } from '../api/scheduling/matching_candidate_workflow_client';

const reasonLabels: Record<string, string> = {
  active_lock: '其他案件等待訂金保留（黃色鎖）',
  assignment: '已有正式排班',
  schedule: '已有服務排程',
  staff_unavailability: '月嫂不可服務',
  historical_reservation: '其他案件歷史預定',
  requires_review: '既有排程待核對',
  coverage_gap: '此段服務尚缺可用人選',
  outside_case_period: '超出本案服務期間',
  draft_overlap: '方案服務段落重疊',
  buffer: '七天緩衝期重疊，僅提醒',
};

export function CandidateAvailabilityNotice({ availability, staffId, showAdvisories = true }: {
  availability: MatchingAvailability;
  staffId: number;
  showAdvisories?: boolean;
}) {
  const conflicts = availability.conflicts.filter(conflict => conflict.staff_id === staffId);
  const option = availability.candidate_options.find(candidate => candidate.staff_id === staffId);
  if (!option && conflicts.length === 0) return <p className="order-case-review-note" role="status">
    此月嫂目前未列入可詢問人選，請先核對狀態。
  </p>;
  const hasWaitingDepositLock = conflicts.some(conflict => conflict.reason_code === 'active_lock');
  const hasConflict = conflicts.some(conflict => !['active_lock', 'buffer'].includes(conflict.reason_code))
    || (!hasWaitingDepositLock && option?.full_case_coverage === false);
  const datesByReason = new Map<string, Set<string>>();
  for (const { reason_code, work_date } of conflicts) {
    const dates = datesByReason.get(reason_code) ?? new Set<string>();
    dates.add(work_date);
    datesByReason.set(reason_code, dates);
  }

  return <>
    {hasConflict && <p className="order-case-review-note" role="status">有檔期衝突，待公會協調</p>}
    {showAdvisories && hasWaitingDepositLock && <p className="order-case-review-note" role="status">其他案件有等待訂金保留，仍可詢問及選定推薦月嫂。</p>}
    {showAdvisories && datesByReason.has('buffer') && <p role="status">{reasonLabels.buffer}</p>}
    {datesByReason.size > 0 && <details>
      <summary>查看衝突日期與原因</summary>
      <ul>{Array.from(datesByReason, ([reason, dates]) => (
        <li key={reason}>{reasonLabels[reason] ?? '檔期待核對'}：{Array.from(dates).sort().join('、')}</li>
      ))}</ul>
    </details>}
  </>;
}
