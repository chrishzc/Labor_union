/**
 * File: matching_coordination_workbench.test.tsx
 * Description: 驗證 M3 工作台由 Query 進入 Preview／Apply、收合技術資料，並保留全部十七種正式操作。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { matchingCoordinationClient } from '../api/matching_coordination/matching_coordination_client';
import { MatchingCoordinationWorkbench } from '../components/MatchingCoordinationWorkbench';
import {
  MATCHING_APPLY_RECEIPT,
  MATCHING_NO_CANDIDATE_PACKAGE,
  MATCHING_OPEN_PACKAGE,
  MATCHING_QUERY_DATA,
  MATCHING_SNAPSHOT,
  MATCHING_ZERO_CANDIDATE_CONFIRMATION_RECEIPT,
} from './fixtures/matching_coordination/matching_coordination_contract_fixtures';
import { ApiTimeoutError } from '../api/matching_coordination/matching_coordination_errors';

afterEach(() => vi.restoreAllMocks());

describe('M3 媒合協調操作台', () => {
  it('查詢後可 Preview／Apply，並列出全部正式操作', async () => {
    const query = vi.spyOn(matchingCoordinationClient, 'query').mockResolvedValue(MATCHING_QUERY_DATA);
    const preview = vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    const apply = vi.spyOn(matchingCoordinationClient, 'applyInitialCriteria').mockResolvedValue(MATCHING_APPLY_RECEIPT);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-001' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢媒合資料' }));
    await screen.findByText(`第 ${MATCHING_SNAPSHOT.criteria_version} 版`);
    expect(screen.getByText(`條件快照：${MATCHING_SNAPSHOT.snapshot_id}`).closest('details')).not.toHaveAttribute('open');
    expect(query).toHaveBeenCalledWith('CASE-M3-001', { expected_source_versions: null });
    expect(screen.getByLabelText('目前要處理的業務').querySelectorAll('option')).toHaveLength(17);

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
    await waitFor(() => expect(screen.getByText('媒合決定已完成並回讀')).toBeInTheDocument());
    expect(screen.getByText(`receipt：${MATCHING_APPLY_RECEIPT.receipt_id}`).closest('details')).not.toHaveAttribute('open');
    expect(apply).toHaveBeenCalledTimes(1);
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('確認零候選只送 owner evidence，顯示 Step 2 blocked 且不宣稱異常解除', async () => {
    const zeroCandidateQuery = {
      ...MATCHING_QUERY_DATA,
      package: MATCHING_OPEN_PACKAGE,
      candidates: [],
    };
    const query = vi.spyOn(matchingCoordinationClient, 'query').mockResolvedValue(zeroCandidateQuery);
    const preview = vi.spyOn(matchingCoordinationClient, 'previewZeroCandidateConfirmation').mockResolvedValue(MATCHING_NO_CANDIDATE_PACKAGE);
    const apply = vi.spyOn(matchingCoordinationClient, 'applyZeroCandidateConfirmation').mockResolvedValue(MATCHING_ZERO_CANDIDATE_CONFIRMATION_RECEIPT);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-R07-001' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢媒合資料' }));
    await screen.findByText('已建立');

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'previewZeroCandidateConfirmation' } });
    const previewPayload = (screen.getByLabelText('系統交換欄位') as HTMLTextAreaElement).value;
    expect(previewPayload).toContain('fresh_pool_query_empty');
    expect(previewPayload).not.toContain('candidate_count');
    expect(previewPayload).not.toContain('disposition');
    expect(previewPayload).not.toContain('"state"');
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));

    await screen.findByText('Step 2 受阻');
    expect(screen.getByText('原始處置：blocked_no_candidate').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('這只記錄目前的受阻事實，不代表異常已解除')).toBeInTheDocument();
    expect(preview).toHaveBeenCalledWith(
      'CASE-R07-001',
      expect.objectContaining({
        evidence: ['fresh_pool_query_empty'],
        package_id: MATCHING_OPEN_PACKAGE.package_id,
        package_version: MATCHING_OPEN_PACKAGE.version,
      }),
      expect.anything(),
    );

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyZeroCandidateConfirmation' } });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' }));
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));

    await screen.findByText(/目前仍停在步驟 2，沒有合法候選/);
    expect(screen.getByText(/不代表異常已解除/)).toBeInTheDocument();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('確認零候選 Apply 結果未知時只以相同 payload 與 idempotency key 重試', async () => {
    const zeroCandidateQuery = {
      ...MATCHING_QUERY_DATA,
      package: MATCHING_OPEN_PACKAGE,
      candidates: [],
    };
    vi.spyOn(matchingCoordinationClient, 'query').mockResolvedValue(zeroCandidateQuery);
    vi.spyOn(matchingCoordinationClient, 'previewZeroCandidateConfirmation').mockResolvedValue(MATCHING_NO_CANDIDATE_PACKAGE);
    const apply = vi.spyOn(matchingCoordinationClient, 'applyZeroCandidateConfirmation')
      .mockRejectedValueOnce(new ApiTimeoutError(10_000))
      .mockResolvedValueOnce(MATCHING_ZERO_CANDIDATE_CONFIRMATION_RECEIPT);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-R07-RETRY' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢媒合資料' }));
    await screen.findByText('已建立');
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'previewZeroCandidateConfirmation' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));
    await screen.findByText('Step 2 受阻');
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyZeroCandidateConfirmation' } });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' }));
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));

    await screen.findByRole('button', { name: '安全重試原操作' });
    expect(screen.getByRole('alert')).toHaveTextContent('提交結果目前無法確認');
    fireEvent.click(screen.getByRole('button', { name: '安全重試原操作' }));
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(2));
    expect(apply.mock.calls[1]?.[1]).toEqual(apply.mock.calls[0]?.[1]);
    expect(apply.mock.calls[1]?.[2].idempotencyKey).toBe(apply.mock.calls[0]?.[2].idempotencyKey);
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

  it('standalone 技術操作欄位與 Preview 證據預設收合', async () => {
    vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    render(<MatchingCoordinationWorkbench />);

    expect(screen.getByText('技術操作欄位').closest('details')).not.toHaveAttribute('open');
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-DETAILS' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));
    await screen.findByText('初始條件快照');
    expect(screen.getByText(`identity：${MATCHING_SNAPSHOT.snapshot_id}`).closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText(`fingerprint：${MATCHING_SNAPSHOT.fingerprint}`).closest('details')).not.toHaveAttribute('open');
  });
});
