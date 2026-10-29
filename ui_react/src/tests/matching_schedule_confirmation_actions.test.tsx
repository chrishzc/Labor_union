/**
 * File: matching_schedule_confirmation_actions.test.tsx
 * Description: 保護 M3 current 日期表 recipient 發送入口與 fresh readback。
 */
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import { MatchingScheduleAndAssignmentActions } from '../components/MatchingScheduleAndAssignmentActions';
import { assignmentPlanMutationClient } from '../api/scheduling/assignment_plan_mutation_client';
import { serviceStartClient } from '../api/scheduling/service_start_client';

describe('正式排班 canonical job failure transport', () => {
  afterEach(() => sessionClient.clearSession());
  it.each(['not_found', 'forbidden'])('保留 %s 終態而不誤判 schema failure', async (category) => {
    sessionClient.setSession('isolated-job-token', { id: 7, username: 'admin', display_name: 'Admin', role: 'admin' });
    vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'ok', error: null, data: {
      job_id: 'isolated-job', status: 'failed', command_type: 'assignment_plan_apply', attempt_count: 1, max_attempts: 3,
      outcome: { kind: 'failure', schema_version: 1, error: { category, code: 'owner_rejected', message: '無法執行此工作。', retryable: false, correlation_id: 'isolated-job', domain_blockers: [] } },
    } });
    await expect(assignmentPlanMutationClient.queryJob('isolated-job')).resolves.toMatchObject({ status: 'failed', outcome: { error: { category } } });
  });
});

afterEach(()=>vi.restoreAllMocks());
it('只顯示協調結果與代班，不再顯示再次確認日期表的操作',async()=>{
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[],total:0,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 render(<MatchingScheduleAndAssignmentActions caseNo="CASE" planId={1} planSegments={[]} waitingLockAcquired={false} assignmentExists={false} onAssignmentCompleted={async()=>{}}/>);
 await screen.findByText('目前沒有需要工會處理的排程衝突或代班。');
 expect(screen.queryByRole('button',{name:/發送日期表|人工確認|確認排班/})).not.toBeInTheDocument();
 expect(screen.getByText(/由月嫂提交開始日期/)).toBeInTheDocument();
});
