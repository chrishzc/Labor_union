import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderTerminalAggregateLane } from '../components/OrderTerminalAggregateLane';

const mocks = vi.hoisted(() => ({
  getAggregates: vi.fn(),
}));

vi.mock('../api/orders/order_terminal_aggregate_client', () => ({
  orderTerminalAggregateClient: {
    getAggregates: mocks.getAggregates,
  },
}));

describe('待辦看板 Beta 完全結案彙總', () => {
  beforeEach(() => {
    mocks.getAggregates.mockReset();
    mocks.getAggregates.mockResolvedValue({
      items: [
        {
          case_no: 'CASE-OPEN',
          applicable: true,
          fully_closed: false,
          components: [
            {
              code: 'client_settlement',
              owner: 'Client Finance',
              completed: false,
              reason: 'client_balance_open',
            },
            {
              code: 'government_subsidy',
              owner: 'Government Subsidy',
              completed: false,
              reason: 'submitted',
            },
          ],
        },
        {
          case_no: 'CASE-CLOSED',
          applicable: true,
          fully_closed: true,
          components: [
            {
              code: 'client_settlement',
              owner: 'Client Finance',
              completed: true,
              reason: null,
            },
          ],
        },
      ],
      next_cursor: null,
    });
  });

  it('直接顯示 server aggregate，未完成時指出負責 owner 與原因', async () => {
    render(<OrderTerminalAggregateLane />);

    fireEvent.click(screen.getByRole('button', { name: /完全結案彙總/ }));

    await waitFor(() => expect(mocks.getAggregates).toHaveBeenCalledWith(
      {
        page_size: 200,
        case_no_search: undefined,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));

    const openCard = (await screen.findByText('CASE-OPEN')).closest('article');
    if (!(openCard instanceof HTMLElement)) throw new Error('找不到未完全結案案件卡');
    expect(within(openCard).getByText('尚未完全結案')).toBeInTheDocument();
    expect(within(openCard).getByText('Client Finance · client_settlement：client_balance_open')).toBeInTheDocument();
    expect(within(openCard).getByText('Government Subsidy · government_subsidy：submitted')).toBeInTheDocument();

    const closedCard = screen.getByText('CASE-CLOSED').closest('article');
    if (!(closedCard instanceof HTMLElement)) throw new Error('找不到完全結案案件卡');
    expect(within(closedCard).getByText('完全結案')).toBeInTheDocument();
    expect(within(closedCard).getByText('所有必要組件已完成。')).toBeInTheDocument();
  });
});
