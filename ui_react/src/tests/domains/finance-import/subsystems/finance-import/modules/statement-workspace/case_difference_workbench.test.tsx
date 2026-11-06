import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CaseDifferenceResolutionWorkbench } from '../../../../../../../components/CaseDifferenceResolutionWorkbench';
import { differenceResolutionClient, type ClientDifferenceView } from '../../../../../../../api/client_finance/difference_resolution_client';

vi.mock('../../../../../../../api/client_finance/difference_resolution_client', () => ({
  differenceResolutionClient: {
    client: vi.fn(),
    apply: vi.fn(),
  },
}));

const mockView: ClientDifferenceView = {
  case_no: '115003',
  version: 2,
  items: [
    {
      identity: 'first',
      label: '第一期',
      kind: 'first',
      direction: 'receivable_from_client',
      expected_ntd: 36000,
      actual_ntd: 25900,
      remaining_ntd: 10100,
      noncash_ntd: 0,
      mode: 'manual',
      computed_ntd: 36000,
      effective_ntd: 36000,
      status: '待處理',
      options: ['loss', 'reduce_service_fee'],
    },
  ],
  events: [],
};

describe('CaseDifferenceResolutionWorkbench', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(differenceResolutionClient.client).mockResolvedValue(mockView);
    vi.mocked(differenceResolutionClient.apply).mockResolvedValue(mockView);
  });

  it('renders difference facts and dual-track options', () => {
    render(
      <CaseDifferenceResolutionWorkbench
        caseNo="115003"
        stageName="第一期"
        stageKey="first"
        expectedNtd={36000}
        actualNtd={25900}
        remainingNtd={10100}
        diffNtd={-10100}
        diffClient={mockView}
        recipientLabel="測試客戶（陳小姐）"
        onOpenNotice={vi.fn()}
        onChanged={vi.fn()}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('第一期 · 差額處置與帳務核對')).toBeInTheDocument();
    expect(screen.getByText('少收 NT$ 10,100')).toBeInTheDocument();
    expect(screen.getByText('NT$ 36,000')).toBeInTheDocument();
    expect(screen.getByText('NT$ 25,900')).toBeInTheDocument();
    expect(screen.getByText('- NT$ 10,100')).toBeInTheDocument();
    expect(screen.getByLabelText(/直接銷帳/)).toBeChecked();
    expect(screen.getByText(/開啟 LINE 補繳通知草稿/)).toBeInTheDocument();
  });

  it('submits settle_direct resolution with optional reason and triggers onChanged', async () => {
    const onChanged = vi.fn();
    render(
      <CaseDifferenceResolutionWorkbench
        caseNo="115003"
        stageName="第一期"
        stageKey="first"
        expectedNtd={36000}
        actualNtd={25900}
        remainingNtd={10100}
        diffNtd={-10100}
        diffClient={mockView}
        onOpenNotice={vi.fn()}
        onChanged={onChanged}
        onClose={vi.fn()}
      />
    );

    fireEvent.change(screen.getByPlaceholderText(/例：雙方協議折讓/), {
      target: { value: '協議折讓 10100' },
    });

    fireEvent.click(screen.getByRole('button', { name: '確認處置並結清本期' }));

    await waitFor(() => expect(differenceResolutionClient.apply).toHaveBeenCalledTimes(1));
    expect(differenceResolutionClient.apply).toHaveBeenCalledWith('115003', 'client', {
      identity: 'first',
      action: 'settle_direct',
      amount_ntd: 10100,
      reason: '協議折讓 10100',
      expected_version: 2,
      key: expect.any(String),
    });
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/已成功依「直接銷帳」處置 第一期 差額/)).toBeInTheDocument();
  });

  it('submits recognize_diff resolution when selected', async () => {
    const onChanged = vi.fn();
    render(
      <CaseDifferenceResolutionWorkbench
        caseNo="115003"
        stageName="第一期"
        stageKey="first"
        expectedNtd={36000}
        actualNtd={25900}
        remainingNtd={10100}
        diffNtd={-10100}
        diffClient={mockView}
        onOpenNotice={vi.fn()}
        onChanged={onChanged}
        onClose={vi.fn()}
      />
    );

    fireEvent.click(screen.getByLabelText(/認列差額/));
    fireEvent.click(screen.getByRole('button', { name: '確認處置並結清本期' }));

    await waitFor(() => expect(differenceResolutionClient.apply).toHaveBeenCalledTimes(1));
    expect(differenceResolutionClient.apply).toHaveBeenCalledWith('115003', 'client', {
      identity: 'first',
      action: 'recognize_diff',
      amount_ntd: 10100,
      reason: '',
      expected_version: 2,
      key: expect.any(String),
    });
  });

  it('triggers onOpenNotice when clicking notice draft button', () => {
    const onOpenNotice = vi.fn();
    render(
      <CaseDifferenceResolutionWorkbench
        caseNo="115003"
        stageName="第一期"
        stageKey="first"
        expectedNtd={36000}
        actualNtd={25900}
        remainingNtd={10100}
        diffNtd={-10100}
        diffClient={mockView}
        onOpenNotice={onOpenNotice}
        onChanged={vi.fn()}
        onClose={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText(/開啟 LINE 補繳通知草稿/));
    expect(onOpenNotice).toHaveBeenCalledTimes(1);
  });
});
