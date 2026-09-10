import { afterEach, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { matchingCandidateWorkflowClient } from '../../../../../../../api/scheduling/matching_candidate_workflow_client';
import { transport } from '../../../../../../../api/shared/transport';

afterEach(() => vi.restoreAllMocks());

it('keeps planned inquiry and formal availability on distinct routes', async () => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-only-token');
  const post = vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: 'ok', error: null, data: {
    case_no: 'INQUIRY-1', planned_start_date: '2026-10-05', planned_end_date: '2026-10-05',
    feasibility: 'partial', complete_combinations: [], segment_candidates: [], candidate_options: [], conflicts: [],
  } });
  await matchingCandidateWorkflowClient.searchInquiryCandidates('INQUIRY-1');
  expect(post).toHaveBeenNthCalledWith(1,
    '/api/v1/orders/INQUIRY-1/candidate-contact-pool/availability/search',
    expect.objectContaining({ segment_count: 1, segment_drafts: [] }), { token: 'test-only-token' });
  await matchingCandidateWorkflowClient.searchSegmentedCaregivers('INQUIRY-1', 2);
  expect(post).toHaveBeenNthCalledWith(2,
    '/api/v1/orders/INQUIRY-1/caregiver-segment-availability/search',
    expect.objectContaining({ segment_count: 2 }), { token: 'test-only-token' });
});

it('rejects a response for a different case', async () => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-only-token');
  vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: 'ok', error: null, data: {
    case_no: 'OTHER', planned_start_date: '2026-10-05', planned_end_date: '2026-10-05',
    feasibility: 'partial', complete_combinations: [], segment_candidates: [], candidate_options: [], conflicts: [],
  } });
  await expect(matchingCandidateWorkflowClient.searchInquiryCandidates('INQUIRY-1')).rejects.toThrow('案件識別不一致');
});
