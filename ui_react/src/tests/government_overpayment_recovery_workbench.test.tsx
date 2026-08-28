/**
 * File: government_overpayment_recovery_workbench.test.tsx
 * Description: 驗證 GOVSUB-006 工作區的 Preview gate、輸入失效與 owner readback predicate。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GovernmentOverpaymentRecoveryWorkbench } from '../components/GovernmentOverpaymentRecoveryWorkbench';
import { GovernmentOverpaymentRecoveryError } from '../api/government_subsidy/government_overpayment_recovery_client';
import type { GovernmentOverpaymentQuery } from '../api/government_subsidy/government_overpayment_recovery_schemas';
import type { AnomalyDetailView } from '../api/anomalies/anomaly_detail_schemas';

const identity = 'government-overpayment:bank:11';
const anomalyFingerprint = 'c'.repeat(64);
const clearedAnomaly = {
  summary: { fingerprint: anomalyFingerprint, definition_code: 'GOVSUB-006', predicate_active: false },
} as unknown as AnomalyDetailView;
const query: GovernmentOverpaymentQuery = {
  overpayment_identity: identity,
  payer_identity: 'hccg',
  remaining_amount_ntd: 900,
  status: 'pending_review',
  overpayment_version: 2,
  source_bank_fact_reference: 'finance-import-row:11',
  source_transaction_reference: 'government-subsidy-transaction:8',
  offset_targets: [{ claim_item_id: 31, claim_batch_id: 4, batch_version: 7, outstanding_amount_ntd: 900, payer_identity: 'hccg' }],
  return_recipient: {
    ready: true,
    blockers: [],
    agency_identity: 'hccg',
    agency_name: '新竹市政府',
    bank_code: '822',
    account_display: '******1234',
    account_fingerprint: 'a'.repeat(64),
    effective_date: '2026-08-01',
  },
  blockers: [],
  available_actions: ['offset', 'return'],
};

describe('GovernmentOverpaymentRecoveryWorkbench', () => {
  it('Preview 前不可 Apply；輸入變更會失效 Preview，成功後只依 owner readback 顯示解除', async () => {
    const resolved = { ...query, status: 'offset_applied' as const, remaining_amount_ntd: 0 };
    const client = {
      query: vi.fn().mockResolvedValueOnce(query).mockResolvedValueOnce(resolved),
      preview: vi.fn().mockResolvedValue({
        overpayment_identity: identity,
        overpayment_version: 2,
        remaining_before_ntd: 900,
        disposition_amount_ntd: 900,
        remaining_after_ntd: 0,
        resulting_status: 'offset_applied' as const,
        disposition_kind: 'offset' as const,
        preview_fingerprint: 'b'.repeat(64),
      }),
      apply: vi.fn().mockResolvedValue({
        overpayment_identity: identity,
        remaining_after_ntd: 0,
        status: 'offset_applied' as const,
        preview_fingerprint: 'b'.repeat(64),
        payable_identity: null,
      }),
    };
    const onResolved = vi.fn().mockResolvedValue({ succeeded: true, originalFingerprintPresent: false });
    const anomalyClient = { queryAnomalyDetail: vi.fn().mockResolvedValue(clearedAnomaly) };
    render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} anomalyClient={anomalyClient} client={client} onResolved={onResolved} />);

    await screen.findByText('目前狀態：');
    const evidence = screen.getByLabelText('處置證據');
    fireEvent.change(evidence, { target: { value: 'phone-call:case-11' } });
    fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '依正式規則書核對後抵扣' } });
    fireEvent.change(screen.getByLabelText('抵扣標的 31 金額'), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await waitFor(() => expect(client.preview).toHaveBeenCalledTimes(1));
    const applyButton = screen.getByRole('button', { name: '確認套用處置' });
    expect(applyButton).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox'));
    expect(applyButton).toBeEnabled();
    fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '改用電話補充證據' } });
    expect(screen.queryByText(/套用後狀態：offset_applied/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await waitFor(() => expect(client.preview).toHaveBeenCalledTimes(2));
    fireEvent.change(evidence, { target: { value: 'phone-call:case-12' } });
    expect(screen.queryByText(/套用後狀態：offset_applied/)).not.toBeInTheDocument();

    fireEvent.change(evidence, { target: { value: 'phone-call:case-11' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await waitFor(() => expect(client.preview).toHaveBeenCalledTimes(3));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用處置' }));
    await waitFor(() => expect(client.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/異常已依 owner root 與原 GOVSUB-006 predicate/)).toBeInTheDocument();
  });

  it('owner query 沒有合法標的或退款對象時顯示 blocker，不產生假 action', async () => {
    const blockedQuery: GovernmentOverpaymentQuery = {
      ...query,
      offset_targets: [],
      return_recipient: {
        ready: false,
        blockers: ['government_subsidy_recipient_account_missing'],
        agency_identity: null,
        agency_name: null,
        bank_code: null,
        account_display: null,
        account_fingerprint: null,
        effective_date: null,
      },
      available_actions: [],
      blockers: ['government_subsidy_recipient_account_missing'],
    };
    const client = {
      query: vi.fn().mockResolvedValue(blockedQuery),
      preview: vi.fn(),
      apply: vi.fn(),
    };
    render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} client={client} />);
    await screen.findByText(/government_subsidy_recipient_account_missing/);
    expect(screen.getByRole('button', { name: '檢查處置影響' })).toBeDisabled();
    expect(client.preview).not.toHaveBeenCalled();
  });

  it('Apply 結果未明時先回讀 owner，再以同一 idempotency key 安全重試', async () => {
    const resolved = { ...query, status: 'offset_applied' as const, remaining_amount_ntd: 0 };
    const client = {
      query: vi.fn().mockResolvedValueOnce(query).mockResolvedValueOnce(resolved),
      preview: vi.fn().mockResolvedValue({
        overpayment_identity: identity, overpayment_version: 2,
        remaining_before_ntd: 900, disposition_amount_ntd: 900, remaining_after_ntd: 0,
        resulting_status: 'offset_applied' as const, disposition_kind: 'offset' as const,
        preview_fingerprint: 'b'.repeat(64),
      }),
      apply: vi.fn()
        .mockRejectedValueOnce(new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_TIMEOUT', 'timeout', true))
        .mockResolvedValueOnce({
          overpayment_identity: identity, remaining_after_ntd: 0, status: 'offset_applied' as const,
          preview_fingerprint: 'b'.repeat(64), payable_identity: null,
        }),
    };
    const anomalyClient = { queryAnomalyDetail: vi.fn().mockResolvedValue(clearedAnomaly) };
    const onResolved = vi.fn().mockResolvedValue({ succeeded: true, originalFingerprintPresent: false });
    render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} anomalyClient={anomalyClient} client={client} onResolved={onResolved} />);
    await screen.findByText('目前狀態：');
    fireEvent.change(screen.getByLabelText('處置證據'), { target: { value: 'phone-log:11' } });
    fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '依電話補件確認' } });
    fireEvent.change(screen.getByLabelText('抵扣標的 31 金額'), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await screen.findByText(/套用後狀態：offset_applied/);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用處置' }));
    await screen.findByText(/Apply 結果未明/);
    const firstKey = client.apply.mock.calls[0][1].idempotencyKey;

    fireEvent.click(screen.getByRole('button', { name: '重新查詢並安全確認結果' }));
    await waitFor(() => expect(client.apply).toHaveBeenCalledTimes(1));
    expect(client.apply.mock.calls[0][1].idempotencyKey).toBe(firstKey);
    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/異常已依 owner root 與原 GOVSUB-006 predicate/)).toBeInTheDocument();
  });

  it('receipt-only 或 anomaly predicate 仍 active 時不宣告完成', async () => {
    const activeAnomaly = {
      summary: { fingerprint: anomalyFingerprint, definition_code: 'GOVSUB-006', predicate_active: true },
    } as unknown as AnomalyDetailView;
    const resolved = { ...query, status: 'offset_applied' as const, remaining_amount_ntd: 0 };
    const client = {
      query: vi.fn().mockResolvedValueOnce(query).mockResolvedValueOnce(resolved),
      preview: vi.fn().mockResolvedValue({
        overpayment_identity: identity, overpayment_version: 2,
        remaining_before_ntd: 900, disposition_amount_ntd: 900, remaining_after_ntd: 0,
        resulting_status: 'offset_applied' as const, disposition_kind: 'offset' as const,
        preview_fingerprint: 'b'.repeat(64),
      }),
      apply: vi.fn().mockResolvedValue({
        overpayment_identity: identity, remaining_after_ntd: 0, status: 'offset_applied' as const,
        preview_fingerprint: 'b'.repeat(64), payable_identity: null,
      }),
    };
    const onResolved = vi.fn().mockResolvedValue({ succeeded: true, originalFingerprintPresent: false });
    const anomalyClient = { queryAnomalyDetail: vi.fn().mockResolvedValue(activeAnomaly) };
    render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} anomalyClient={anomalyClient} client={client} onResolved={onResolved} />);
    await screen.findByText('目前狀態：');
    fireEvent.change(screen.getByLabelText('處置證據'), { target: { value: 'receipt-only:11' } });
    fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '根因仍待投影確認' } });
    fireEvent.change(screen.getByLabelText('抵扣標的 31 金額'), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await screen.findByText(/套用後狀態：offset_applied/);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用處置' }));
    await waitFor(() => expect(client.apply).toHaveBeenCalledTimes(1));
    expect(onResolved).not.toHaveBeenCalled();
    expect(screen.getByText(/尚未完成 owner 與 anomaly predicate 雙重回讀/)).toBeInTheDocument();
  });

  it('receipt 後 owner readback 暫時失敗可恢復，且只重做 GET', async () => {
    const resolved = { ...query, status: 'offset_applied' as const, remaining_amount_ntd: 0 };
    const client = {
      query: vi.fn().mockResolvedValueOnce(query).mockRejectedValueOnce(new Error('readback unavailable')).mockResolvedValueOnce(resolved),
      preview: vi.fn().mockResolvedValue({
        overpayment_identity: identity, overpayment_version: 2,
        remaining_before_ntd: 900, disposition_amount_ntd: 900, remaining_after_ntd: 0,
        resulting_status: 'offset_applied' as const, disposition_kind: 'offset' as const,
        preview_fingerprint: 'b'.repeat(64),
      }),
      apply: vi.fn().mockResolvedValue({
        overpayment_identity: identity, remaining_after_ntd: 0, status: 'offset_applied' as const,
        preview_fingerprint: 'b'.repeat(64), payable_identity: null,
      }),
    };
    const anomalyClient = { queryAnomalyDetail: vi.fn().mockResolvedValue(clearedAnomaly) };
    const onResolved = vi.fn().mockResolvedValue({ succeeded: true, originalFingerprintPresent: false });
    render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} anomalyClient={anomalyClient} client={client} onResolved={onResolved} />);
    await screen.findByText('目前狀態：');
    fireEvent.change(screen.getByLabelText('處置證據'), { target: { value: 'readback:11' } });
    fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '重新查詢 owner 根事實' } });
    fireEvent.change(screen.getByLabelText('抵扣標的 31 金額'), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await screen.findByText(/套用後狀態：offset_applied/);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用處置' }));
    await screen.findByText(/owner／anomaly readback 暫時失敗/);
    fireEvent.click(screen.getByRole('button', { name: '重新查詢 owner 與 anomaly' }));
    await waitFor(() => expect(client.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(3));
    expect(onResolved).toHaveBeenCalledTimes(1);
  });

  it('stale Apply 先 GET 最新 owner、清除舊 Preview，且不自動再次 Apply', async () => {
    const freshQuery = { ...query, overpayment_version: 3 };
    const client = {
      query: vi.fn().mockResolvedValueOnce(query).mockResolvedValueOnce(freshQuery),
      preview: vi.fn().mockResolvedValue({
        overpayment_identity: identity, overpayment_version: 2,
        remaining_before_ntd: 900, disposition_amount_ntd: 900, remaining_after_ntd: 0,
        resulting_status: 'offset_applied' as const, disposition_kind: 'offset' as const,
        preview_fingerprint: 'b'.repeat(64),
      }),
      apply: vi.fn().mockRejectedValue(new GovernmentOverpaymentRecoveryError('GOVERNMENT_OVERPAYMENT_PREVIEW_STALE', 'stale')),
    };
    render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} client={client} />);
    await screen.findByText('目前狀態：');
    fireEvent.change(screen.getByLabelText('處置證據'), { target: { value: 'stale-case:11' } });
    fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '重新核對最新版本' } });
    fireEvent.change(screen.getByLabelText('抵扣標的 31 金額'), { target: { value: '900' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
    await screen.findByText(/套用後狀態：offset_applied/);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: '確認套用處置' }));
    await waitFor(() => expect(client.apply).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(client.query).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/套用後狀態：offset_applied/)).not.toBeInTheDocument();
    expect(screen.getByText(/舊 Preview 已清除，請重新檢查處置影響/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查處置影響' })).toBeEnabled();
    expect(client.apply).toHaveBeenCalledTimes(1);
  });

  it('active list refresh 回傳 typed 結果為失敗或仍含原 fingerprint 時不宣告完成', async () => {
    const resolved = { ...query, status: 'offset_applied' as const, remaining_amount_ntd: 0 };
    for (const refresh of [
      { succeeded: false, originalFingerprintPresent: false },
      { succeeded: true, originalFingerprintPresent: true },
    ]) {
      const client = {
        query: vi.fn().mockResolvedValueOnce(query).mockResolvedValueOnce(resolved),
        preview: vi.fn().mockResolvedValue({
          overpayment_identity: identity, overpayment_version: 2,
          remaining_before_ntd: 900, disposition_amount_ntd: 900, remaining_after_ntd: 0,
          resulting_status: 'offset_applied' as const, disposition_kind: 'offset' as const,
          preview_fingerprint: 'b'.repeat(64),
        }),
        apply: vi.fn().mockResolvedValue({
          overpayment_identity: identity, remaining_after_ntd: 0, status: 'offset_applied' as const,
          preview_fingerprint: 'b'.repeat(64), payable_identity: null,
        }),
      };
      const onResolved = vi.fn().mockResolvedValue(refresh);
      const anomalyClient = { queryAnomalyDetail: vi.fn().mockResolvedValue(clearedAnomaly) };
      const { unmount } = render(<GovernmentOverpaymentRecoveryWorkbench overpaymentIdentity={identity} anomalyFingerprint={anomalyFingerprint} anomalyClient={anomalyClient} client={client} onResolved={onResolved} />);
      await screen.findByText('目前狀態：');
      fireEvent.change(screen.getByLabelText('處置證據'), { target: { value: 'refresh-case:11' } });
      fireEvent.change(screen.getByLabelText('人工處置原因'), { target: { value: '重新核對清單' } });
      fireEvent.change(screen.getByLabelText('抵扣標的 31 金額'), { target: { value: '900' } });
      fireEvent.click(screen.getByRole('button', { name: '檢查處置影響' }));
      await screen.findByText(/套用後狀態：offset_applied/);
      fireEvent.click(screen.getByRole('checkbox'));
      fireEvent.click(screen.getByRole('button', { name: '確認套用處置' }));
      await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
      expect(screen.queryByText(/異常已依 owner root 與原 GOVSUB-006 predicate/)).not.toBeInTheDocument();
      unmount();
    }
  });
});
