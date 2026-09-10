import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderCandidateContactStatusPanel } from '../../../../../../../components/OrderCandidateContactStatusPanel';
import { OrderInformationSheets } from '../../../../../../../components/OrderInformationSheets';
import { candidateContactPoolClient as client } from '../../../../../../../api/scheduling/candidate_contact_pool_client';

vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { query: vi.fn(), previewInformation: vi.fn(), sendInformation: vi.fn() } }));
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(client.query).mockResolvedValue({ case_no: 'CASE-1', pool_id: 1, candidates: [{ id: 3, staff_id: 2, staff_name: '測試月嫂', status: 'active', willingness: 'pending', information: { '1': null, '2': null }, service_start_date: '2026-10-01', service_end_date: '2026-10-02' }] } as never);
  vi.mocked(client.previewInformation).mockImplementation(async (caseNo, candidateId, kind) => ({ case_no: caseNo, candidate_id: candidateId, info_type: kind, staff_name: '測試月嫂', text: `資訊${kind}：服務報酬待確認`, preview_fingerprint: String(kind).repeat(64) }));
  vi.mocked(client.sendInformation).mockResolvedValue({ status: 'queued', event_id: 4, line_task_id: 5 });
});

it.each([1, 2] as const)('previews information %i independently and sends exactly that preview', async (kind) => {
  render(<OrderCandidateContactStatusPanel caseNo="CASE-1" />);
  fireEvent.click(await screen.findByRole('button', { name: `寄送訂單資訊－${kind}` }));
  await screen.findByText(`資訊${kind}：服務報酬待確認`);
  expect(client.sendInformation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('確認寄送'));
  await waitFor(() => expect(client.sendInformation).toHaveBeenCalledWith('CASE-1', 3, kind, String(kind).repeat(64), expect.any(String)));
  expect(client.sendInformation).toHaveBeenCalledTimes(1);
});

it('previews a candidate without creating or requiring an assignment', async () => {
  render(<OrderInformationSheets caseNo="CASE-1" assignments={[]} />);
  expect(await screen.findByText('資訊1：服務報酬待確認')).toBeInTheDocument();
  fireEvent.click(screen.getByText('訂單資訊－2'));
  expect(await screen.findByText('資訊2：服務報酬待確認')).toBeInTheDocument();
  expect(client.sendInformation).not.toHaveBeenCalled();
});
