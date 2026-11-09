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
import { StaffPayoutRemediationError, staffPayoutBlockerMessage } from '../api/staff_payables/staff_payout_remediation_errors';

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

  it('顯示完整出款、正式65元手續費，方案一保留補助待付並等待台新核銷', async () => {
    const portions = [
      { funding_kind: 'client', amount_ntd: 18000, due_date: '2026-10-15', settled_ntd: 0, remaining_ntd: 18000 },
      { funding_kind: 'subsidy', amount_ntd: 12000, due_date: '2026-10-15', settled_ntd: 0, remaining_ntd: 12000 },
    ];
    const query = { ...initial, obligations: [{ ...initial.obligations[0], amount_due_ntd: 30000, balance_ntd: 30000, funding_portions: portions }] };
    const after = { ...query, staff_payables_version: 5, obligations: [{ ...query.obligations[0], net_paid_ntd: 18000, balance_ntd: 12000,
      payout_status: 'partially_paid', funding_portions: [{ ...portions[0], settled_ntd: 18000, remaining_ntd: 0 }, portions[1]] }] };
    const checked = { ...preview, candidate: { ...preview.candidate, bank_total: { amount: 17935 }, obligation_total: { amount: 18000 },
      transfer_fee: { amount: 65 }, resulting_status: 'partially_paid', allocations: [{ bank_fact_identity: 'bank:91', obligation_identity: initial.obligations[0].obligation_identity, amount: { amount: 18000 } }] } };
    const client = clientFor({});
    client.query = vi.fn().mockResolvedValueOnce(query).mockResolvedValue(after);
    client.preview = vi.fn().mockResolvedValue(checked);
    const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: initial.obligations[0].obligation_identity }}
      sourceBank="sinopac" financeImportRowId={91} bankSource={{ transaction_date: '2026-10-15', amount_ntd: 17935, reference: '合成轉帳摘要', counterparty_name: '合成月嫂' }}
      confirmPreview client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText('交易日：2026-10-15');
    expect(screen.getByText('收款對象：合成月嫂')).toBeInTheDocument();
    expect(screen.getByText('交易摘要：合成轉帳摘要')).toBeInTheDocument();
    expect(screen.getByText('銀行實付：NT$ 17,935')).toBeInTheDocument();
    expect(screen.queryByText('內扣手續費：NT$ 65')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '預覽核銷' }));
    await screen.findByText('內扣手續費：NT$ 65');
    expect(screen.getByText('核銷後剩餘待付：NT$ 12,000')).toBeInTheDocument();
    expect(screen.getByText(/剩餘補助待付：NT\$ 12,000/)).toBeInTheDocument();
    expect(client.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '確認核銷' }));
    await screen.findByText(/最新應付款仍未結清（餘額 NT\$ 12,000/);
    expect(onResolved).not.toHaveBeenCalled();
    expect(screen.getByText(/自備款（永豐）：應付 NT\$ 18,000 · 待付 NT\$ 0/)).toBeInTheDocument();
    expect(screen.getByText(/補助款（台新）：應付 NT\$ 12,000 · 待付 NT\$ 12,000/)).toBeInTheDocument();
  });

  it.each(['staff_payout_amount_mismatch','staff_obligation_not_exactly_settled','staff_payout_difference_mode_invalid'])(
    'shows the scoped Sinopac reason for preview, direct Apply and terminal rejection: %s',async code=>{
      const {cleanup}=await import('@testing-library/react');
      const message=staffPayoutBlockerMessage(code,'sinopac')!;
      expect(message).toBeTruthy();
      expect(staffPayoutBlockerMessage(code,'legacy')).toBeUndefined();
      for(const stage of ['preview','apply','job']){
        const client=clientFor({job:{job_id:'job-1',status:'failed',command_type:'staff_payout_apply',attempt_count:1,max_attempts:3,
          outcome:{kind:'failure',schema_version:1,error:{category:'domain_blocked',code,message:'private detail',retryable:false,correlation_id:'synthetic',domain_blockers:[code]}}}});
        if(stage==='preview')client.preview=vi.fn().mockRejectedValue(new StaffPayoutRemediationError(code,'private detail'));
        if(stage==='apply')client.apply=vi.fn().mockRejectedValue(new StaffPayoutRemediationError(code,'private detail'));
        render(<StaffPayoutRemediationWorkbench target={{staffId:11,obligationIdentity:'obligation:11:CASE-1'}} sourceBank="sinopac"
          financeImportRowId={91} client={client} pollIntervalMs={0}/>);
        await screen.findByText(/餘額 NT\$ 12,000/);
        fireEvent.click(screen.getByRole('button',{name:'儲存核銷'}));
        expect(await screen.findByText(message)).toBeInTheDocument();
        expect(screen.queryByText('private detail')).not.toBeInTheDocument();
        if(stage==='preview')expect(client.apply).not.toHaveBeenCalled();
        cleanup();
      }
    });

  it.each([
    ['bank_transaction_date_missing','缺少交易日'],
    ['bank_currency_not_twd','不是新臺幣'],
    ['due_date_missing','缺少原預計撥款日'],
    ['staff_payout_amount_mismatch','不符合足額或100元內手續費條件'],
    ['staff_memo_recipient_unconfirmed','不以六碼或帳號代替月嫂姓名'],
    ['cross_staff_allocation_forbidden','原銀行備註確認的月嫂與所選應付款月嫂不同'],
    ['staff_payable_not_found','所選應付款已不存在或無法讀取'],
    ['staff_obligation_not_exactly_settled','這不代表禁止部分付款'],
  ])('shows the Taishin cause consistently in preview, direct Apply and terminal: %s',async(code,expected)=>{
    const {cleanup}=await import('@testing-library/react');
    for(const stage of ['preview','apply','job']){
      const client=clientFor({job:{job_id:'job-1',status:'failed',command_type:'staff_payout_apply',attempt_count:1,max_attempts:3,
        outcome:{kind:'failure',schema_version:1,error:{category:'domain_blocked',code,message:'private detail',retryable:false,correlation_id:'synthetic',domain_blockers:[code]}}}});
      if(stage==='preview')client.preview=vi.fn().mockRejectedValue(new StaffPayoutRemediationError(code,'private detail'));
      if(stage==='apply')client.apply=vi.fn().mockRejectedValue(new StaffPayoutRemediationError(code,'private detail'));
      render(<StaffPayoutRemediationWorkbench target={{staffId:11,obligationIdentity:'obligation:11:CASE-1'}} sourceBank="taishin" financeImportRowId={91} client={client} pollIntervalMs={0}/>);
      await screen.findByText(/餘額 NT\$ 12,000/);
      fireEvent.click(screen.getByRole('button',{name:'儲存核銷'}));
      expect(await screen.findByText(new RegExp(expected))).toBeInTheDocument();
      expect(screen.queryByText('private detail')).not.toBeInTheDocument();
      if(stage==='preview')expect(client.apply).not.toHaveBeenCalled();
      cleanup();
    }
  });

  it.each([
    ['staff_bank_account_ambiguous', '銀行流水缺少收款帳號，或無法對應唯一有效的月嫂主要帳戶，請核對原流水與月嫂帳戶。'],
    ['staff_memo_recipient_unconfirmed', '銀行備註中的月嫂姓名無法唯一確認，請核對原始備註與月嫂姓名。'],
    ['cross_staff_allocation_forbidden', '銀行流水、收款帳戶與待付款項的月嫂歸屬不一致，請核對付款對象。'],
    ['bank_transaction_date_missing', '原銀行流水缺少交易日，無法核銷月嫂付款，請先查核來源資料。'],
    ['bank_currency_not_twd', '原銀行流水幣別不是新臺幣，無法核銷月嫂付款，請先查核來源資料。'],
    ['outgoing_bank_fact_not_eligible', '原銀行出款未通過核銷資格檢查，原操作未留存更細的拒絕原因，請查核原流水。'],
  ])('shows the same safe cause at preview, direct Apply rejection and failed terminal: %s', async (code, message) => {
    const { cleanup } = await import('@testing-library/react');
    for (const stage of ['preview', 'apply', 'job']) {
      const client = clientFor({ job: { job_id: 'job-1', status: 'failed', command_type: 'staff_payout_apply',
        attempt_count: 1, max_attempts: 3, outcome: { kind: 'failure', schema_version: 1, error: {
          category: 'domain_blocked', code, message: 'private provider detail', retryable: false,
          correlation_id: 'synthetic-cause', domain_blockers: [code],
        } } } });
      if (stage === 'preview') client.preview = vi.fn().mockRejectedValue(new StaffPayoutRemediationError(code, 'private provider detail'));
      if (stage === 'apply') client.apply = vi.fn().mockRejectedValue(new StaffPayoutRemediationError(code, 'private provider detail'));
      const onResolved = vi.fn(); const onPosted = vi.fn();
      render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }}
        sourceBank={['bank_transaction_date_missing','bank_currency_not_twd'].includes(code) ? 'sinopac' : undefined}
        client={client} pollIntervalMs={0} onResolved={onResolved} onPosted={onPosted} />);
      await screen.findByText(/餘額 NT\$ 12,000/);
      fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } });
      fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(screen.queryByText(/private provider detail/)).not.toBeInTheDocument();
      expect(onResolved).not.toHaveBeenCalled(); expect(onPosted).not.toHaveBeenCalled();
      if (stage === 'preview') expect(client.apply).not.toHaveBeenCalled();
      cleanup();
    }
  });

  it('marks unknown or missing terminal causes without exposing the server message', async () => {
    const client = clientFor({ job: { job_id: 'job-1', status: 'failed', command_type: 'staff_payout_apply', attempt_count: 1, max_attempts: 3,
      outcome: { kind: 'failure', schema_version: 1, error: { category: 'domain_blocked', code: 'unknown_legacy_reason',
        message: 'private provider detail', retryable: false, correlation_id: null, domain_blockers: [] } } } });
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/);
    fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
    expect(await screen.findByText(/未留存可顯示的具體阻擋原因/)).toBeInTheDocument();
    expect(screen.queryByText(/private provider detail|unknown_legacy_reason/)).not.toBeInTheDocument();
  });

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
    fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));



    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    expect(client.apply).toHaveBeenCalledTimes(1); expect(client.queryJob).toHaveBeenCalledTimes(1); expect(client.query).toHaveBeenCalledTimes(2);
  });

  it('不足額核銷保留餘額，確認成功後才允許下一筆補款', async () => {
    const partial = { ...initial, staff_payables_version: 5, obligations: [{ ...initial.obligations[0], net_paid_ntd: 4000, balance_ntd: 8000, payout_status: 'partially_paid' }] };
    const client = clientFor({ settled: partial }); const onResolved = vi.fn(); const onPosted = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} onPosted={onPosted} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/);
    fireEvent.change(screen.getByLabelText('核銷方式'), { target: { value: 'underpayment' } });
    fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
    await screen.findAllByText(/餘額 NT\$ 8,000/);
    expect(client.preview).toHaveBeenCalledWith(expect.objectContaining({ differenceMode: 'underpayment' }), expect.anything());
    expect(onPosted).toHaveBeenCalledTimes(1);
    expect(onResolved).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '繼續核銷剩餘款' }));
    expect(screen.getByLabelText('銀行流水紀錄編號')).toHaveValue('');
    expect(screen.getByLabelText('核銷方式')).toHaveValue('');
    expect(screen.getByRole('button', { name: '儲存核銷' })).toBeDisabled();
  });

  it('綁定銀行流水核銷多筆款項時，其他款項未清償就保留待付', async () => {
    const second = { ...initial.obligations[0], obligation_identity: 'obligation:11:CASE-2', case_no: 'CASE-2' };
    const combined = { ...initial, obligations: [...initial.obligations, second] };
    const partial = { ...settled, obligations: [...settled.obligations, second] };
    const client = clientFor({ query: combined, settled: partial }); const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1', obligationIdentities: combined.obligations.map(item => item.obligation_identity) }} financeImportRowId={91} confirmPreview client={client} onResolved={onResolved} pollIntervalMs={0}/>);
    await screen.findAllByText(/餘額 NT\$ 12,000/);
    expect(screen.queryByLabelText('銀行流水紀錄編號')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('核銷方式'), { target: { value: 'underpayment' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽核銷' }));
    const confirm = await screen.findByRole('button', { name: '確認核銷' });
    expect(client.apply).not.toHaveBeenCalled();
    fireEvent.click(confirm);
    await screen.findByText('剩餘款繼續待付；請由補款流水接續核銷。');
    expect(client.preview).toHaveBeenCalledWith(expect.objectContaining({ financeImportRowIds: [91], obligationIdentities: combined.obligations.map(item => item.obligation_identity), differenceMode: 'underpayment' }), expect.anything());
    expect(onResolved).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '繼續核銷剩餘款' })).not.toBeInTheDocument();
  });

  it('Job succeeded 但 result reference 或 fresh root 不符合時，異常保留且不通知解除', async () => {
    const client = clientFor({ job: { job_id: 'job-1', status: 'succeeded', command_type: 'staff_payout_apply', attempt_count: 1, max_attempts: 3, outcome: { kind: 'success', schema_version: 1, result_reference: 'staff_payout:99' } } }); const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('應付款核銷目前無法完成')); expect(screen.getByRole('alert')).not.toHaveTextContent('STAFF_PAYOUT_JOB_RESULT_MISMATCH'); expect(onResolved).not.toHaveBeenCalled();
  });

  it('Job succeeded 但 fresh root 尚未結清時仍提供 owner readback，不形成永久死路', async () => {
    const client = clientFor({}); const onResolved = vi.fn();
    render(<StaffPayoutRemediationWorkbench target={{ staffId: 11, obligationIdentity: 'obligation:11:CASE-1' }} client={client} onResolved={onResolved} pollIntervalMs={0} />);
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
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
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
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
    await screen.findByText(/餘額 NT\$ 12,000/); fireEvent.change(screen.getByLabelText('銀行流水紀錄編號'), { target: { value: '91' } }); fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '理由' } }); fireEvent.click(screen.getByRole('button', { name: '儲存核銷' }));
    await screen.findByText(/應付款資料已更新/);
    expect(client.query).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('核銷影響已確認，尚未寫入')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存核銷' })).toBeEnabled();
    expect(client.apply).toHaveBeenCalledTimes(1);
  });
});
