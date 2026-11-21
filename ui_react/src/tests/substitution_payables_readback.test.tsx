/** The historical Scheduling/Payroll/Staff Payables lineage remains a read-only contract. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import { ApiHttpError } from '../api/shared/typed_errors';
import { substitutionPayablesLineageClient, type SubstitutionPayablesLineage } from '../api/scheduling/substitution_payables_lineage_client';
import { LEAVE_CASE_NO, LEAVE_RECEIPT } from './fixtures/scheduling/leave_substitution_contract_fixtures';

function lineage(): SubstitutionPayablesLineage {
  return {
    case_no: LEAVE_CASE_NO,
    batch_key: LEAVE_RECEIPT.batch_key,
    scheduling_receipt_id: 901,
    scheduling_version: LEAVE_RECEIPT.scheduling_version,
    scheduling_generation: LEAVE_RECEIPT.scheduling_generation,
    expected_payroll_version: LEAVE_RECEIPT.payroll_version - 1,
    resulting_payroll_version: LEAVE_RECEIPT.payroll_version,
    items: [
      {
        item_index: 0,
        outcome_event_id: 701,
        original_assignment_id: 101,
        original_schedule_id: 1001,
        original_staff_id: 11,
        original_work_date: '2026-08-10',
        resolution_type: 'substitute',
        resulting_assignment_id: 201,
        resulting_staff_id: 12,
        resulting_service_date: '2026-08-10',
        payroll_event_id: 801,
        payroll_event_expected_version: LEAVE_RECEIPT.payroll_version - 1,
        payroll_event_resulting_version: LEAVE_RECEIPT.payroll_version,
        payroll_fingerprint: 'a'.repeat(64),
        payables_evidence: {
          obligation_identity: 'obligation:substitute:201',
          assignment_id: 201,
          staff_id: 12,
          amount_due_ntd: 4800,
          due_date: '2026-08-31',
          obligation_status: 'open',
          obligation_payroll_version: LEAVE_RECEIPT.payroll_version,
          obligation_event_id: 801,
          projection_status: 'payable',
          projection_amount_ntd: 4800,
          projection_net_paid_ntd: 0,
          projection_balance_ntd: 4800,
          projection_version: 7,
          projection_event_id: 901,
          blockers: [],
        },
        lineage_subject: 'substitution:batch:outcome:701',
        blockers: [],
      },
      {
        item_index: 1,
        outcome_event_id: 702,
        original_assignment_id: 101,
        original_schedule_id: 1002,
        original_staff_id: 11,
        original_work_date: '2026-08-11',
        resolution_type: 'defer_following_assignments',
        resulting_assignment_id: 202,
        resulting_staff_id: 11,
        resulting_service_date: '2026-08-11',
        payroll_event_id: 802,
        payroll_event_expected_version: LEAVE_RECEIPT.payroll_version - 1,
        payroll_event_resulting_version: LEAVE_RECEIPT.payroll_version,
        payroll_fingerprint: 'b'.repeat(64),
        payables_evidence: {
          obligation_identity: 'obligation:original:202',
          assignment_id: 202,
          staff_id: 11,
          amount_due_ntd: 3200,
          due_date: '2026-08-31',
          obligation_status: 'open',
          obligation_payroll_version: LEAVE_RECEIPT.payroll_version,
          obligation_event_id: 802,
          projection_status: 'payable',
          projection_amount_ntd: 3200,
          projection_net_paid_ntd: 0,
          projection_balance_ntd: 3200,
          projection_version: 7,
          projection_event_id: 902,
          blockers: [],
        },
        lineage_subject: 'substitution:batch:outcome:702',
        blockers: [],
      },
    ],
    authoritative_complete: true,
    blockers: [],
  };
}

describe('歷史代班應付款唯讀結果', () => {
  beforeEach(() => sessionClient.setSession('synthetic-payables-token', {
    id: 1, username: 'fixture', display_name: 'Fixture', role: 'system_admin',
  }));
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('讀回本案原人員與代班人員的應付義務', async () => {
    const result = lineage();
    const get = vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'ok', data: result });
    await expect(substitutionPayablesLineageClient.query(LEAVE_CASE_NO, LEAVE_RECEIPT.batch_key)).resolves.toEqual(result);
    expect(get).toHaveBeenCalledWith(
      `/api/v1/orders/${encodeURIComponent(LEAVE_CASE_NO)}/leave-substitution/${encodeURIComponent(LEAVE_RECEIPT.batch_key)}/payables-lineage`,
      expect.any(Object),
    );
    expect(result.items.map(item => item.payables_evidence?.amount_due_ntd)).toEqual([4800, 3200]);
  });

  it('回讀失敗後只重查 GET，再返回不完整投影及具體原因', async () => {
    const result = { ...lineage(), authoritative_complete: false, blockers: ['staff_payables_projection_missing'] };
    const get = vi.spyOn(transport, 'get')
      .mockRejectedValueOnce(new ApiHttpError(503, 'STAFF_PAYABLES_UNAVAILABLE', '讀取暫時失敗'))
      .mockResolvedValueOnce({ success: true, message: 'ok', data: result });
    const post = vi.spyOn(transport, 'post');
    await expect(substitutionPayablesLineageClient.query(LEAVE_CASE_NO, LEAVE_RECEIPT.batch_key)).rejects.toBeInstanceOf(Error);
    await expect(substitutionPayablesLineageClient.query(LEAVE_CASE_NO, LEAVE_RECEIPT.batch_key)).resolves.toMatchObject({
      authoritative_complete: false, blockers: ['staff_payables_projection_missing'],
    });
    expect(get).toHaveBeenCalledTimes(2);
    expect(post).not.toHaveBeenCalled();
  });
});
