/**
 * File: historical_baseline_projector_readback.test.tsx
 * Description: 驗證 HPROJ readback 顯示 server status/referrals/outcome_unknown 且零 mutation。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  HistoricalBaselineProjectorUnavailableError,
  type HistoricalBaselineProjectorClient,
} from '../api/anomalies/historical_baseline_projector_client';
import { HistoricalBaselineProjectorReadback } from '../components/HistoricalBaselineProjectorReadback';
import {
  HISTORICAL_BASELINE_CASE_NO,
  HISTORICAL_BASELINE_PROJECTOR_VIEW,
} from './fixtures/anomalies/historical_baseline_projector_contract_fixtures';

describe('HistoricalBaselineProjectorReadback', () => {
  it('顯示 server delivery、active count、earliest step、typed referrals 與 outcome_unknown', async () => {
    const client: HistoricalBaselineProjectorClient = {
      queryByCase: vi.fn().mockResolvedValue(HISTORICAL_BASELINE_PROJECTOR_VIEW),
    };
    render(<HistoricalBaselineProjectorReadback caseNo={HISTORICAL_BASELINE_CASE_NO} client={client} />);

    await waitFor(() => expect(screen.getByText('committed_unverified')).toBeInTheDocument());
    expect(screen.getByText('2 項')).toBeInTheDocument();
    expect(screen.getByText('Step 3')).toBeInTheDocument();
    expect(screen.getByText('orders.historical_review.remediate')).toBeInTheDocument();
    expect(screen.getByText('scheduling.assignment.repair')).toBeInTheDocument();
    expect(screen.getByText(/提交後結果仍無法確認/)).toBeInTheDocument();
    expect(screen.getByText('retry_original_trigger_reconcile')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /resolve|reconcile|排除|確認套用/i })).not.toBeInTheDocument();
    expect(Object.keys(client)).toEqual(['queryByCase']);
  });

  it('query error 保持 typed unavailable，重新讀取也只呼叫同案 GET client', async () => {
    const queryByCase = vi.fn()
      .mockRejectedValueOnce(new HistoricalBaselineProjectorUnavailableError(
        'historical_baseline_projection_unavailable',
        'unavailable',
        true,
        503,
      ))
      .mockResolvedValueOnce(HISTORICAL_BASELINE_PROJECTOR_VIEW);
    render(<HistoricalBaselineProjectorReadback
      caseNo={HISTORICAL_BASELINE_CASE_NO}
      client={{ queryByCase }}
    />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('historical_baseline_projection_unavailable'));
    fireEvent.click(screen.getByRole('button', { name: '重新讀取' }));
    await waitFor(() => expect(screen.getByText('committed_unverified')).toBeInTheDocument());
    expect(queryByCase).toHaveBeenCalledTimes(2);
    expect(queryByCase).toHaveBeenNthCalledWith(1, HISTORICAL_BASELINE_CASE_NO, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(queryByCase).toHaveBeenNthCalledWith(2, HISTORICAL_BASELINE_CASE_NO, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('案件切換時忽略先前案件的 stale readback', async () => {
    let resolveFirst: ((value: typeof HISTORICAL_BASELINE_PROJECTOR_VIEW) => void) | undefined;
    const queryByCase = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({
        ...HISTORICAL_BASELINE_PROJECTOR_VIEW,
        receipt: { ...HISTORICAL_BASELINE_PROJECTOR_VIEW.receipt!, case_no: 'CASE-HPROJ-2' },
        current_alert: {
          ...HISTORICAL_BASELINE_PROJECTOR_VIEW.current_alert!,
          display: { ...HISTORICAL_BASELINE_PROJECTOR_VIEW.current_alert!.display, case_no: 'CASE-HPROJ-2' },
        },
      });
    const { rerender } = render(<HistoricalBaselineProjectorReadback caseNo={HISTORICAL_BASELINE_CASE_NO} client={{ queryByCase }} />);
    rerender(<HistoricalBaselineProjectorReadback caseNo="CASE-HPROJ-2" client={{ queryByCase }} />);

    await waitFor(() => expect(queryByCase).toHaveBeenCalledTimes(2));
    resolveFirst?.(HISTORICAL_BASELINE_PROJECTOR_VIEW);
    await waitFor(() => expect(screen.getByText('2 項')).toBeInTheDocument());
    expect(screen.getByLabelText('歷史基線投影回讀')).toHaveAttribute('data-delivery-status', 'committed_unverified');
  });
});
