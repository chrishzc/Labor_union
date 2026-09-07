import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCandidateContactStatusPanel } from '../components/OrderCandidateContactStatusPanel';

const mocks = vi.hoisted(() => ({
  query: vi.fn(),
  sendInformation: vi.fn(),
  recordWillingness: vi.fn(),
  addCandidates: vi.fn(),
}));

vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: {
    query: mocks.query,
    sendInformation: mocks.sendInformation,
    recordWillingness: mocks.recordWillingness,
    addCandidates: mocks.addCandidates,
  },
}));

function pool(firstWillingness = 'willing', firstReason: string | null = null) {
  return {
    pool_id: 9,
    case_no: 'CASE-CONTACT',
    candidates: [
      {
        id: 17,
        staff_id: 8892,
        service_start_date: '2026-09-01',
        service_end_date: '2026-09-05',
        status: 'active',
        created_at: '2026-09-03T00:00:00Z',
        staff_name: '月嫂甲',
        willingness: firstWillingness,
        reason: firstReason,
        information: {
          '1': { status: 'sent', sent_at: '2026-09-03T00:05:00Z' },
          '2': { status: 'retryable_failed', sent_at: '2026-09-03T00:06:00Z' },
        },
      },
      {
        id: 18,
        staff_id: 8893,
        service_start_date: '2026-09-01',
        service_end_date: '2026-09-05',
        status: 'selected',
        created_at: '2026-09-03T00:01:00Z',
        staff_name: '月嫂乙',
        willingness: 'unwilling',
        reason: '日期不合',
        information: { '1': null, '2': null },
      },
    ],
  };
}

describe('待辦看板 Beta 第 3～4 階候選聯絡狀態', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('只讀既有候選池 owner facts，原樣顯示聯絡、回覆與意願狀態，不觸發 mutation', async () => {
    mocks.query.mockResolvedValue(pool());
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    fireEvent.click(screen.getByRole('button', { name: '讀取候選聯絡狀態' }));

    await waitFor(() => expect(mocks.query).toHaveBeenCalledWith('CASE-CONTACT'));
    expect(await screen.findByText('月嫂甲 · 月嫂 #8892')).toBeInTheDocument();
    expect(screen.getByText('候選狀態：active')).toBeInTheDocument();
    expect(screen.getByText('回覆／意願：willing')).toBeInTheDocument();
    expect(screen.getByText('聯絡資訊 1：sent · 2026-09-03T00:05:00Z')).toBeInTheDocument();
    expect(screen.getByText('聯絡資訊 2：retryable_failed · 2026-09-03T00:06:00Z')).toBeInTheDocument();
    expect(screen.getByText('月嫂乙 · 月嫂 #8893')).toBeInTheDocument();
    expect(screen.getByText('回覆／意願：unwilling')).toBeInTheDocument();
    expect(screen.getByText('回覆原因：日期不合')).toBeInTheDocument();
    expect(screen.getAllByText(/聯絡資訊 [12]：尚無紀錄/)).toHaveLength(2);
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(mocks.recordWillingness).not.toHaveBeenCalled();
    expect(mocks.addCandidates).not.toHaveBeenCalled();
  });

  it('人工意願寫入後回讀 owner facts，更新畫面並阻止再次記錄相同意願', async () => {
    const readback = pool('unwilling', '已電話確認但日期不合');
    mocks.query.mockResolvedValueOnce(pool()).mockResolvedValueOnce(readback);
    mocks.recordWillingness.mockResolvedValue({ status: 'recorded', event_id: 45 });
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    fireEvent.click(screen.getByRole('button', { name: '讀取候選聯絡狀態' }));
    expect(await screen.findByText('月嫂甲 · 月嫂 #8892')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('人工意願原因（月嫂甲）'), {
      target: { value: '已電話確認但日期不合' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄 月嫂甲 無意願' }));

    await waitFor(() => expect(mocks.recordWillingness).toHaveBeenCalledWith(
      'CASE-CONTACT',
      17,
      'unwilling',
      '已電話確認但日期不合',
    ));
    await waitFor(() => expect(mocks.query).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('意願已記錄並回讀：recorded · event #45')).toBeInTheDocument();
    expect(screen.getByText('回覆原因：已電話確認但日期不合')).toBeInTheDocument();

    const sameWillingnessButton = screen.getByRole('button', { name: '記錄 月嫂甲 無意願' });
    expect(sameWillingnessButton).toBeDisabled();
    fireEvent.click(sameWillingnessButton);
    expect(mocks.recordWillingness).toHaveBeenCalledTimes(1);
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(mocks.addCandidates).not.toHaveBeenCalled();
  });

  it('寫入後回讀的意願不一致時 fail closed，不宣告成功', async () => {
    mocks.query.mockResolvedValueOnce(pool()).mockResolvedValueOnce(pool());
    mocks.recordWillingness.mockResolvedValue({ status: 'recorded', event_id: 46 });
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    fireEvent.click(screen.getByRole('button', { name: '讀取候選聯絡狀態' }));
    expect(await screen.findByText('月嫂甲 · 月嫂 #8892')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('人工意願原因（月嫂甲）'), {
      target: { value: '日期不合' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄 月嫂甲 無意願' }));

    expect(await screen.findByText('人工意願回讀與本次寫入不一致。')).toBeInTheDocument();
    expect(screen.queryByText(/意願已記錄並回讀/)).not.toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledTimes(2);
    expect(mocks.recordWillingness).toHaveBeenCalledTimes(1);
    expect(mocks.sendInformation).not.toHaveBeenCalled();
  });

  it('owner query 不可用時顯示阻塞，不用其他來源猜測狀態', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    fireEvent.click(screen.getByRole('button', { name: '讀取候選聯絡狀態' }));

    expect(await screen.findByText('candidate pool unavailable')).toBeInTheDocument();
    expect(screen.getByText('候選聯絡狀態不可用')).toBeInTheDocument();
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(mocks.recordWillingness).not.toHaveBeenCalled();
  });
});
