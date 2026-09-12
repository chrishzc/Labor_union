import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCandidateContactStatusPanel } from '../components/OrderCandidateContactStatusPanel';
import type { CandidateContactPool } from '../api/scheduling/candidate_contact_pool_client';

const mocks = vi.hoisted(() => ({
  query: vi.fn(),
  sendInformation: vi.fn(),
  recordWillingness: vi.fn(),
  addCandidates: vi.fn(),
  createCandidateWillingnessCommand: vi.fn(),
  createCandidateInformationSendCommand: vi.fn(),
}));

vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: {
    query: mocks.query,
    sendInformation: mocks.sendInformation,
    recordWillingness: mocks.recordWillingness,
    addCandidates: mocks.addCandidates,
  },
  createCandidateInformationSendCommand: mocks.createCandidateInformationSendCommand,
  createCandidateWillingnessCommand: mocks.createCandidateWillingnessCommand,
}));

function pool(
  firstWillingness: CandidateContactPool['candidates'][number]['willingness'] = 'willing',
  firstReason: string | null = null,
  latestWillingnessEventId: number | null = null,
): CandidateContactPool {
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
        latest_willingness_event_id: latestWillingnessEventId,
        information: {
          '1': { status: 'sent', sent_at: '2026-09-03T00:05:00Z', event_id: 41, line_task_id: 51 },
          '2': { status: 'retryable_failed', sent_at: '2026-09-03T00:06:00Z', event_id: null, line_task_id: null },
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
        latest_willingness_event_id: null,
        information: { '1': null, '2': null },
      },
    ],
  };
}

describe('待辦看板 Beta 第 3～4 階候選聯絡狀態', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.createCandidateWillingnessCommand.mockImplementation((caseNo, candidateId, willingness, reason) => ({
      caseNo,
      candidateId,
      willingness,
      reason,
      actor: 'operator-1',
      eventKey: 'candidate-willingness-test-key',
    }));
    mocks.createCandidateInformationSendCommand.mockImplementation((caseNo, candidateId, infoType, previewFingerprint) => ({
      caseNo,
      candidateId,
      infoType,
      previewFingerprint,
      actor: 'operator-1',
      eventKey: 'candidate-information-test-key',
    }));
  });

  it('只讀既有候選池 owner facts，原樣顯示聯絡、回覆與意願狀態，不觸發 mutation', async () => {
    mocks.query.mockResolvedValue(pool());
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    // 候選清單在掛載後自動查詢。

    await waitFor(() => expect(mocks.query).toHaveBeenCalledWith('CASE-CONTACT', { signal: expect.any(AbortSignal) }));
    expect(await screen.findByText('月嫂甲')).toBeInTheDocument();
    expect(screen.getByText('願意承接')).toBeInTheDocument();
    expect(screen.getByText('已發送 · 2026-09-03T00:05:00Z')).toBeInTheDocument();
    expect(screen.getByText('發送未完成 · 2026-09-03T00:06:00Z')).toBeInTheDocument();
    expect(screen.getByText('月嫂乙')).toBeInTheDocument();
    expect(screen.getByText('已選定')).toBeInTheDocument();
    expect(screen.getByText('回覆說明：日期不合')).toBeInTheDocument();
    expect(screen.getAllByText('尚無紀錄')).toHaveLength(2);
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(mocks.recordWillingness).not.toHaveBeenCalled();
    expect(mocks.addCandidates).not.toHaveBeenCalled();
  });

  it('人工意願寫入後回讀 owner facts，更新畫面並阻止再次記錄相同意願', async () => {
    const readback = pool('unwilling', '已電話確認但日期不合', 45);
    mocks.query.mockResolvedValueOnce(pool()).mockResolvedValueOnce(readback);
    mocks.recordWillingness.mockResolvedValue({ status: 'recorded', event_id: 45 });
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    // 候選清單在掛載後自動查詢。
    expect(await screen.findByText('月嫂甲')).toBeInTheDocument();
    fireEvent.click(screen.getAllByText('記錄電話或現場詢問結果')[0]!);

    fireEvent.change(screen.getByLabelText('詢問結果備註（月嫂甲）'), {
      target: { value: '已電話確認但日期不合' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄 月嫂甲 無意願' }));

    await waitFor(() => expect(mocks.recordWillingness).toHaveBeenCalledWith({
      caseNo: 'CASE-CONTACT',
      candidateId: 17,
      willingness: 'unwilling',
      reason: '已電話確認但日期不合',
      actor: 'operator-1',
      eventKey: 'candidate-willingness-test-key',
    }));
    await waitFor(() => expect(mocks.query).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('回覆已儲存。')).toBeInTheDocument();
    expect(screen.getByText('回覆說明：已電話確認但日期不合')).toBeInTheDocument();

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

    // 候選清單在掛載後自動查詢。
    expect(await screen.findByText('月嫂甲')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('詢問結果備註（月嫂甲）'), {
      target: { value: '日期不合' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄 月嫂甲 無意願' }));

    expect(await screen.findByText('目前無法確認回覆是否已儲存，請重新讀取最新結果。')).toBeInTheDocument();
    expect(screen.queryByText('回覆已儲存。')).not.toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledTimes(2);
    expect(mocks.recordWillingness).toHaveBeenCalledTimes(1);
    expect(mocks.sendInformation).not.toHaveBeenCalled();
  });

  it('owner query 不可用時顯示阻塞，不用其他來源猜測狀態', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    render(<OrderCandidateContactStatusPanel caseNo="CASE-CONTACT" />);

    // 候選清單在掛載後自動查詢。

    expect(await screen.findByText('candidate pool unavailable')).toBeInTheDocument();
    expect(screen.getByText('候選聯絡狀態不可用')).toBeInTheDocument();
    expect(mocks.sendInformation).not.toHaveBeenCalled();
    expect(mocks.recordWillingness).not.toHaveBeenCalled();
  });
});
