/**
 * File: staff_overpayment_recovery_actions.test.tsx
 * Description: 驗證 Staff recovery renderer 的 branch、Preview invalidation、精確調整與 owner readback。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffOverpaymentRecoveryActions } from '../components/StaffOverpaymentRecoveryActions';
import { staffOverpaymentRecoveryClient } from '../api/staff_payables/staff_overpayment_recovery_client';

const openQuery = {
  staff_id: 7, recovery_identity: 'staff-overpayment-recovery:1', remaining_amount_ntd: 500,
  status: 'open' as const, recovery_version: 3, staff_payables_version: 9,
  source_bank_fact_references: ['redacted:source'], source_payout_event_references: ['redacted:payout'],
  source_obligation_references: ['redacted:obligation'], matchings: [],
};
const matchedQuery = {
  ...openQuery,
  matchings: [{ matching_identity: 'staff-recovery-match:1', matching_version: 1, finance_import_row_identity: 'redacted:incoming' }],
};
const recoveredQuery = { ...matchedQuery, remaining_amount_ntd: 0, status: 'recovered' as const, recovery_version: 4, staff_payables_version: 10 };
const adjustmentPreview = {
  recovery_identity: openQuery.recovery_identity, recovery_version: 3, staff_payables_version: 9,
  adjustment_amount_ntd: 500, remaining_before_ntd: 500, remaining_after_ntd: 0 as const,
  resulting_status: 'adjusted' as const, preview_fingerprint: 'a'.repeat(64),
};
const collectionPreview = {
  recovery_identity: openQuery.recovery_identity, recovery_version: 3, staff_payables_version: 9,
  received_amount_ntd: 500, remaining_before_ntd: 500, remaining_after_ntd: 0,
  resulting_status: 'recovered' as const, preview_fingerprint: 'b'.repeat(64),
};

describe('StaffOverpaymentRecoveryActions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function fillExplanation() {
    fireEvent.change(screen.getByLabelText('處理理由'), { target: { value: '人工電話確認已完成追償。' } });
    fireEvent.change(screen.getByLabelText('佐證紀錄'), { target: { value: '電話紀錄:case-1' } });
  }

  it('open recovery exposes matching and exact adjustment, and invalidates Preview on input change', async () => {
    vi.spyOn(staffOverpaymentRecoveryClient, 'query').mockResolvedValue(openQuery);
    vi.spyOn(staffOverpaymentRecoveryClient, 'previewAdjustment').mockResolvedValue(adjustmentPreview);
    vi.spyOn(staffOverpaymentRecoveryClient, 'applyAdjustment').mockResolvedValue({
      recovery_identity: openQuery.recovery_identity, recovery_version: 4, staff_payables_version: 10,
      remaining_after_ntd: 0, resulting_status: 'adjusted', preview_fingerprint: adjustmentPreview.preview_fingerprint,
      evidence_reference: '電話紀錄:case-1',
    });
    vi.spyOn(staffOverpaymentRecoveryClient, 'previewMatching');
    vi.spyOn(staffOverpaymentRecoveryClient, 'applyMatching');
    const onCommitted = vi.fn();
    render(<StaffOverpaymentRecoveryActions staffId={7} recoveryIdentity={openQuery.recovery_identity} onCommitted={onCommitted} />);
    await waitFor(() => expect(screen.getByText(/目前狀態：待處理/)).toBeInTheDocument());
    expect(screen.getByText(/調整金額固定為目前剩餘追償額/)).toBeInTheDocument();
    expect(screen.queryByText(/版本 3|owner root|receipt|staff-overpayment-recovery:1/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/調整金額/)).not.toBeInTheDocument();
    fillExplanation();
    fireEvent.click(screen.getByRole('button', { name: /檢查精確調整影響/ }));
    await waitFor(() => expect(screen.getByText('處理影響已確認（尚未寫入）')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '確認並提交' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('處理理由'), { target: { value: '改寫理由使舊 Preview 失效。' } });
    expect(screen.queryByText('處理影響已確認（尚未寫入）')).not.toBeInTheDocument();
    expect(onCommitted).not.toHaveBeenCalled();
  });

  it('matched recovery requires the owner numeric bank binding and removes only after terminal readback', async () => {
    const query = vi.spyOn(staffOverpaymentRecoveryClient, 'query')
      .mockResolvedValueOnce(matchedQuery)
      .mockResolvedValueOnce(recoveredQuery);
    vi.spyOn(staffOverpaymentRecoveryClient, 'previewCollection').mockResolvedValue(collectionPreview);
    const apply = vi.spyOn(staffOverpaymentRecoveryClient, 'applyCollection').mockResolvedValue({
      recovery_identity: openQuery.recovery_identity, recovery_version: 4, staff_payables_version: 10,
      remaining_after_ntd: 0, resulting_status: 'recovered', preview_fingerprint: collectionPreview.preview_fingerprint,
      evidence_reference: '電話紀錄:case-2',
    });
    const onCommitted = vi.fn();
    render(<StaffOverpaymentRecoveryActions staffId={7} recoveryIdentity={openQuery.recovery_identity} initialFinanceImportRowId={11} onCommitted={onCommitted} />);
    await waitFor(() => expect(screen.getByText(/目前狀態：待處理/)).toBeInTheDocument());
    fillExplanation();
    fireEvent.click(screen.getByRole('button', { name: /檢查收款核銷影響/ }));
    await waitFor(() => expect(screen.getByText(/收款後剩餘 NT\$ 0/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '確認並提交' }));
    await waitFor(() => expect(screen.getByText('已重新確認追償餘額歸零且完成處理，異常可解除。')).toBeInTheDocument());
    expect(apply).toHaveBeenCalledWith(collectionPreview, expect.objectContaining({ finance_import_row_id: 11, matching_identity: 'staff-recovery-match:1', matching_version: 1 }), expect.anything());
    expect(query).toHaveBeenCalledTimes(2);
    expect(onCommitted).toHaveBeenCalledTimes(1);
  });

  it('fails closed when Query contains ambiguous current matchings', async () => {
    vi.spyOn(staffOverpaymentRecoveryClient, 'query').mockResolvedValue({
      ...matchedQuery,
      matchings: [...matchedQuery.matchings, { matching_identity: 'staff-recovery-match:2', matching_version: 1, finance_import_row_identity: 'redacted:incoming-2' }],
    });
    render(<StaffOverpaymentRecoveryActions staffId={7} recoveryIdentity={openQuery.recovery_identity} initialFinanceImportRowId={11} />);
    await waitFor(() => expect(screen.getByText(/目前有多筆入款配對/)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /檢查收款核銷影響/ })).not.toBeInTheDocument();
  });
});
