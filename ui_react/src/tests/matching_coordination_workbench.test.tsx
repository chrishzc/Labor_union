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
    expect(screen.getByLabelText('目前要處理的業務').querySelectorAll('option')).toHaveLength(15);

    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));
    await screen.findByText('初始條件快照');
    expect(preview).toHaveBeenCalledTimes(1);
    expect(preview).toHaveBeenCalledWith(
      'CASE-M3-001',
      expect.objectContaining({ expected_source_versions: MATCHING_QUERY_DATA.source_versions }),
      expect.anything(),
    );

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyInitialCriteria' } });
    expect((screen.getByLabelText('系統交換欄位') as HTMLTextAreaElement).value).toContain(MATCHING_SNAPSHOT.fingerprint);
    expect((screen.getByLabelText('系統交換欄位') as HTMLTextAreaElement).value).toContain('orders_terms');
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' }));
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));
    await waitFor(() => expect(screen.getByText('Apply 已提交')).toBeInTheDocument());
    expect(apply).toHaveBeenCalledTimes(1);
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('無舊快照時，初始 Preview 會交由後端 fresh-read 來源版本', async () => {
    const preview = vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-LEGACY' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));

    await screen.findByText('初始條件快照');
    expect(preview).toHaveBeenCalledWith(
      'CASE-M3-LEGACY',
      expect.objectContaining({ expected_source_versions: null }),
      expect.anything(),
    );

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyInitialCriteria' } });
    const applyPayload = (screen.getByLabelText('系統交換欄位') as HTMLTextAreaElement).value;
    expect(applyPayload).toContain('orders_terms');
    expect(applyPayload).toContain(MATCHING_SNAPSHOT.fingerprint);
  });

  it('提交業務決定前，要求完成同一業務的對應試算', () => {
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-LOCK' } });
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyCustomerDecision' } });
    expect(screen.getByText('請先完成「3. 試算可推薦月嫂與服務分段」。')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '確認提交此業務決定' })).toBeDisabled();
  });

  it('嵌入既有媒合工作台時沿用案件內容，並以業務結果取代技術交換欄位', async () => {
    vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    render(<MatchingCoordinationWorkbench initialCaseNo="CASE-IN-DRAWER-001" />);

    expect(screen.getByText('案件 CASE-IN-DRAWER-001')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '核對媒合條件' })).toBeEnabled();
    expect(screen.queryByLabelText('案件編號')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('系統交換欄位')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '核對媒合條件' }));
    await screen.findByText('條件已核對');
    expect(screen.queryByText(/fingerprint：/)).not.toBeInTheDocument();
  });
});
