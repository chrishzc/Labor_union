import type { MatchingAvailability } from '../api/scheduling/matching_candidate_workflow_client';
import { candidateDateAssessment, missingCandidateServiceDates } from '../adapters/scheduling/candidate_date_status';
import { calendarServicePeriod } from '../../../line/static/service-date-calendar.js';

const reasonLabels: Record<string, string> = {
  active_lock: '其他案件等待訂金保留，僅提醒',
  assignment: '已有正式排班',
  schedule: '已有服務排程',
  staff_unavailability: '月嫂不可服務',
  historical_reservation: '其他案件歷史／暫定檔期，僅供參考',
  requires_review: '既有排程待核對',
  coverage_gap: '此段服務尚缺可用人選',
  outside_case_period: '超出本案服務期間',
  draft_overlap: '方案服務段落重疊',
  buffer: '七天緩衝期重疊，僅提醒',
};

export function CandidateAvailabilityNotice({ availability, staffId, showAdvisories = true, segmentIndex, showCoverageGaps = false }: {
  availability: MatchingAvailability;
  staffId: number;
  showAdvisories?: boolean;
  segmentIndex?: number;
  showCoverageGaps?: boolean;
}) {
  const conflicts = availability.conflicts.filter(conflict => conflict.staff_id === staffId
    && (segmentIndex === undefined || conflict.segment_index === segmentIndex));
  const option = availability.candidate_options.find(candidate => candidate.staff_id === staffId
    && (segmentIndex === undefined || candidate.segment_index === segmentIndex));
  if (!option && conflicts.length === 0) return <p className="order-case-review-note" role="status">
    此月嫂目前未列入可詢問人選，請先核對狀態。
  </p>;
  const hasConflict = candidateDateAssessment(option, conflicts).status === 'conflict';
  const datesByReason = new Map<string, Set<string>>();
  for (const { reason_code, work_date, case_no, service_start_at, service_end_at } of conflicts) {
    const dates = datesByReason.get(reason_code) ?? new Set<string>();
    const period = calendarServicePeriod(service_start_at, service_end_at);
    const dateWithUnknownTime = case_no || reason_code === 'active_lock' ? `${work_date}（服務時段待確認）` : work_date;
    const servicePeriod = period?.full ?? dateWithUnknownTime;
    dates.add(case_no ? `案件 ${case_no}，${servicePeriod}` : servicePeriod);
    datesByReason.set(reason_code, dates);
  }

  const missingDates = showCoverageGaps ? missingCandidateServiceDates(option) : [];
  if (missingDates.length > 0) {
    datesByReason.set('coverage_gap', new Set([...(datesByReason.get('coverage_gap') ?? []), ...missingDates]));
  }

  return <>
    {hasConflict && <p className="order-case-review-note" role="status">有檔期衝突，待公會協調</p>}
    {showAdvisories && datesByReason.has('active_lock') && <p className="order-case-review-note" role="status">{reasonLabels.active_lock}。</p>}
    {showAdvisories && datesByReason.has('buffer') && <p role="status">{reasonLabels.buffer}</p>}
    {datesByReason.has('historical_reservation') && <p role="status">{reasonLabels.historical_reservation}</p>}
    {datesByReason.size > 0 && <details>
      <summary>{hasConflict ? '查看衝突日期與原因' : '查看檔期日期與原因'}</summary>
      <ul>{Array.from(datesByReason, ([reason, dates]) => (
        <li key={reason}>{reasonLabels[reason] ?? '檔期待核對'}：{Array.from(dates).sort().join('、')}</li>
      ))}</ul>
    </details>}
  </>;
}
