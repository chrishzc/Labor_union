import type { MatchingAvailability, MatchingCandidateOption } from '../../api/scheduling/matching_candidate_workflow_client';

type CandidateConflict = MatchingAvailability['conflicts'][number];
export type CandidateDateStatus = 'clear' | 'advisory' | 'conflict' | 'unverified';

const ADVISORY_REASONS: ReadonlySet<string> = new Set(['active_lock', 'buffer', 'historical_reservation']);

export function missingCandidateServiceDates(option: MatchingCandidateOption | undefined): string[] {
  if (option?.full_case_coverage !== false) return [];
  const supportedDates = new Set(option.supported_service_dates);
  return option.required_service_dates.filter(date => !supportedDates.has(date));
}

export function candidateDateAssessment(
  option: MatchingCandidateOption | undefined,
  conflicts: readonly CandidateConflict[],
): { status: CandidateDateStatus; dates: readonly string[] } {
  const hardConflicts = conflicts.filter(({ reason_code }) => !ADVISORY_REASONS.has(reason_code));
  if (hardConflicts.length > 0 || option?.full_case_coverage === false) {
    const dates = new Set([...hardConflicts.map(({ work_date }) => work_date), ...missingCandidateServiceDates(option)]);
    return { status: 'conflict', dates: [...dates].sort() };
  }
  if (conflicts.length > 0) {
    return { status: 'advisory', dates: [...new Set(conflicts.map(({ work_date }) => work_date))].sort() };
  }
  return { status: option?.full_case_coverage === true ? 'clear' : 'unverified', dates: [] };
}
