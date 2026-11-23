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
  MATCHING_PACKAGE,
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
    expect(screen.queryByText(`條件快照：${MATCHING_SNAPSHOT.snapshot_id}`)).not.toBeInTheDocument();
    expect(query).toHaveBeenCalledWith('CASE-M3-001', { expected_source_versions: null });
    expect(screen.getByLabelText('目前要處理的業務').querySelectorAll('option')).toHaveLength(17);

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'previewInitialCriteria' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));
    await screen.findByText('初始條件快照');
    expect(preview).toHaveBeenCalledTimes(1);
    expect(preview).toHaveBeenCalledWith(
      'CASE-M3-001',
      expect.objectContaining({ expected_source_versions: MATCHING_QUERY_DATA.source_versions }),
      expect.anything(),
    );

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyInitialCriteria' } });
    expect(screen.queryByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));
    await waitFor(() => expect(screen.getByText('媒合決定已完成並回讀')).toBeInTheDocument());
    expect(screen.queryByText(`receipt：${MATCHING_APPLY_RECEIPT.receipt_id}`)).not.toBeInTheDocument();
    expect(apply).toHaveBeenCalledWith(
      'CASE-M3-001',
      expect.objectContaining({
        preview_fingerprint: MATCHING_SNAPSHOT.fingerprint,
        expected_source_versions: MATCHING_QUERY_DATA.source_versions,
      }),
      expect.anything(),
    );
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
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));

    await screen.findByText('步驟 2 受阻');
    expect(screen.queryByText('原始處置：blocked_no_candidate')).not.toBeInTheDocument();
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
    expect(preview.mock.calls[0]?.[1]).not.toHaveProperty('candidate_count');
    expect(preview.mock.calls[0]?.[1]).not.toHaveProperty('disposition');
    expect(preview.mock.calls[0]?.[1]).not.toHaveProperty('state');

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyZeroCandidateConfirmation' } });
    expect(screen.queryByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));

    await screen.findByText(/目前仍停在步驟 2，沒有合法候選/);
    expect(screen.getByText(/不代表異常已解除/)).toBeInTheDocument();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('首次非零 Preview 會把完整 package 帶入 caregiver Apply，完成後重新 Query', async () => {
    const firstQuery = { ...MATCHING_QUERY_DATA, package: null };
    const query = vi.spyOn(matchingCoordinationClient, 'query')
      .mockResolvedValueOnce(firstQuery)
      .mockResolvedValueOnce(MATCHING_QUERY_DATA);
    vi.spyOn(matchingCoordinationClient, 'previewMatchingPackage')
      .mockResolvedValue(MATCHING_PACKAGE);
    const apply = vi.spyOn(matchingCoordinationClient, 'applyCaregiverSelection')
      .mockResolvedValue(MATCHING_APPLY_RECEIPT);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-FIRST' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢媒合資料' }));
    await screen.findByText('尚未建立');
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'previewMatchingPackage' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));
    await screen.findByText('媒合方案');

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyCaregiverSelection' } });
    expect(screen.queryByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));
    await screen.findByText('媒合決定已完成並回讀');
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply.mock.calls[0]?.[1]).toEqual(expect.objectContaining({
      package_id: MATCHING_PACKAGE.package_id,
      package_version: MATCHING_PACKAGE.version,
      segments: MATCHING_PACKAGE.segments,
      required_service_dates: MATCHING_PACKAGE.required_service_dates,
    }));
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
    await screen.findByText('步驟 2 受阻');
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyZeroCandidateConfirmation' } });
    expect(screen.queryByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' })).not.toBeInTheDocument();
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
    const apply = vi.spyOn(matchingCoordinationClient, 'applyInitialCriteria').mockResolvedValue(MATCHING_APPLY_RECEIPT);
    vi.spyOn(matchingCoordinationClient, 'query').mockResolvedValue(MATCHING_QUERY_DATA);
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-LEGACY' } });
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'previewInitialCriteria' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));

    await screen.findByText('初始條件快照');
    expect(preview).toHaveBeenCalledWith(
      'CASE-M3-LEGACY',
      expect.objectContaining({ expected_source_versions: null }),
      expect.anything(),
    );

    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyInitialCriteria' } });
    fireEvent.click(screen.getByRole('button', { name: '確認提交此業務決定' }));
    await waitFor(() => expect(apply).toHaveBeenCalledWith(
      'CASE-M3-LEGACY',
      expect.objectContaining({
        preview_fingerprint: MATCHING_SNAPSHOT.fingerprint,
        expected_source_versions: { items: MATCHING_SNAPSHOT.source_versions },
      }),
      expect.anything(),
    ));
  });

  it('提交業務決定沿用自動核對來源版本的單次儲存入口', () => {
    render(<MatchingCoordinationWorkbench />);

    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-LOCK' } });
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'applyCustomerDecision' } });
    expect(screen.getByText('儲存時自動核對目前資料與版本；原因可留空。')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: '我已核對試算結果、來源版本與即將提交的決定' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認提交此業務決定' })).toBeEnabled();
  });

  it('嵌入既有媒合工作台時沿用案件內容，並以業務結果取代技術交換欄位', async () => {
    const checked = vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    const saved = vi.spyOn(matchingCoordinationClient, 'applyInitialCriteria').mockResolvedValue(MATCHING_APPLY_RECEIPT);
    vi.spyOn(matchingCoordinationClient, 'query').mockResolvedValue(MATCHING_QUERY_DATA);
    render(<MatchingCoordinationWorkbench initialCaseNo="CASE-IN-DRAWER-001" />);

    expect(screen.getByText('案件 CASE-IN-DRAWER-001')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存媒合條件' })).toBeEnabled();
    expect(screen.queryByLabelText('案件編號')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('系統交換欄位')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存媒合條件' }));
    await screen.findByText('媒合決定已完成並回讀');
    expect(checked).toHaveBeenCalledOnce();
    expect(saved).toHaveBeenCalledOnce();
    expect(checked.mock.invocationCallOrder[0]).toBeLessThan(saved.mock.invocationCallOrder[0]);
    expect(screen.queryByText(/fingerprint：/)).not.toBeInTheDocument();
  });

  it('standalone 技術操作欄位與 Preview 證據預設收合', async () => {
    vi.spyOn(matchingCoordinationClient, 'previewInitialCriteria').mockResolvedValue(MATCHING_SNAPSHOT);
    render(<MatchingCoordinationWorkbench />);

    expect(screen.queryByText('技術操作欄位')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-M3-DETAILS' } });
    fireEvent.change(screen.getByLabelText('目前要處理的業務'), { target: { value: 'previewInitialCriteria' } });
    fireEvent.click(screen.getByRole('button', { name: '執行試算' }));
    await screen.findByText('初始條件快照');
    expect(screen.queryByText(`identity：${MATCHING_SNAPSHOT.snapshot_id}`)).not.toBeInTheDocument();
    expect(screen.queryByText(`fingerprint：${MATCHING_SNAPSHOT.fingerprint}`)).not.toBeInTheDocument();
  });
});
