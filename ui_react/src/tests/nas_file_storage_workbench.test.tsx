/**
 * File: nas_file_storage_workbench.test.tsx
 * Description: 驗證 Data Center 保留既有版面並改由 controlled-file API 驅動清單、下載與上傳。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DataImportPage from '../pages/DataImportPage';

const storage = vi.hoisted(() => ({
  list: vi.fn(),
  download: vi.fn(),
  stage: vi.fn(),
  preview: vi.fn(),
  apply: vi.fn(),
}));

vi.mock('../api/storage/controlled_file_client', () => ({
  listControlledFiles: storage.list,
  downloadControlledFile: storage.download,
  stageControlledFile: storage.stage,
  previewControlledFile: storage.preview,
  applyControlledFile: storage.apply,
}));

vi.mock('../api/case_import/hcm_import_result_client', () => ({
  hcmImportResultClient: { query: vi.fn(() => new Promise(() => {})) },
}));
vi.mock('../api/data_browser/data_browser_query_client', () => ({
  dataBrowserQueryClient: { querySource: vi.fn(() => new Promise(() => {})) },
}));

const FILE = {
  file_id: 'cf_0123456789abcdef0123456789abcdef',
  owner: 'orders',
  purpose: 'order_notice',
  subject_reference: 'ORD-2026-HC019',
  filename: 'NOTICE_ORD-HC019_SEQ-1.pdf',
  logical_folder: 'orders/ORD-HC019/contracts',
  version: 1,
  mime_type: 'application/pdf',
  size_bytes: 1024,
  status: 'registered',
  applied_at: '2026-08-26T08:00:00Z',
};

describe('NAS controlled-file workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storage.list.mockResolvedValue([FILE]);
    storage.download.mockResolvedValue(undefined);
    storage.stage.mockResolvedValue({
      staging_id: 'cfs_0123456789abcdef0123456789abcdef',
      filename: 'notice.pdf',
      mime_type: 'application/pdf',
      size_bytes: 3,
      sha256_digest: 'a'.repeat(64),
      expires_at: '2026-08-27T08:00:00Z',
    });
    storage.preview.mockResolvedValue({
      candidate: {},
      preview_fingerprint: 'b'.repeat(64),
      expected_staging_version: 1,
      blockers: [],
    });
    storage.apply.mockResolvedValue({});
  });

  it('loads authenticated controlled-file rows without design-data fallback', async () => {
    render(<DataImportPage initialTab="nas-storage" />);
    expect(screen.getByText(/清單來自 authenticated controlled-file API/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(FILE.filename)).toBeInTheDocument());
    expect(storage.list).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/全部 1 檔/)).toBeInTheDocument();
    expect(screen.getByText('📁 ORD-2026-HC019')).toBeInTheDocument();
    expect(screen.queryByText(/林美真|張美敏|陳雅萱/)).not.toBeInTheDocument();
    expect(screen.queryByText(/SHA-256/)).not.toBeInTheDocument();
  });

  it('preserves Data Center tabs and read-only Data Browser navigation', async () => {
    render(<DataImportPage initialTab="nas-storage" />);
    await waitFor(() => expect(screen.getByText(FILE.filename)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /NAS 檔案管理/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /數據瀏覽/i }));
    expect(screen.getByRole('heading', { name: /營運資料查詢/i })).toBeInTheDocument();
  });

  it('downloads only through the authenticated controlled-file client', async () => {
    render(<DataImportPage initialTab="nas-storage" />);
    await waitFor(() => expect(screen.getByText(FILE.filename)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /⬇️ 下載/i }));
    await waitFor(() => expect(storage.download).toHaveBeenCalledWith(FILE));
  });

  it('keeps destructive delete disabled because the Work Package does not authorize it', async () => {
    render(<DataImportPage initialTab="nas-storage" />);
    await waitFor(() => expect(screen.getByText(FILE.filename)).toBeInTheDocument());
    expect(screen.getByTitle(/自 NAS 安全刪除/i)).toBeDisabled();
    expect(screen.getByRole('button', { name: /批次下載/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /批次刪除/i })).toBeDisabled();
  });

  it('runs staging, Preview and Apply before refreshing the list', async () => {
    render(<DataImportPage initialTab="nas-storage" />);
    await waitFor(() => expect(screen.getByText(FILE.filename)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /補充上傳新附件/i }));
    const input = document.querySelector('input[type="file"]');
    expect(input).toBeInstanceOf(HTMLInputElement);
    fireEvent.change(input as HTMLInputElement, {
      target: { files: [new File(['pdf'], 'notice.pdf', { type: 'application/pdf' })] },
    });
    fireEvent.change(screen.getByLabelText(/authenticated owner subject/i), {
      target: { value: FILE.file_id },
    });
    const applyButton = screen.getByRole('button', { name: /Staging → Preview → Apply/i });
    await waitFor(() => expect(applyButton).toBeEnabled());
    fireEvent.submit(applyButton.closest('form') as HTMLFormElement);

    await waitFor(() => expect(storage.apply).toHaveBeenCalledTimes(1));
    expect(storage.stage).toHaveBeenCalledTimes(1);
    expect(storage.preview).toHaveBeenCalledTimes(1);
    expect(storage.list).toHaveBeenCalledTimes(2);
  });

  it('blocks upload when no authenticated owner subject exists', async () => {
    storage.list.mockResolvedValue([]);
    render(<DataImportPage initialTab="nas-storage" />);

    await waitFor(() => expect(storage.list).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: /補充上傳新附件/i })).toBeDisabled();
  });

  it('keeps direct component default on workbook import and explicit deep-link projection on data browser', async () => {
    const direct = render(<DataImportPage />);
    expect(screen.getByRole('heading', { name: /批次資料匯入中心/i })).toBeInTheDocument();
    direct.unmount();

    render(<DataImportPage initialTab="data-browser" />);
    await waitFor(() => expect(screen.getByRole('heading', { name: /營運資料查詢/i })).toBeInTheDocument());
  });
});
