import type { MatchingAvailability, MatchingCandidateOption } from '../../api/scheduling/matching_candidate_workflow_client';

type CandidateConflict = MatchingAvailability['conflicts'][number];
export type CandidateDateStatus = 'clear' | 'advisory' | 'conflict' | 'unverified';

const ADVISORY_REASONS: ReadonlySet<string> = new Set(['active_lock', 'buffer', 'historical_reservation']);

export function missingCandidateServiceDates(option: MatchingCandidateOption | undefined): string[] {
  if (option?.full_case_coverage !== false) return [];
  const supportedDates = new Set(option.supported_service_dates);
  return option.required_service_dates.filter(date => !supportedDates.has(date));
}

export function candidateDateStatus(
  option: MatchingCandidateOption | undefined,
  conflicts: readonly CandidateConflict[],
): CandidateDateStatus {
  if (option?.full_case_coverage === false || conflicts.some(({ reason_code }) => !ADVISORY_REASONS.has(reason_code))) {
    return 'conflict';
  }
  if (conflicts.length > 0) return 'advisory';
  return option?.full_case_coverage === true ? 'clear' : 'unverified';
}

export function candidateDateAssessment(
  option: MatchingCandidateOption,
  conflicts: readonly CandidateConflict[],
): { status: CandidateDateStatus; dates: readonly string[] } {
  const status = candidateDateStatus(option, conflicts);
  const dates = conflicts.filter(({ reason_code }) => status !== 'conflict' || !ADVISORY_REASONS.has(reason_code))
    .map(({ work_date }) => work_date);
  return { status, dates: [...new Set([...dates, ...missingCandidateServiceDates(option)])].sort() };
}
