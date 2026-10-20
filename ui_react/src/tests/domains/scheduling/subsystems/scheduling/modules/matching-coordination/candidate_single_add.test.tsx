import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderCandidateQueryPanel } from '../../../../../../../components/OrderCandidateQueryPanel';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({ search: vi.fn(), query: vi.fn(), add: vi.fn(), command: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', async importOriginal => {
  const original = await importOriginal<typeof import('../../../../../../../api/scheduling/matching_candidate_workflow_client')>();
  return { ...original, matchingCandidateWorkflowClient: { ...original.matchingCandidateWorkflowClient, searchInquiryCandidates: mocks.search } };
});
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: { query: mocks.query, addCandidates: mocks.add }, createCandidateAddCommand: mocks.command,
}));

const option = (staffId: number, name: string) => ({
  segment_index: 0, staff_id: staffId, staff_name: name, supported_day_count: 5, required_day_count: 5,
  full_case_coverage: true, selected_segment_start: '2026-09-01', selected_segment_end: '2026-09-05',
});
const entry = (staffId: number, name: string, id: number, status = 'active') => ({
  id, staff_id: staffId, staff_name: name, status, service_start_date: '2026-09-01', service_end_date: '2026-09-05',
});
const pool = (candidates: ReturnType<typeof entry>[]) => ({ case_no: 'CASE-ADD', pool_id: 9, candidates });

beforeEach(() => {
  Object.values(mocks).forEach(mock => mock.mockReset());
  mocks.search.mockResolvedValue({ case_no: 'CASE-ADD', planned_start_date: '2026-09-01', planned_end_date: '2026-09-05',
    candidate_options: [option(11, '月嫂甲'), option(12, '月嫂乙')], conflicts: [] });
  mocks.command.mockImplementation((caseNo, candidates) => ({ caseNo, candidates, actor: 'operator-1', eventKey: `add-${candidates[0].staff_id}` }));
});

async function search(onPoolReadback = vi.fn()) {
  render(<OrderCandidateQueryPanel caseNo="CASE-ADD" presentation="workbench" includeMultiCaregiver={false} onPoolReadback={onPoolReadback} />);
  fireEvent.click(screen.getByRole('button', { name: '查詢合適人選' }));
  await screen.findByText('未設定 月嫂甲');
  return onPoolReadback;
}

it('reads existing membership, allows withdrawn candidates and replaces selection with row buttons', async () => {
  mocks.query.mockResolvedValue(pool([entry(11, '月嫂甲', 17), entry(12, '月嫂乙', 18, 'withdrawn')]));
  await search();
  expect(screen.getByRole('button', { name: '已加入候選池（月嫂甲）' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '加入候選池（月嫂乙）' })).toBeEnabled();
  expect(screen.getAllByRole('checkbox')).toHaveLength(4); // only matching filters
  expect(screen.queryByRole('button', { name: /加入候選清單/ })).not.toBeInTheDocument();
  expect(mocks.add).not.toHaveBeenCalled();
});

it('adds one candidate at a time and marks each joined only after its exact receipt readback', async () => {
  const entries: ReturnType<typeof entry>[] = [];
  mocks.query.mockImplementation(async () => pool([...entries]));
  mocks.add.mockImplementation(async command => {
    const selected = command.candidates[0];
    const id = selected.staff_id === 11 ? 17 : 18;
    entries.push(entry(selected.staff_id, selected.staff_id === 11 ? '月嫂甲' : '月嫂乙', id));
    return { pool_id: 9, candidate_ids: [id], status: 'recorded' };
  });
  const onPoolReadback = await search();
  for (const [name, staffId] of [['月嫂甲', 11], ['月嫂乙', 12]] as const) {
    fireEvent.click(screen.getByRole('button', { name: `加入候選池（${name}）` }));
    const joined = await screen.findByRole('button', { name: `已加入候選池（${name}）` });
    expect(joined).toBeDisabled();
    expect(mocks.add).toHaveBeenLastCalledWith(expect.objectContaining({ candidates: [{ staff_id: staffId, start_date: '2026-09-01', end_date: '2026-09-05' }] }));
    fireEvent.click(joined);
  }
  expect(mocks.add).toHaveBeenCalledTimes(2);
  expect(onPoolReadback).toHaveBeenCalledTimes(2);
  expect(screen.getAllByRole('button', { name: /已加入候選池/ })).toHaveLength(2);
});

it('does not claim membership after an unknown outcome and recovers using the original command', async () => {
  let recovered = false;
  mocks.query.mockImplementation(async () => pool(recovered ? [entry(11, '月嫂甲', 17)] : []));
  mocks.add.mockRejectedValueOnce(new ApiHttpError(503, 'unavailable', '暫時無法確認寄送結果'))
    .mockImplementationOnce(async () => { recovered = true; return { pool_id: 9, candidate_ids: [17], status: 'recorded' }; });
  await search();
  fireEvent.click(screen.getByRole('button', { name: '加入候選池（月嫂甲）' }));
  const recover = await screen.findByRole('button', { name: '以原操作重新確認加入候選池' });
  expect(screen.queryByRole('button', { name: '已加入候選池（月嫂甲）' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '加入候選池（月嫂乙）' })).toBeDisabled();
  fireEvent.click(recover);
  await waitFor(() => expect(screen.getByRole('button', { name: '已加入候選池（月嫂甲）' })).toBeDisabled());
  expect(mocks.command).toHaveBeenCalledTimes(1);
  expect(mocks.add.mock.calls[0][0]).toEqual(mocks.add.mock.calls[1][0]);
});
