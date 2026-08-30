/**
 * File: historical_operational_baseline_readback.test.tsx
 * Description: 驗證 Orders baseline readback 顯示 typed owner facts 且零 mutation。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  HistoricalOperationalBaselineUnavailableError,
  type HistoricalOperationalBaselineClient,
} from '../api/orders/historical_operational_baseline_client';
import { HistoricalOperationalBaselineReadback } from '../components/HistoricalOperationalBaselineReadback';
import {
  HISTORICAL_BASELINE_CASE_NO,
  HISTORICAL_OPERATIONAL_BASELINE_VIEW,
} from './fixtures/orders/historical_operational_baseline_contract_fixtures';

describe('HistoricalOperationalBaselineReadback Orders owner', () => {
  it('顯示 Orders identity、version、selected step 與 typed step projection', async () => {
    const client: HistoricalOperationalBaselineClient = {
      queryByCase: vi.fn().mockResolvedValue(HISTORICAL_OPERATIONAL_BASELINE_VIEW),
    };
    render(<HistoricalOperationalBaselineReadback caseNo={HISTORICAL_BASELINE_CASE_NO} client={client} />);

    await waitFor(() => expect(screen.getByText('Step 3')).toBeInTheDocument());
    expect(screen.getByText('order:CASE-HOB-1')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getAllByText('historical_baseline_completed')).toHaveLength(2);
    expect(screen.getByText('in_progress')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /resolve|reconcile|排除|確認套用/i })).not.toBeInTheDocument();
    expect(Object.keys(client)).toEqual(['queryByCase']);
  });

  it('query error 保持 typed unavailable，重新讀取也只呼叫同案 Orders GET client', async () => {
    const queryByCase = vi.fn()
      .mockRejectedValueOnce(new HistoricalOperationalBaselineUnavailableError(
        'historical_operational_baseline_unavailable',
        'unavailable',
        true,
        503,
      ))
      .mockResolvedValueOnce(HISTORICAL_OPERATIONAL_BASELINE_VIEW);
    render(<HistoricalOperationalBaselineReadback
      caseNo={HISTORICAL_BASELINE_CASE_NO}
      client={{ queryByCase }}
    />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('historical_operational_baseline_unavailable'));
    fireEvent.click(screen.getByRole('button', { name: '重新讀取' }));
    await waitFor(() => expect(screen.getByText('Step 3')).toBeInTheDocument());
    expect(queryByCase).toHaveBeenCalledTimes(2);
    expect(queryByCase).toHaveBeenNthCalledWith(1, HISTORICAL_BASELINE_CASE_NO, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(queryByCase).toHaveBeenNthCalledWith(2, HISTORICAL_BASELINE_CASE_NO, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('案件切換時忽略先前案件的 stale readback', async () => {
    let resolveFirst: ((value: typeof HISTORICAL_OPERATIONAL_BASELINE_VIEW) => void) | undefined;
    const queryByCase = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce({
        ...HISTORICAL_OPERATIONAL_BASELINE_VIEW,
        case_no: 'CASE-HOB-2',
        order_identity: 'order:CASE-HOB-2',
      });
    const { rerender } = render(<HistoricalOperationalBaselineReadback caseNo={HISTORICAL_BASELINE_CASE_NO} client={{ queryByCase }} />);
    rerender(<HistoricalOperationalBaselineReadback caseNo="CASE-HOB-2" client={{ queryByCase }} />);

    await waitFor(() => expect(queryByCase).toHaveBeenCalledTimes(2));
    resolveFirst?.(HISTORICAL_OPERATIONAL_BASELINE_VIEW);
    await waitFor(() => expect(screen.getByText('order:CASE-HOB-2')).toBeInTheDocument());
    expect(screen.getByLabelText('歷史案件作業基準')).toHaveAttribute('data-baseline-step', '3');
  });
});
