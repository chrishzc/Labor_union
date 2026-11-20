import { afterEach, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { matchingCandidateWorkflowClient } from '../../../../../../../api/scheduling/matching_candidate_workflow_client';

afterEach(() => vi.restoreAllMocks());

it('keeps the typed 409 and reports the conflicting case and cross-day service period', async () => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-session');
  const username = 'test-admin';
  vi.spyOn(sessionClient, 'getUser').mockReturnValue({
    id: 1, username, display_name: 'Test admin', role: 'admin', capabilities: [], is_root: false, access_control_version: 1,
  });
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: {
    error: {
      code: 'matching_plan_staff_occupancy_conflict', category: 'domain_blocked', retryable: false,
      message: '推薦月嫂檔期衝突，不能建立方案。', field_errors: [], domain_blockers: [], correlation_id: 'test-conflict', current_version: null,
    },
    occupancy_conflicts: [{ segment_index: 0, staff_id: 12, work_date: '2026-11-16', reason_code: 'assignment',
      case_no: 'TEST-OTHER-CASE', actual_start_date: '2026-11-15',
      service_start_at: '2026-11-15T22:00:00+08:00', service_end_at: '2026-11-16T06:00:00+08:00' }],
  } }), { status: 409 }));

  await expect(matchingCandidateWorkflowClient.createSingleCaregiverPlan({ caseNo: 'TEST-CURRENT', actor: username,
    asOf: '2026-11-16', key: 'test-409', segments: [{ staff_id: 12, start_date: '2026-11-16', end_date: '2026-11-16' }],
  })).rejects.toMatchObject({ status: 409, code: 'matching_plan_staff_occupancy_conflict', retryable: false,
    message: expect.stringMatching(/案件 TEST-OTHER-CASE.*22:00:00.*06:00:00/),
  });
});
