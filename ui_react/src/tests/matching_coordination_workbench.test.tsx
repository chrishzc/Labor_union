/**
 * File: matching_coordination_workbench.test.tsx
 * Description: 驗證 M3 工作台由 Query 進入 Preview／Apply，並暴露全部十五種正式操作。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { matchingCoordinationClient } from '../api/matching_coordination/matching_coordination_client';
import { MatchingCoordinationWorkbench } from '../components/MatchingCoordinationWorkbench';
import {
  MATCHING_APPLY_RECEIPT,
  MATCHING_QUERY_DATA,
  MATCHING_SNAPSHOT,
} from './fixtures/matching_coordination/matching_coordination_contract_fixtures';

afterEach(() => vi.restoreAllMocks());

describe('M3 媒合協調操作台', () => {
  it('查詢後可 Preview／Apply，並列出全部正式操作', async () => {
    const query = vi.spyOn(matchingCoordinationClient, 'query').mockResolvedValue(MATCHING_QUERY_DATA);
    const preview = vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    const apply = vi.spyOn(matchingCoordinationClient, 'applyInitialCriteria').mockResolvedValue(MATCHING_APPLY_RECEIPT);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-001' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢媒合根事實' }));
    await screen.findByText(MATCHING_SNAPSHOT.snapshot_id);
    expect(query).toHaveBeenCalledWith('CASE-M3-001', { expected_source_versions: null });
    expect(screen.getByLabelText('操作').querySelectorAll('option')).toHaveLength(15);

    fireEvent.click(screen.getByRole('button', { name: 'Preview｜建立初始條件快照' }));
    await screen.findByText('初始條件快照');
    expect(preview).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText('操作'), { target: { value: 'applyInitialCriteria' } });
    expect((screen.getByLabelText('Typed request 欄位') as HTMLTextAreaElement).value).toContain(MATCHING_SNAPSHOT.fingerprint);
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對 Preview、來源版本與即將提交的決定' }));
    fireEvent.click(screen.getByRole('button', { name: 'Apply｜提交初始條件' }));
    await waitFor(() => expect(screen.getByText('Apply 已提交')).toBeInTheDocument());
    expect(apply).toHaveBeenCalledTimes(1);
    expect(query).toHaveBeenCalledTimes(2);
  });
});
