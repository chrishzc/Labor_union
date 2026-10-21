/** Old willing candidate records remain readable but cannot become new recommendations. */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';
import { OrderRecommendationReplacementPanel } from '../../../../../../../components/OrderRecommendationReplacementPanel';
import * as staffDirectory from '../../../../../../../api/staff_directory/staff_directory_client';
import { candidateContactPoolClient } from '../../../../../../../api/scheduling/candidate_contact_pool_client';
import { waitingDepositLockClient } from '../../../../../../../api/scheduling/waiting_deposit_lock_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const CASE = 'RETIRE-SELECTION-TEST';
const pool = { pool_id: 1, case_no: CASE, candidates: [
  { id: 11, staff_id: 1, staff_name: '現役測試月嫂', status: 'active', willingness: 'willing', service_start_date: '2026-11-16', service_end_date: '2026-11-20' },
  { id: 12, staff_id: 2, staff_name: '退役歷史月嫂', status: 'active', willingness: 'willing', service_start_date: '2026-11-16', service_end_date: '2026-11-20' },
] };
const plan = { planId: 51, status: 'proposed', activeLockId: null, planVersion: 1, segments: [{ segmentId: 71, sequence: 1, staffId: 3, assignedStartDate: '2026-11-16', assignedEndDate: '2026-11-20' }] };
const contact = { plan: { id: 51, case_no: CASE, status: 'proposed', communication_version: 4, is_active: 1 }, segments: [{ segment_id: 71, staff_id: 3, staff_name: '原推薦月嫂', willingness: 'willing' }], all_willing: true, customer_decision: 'accepted', customer_profiles_status: null, customer_profiles_manual_confirmation: null };

describe('Retired staff in saved candidate history', () => {
  beforeEach(() => {
    orderMutationFlowStore.clearAll();
    vi.spyOn(staffDirectory, 'loadActiveStaffIds').mockResolvedValue(new Set([1, 3]));
    vi.spyOn(candidateContactPoolClient, 'query').mockResolvedValue(pool as never);
    vi.spyOn(waitingDepositLockClient, 'queryPlan').mockRejectedValue(new ApiHttpError(404, 'not_found', 'No current plan'));
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue({ case_no: CASE, assignments: [], service_started: false } as never);
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'test-operator' } as never);
  });
  afterEach(() => vi.restoreAllMocks());

  it('excludes retired willing staff from new recommendations and keeps the original pool intact', async () => {
    render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={vi.fn()} />);
    expect(await screen.findByRole('button', { name: '以 現役測試月嫂 建立正式媒合方案' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '以 退役歷史月嫂 建立正式媒合方案' })).not.toBeInTheDocument();
    expect(pool.candidates.some(candidate => candidate.staff_id === 2)).toBe(true);
  });

  it('excludes retired willing successors without changing the original recommendation', async () => {
    render(<OrderRecommendationReplacementPanel caseNo={CASE} plan={plan as never} contact={contact as never} onObserved={vi.fn()} onReplacementStarted={vi.fn()} onClose={vi.fn()} onEditStateChange={vi.fn()} />);
    expect(await screen.findByRole('radio', { name: /現役測試月嫂/ })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: /退役歷史月嫂/ })).not.toBeInTheDocument();
    expect(contact.segments[0].staff_name).toBe('原推薦月嫂');
    expect(pool.candidates.some(candidate => candidate.staff_id === 2)).toBe(true);
  });
});
