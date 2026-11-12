import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import type { HistoricalPayableAuditItem } from '../../../../../../../api/accounts_payable/accounts_payable_query_schemas';
import { HistoricalPayableEditor, HistoricalPayableLookup } from '../../../../../../../components/HistoricalPayableReview';

const pending: HistoricalPayableAuditItem = {
  case_no: 'CASE-OLD-1', staff_id: 42, recipient_name: '合成月嫂甲',
  obligation_identity: null, current_event_id: null, amount_due_ntd: null, balance_ntd: null,
  order_due_date: null, effective_due_date: null, source: 'order_facts',
  disposition: 'date_not_formed', reason: '尚未建立月嫂應付帳務及付款日。',
};

afterEach(() => vi.restoreAllMocks());

it('帶入同案及月嫂，同步後重新查核清冊', async () => {
  const lookup = vi.spyOn(accountsPayableQueryClient, 'lookupHistorical')
    .mockResolvedValueOnce([pending])
    .mockResolvedValueOnce([{
      ...pending, obligation_identity: 'original-42', current_event_id: 1,
      amount_due_ntd: 12000, balance_ntd: 12000, effective_due_date: '2026-10-15',
      source: 'formal_obligation', disposition: 'selected_month', reason: '列入所選付款月份。',
    }]);
  const sync = vi.spyOn(accountsPayableQueryClient, 'synchronizeHistorical').mockResolvedValue('created');

  function Workspace() {
    const [selected, setSelected] = useState<HistoricalPayableAuditItem>();
    const [revision, setRevision] = useState(0);
    return <>
      <HistoricalPayableLookup month="2026-10" revision={revision} onCase={setSelected} />
      {selected && <HistoricalPayableEditor item={selected} onSaved={() => setRevision(value => value + 1)} />}
    </>;
  }

  render(<Workspace />);
  fireEvent.click(screen.getByText('查未列入原因'));
  fireEvent.change(screen.getByLabelText('案號、月嫂完整姓名或公會編號'), { target: { value: '合成月嫂甲' } });
  fireEvent.click(screen.getByRole('button', { name: '查核歷史月嫂款' }));
  fireEvent.click(await screen.findByRole('button', { name: '查看本案帳務' }));
  expect(screen.getByRole('heading', { name: '合成月嫂甲 · 應付清冊查核' })).toBeInTheDocument();
  expect(screen.queryByLabelText('原付款日')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '同步月嫂應付' }));
  await waitFor(() => expect(sync).toHaveBeenCalledWith('CASE-OLD-1'));
  expect(await screen.findByText(/列入所選付款月份/)).toBeInTheDocument();
  expect(lookup).toHaveBeenCalledTimes(2);
});

it('已結清款項只顯示查核原因', () => {
  render(<HistoricalPayableEditor item={{
    ...pending, disposition: 'paid_or_settled', obligation_identity: 'original-42',
    current_event_id: 1, amount_due_ntd: 12000, balance_ntd: 0, reason: '已有結清證據。',
  }} onSaved={vi.fn()} />);
  expect(screen.getByText('已有結清證據。')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '更正應付' })).not.toBeInTheDocument();
});
