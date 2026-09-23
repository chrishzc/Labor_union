import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderOfficialDateCorrectionPanel } from '../../../../../../../components/OrderOfficialDateCorrectionPanel';

const mocks = vi.hoisted(() => ({ query: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
vi.mock('../../../../../../../api/orders/official_service_date_correction_client', () => ({
  officialServiceDateCorrectionClient: mocks,
}));

const original = {
  case_no: 'ISSUE-346', order_version: 1, scheduling_version: 1, generation_id: 11,
  order_status: '訂單完成', service_data_locked: true, actual_end_date: '2026-09-20',
  monetary_change_blocker: false,
  assignments: [{ assignment_id: 13, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-19', '2026-09-20'] }],
};
const changed = {
  ...original, order_version: 2, scheduling_version: 2, generation_id: 12,
  actual_end_date: '2026-09-21',
  assignments: [{ assignment_id: 14, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-19', '2026-09-21'] }],
};

describe('official date correction panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('crypto', { randomUUID: () => 'issue346-key' });
    mocks.query.mockResolvedValueOnce(original).mockResolvedValueOnce(changed);
    mocks.preview.mockImplementation(async (_caseNo, assignments) => ({
      ...original, proposed_assignments: assignments,
      finance_impact: 'no_op', payroll_impact: 'no_op', preview_fingerprint: 'a'.repeat(64),
    }));
    mocks.apply.mockResolvedValue({
      case_no: 'ISSUE-346', order_version: 2, scheduling_version: 2, generation_id: 12,
      effective_assignments: [{ assignment_id: 14, service_dates: ['2026-09-19', '2026-09-21'] }],
      preview_fingerprint: 'a'.repeat(64),
    });
  });

  it('previews a full corrected allocation and requires effective readback after apply', async () => {
    const onObserved = vi.fn();
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" onObserved={onObserved} />);
    const second = await screen.findByLabelText('王月嫂 第 2 個正式服務日');
    fireEvent.change(second, { target: { value: '2026-09-21' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽更正' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('ISSUE-346', [
      { assignment_id: 13, service_dates: ['2026-09-19', '2026-09-21'] },
    ]));
    fireEvent.change(screen.getByLabelText('更正原因'), { target: { value: '原正式日期登錄錯誤' } });
    fireEvent.click(screen.getByRole('button', { name: '確認更正正式排班' }));
    await waitFor(() => expect(onObserved).toHaveBeenCalledOnce());
    expect(mocks.apply).toHaveBeenCalledWith('ISSUE-346', expect.objectContaining({
      preview_fingerprint: 'a'.repeat(64),
    }), '原正式日期登錄錯誤', 'issue346-key');
    expect(mocks.query).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('status')).toHaveTextContent('正式排班日期已更正');
  });

  it('shows both caregivers and rejects readback that assigns a substitute date to the wrong caregiver', async () => {
    const multiOriginal = {
      ...original,
      assignments: [
        { assignment_id: 13, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-19'] },
        { assignment_id: 15, staff_id: 8, staff_name: '代班李月嫂', service_dates: ['2026-09-20'] },
      ],
    };
    const swappedReadback = {
      ...changed,
      assignments: [
        { assignment_id: 14, staff_id: 7, staff_name: '王月嫂', service_dates: ['2026-09-21'] },
        { assignment_id: 16, staff_id: 8, staff_name: '代班李月嫂', service_dates: ['2026-09-19'] },
      ],
    };
    mocks.query.mockReset().mockResolvedValueOnce(multiOriginal).mockResolvedValueOnce(swappedReadback);
    mocks.apply.mockResolvedValue({
      case_no: 'ISSUE-346', order_version: 2, scheduling_version: 2, generation_id: 12,
      effective_assignments: [
        { assignment_id: 14, service_dates: ['2026-09-19'] },
        { assignment_id: 16, service_dates: ['2026-09-21'] },
      ],
      preview_fingerprint: 'a'.repeat(64),
    });
    const onObserved = vi.fn();
    render(<OrderOfficialDateCorrectionPanel caseNo="ISSUE-346" onObserved={onObserved} />);
    const substituteDay = await screen.findByLabelText('代班李月嫂 第 1 個正式服務日');
    expect(screen.getByLabelText('王月嫂 第 1 個正式服務日')).toHaveValue('2026-09-19');
    fireEvent.change(substituteDay, { target: { value: '2026-09-21' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽更正' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('ISSUE-346', [
      { assignment_id: 13, service_dates: ['2026-09-19'] },
      { assignment_id: 15, service_dates: ['2026-09-21'] },
    ]));
    fireEvent.change(screen.getByLabelText('更正原因'), { target: { value: '代班日期登錄錯誤' } });
    fireEvent.click(screen.getByRole('button', { name: '確認更正正式排班' }));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('提交後正式排班回讀不一致'));
    expect(onObserved).not.toHaveBeenCalled();
  });
});
