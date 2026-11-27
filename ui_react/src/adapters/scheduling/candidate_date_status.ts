import type { MatchingAvailability, MatchingCandidateOption } from '../../api/scheduling/matching_candidate_workflow_client';

type CandidateConflict = MatchingAvailability['conflicts'][number];
export type CandidateDateStatus = 'clear' | 'advisory' | 'conflict' | 'unverified';

const ADVISORY_REASONS: ReadonlySet<string> = new Set(['active_lock', 'buffer', 'historical_reservation']);

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

export function candidateAssignmentDateRange({ reason_code, assignment_start_date, assignment_end_date }: CandidateConflict): string | null {
  if (reason_code !== 'assignment' && reason_code !== 'schedule') return null;
  if (!assignment_start_date || !assignment_end_date) return null;
  return `${assignment_start_date} ～ ${assignment_end_date}`;
}
