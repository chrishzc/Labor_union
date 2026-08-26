/**
 * File: nas_file_storage_workbench.test.tsx
 * Description: 驗證資料中心三分頁、NAS 本機預覽、資料夾導覽及既有匯入／數據瀏覽相容性。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DataImportPage from '../pages/DataImportPage';

// Mock API clients for workbook import cards to isolate rendering
vi.mock('../api/case_import/hcm_import_result_client', () => ({
  hcmImportResultClient: {
    query: vi.fn(() => new Promise(() => {})),
  },
}));

vi.mock('../api/data_browser/data_browser_query_client', () => ({
  dataBrowserQueryClient: {
    querySource: vi.fn(() => new Promise(() => {})),
  },
}));

vi.mock('../api/case_import/hcm_workbook_client', () => ({
  hcmWorkbookPreviewClient: {
    preview: vi.fn(),
    apply: vi.fn(),
  },
  HcmWorkbookSnapshot: { fromFile: vi.fn() },
}));

vi.mock('../api/case_import/client_beclass_workbook/client', () => ({
  clientBeClassWorkbookPreviewClient: {
    preview: vi.fn(),
    apply: vi.fn(),
  },
  ClientBeClassWorkbookSnapshot: { fromFile: vi.fn() },
}));

vi.mock('../api/case_import/staff_historical_workbook/client', () => ({
  staffHistoricalWorkbookPreviewClient: {
    preview: vi.fn(),
    apply: vi.fn(),
  },
  StaffHistoricalWorkbookSnapshot: { fromFile: vi.fn() },
}));

vi.mock('../api/orders/historical_order_workbook/client', () => ({
  historicalOrderWorkbookPreviewClient: {
    preview: vi.fn(),
    apply: vi.fn(),
  },
  HistoricalOrderWorkbookSnapshot: { fromFile: vi.fn() },
}));

describe('NAS File Storage Workbench & Data Center Tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders NAS storage tab by default with quota banner and folder tree', () => {
    render(<DataImportPage />);

    // Top Tabs
    expect(screen.getByRole('button', { name: /NAS 檔案管理/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /工作簿資料匯入/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /數據瀏覽/i })).toBeInTheDocument();
    expect(screen.getByText(/NAS 前端操作預覽/)).toBeInTheDocument();

    // Quota Banner
    expect(screen.getByText(/Synology NAS 儲存容量監控/i)).toBeInTheDocument();
    expect(screen.getByText(/已使用/i)).toBeInTheDocument();
    expect(screen.getByText(/38.5 GB/i)).toBeInTheDocument();

    // Folder Tree
    expect(screen.getByText(/檔案目錄導覽/i)).toBeInTheDocument();
    expect(screen.getByText(/訂單專區檔案庫/i)).toBeInTheDocument();
    expect(screen.getByText(/月嫂專區檔案庫/i)).toBeInTheDocument();

    // Dispute comparison notice
    expect(screen.getByText(/爭議比對提示/i)).toBeInTheDocument();
  });

  it('switches to the existing read-only Data Browser', () => {
    render(<DataImportPage />);
    fireEvent.click(screen.getByRole('button', { name: /數據瀏覽/i }));
    expect(screen.getByRole('heading', { name: /營運資料查詢/i })).toBeInTheDocument();
    expect(screen.getAllByText('唯讀查詢').length).toBeGreaterThan(0);
  });

  it('switches between NAS storage tab and Workbook import tab', () => {
    render(<DataImportPage />);

    // Click on Workbook Import tab
    const workbookTab = screen.getByRole('button', { name: /工作簿資料匯入/i });
    fireEvent.click(workbookTab);

    // Expect 4 workbook cards
    expect(screen.getByText(/1\. HCM 案件匯入/i)).toBeInTheDocument();
    expect(screen.getByText(/2\. 客戶 BeClass 問卷匯入/i)).toBeInTheDocument();
    expect(screen.getByText(/3\. 月嫂歷史資料匯入/i)).toBeInTheDocument();
    expect(screen.getByText(/4\. 歷史訂單認領匯入/i)).toBeInTheDocument();

    // Click back to NAS storage tab
    const nasTab = screen.getByRole('button', { name: /NAS 檔案管理/i });
    fireEvent.click(nasTab);

    expect(screen.getByText(/Synology NAS 儲存容量監控/i)).toBeInTheDocument();
  });

  it('filters files when clicking caregiver folder in left tree', () => {
    render(<DataImportPage />);

    // Click on caregiver folder
    const caregiverFolder = screen.getByText(/STF-012 \(張美敏 月嫂\)/i);
    fireEvent.click(caregiverFolder);

    // File list should show caregiver files
    expect(screen.getByText(/RESUME_STF-012_張美敏_v1\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/CERT_STF-012_張美敏_良民證_20260115\.pdf/i)).toBeInTheDocument();
    expect(screen.queryByText(/CONTRACT_ORD-HC019/i)).not.toBeInTheDocument();
  });

  it('filters files via search input', () => {
    render(<DataImportPage />);

    // Switch to all files
    const allFilesFolder = screen.getByText('📁 全部檔案');
    fireEvent.click(allFilesFolder);

    const searchInput = screen.getByPlaceholderText(/搜尋訂單編號、產婦姓名、檔名或時間/i);
    fireEvent.change(searchInput, { target: { value: 'NOTICE_ORD-HC019' } });

    // Should show notice SEQ-1 and SEQ-2
    expect(screen.getByText(/NOTICE_ORD-HC019_林美真_SEQ-1_20260518-1430\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/NOTICE_ORD-HC019_林美真_SEQ-2_20260520-0915\.pdf/i)).toBeInTheDocument();
    expect(screen.queryByText(/CONTRACT_ORD-HC020/i)).not.toBeInTheDocument();
  });

  it('opens preview modal when clicking preview button', () => {
    render(<DataImportPage />);

    // Find preview buttons
    const previewButtons = screen.getAllByRole('button', { name: /預覽/i });
    fireEvent.click(previewButtons[0]);

    // Expect modal to show
    expect(screen.getByText(/文件電子檔案檢視|照片預覽燈箱/i)).toBeInTheDocument();
    expect(screen.getByText(/SHA-256 完整性雜湊值/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /關閉/i })).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByRole('button', { name: /關閉/i }));
    expect(screen.queryByText(/文件電子檔案檢視/i)).not.toBeInTheDocument();
  });

  it('opens safe deletion modal and warns about ongoing contract', () => {
    render(<DataImportPage />);

    // Find delete buttons
    const deleteButtons = screen.getAllByTitle(/自 NAS 安全刪除/i);
    fireEvent.click(deleteButtons[0]); // Delete CONTRACT_ORD-HC019 (ongoing)

    // Expect safe deletion modal
    expect(screen.getByText(/⚠️ 安全刪除確認/i)).toBeInTheDocument();
    expect(screen.getByText(/進行中合約保護警示/i)).toBeInTheDocument();
    expect(screen.getByText(/容量釋放預覽/i)).toBeInTheDocument();

    // Cancel deletion
    const cancelBtn = screen.getByRole('button', { name: /取消保留/i });
    fireEvent.click(cancelBtn);
    expect(screen.queryByText(/⚠️ 安全刪除確認/i)).not.toBeInTheDocument();
  });

  it('opens upload modal and previews a standardized filename without claiming NAS persistence', () => {
    render(<DataImportPage />);

    const uploadBtn = screen.getByRole('button', { name: /➕ 補充上傳新附件/i });
    fireEvent.click(uploadBtn);

    expect(screen.getByText(/➕ 補充上傳新附件至 NAS 檔案庫/i)).toBeInTheDocument();
    expect(screen.getByText(/自動防呆命名預覽/i)).toBeInTheDocument();

    // Submit upload
    const submitBtn = screen.getByRole('button', { name: /📤 預覽上傳結果/i });
    fireEvent.click(submitBtn);

    // Modal closes and toast shows
    expect(screen.queryByText(/➕ 補充上傳新附件至 NAS 檔案庫/i)).not.toBeInTheDocument();
    expect(screen.getByText(/已加入上傳候選/)).toBeInTheDocument();
    expect(screen.getByText(/NAS 與資料庫均未變更/)).toBeInTheDocument();
  });
});
