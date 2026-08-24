/**
 * File: matching_candidate_workflow_client.test.ts
 * Description: 驗證單月嫂與多月嫂候選查詢及正式方案建立的 closed typed client 契約。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { matchingCandidateWorkflowClient } from '../api/scheduling/matching_candidate_workflow_client';
import { transport } from '../api/shared/transport';

const envelope = (data: unknown) => ({ success: true, message: 'ok', data, error: null });

describe('matchingCandidateWorkflowClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('volatile-token');
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
  });

  it('searches the typed single-caregiver availability endpoint and preserves owner identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope({
      case_no: 'CASE-MATCH-1',
      planned_start_date: '2026-09-01',
      planned_end_date: '2026-09-05',
      feasibility: 'complete',
      complete_combinations: [[{ segment_index: 0, staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }]],
      segment_candidates: [{ segment_index: 0, staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }],
      candidate_options: [{
        segment_index: 0,
        staff_id: 8892,
        staff_name: '測試月嫂',
        coverage_day_count: 5,
        available_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-05' }],
        case_period_start: '2026-09-01',
        case_period_end: '2026-09-05',
        required_service_dates: ['2026-09-01'],
        supported_service_dates: ['2026-09-01'],
        supported_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-05', service_day_count: 1 }],
        supported_day_count: 1,
        required_day_count: 1,
        full_case_coverage: true,
        selected_segment_start: '2026-09-01',
        selected_segment_end: '2026-09-05',
        full_selected_segment_coverage: true,
        uncovered_segment_dates: [],
        source_scheduling_version: 3,
        filter_results: { schedule: true },
      }],
      conflicts: [],
    }));

    const result = await matchingCandidateWorkflowClient.searchSingleCaregiver(
      'CASE-MATCH-1', '2026-09-01', '2026-09-05',
    );
    expect(result.candidate_options[0]?.staff_id).toBe(8892);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-MATCH-1/caregiver-segment-availability/search',
      expect.objectContaining({
        segment_count: 1,
        segment_drafts: [{ start_date: '2026-09-01', end_date: '2026-09-05' }],
        filters: {
          region: true,
          cooking: true,
          preferred_service_days: true,
          daily_service_hours: true,
        },
      }),
      { token: 'volatile-token' },
    );
  });

  it('sends an explicit query-only filter policy without changing formal-plan payloads', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope({
      case_no: 'CASE-MATCH-FILTER', planned_start_date: '2026-09-01', planned_end_date: '2026-09-05',
      feasibility: 'partial', complete_combinations: [], segment_candidates: [], candidate_options: [], conflicts: [],
    }));
    await matchingCandidateWorkflowClient.searchSingleCaregiver(
      'CASE-MATCH-FILTER', '2026-09-01', '2026-09-05',
      { region: false, cooking: true, preferred_service_days: true, daily_service_hours: false },
    );
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-MATCH-FILTER/caregiver-segment-availability/search',
      expect.objectContaining({ filters: {
        region: false, cooking: true, preferred_service_days: true, daily_service_hours: false,
      } }),
      { token: 'volatile-token' },
    );
  });

  it('accepts a zero-coverage candidate so partial availability can remain inspectable', async () => {
    vi.spyOn(transport, 'post').mockResolvedValue(envelope({
      case_no: 'CASE-MATCH-EMPTY',
      planned_start_date: '2026-09-01',
      planned_end_date: '2026-09-05',
      feasibility: 'partial',
      complete_combinations: [],
      segment_candidates: [],
      candidate_options: [{
        segment_index: 0,
        staff_id: 8892,
        staff_name: '受阻月嫂',
        coverage_day_count: 0,
        available_ranges: [],
        case_period_start: '2026-09-01',
        case_period_end: '2026-09-05',
        required_service_dates: ['2026-09-01'],
        supported_service_dates: [],
        supported_ranges: [],
        supported_day_count: 0,
        required_day_count: 1,
        full_case_coverage: false,
        selected_segment_start: '2026-09-01',
        selected_segment_end: '2026-09-05',
        full_selected_segment_coverage: false,
        uncovered_segment_dates: ['2026-09-01'],
        source_scheduling_version: 3,
        filter_results: { schedule: false },
      }],
      conflicts: [{ segment_index: 0, staff_id: 8892, work_date: '2026-09-01', reason_code: 'active_lock' }],
    }));

    await expect(matchingCandidateWorkflowClient.searchSingleCaregiver(
      'CASE-MATCH-EMPTY', '2026-09-01', '2026-09-05',
    )).resolves.toMatchObject({
      candidate_options: [expect.objectContaining({ coverage_day_count: 0 })],
    });
  });

  it('creates one formal segment and rejects response identity drift', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope({
      plan_id: 51,
      case_no: 'CASE-MATCH-1',
      version: 2,
      status: 'proposed',
      result: 'created',
      segments: [{
        segment_order: 1,
        staff_id: 8892,
        assigned_start_date: '2026-09-01',
        assigned_end_date: '2026-09-05',
      }],
    }));

    await expect(matchingCandidateWorkflowClient.createSingleCaregiverPlan(
      'CASE-MATCH-1',
      { staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' },
    )).resolves.toMatchObject({ plan_id: 51, result: 'created' });
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-MATCH-1/matching-plans',
      expect.objectContaining({
        segments: [{ staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }],
        created_by: 'operator-1',
      }),
      { token: 'volatile-token' },
    );

    vi.mocked(transport.post).mockResolvedValueOnce(envelope({
      plan_id: 52,
      case_no: 'CASE-OTHER',
      version: 1,
      status: 'proposed',
      result: 'created',
      segments: [{
        segment_order: 1,
        staff_id: 8892,
        assigned_start_date: '2026-09-01',
        assigned_end_date: '2026-09-05',
      }],
    }));
    await expect(matchingCandidateWorkflowClient.createSingleCaregiverPlan(
      'CASE-MATCH-1',
      { staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' },
    )).rejects.toThrow('identity 不一致');
  });

  it('uses a server-selected two-segment combination without browser date calculation', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope({
      case_no: 'CASE-MATCH-2',
      planned_start_date: '2026-09-01',
      planned_end_date: '2026-09-05',
      feasibility: 'complete',
      complete_combinations: [[
        { segment_index: 0, staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-03' },
        { segment_index: 1, staff_id: 8893, start_date: '2026-09-04', end_date: '2026-09-05' },
      ]],
      segment_candidates: [], candidate_options: [], conflicts: [],
    })).mockResolvedValueOnce(envelope({
      plan_id: 52, case_no: 'CASE-MATCH-2', version: 1, status: 'proposed', result: 'created',
      segments: [
        { segment_order: 1, staff_id: 8892, assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-03' },
        { segment_order: 2, staff_id: 8893, assigned_start_date: '2026-09-04', assigned_end_date: '2026-09-05' },
      ],
    }));

    await expect(matchingCandidateWorkflowClient.searchSegmentedCaregivers('CASE-MATCH-2', 2)).resolves.toMatchObject({
      complete_combinations: [expect.arrayContaining([expect.objectContaining({ staff_id: 8892 })])],
    });
    const plan = await matchingCandidateWorkflowClient.createMatchingPlan('CASE-MATCH-2', [
      { staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-03' },
      { staff_id: 8893, start_date: '2026-09-04', end_date: '2026-09-05' },
    ]);
    expect(plan).toMatchObject({ plan_id: 52 });
    expect(plan.segments).toHaveLength(2);
    expect(post).toHaveBeenNthCalledWith(
      1,
      '/api/v1/orders/CASE-MATCH-2/caregiver-segment-availability/search',
      expect.objectContaining({ segment_count: 2, segment_drafts: [] }),
      { token: 'volatile-token' },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/api/v1/orders/CASE-MATCH-2/matching-plans',
      expect.objectContaining({ segments: [
        { staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-03' },
        { staff_id: 8893, start_date: '2026-09-04', end_date: '2026-09-05' },
      ] }),
      { token: 'volatile-token' },
    );
  });
});
