/**
 * File: data_import_hcm_preview_flow.test.tsx
 * Description: 驗證HCM Preview／Apply、安全replay identity、未新增提示與結果重新查詢。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hcmWorkbookPreviewClient } from '../api/case_import/hcm_workbook_client';
import { DataImportPage } from '../pages/DataImportPage';
import { HCM_WORKBOOK_PREVIEW_FIXTURE } from './fixtures/hcm_workbook_contract_fixtures';

function hcmWorkbook(contents: string): File {
  return new File([contents], 'hcm-current.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

describe('DataImport HCM Preview retirement compatibility', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmWorkbookPreviewClient, 'preview').mockResolvedValue(HCM_WORKBOOK_PREVIEW_FIXTURE);
    vi.spyOn(hcmWorkbookPreviewClient, 'apply').mockResolvedValue({
      source_content_digest: HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest,
      source_row_count: 1,
      inserted_count: 1,
      inserted_with_warning_count: 0,
      exact_replay_count: 0,
      review_required_count: 0,
      failed_count: 0,
      skipped_existing_count: 0,
      replayed_workbook: false,
      row_outcomes_available: true,
      legacy_summary_only: false,
      row_outcomes: [],
    });
  });

  it('imports with one click and no human preview or confirmation checkbox', async () => {
    render(<DataImportPage />);
    fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), { target: { files: [hcmWorkbook('workbook-a')] } });
    expect(hcmWorkbookPreviewClient.apply).not.toHaveBeenCalled();
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await waitFor(() => expect(hcmWorkbookPreviewClient.apply).toHaveBeenCalledOnce());
    expect(hcmWorkbookPreviewClient.preview).toHaveBeenCalledOnce();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.getByText('匯入結果')).toBeInTheDocument();
  });

  it('整份HCM工作簿replay先標示未新增，原receipt統計僅供追溯', async () => {
    vi.mocked(hcmWorkbookPreviewClient.apply).mockResolvedValueOnce({
      source_content_digest: HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest,
      source_row_count: 1,
      inserted_count: 1,
      inserted_with_warning_count: 0,
      exact_replay_count: 0,
      review_required_count: 0,
      failed_count: 0,
      skipped_existing_count: 0,
      replayed_workbook: true,
      row_outcomes_available: true,
      legacy_summary_only: false,
      row_outcomes: [],
    });
    render(<DataImportPage />);
    fireEvent.change(screen.getByLabelText('選擇 HCM Current Workbook'), { target: { files: [hcmWorkbook('replayed-workbook')] } });
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await waitFor(() => expect(screen.getByText('已處理過，以下為原處理結果')).toBeInTheDocument());
    expect(Array.from(document.querySelectorAll('dd > span')).map(node => node.textContent)).toEqual(['1', '1', '0', '0']);
  });

  it('reuses the workbook digest idempotency key while refreshing correlation identity', async () => {
    vi.spyOn(globalThis.crypto, 'randomUUID')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000001')
      .mockReturnValueOnce('00000000-0000-4000-8000-000000000002');
    render(<DataImportPage />);
    const input = screen.getByLabelText('選擇 HCM Current Workbook');

    for (const callCount of [1, 2]) {
      fireEvent.change(input, { target: { files: [hcmWorkbook('same-workbook')] } });
      fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
      await waitFor(() => expect(hcmWorkbookPreviewClient.apply).toHaveBeenCalledTimes(callCount));
      await waitFor(() => expect(screen.getByText('匯入結果')).toBeInTheDocument());
    }

    const calls = vi.mocked(hcmWorkbookPreviewClient.apply).mock.calls;
    const firstSnapshot = calls[0]?.[0];
    const secondSnapshot = calls[1]?.[0];
    const firstOptions = calls[0]?.[2];
    const secondOptions = calls[1]?.[2];
    const expectedKey = `ui-import-hcm-current-${HCM_WORKBOOK_PREVIEW_FIXTURE.source_content_digest}`;
    expect(firstSnapshot?.sha256).toBe(secondSnapshot?.sha256);
    expect(firstOptions?.idempotencyKey).toBe(expectedKey);
    expect(secondOptions?.idempotencyKey).toBe(expectedKey);
    expect(firstOptions?.correlationId).toBe('ui-import-hcm-current-00000000-0000-4000-8000-000000000001');
    expect(secondOptions?.correlationId).toBe('ui-import-hcm-current-00000000-0000-4000-8000-000000000002');
  });

  it('same-name different bytes clears prior Preview and produces distinct snapshot digests', async () => {
    render(<DataImportPage />);
    const input = screen.getByLabelText('選擇 HCM Current Workbook');

    fireEvent.change(input, { target: { files: [hcmWorkbook('workbook-a')] } });
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await waitFor(() => expect(hcmWorkbookPreviewClient.apply).toHaveBeenCalledTimes(1));

    fireEvent.change(input, { target: { files: [hcmWorkbook('workbook-b')] } });
    expect(screen.queryByText('預覽結果')).not.toBeInTheDocument();
    fireEvent.click(document.querySelector('[data-control-id="imports.hcm-current.preview"]') as HTMLButtonElement);
    await waitFor(() => expect(hcmWorkbookPreviewClient.preview).toHaveBeenCalledTimes(2));

    const firstSnapshot = vi.mocked(hcmWorkbookPreviewClient.preview).mock.calls[0]?.[0];
    const secondSnapshot = vi.mocked(hcmWorkbookPreviewClient.preview).mock.calls[1]?.[0];
    expect(firstSnapshot?.sha256).not.toBe(secondSnapshot?.sha256);
  });
});
