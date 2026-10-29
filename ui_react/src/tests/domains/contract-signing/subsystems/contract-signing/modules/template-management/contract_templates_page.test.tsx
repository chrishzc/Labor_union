import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ContractTemplatesPage } from '../../../../../../../pages/ContractTemplatesPage';
import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { contractTemplatesClient as client, type TemplateCatalog, type TemplatePreview } from '../../../../../../../api/contract_templates/contract_templates_client';
import { ApiHttpError, ApiNetworkError } from '../../../../../../../api/shared/typed_errors';

vi.mock('../../../../../../../api/contract_templates/contract_templates_client', () => ({ contractTemplatesClient: { query: vi.fn(), read: vi.fn(), inspect: vi.fn(), save: vi.fn(), activate: vi.fn(), receipt: vi.fn(), download: vi.fn() } }));
const key = 'contract_client_copy';
const metadata = { version_id: 'builtin', template_key: key, number: 0, filename: '原始契約.xlsx', worksheet_name: '契約', template_sha256: 'a'.repeat(64), mapping_sha256: 'b'.repeat(64), created_by: 'system', created_at: null };
const catalog: TemplateCatalog = { template_key: key, catalog_version: 0, active_version_id: 'builtin', versions: [metadata], fields: [
  { key: 'client_name', label: '客戶姓名', requiredness: 'required', applicability: null, example: '範例客戶' },
  { key: 'contract_signed_date', label: '簽約日期', requiredness: 'required', applicability: null, example: '2026/11/01' },
] };
const style = { font: '新細明體', size: 12, bold: false, italic: false, color: '#222222', fill: '', align: 'left', vertical: 'center', wrap: false, borders: {} };
const original: TemplatePreview = { filename: metadata.filename, worksheet_name: '契約', worksheet_names: ['契約'], missing_fields: [], assignments: { B1: 'client_name', B2: 'contract_signed_date' }, sample_values: {}, sheet: {
  name: '契約', rows: 2, columns: 4, column_widths: { '1': 20, '2': 20, '3': 10, '4': 10 }, row_heights: { '1': 24, '2': 20 }, formula_cells: [], images: [], merges: [{ start_row: 1, end_row: 1, start_col: 2, end_col: 4 }],
  cells: [1, 2].flatMap(row => [1, 2, 3, 4].map(col => ({ ref: String.fromCharCode(64 + col) + row, row, col, value: col === 1 ? row === 1 ? '原有客戶姓名條文' : '簽約日期說明' : '', style }))),
} };
const nextVersion = { ...metadata, version_id: 'v_' + '1'.repeat(32), number: 1, filename: '新契約.xlsx', created_by: 'admin', created_at: '2026-10-29T00:00:00Z' };
const savedCatalog = { ...catalog, catalog_version: 1, versions: [metadata, nextVersion] };

function page() { return render(<UnsavedChangesProvider><ContractTemplatesPage /></UnsavedChangesProvider>); }
async function ready() { await screen.findByText('原始契約.xlsx', { selector: '.ctm-file strong' }); await waitFor(() => expect(screen.getByRole('button', { name: '上傳新模板' })).not.toBeDisabled()); }
async function uploadAndMap() {
  fireEvent.click(screen.getByRole('checkbox', { name: '沿用目前版本映射' }));
  const uploaded = { ...original, filename: '新契約.xlsx', assignments: {}, missing_fields: ['客戶姓名', '簽約日期'] };
  vi.mocked(client.inspect).mockImplementation(async (_key, source, sample): Promise<TemplatePreview> => ({ ...uploaded, assignments: source.assignments, sample_values: sample ? { B1: '範例客戶', B2: '2026/11/01' } : {} }));
  fireEvent.change(screen.getByLabelText('上傳 Excel 模板'), { target: { files: [new File(['xlsx-bytes'], '新契約.xlsx')] } });
  await waitFor(() => expect(screen.getByText('新契約.xlsx')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: '保存版本' })).toBeDisabled();
  fireEvent.click(screen.getByRole('cell', { name: 'B1 空白' }));
  fireEvent.change(screen.getByLabelText('要帶入什麼資料？'), { target: { value: 'client_name' } });
  fireEvent.click(screen.getByRole('button', { name: '套用映射' }));
  fireEvent.click(screen.getByRole('cell', { name: 'B2 空白' }));
  fireEvent.change(screen.getByLabelText('要帶入什麼資料？'), { target: { value: 'contract_signed_date' } });
  fireEvent.click(screen.getByRole('button', { name: '套用映射' }));
}

describe('ContractTemplatesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks(); sessionStorage.clear();
    vi.mocked(client.query).mockResolvedValue(catalog);
    vi.mocked(client.read).mockResolvedValue(original);
    vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement) { this.setAttribute('open', ''); });
    vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (this: HTMLDialogElement) { this.removeAttribute('open'); });
  });
  it('can opt out of inherited mappings, preview samples, and save before explicit activation', async () => {
    page(); await ready(); await uploadAndMap();
    expect(vi.mocked(client.inspect).mock.calls[0]?.[1].assignments).toEqual({});
    fireEvent.click(screen.getByRole('button', { name: '示範套值' }));
    await waitFor(() => expect(screen.getByRole('cell', { name: 'B1 客戶姓名' })).toHaveTextContent('範例客戶'));
    vi.mocked(client.save).mockResolvedValue({ catalog: savedCatalog, version_id: nextVersion.version_id, replayed: false });
    fireEvent.click(screen.getByRole('button', { name: '保存版本' }));
    await screen.findByText('模板版本已保存，尚未啟用；既有契約不受影響。');
    expect(client.activate).not.toHaveBeenCalled();
    expect(vi.mocked(client.save).mock.calls[0]?.[1]).toMatchObject({ expectedVersion: 0, assignments: { B1: 'client_name', B2: 'contract_signed_date' } });
    vi.mocked(client.activate).mockResolvedValue({ catalog: { ...savedCatalog, catalog_version: 2, active_version_id: nextVersion.version_id }, version_id: nextVersion.version_id, replayed: false });
    fireEvent.click(screen.getByRole('button', { name: '啟用此版本' }));
    const dialog = screen.getByRole('dialog', { name: '啟用此模板版本？' });
    expect(within(dialog).getByText(/已保存的契約、PDF 及簽回文件保留原版本/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '確認啟用' }));
    await screen.findByText('指定模板已啟用，後續產製使用此版本；既有契約保留原版本。');
    expect(client.activate).toHaveBeenCalledWith(key, nextVersion.version_id, 1, expect.any(String));
  });
  it('inherits current mappings by default and saves only the adjusted positions with the uploaded workbook', async () => {
    page(); await ready();
    expect(screen.getByRole('checkbox', { name: '沿用目前版本映射' })).toBeChecked();
    vi.mocked(client.inspect).mockImplementation(async (_key, source, sample) => ({ ...original,
      filename: '文字更新.xlsx', assignments: source.assignments,
      sample_values: sample ? Object.fromEntries(Object.entries(source.assignments).map(([ref, field]) => [ref, field === 'client_name' ? '範例客戶' : '2026/11/01'])) : {},
    }));
    const uploaded = new File(['updated-xlsx'], '文字更新.xlsx');
    fireEvent.change(screen.getByLabelText('上傳 Excel 模板'), { target: { files: [uploaded] } });
    await screen.findByText(/沿用目前 2 個映射位置/);
    expect(screen.getByRole('cell', { name: 'B1 客戶姓名' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'B2 簽約日期' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('cell', { name: 'B1 客戶姓名' }));
    fireEvent.click(screen.getByRole('button', { name: '移除此格映射' }));
    fireEvent.click(screen.getByRole('cell', { name: 'C2 空白' }));
    fireEvent.change(screen.getByLabelText('要帶入什麼資料？'), { target: { value: 'client_name' } });
    fireEvent.click(screen.getByRole('button', { name: '套用映射' }));
    fireEvent.click(screen.getByRole('button', { name: '示範套值' }));
    await waitFor(() => expect(screen.getByRole('cell', { name: 'C2 客戶姓名' })).toHaveTextContent('範例客戶'));
    expect(screen.getByRole('cell', { name: 'B2 簽約日期' })).toHaveTextContent('2026/11/01');
    vi.mocked(client.save).mockResolvedValue({ catalog: savedCatalog, version_id: nextVersion.version_id, replayed: false });
    fireEvent.click(screen.getByRole('button', { name: '保存版本' }));
    await screen.findByText('模板版本已保存，尚未啟用；既有契約不受影響。');
    expect(vi.mocked(client.save).mock.calls[0]![1]).toMatchObject({ file: uploaded, sourceVersionId: null,
      assignments: { B2: 'contract_signed_date', C2: 'client_name' } });
    expect(client.activate).not.toHaveBeenCalled();
  });
  it.each(['merged', 'outside'] as const)('retains %s inherited locations for explicit relocation instead of silently dropping mappings', async kind => {
    page(); await ready();
    const sheet = kind === 'merged' ? { ...original.sheet, merges: [{ start_row: 1, end_row: 1, start_col: 1, end_col: 2 }] }
      : { ...original.sheet, columns: 1, merges: [], cells: original.sheet.cells.filter(cell => cell.col === 1) };
    vi.mocked(client.inspect).mockImplementation(async (_key, source) => ({ ...original, filename: '版型更新.xlsx', sheet, assignments: source.assignments }));
    fireEvent.change(screen.getByLabelText('上傳 Excel 模板'), { target: { files: [new File(['new-layout'], '版型更新.xlsx')] } });
    await screen.findByText(/個原映射位置需要調整/);
    expect(screen.getByRole('alert')).toHaveTextContent(kind === 'merged' ? '已變成合併格內部' : '不在新工作表範圍內');
    expect(screen.getByRole('alert')).toHaveTextContent('B1');
    expect(screen.getByRole('button', { name: '保存版本' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '示範套值' })).toBeDisabled();
    fireEvent.click(screen.getByRole('cell', { name: 'A1 原有客戶姓名條文' }));
    fireEvent.click(screen.getByRole('button', { name: '將 B1 移至 A1' }));
    if (kind === 'outside') {
      fireEvent.click(screen.getByRole('cell', { name: 'A2 簽約日期說明' }));
      fireEvent.click(screen.getByRole('button', { name: '將 B2 移至 A2' }));
    }
    expect(screen.queryByText(/個原映射位置需要調整/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存版本' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '示範套值' }));
    await waitFor(() => expect(vi.mocked(client.inspect).mock.calls.at(-1)?.[1].assignments).toEqual(kind === 'merged'
      ? { A1: 'client_name', B2: 'contract_signed_date' } : { A1: 'client_name', A2: 'contract_signed_date' }));
  });
  it('retains original command identity and recovers a lost save response', async () => {
    page(); await ready(); await uploadAndMap();
    vi.mocked(client.save).mockRejectedValue(new ApiNetworkError());
    fireEvent.click(screen.getByRole('button', { name: '保存版本' }));
    await screen.findByText('網路連線失敗，請檢查網路狀態');
    expect(screen.getByRole('button', { name: '上傳新模板' })).toBeDisabled();
    const commandId = vi.mocked(client.save).mock.calls[0]![1].commandId;
    vi.mocked(client.receipt).mockResolvedValue({ catalog: savedCatalog, version_id: nextVersion.version_id, replayed: true });
    fireEvent.click(screen.getByRole('button', { name: '核對原操作結果' }));
    await screen.findByText('模板版本已保存，尚未啟用；既有契約不受影響。');
    expect(client.receipt).toHaveBeenCalledWith(key, commandId);
    expect(client.save).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem('contract-template-pending-command')).toBeNull();
  });
  it('keeps the loaded template when server rejects a damaged upload', async () => {
    page(); await ready();
    vi.mocked(client.inspect).mockRejectedValue(new ApiHttpError(422, 'contract_template_workbook_invalid', '無法讀取 Excel'));
    fireEvent.change(screen.getByLabelText('上傳 Excel 模板'), { target: { files: [new File(['invalid'], '損壞.xlsx')] } });
    await screen.findByText('無法讀取 Excel');
    expect(screen.getByText('原始契約.xlsx', { selector: '.ctm-file strong' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存版本' })).toBeDisabled();
  });
  it('recovers the same saved command after reload and reads the actual saved template', async () => {
    sessionStorage.setItem('contract-template-pending-command', JSON.stringify({ key, id: 'original-save', action: 'save', expectedVersion: 0,
      requiresFile: true, fileName: '新契約.xlsx', fileDigest: 'a'.repeat(64), save: { file: null, sourceVersionId: null, worksheetName: '契約', assignments: original.assignments, expectedVersion: 0, commandId: 'original-save' } }));
    vi.mocked(client.read).mockResolvedValueOnce(original).mockResolvedValueOnce({ ...original, filename: '新契約.xlsx' });
    vi.mocked(client.receipt).mockResolvedValue({ catalog: savedCatalog, version_id: nextVersion.version_id, replayed: true });
    page(); await screen.findByText('原始契約.xlsx', { selector: '.ctm-file strong' });
    await waitFor(() => expect(screen.getByRole('button', { name: '核對原操作結果' })).not.toBeDisabled());
    expect(screen.getByRole('button', { name: '重新選取原 Excel 以核對' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '核對原操作結果' }));
    await screen.findByText('新契約.xlsx', { selector: '.ctm-file strong' });
    expect(client.receipt).toHaveBeenCalledWith(key, 'original-save');
    expect(client.save).not.toHaveBeenCalled();
    expect(client.read).toHaveBeenLastCalledWith(key, nextVersion.version_id);
  });
});
