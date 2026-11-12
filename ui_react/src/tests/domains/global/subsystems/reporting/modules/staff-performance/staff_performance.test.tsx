import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffPerformancePanel } from '../../../../../../../components/reports/StaffPerformancePanel';
import { staffPerformanceClient, type StaffPerformanceReport } from '../../../../../../../api/reports/staff_performance_client';
import { performanceFixture } from './staff_performance_fixture';

beforeEach(() => {
  vi.restoreAllMocks();
  vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-11-04T02:00:00Z'));
  vi.spyOn(staffPerformanceClient, 'query').mockImplementation(async filters => performanceFixture(filters));
  vi.spyOn(staffPerformanceClient, 'download').mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'performance.xlsx' });
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:performance');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement) { this.open = true; });
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (this: HTMLDialogElement) { this.open = false; });
});
afterEach(() => vi.useRealTimers());

describe('staff performance accepted UI', () => {
  it('uses a naturally sorted numbered dropdown and removes explanatory notices', async () => {
    render(<StaffPerformancePanel />);
    await screen.findByRole('table', { name: '月嫂表現比較' });
    const selector = screen.getByRole('combobox', { name: '月嫂' });
    expect(within(selector).getAllByRole('option').map(option => option.textContent)).toEqual(['全部月嫂', 'U2 甲月嫂', 'U10 乙月嫂']);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText(/統計口徑|示意資料|不代表實際/)).not.toBeInTheDocument();
    fireEvent.change(selector, { target: { value: '2' } });
    await waitFor(() => expect(staffPerformanceClient.query).toHaveBeenLastCalledWith(expect.objectContaining({ staff_id: 2 }), expect.any(AbortSignal)));
    const table = await screen.findByRole('table', { name: '月嫂表現比較' });
    expect(within(table).getByRole('button', { name: '乙月嫂' })).toBeInTheDocument();
  });

  it('switches periods, opens case details and exports the selected metric', async () => {
    render(<StaffPerformancePanel />);
    await screen.findByRole('table', { name: '月嫂表現比較' });
    fireEvent.click(screen.getByRole('button', { name: '季' }));
    await waitFor(() => expect(staffPerformanceClient.query).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'quarter' }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole('button', { name: '年' }));
    await waitFor(() => expect(staffPerformanceClient.query).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'year' }), expect.any(AbortSignal)));
    await screen.findByRole('table', { name: '月嫂表現比較' });
    fireEvent.click(within(screen.getByRole('table', { name: '月嫂表現比較' })).getByRole('button', { name: '甲月嫂' }));
    const dialog = screen.getByRole('dialog', { name: 'U2 甲月嫂' });
    expect(within(dialog).getByText('PERF-001')).toHaveAttribute('href', '#order-workbench-v2?case=PERF-001');
    expect(within(dialog).getByRole('columnheader', { name: '服務工時（含歷史估算）' })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '關閉個人分析' }));
    fireEvent.click(screen.getByRole('columnheader', { name: '本期認列金額' }).querySelector('button')!);
    fireEvent.click(screen.getByRole('button', { name: '匯出 XLSX' }));
    await waitFor(() => expect(staffPerformanceClient.download).toHaveBeenCalledWith(expect.objectContaining({ period: 'year' }), 'total_amount_ntd', expect.any(AbortSignal)));
    expect(await screen.findByText('XLSX 已開始下載。')).toBeInTheDocument();
  });

  it('clears prior values and ignores late results after a period switch', async () => {
    let resolveFirst!: (value: StaffPerformanceReport) => void;
    vi.mocked(staffPerformanceClient.query).mockImplementationOnce(() => new Promise(resolve => { resolveFirst = resolve; }));
    render(<StaffPerformancePanel />);
    fireEvent.click(screen.getByRole('button', { name: '年' }));
    await screen.findByRole('table', { name: '月嫂表現比較' });
    await act(async () => { resolveFirst({ ...performanceFixture(), rows: [], service_staff_count: 99 }); });
    expect(screen.getByText(/統計期間\s+2026年全年/)).toBeInTheDocument();
    expect(screen.queryByText('99')).not.toBeInTheDocument();
    expect(screen.getByRole('table', { name: '月嫂表現比較' })).toBeInTheDocument();
  });

  it('shows a query error and retries without showing old results', async () => {
    vi.mocked(staffPerformanceClient.query).mockRejectedValueOnce(new Error('分析暫時無法載入'));
    render(<StaffPerformancePanel />);
    expect(await screen.findByRole('alert')).toHaveTextContent('分析暫時無法載入');
    expect(screen.getByRole('button', { name: '匯出 XLSX' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    expect(await screen.findByRole('table', { name: '月嫂表現比較' })).toBeInTheDocument();
  });

  it('keeps a continuing worker in the hours ranking and shows original versus recognized amounts', async () => {
    render(<StaffPerformancePanel />);
    const table = await screen.findByRole('table', { name: '月嫂表現比較' });
    const secondary = within(table).getByRole('button', { name: '乙月嫂' }).closest('tr')!;
    expect(within(secondary).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['2', '乙月嫂U10', '0', '8', 'NT$ 0', '+100.0%', '查看明細 →']);
    expect(screen.getAllByRole('button', { name: /乙月嫂/ })).toHaveLength(2);
    fireEvent.click(within(secondary).getByRole('button', { name: '乙月嫂' }));
    const dialog = screen.getByRole('dialog', { name: 'U10 乙月嫂' });
    expect(within(dialog).getByRole('columnheader', { name: '整案總額' })).toBeInTheDocument();
    expect(within(dialog).getByRole('columnheader', { name: '本期認列金額' })).toBeInTheDocument();
    expect(within(dialog).getByText('NT$ 99,000')).toBeInTheDocument();
    expect(within(dialog).getByText('U2 甲月嫂')).toBeInTheDocument();
    expect(screen.queryByText(/每日/)).not.toBeInTheDocument();
  });

  it('shows an unknown case amount while keeping the service hours visible', async () => {
    const report = performanceFixture();
    const opening = report.rows[0].cases[0];
    opening.total_amount_ntd = null;
    opening.recognized_amount_ntd = null;
    vi.mocked(staffPerformanceClient.query).mockResolvedValueOnce(report);
    render(<StaffPerformancePanel />);
    const table = await screen.findByRole('table', { name: '月嫂表現比較' });
    fireEvent.click(within(table).getByRole('button', { name: '甲月嫂' }));
    const detail = screen.getByRole('link', { name: 'PERF-001' }).closest('tr')!;
    expect(within(detail).getAllByText('待確認')).toHaveLength(2);
    expect(within(detail).getByText('16.5')).toBeInTheDocument();
  });

  it('does not label continuing service as no service when new-case recognition is zero', async () => {
    render(<StaffPerformancePanel initialStaffId={2} />);
    await screen.findByRole('table', { name: '月嫂表現比較' });
    fireEvent.click(screen.getByRole('button', { name: '本期認列金額', pressed: false }));
    expect(screen.getByText('本期沒有可排名的資料。')).toBeInTheDocument();
    expect(screen.queryByText('本期沒有服務資料。')).not.toBeInTheDocument();
  });
});
