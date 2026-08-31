/**
 * File: staff_payout_remediation_workbench.test.tsx
 * Description: 驗證 PAYOUT-001 工作台的 Q/P/A、Job terminal 與 fresh root 解除條件。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StaffPayoutRemediationWorkbench } from '../components/StaffPayoutRemediationWorkbench';
import type { StaffPayoutRemediationClient } from '../api/staff_payables/staff_payout_remediation_client';
import type { StaffPayoutJob } from '../api/staff_payables/staff_payout_remediation_schemas';
import { StaffPayoutRemediationError } from '../api/staff_payables/staff_payout_remediation_errors';

const initial = { staff_id: 11, staff_payables_version: 4, obligations: [{ obligation_identity: 'obligation:11:CASE-1', case_no: 'CASE-1', amount_due_ntd: 12000, due_date: '2026-08-01', net_paid_ntd: 0, balance_ntd: 12000, payout_status: 'payable' }], events: [] };
const settled = { ...initial, staff_payables_version: 5, obligations: [{ ...initial.obligations[0], net_paid_ntd: 12000, balance_ntd: 0, payout_status: 'completed' }] };
const preview = { event_type: 'payout', staff_payables_version: 4, bank_facts_version: 8, candidate: { staff_id: 11, bank_total: { amount: 12000 }, obligation_total: { amount: 12000 }, allocations: [{ bank_fact_identity: 'bank:91', obligation_identity: 'obligation:11:CASE-1', amount: { amount: 12000 } }], fingerprint: 'a'.repeat(64), events: [], obligation_links: [], resulting_status: 'completed' as const, difference_mode: null, recovery: null }, preview_fingerprint: 'b'.repeat(64) };

function clientFor(values: { query?: typeof initial; preview?: typeof preview; job?: StaffPayoutJob; settled?: typeof settled }): StaffPayoutRemediationClient {
  let queryCount = 0;
  return {
    query: vi.fn(async () => { queryCount += 1; return queryCount > 1 && values.settled ? values.settled : values.query ?? initial; }),
    preview: vi.fn(async () => values.preview ?? preview),
    apply: vi.fn(async () => ({ job_id: 'job-1', status_url: '/api/v1/jobs/job-1' })),
    queryJob: vi.fn(async (_jobId: string): Promise<StaffPayoutJob> => values.job ?? { job_id: 'job-1', status: 'succeeded', command_type: 'staff_payout_apply', attempt_count: 1, max_attempts: 3, outcome: { kind: 'success', schema_version: 1, result_reference: 'staff_payout:11' } }),
  };
}

describe('PAYOUT-001 remediation workbench', () => {
  afterEach(() => vi.restoreAllMocks());

  it('React StrictMode effect replay 後仍完成 owner Query，不停在永久讀取狀態', async () => {
    const client = clientFor({});
    render(
      <StrictMode>
        <StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} pollIntervalMs={0} />
      </StrictMode>,
    );

    await screen.findByText(/餘額 NT\$ 12,000/);
    expect(screen.queryByText('正在讀取最新應付款資料…')).not.toBeInTheDocument();
    expect(screen.queryByText(/Staff #11|obligation:11:CASE-1|版本 4|owner root|Job：/)).not.toBeInTheDocument();
  });

  it('完成 Query→Preview→Confirm→Apply→terminal→fresh readback 後才通知解除', async () => {
    const client = clientFor({ settled }); const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/);
    fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } });
    fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '電話核對後核銷' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' }));
    await screen.findByText('核銷影響已確認，尚未寫入');
    fireEvent.click(screen.getByRole('checkbox', { name: '確認核銷影響' }));
    fireEvent.click(screen.getByRole('button', { name: '確認並提交核銷' }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    expect(client.apply).toHaveBeenCalledTimes(1); expect(client.queryJob).toHaveBeenCalledTimes(1); expect(client.query).toHaveBeenCalledTimes(2);
  });

  it('輸入改變會使 Preview 失效，且不允許 double submit', async () => {
    const client = clientFor({});
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/);
    fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' }));
    await screen.findByText('核銷影響已確認，尚未寫入'); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '修改後理由' } });
    expect(screen.queryByText('核銷影響已確認，尚未寫入')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查核銷影響' })).toBeEnabled(); expect(client.apply).not.toHaveBeenCalled();
  });

  it('Job succeeded 但 result reference 或 fresh root 不符合時，異常保留且不通知解除', async () => {
    const client = clientFor({ job: { job_id: 'job-1', status: 'succeeded', command_type: 'staff_payout_apply', attempt_count: 1, max_attempts: 3, outcome: { kind: 'success', schema_version: 1, result_reference: 'staff_payout:99' } } }); const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' })); await screen.findByText('核銷影響已確認，尚未寫入'); fireEvent.click(screen.getByRole('checkbox', { name: '確認核銷影響' })); fireEvent.click(screen.getByRole('button', { name: '確認並提交核銷' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('應付款核銷目前無法完成')); expect(screen.getByRole('alert')).not.toHaveTextContent('STAFF_PAYOUT_JOB_RESULT_MISMATCH'); expect(onResolved).not.toHaveBeenCalled();
  });

  it('Job succeeded 但 fresh root 尚未結清時仍提供 owner readback，不形成永久死路', async () => {
    const client = clientFor({}); const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' })); await screen.findByText('核銷影響已確認，尚未寫入'); fireEvent.click(screen.getByRole('checkbox', { name: '確認核銷影響' })); fireEvent.click(screen.getByRole('button', { name: '確認並提交核銷' }));
    await screen.findByText(/最新應付款仍未結清/);
    const readback = screen.getByRole('button', { name: '重新查詢核銷結果' });
    fireEvent.click(readback);
    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(3));
    expect(onResolved).not.toHaveBeenCalled();
  });

  it('Apply 在取得 accepted 前逾時時保留原命令，安全重試不產生新 Idempotency-Key', async () => {
    const base = clientFor({ settled });
    const apply = vi.fn()
      .mockRejectedValueOnce(new StaffPayoutRemediationError('STAFF_PAYOUT_TIMEOUT', 'Apply timeout', true))
      .mockResolvedValueOnce({ job_id: 'job-1', status_url: '/api/v1/jobs/job-1' });
    const client: StaffPayoutRemediationClient = { ...base, apply };
    const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' })); await screen.findByText('核銷影響已確認，尚未寫入'); fireEvent.click(screen.getByRole('checkbox', { name: '確認核銷影響' })); fireEvent.click(screen.getByRole('button', { name: '確認並提交核銷' }));
    const retry = await screen.findByRole('button', { name: '使用原操作安全重試' });
    fireEvent.click(retry); await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    expect(apply).toHaveBeenCalledTimes(2); expect(apply.mock.calls[0][3]).toBe(apply.mock.calls[1][3]);
  });

  it('Apply 明確 stale 時 fresh Query 並要求重新 Preview，不重送舊命令', async () => {
    const staleQuery = { ...initial, staff_payables_version: 5 };
    let queryCount = 0;
    const base = clientFor({});
    const client: StaffPayoutRemediationClient = {
      ...base,
      query: vi.fn(async () => { queryCount += 1; return queryCount > 1 ? staleQuery : initial; }),
      apply: vi.fn(async () => { throw new StaffPayoutRemediationError('staff_payable_candidate_stale', 'stale'); }),
    };
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' })); await screen.findByText('核銷影響已確認，尚未寫入'); fireEvent.click(screen.getByRole('checkbox', { name: '確認核銷影響' })); fireEvent.click(screen.getByRole('button', { name: '確認並提交核銷' }));
    await screen.findByText(/應付款資料已更新/);
    expect(client.query).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('核銷影響已確認，尚未寫入')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查核銷影響' })).toBeEnabled();
    expect(client.apply).toHaveBeenCalledTimes(1);
  });
});
