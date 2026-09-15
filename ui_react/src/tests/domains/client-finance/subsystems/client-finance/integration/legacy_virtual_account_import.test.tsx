import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LegacyVirtualAccountImport } from '../../../../../../components/LegacyVirtualAccountImport';


const mocks = vi.hoisted(() => ({ fromFile: vi.fn(), preview: vi.fn(), apply: vi.fn() }));

vi.mock('../../../../../../api/client_finance/legacy_virtual_account_import', () => ({
  LegacyVirtualAccountWorkbookSnapshot: { fromFile: mocks.fromFile },
  legacyVirtualAccountImportClient: { preview: mocks.preview, apply: mocks.apply },
}));

describe('LegacyVirtualAccountImport', () => {
  it('keeps skipped rows out of errors and applies only after confirmation', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: '預覽檔案' }));

    expect(await screen.findByText('預覽結果')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('136')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認匯入' })).toBeDisabled();

    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對預覽筆數' }));
    fireEvent.click(screen.getByRole('button', { name: '確認匯入' }));

    await waitFor(() => expect(mocks.apply).toHaveBeenCalledWith(
      snapshot,
      'c'.repeat(64),
      expect.stringMatching(/^legacy-va-/),
    ));
    expect(await screen.findByText('新增 130 筆、已存在 1 筆、略過 136 筆。')).toBeInTheDocument();
  });
});
