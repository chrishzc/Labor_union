import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LegacyVirtualAccountImport } from '../../../../../../components/LegacyVirtualAccountImport';


const mocks = vi.hoisted(() => ({ fromFile: vi.fn(), preview: vi.fn(), apply: vi.fn() }));

vi.mock('../../../../../../api/client_finance/legacy_virtual_account_import', () => ({
  LegacyVirtualAccountWorkbookSnapshot: { fromFile: mocks.fromFile },
  legacyVirtualAccountImportClient: { preview: mocks.preview, apply: mocks.apply },
}));

describe('LegacyVirtualAccountImport', () => {
  it('keeps skipped rows out of errors and applies from one click', async () => {
    const snapshot = { digest: 'a'.repeat(64) };
    mocks.fromFile.mockResolvedValue(snapshot);
    mocks.preview.mockResolvedValue({
      source_content_digest: 'a'.repeat(64), sheet_identity: 'b'.repeat(64),
      source_row_count: 267, candidate_count: 131, import_count: 130,
      existing_count: 1, skipped_count: 136, preview_fingerprint: 'c'.repeat(64),
    });
    mocks.apply.mockResolvedValue({
      source_content_digest: 'a'.repeat(64), source_row_count: 267,
      inserted_count: 130, existing_count: 1, skipped_count: 136,
      replayed_workbook: false,
    });
    render(<LegacyVirtualAccountImport />);

    fireEvent.change(screen.getByLabelText('選擇虛擬帳號對照表'), {
      target: { files: [new File(['xlsx'], '虛擬帳號對照表.xlsx')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '匯入虛擬帳號' }));
    expect(await screen.findByText('處理筆數')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('136')).toBeInTheDocument();

    await waitFor(() => expect(mocks.apply).toHaveBeenCalledWith(
      snapshot,
      'c'.repeat(64),
      expect.stringMatching(/^legacy-va-/),
    ));
    expect(await screen.findByText('新增 130 筆、已存在 1 筆、略過 136 筆。')).toBeInTheDocument();
  });

  it('shows transfers and conflicts in a mixed workbook before confirming eligible rows', async () => {
    mocks.apply.mockClear();
    const snapshot = { digest: 'a'.repeat(64) };
    const rows = [
      { source_row: 2, case_no: 'A115001', status: 'transfer', related_case_nos: ['115000003'] },
      { source_row: 3, case_no: 'A115002', status: 'conflict', related_case_nos: ['115000004'] },
      { source_row: 4, case_no: 'A115003', status: 'replace_required', related_case_nos: [] },
      { source_row: 5, case_no: 'A116001', status: 'ineligible_year', related_case_nos: [] },
    ];
    mocks.fromFile.mockResolvedValue(snapshot);
    mocks.preview.mockResolvedValue({
      source_content_digest: 'a'.repeat(64), sheet_identity: 'b'.repeat(64),
      source_row_count: 5, candidate_count: 2, import_count: 2,
      existing_count: 0, skipped_count: 3, preview_fingerprint: 'c'.repeat(64),
      non_citizen_rows: rows,
    });
    mocks.apply.mockResolvedValue({
      source_content_digest: 'a'.repeat(64), source_row_count: 5,
      inserted_count: 2, existing_count: 0, skipped_count: 3,
      replayed_workbook: false, non_citizen_rows: rows,
    });
    render(<LegacyVirtualAccountImport />);
    fireEvent.change(screen.getByLabelText('選擇虛擬帳號對照表'), {
      target: { files: [new File(['xlsx'], '虛擬帳號對照表.xlsx')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '匯入虛擬帳號' }));

    const confirm = await screen.findByRole('button', { name: '確認套用' });
    expect(mocks.apply).not.toHaveBeenCalled();
    expect(screen.getByRole('row', { name: '2 A115001 從取消案轉入 115000003' })).toBeInTheDocument();
    expect(screen.getByRole('row', { name: '3 A115002 衝突，略過 115000004' })).toBeInTheDocument();
    expect(screen.getByText('已有其他對照，請至客戶名冊單案更正')).toBeInTheDocument();
    expect(screen.getByText('年度不適用')).toBeInTheDocument();
    fireEvent.click(confirm);
    expect(await screen.findByText('新增或轉入 2 筆、已存在 0 筆、略過 3 筆。')).toBeInTheDocument();
    expect(mocks.apply).toHaveBeenCalledExactlyOnceWith(snapshot, 'c'.repeat(64), expect.stringMatching(/^legacy-va-/));
  });

  it('shows a non-citizen owner blocking an ordinary row and imports the other rows in one click', async () => {
    mocks.apply.mockClear();
    const snapshot = { digest: 'a'.repeat(64) };
    const rows = [{ source_row: 2, case_no: '115000001', status: 'conflict', related_case_nos: ['A115001'] }];
    mocks.fromFile.mockResolvedValue(snapshot);
    mocks.preview.mockResolvedValue({
      source_row_count: 2, candidate_count: 1, import_count: 1, existing_count: 0, skipped_count: 1,
      preview_fingerprint: 'c'.repeat(64), non_citizen_rows: rows,
    });
    mocks.apply.mockResolvedValue({
      inserted_count: 1, existing_count: 0, skipped_count: 1, replayed_workbook: false, non_citizen_rows: rows,
    });
    render(<LegacyVirtualAccountImport />);
    fireEvent.change(screen.getByLabelText('選擇虛擬帳號對照表'), {
      target: { files: [new File(['xlsx'], '一般案對照表.xlsx')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '匯入虛擬帳號' }));

    expect(await screen.findByRole('row', { name: '2 115000001 衝突，略過 A115001' })).toBeInTheDocument();
    expect(await screen.findByText('新增 1 筆、已存在 0 筆、略過 1 筆。')).toBeInTheDocument();
    expect(mocks.apply).toHaveBeenCalledExactlyOnceWith(snapshot, 'c'.repeat(64), expect.stringMatching(/^legacy-va-/));
  });
});
