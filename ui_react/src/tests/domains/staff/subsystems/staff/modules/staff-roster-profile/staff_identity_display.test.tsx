import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as directory from '../../../../../../../api/staff_directory/staff_directory_client';
import { StaffIdentityProvider, useStaffIdentityLabels } from '../../../../../../../components/StaffIdentityProvider';

const person = (id: number, union_no: string | null) => ({ id, union_no, name: '同名月嫂', phone: null, education: null });
function IdentityConsumers() {
  const identity = useStaffIdentityLabels();
  return <><p>{identity.label(17, '來源姓名')}</p><p>{identity.label(18, '來源姓名')}</p>
    <select aria-label="測試月嫂選單" defaultValue={17}>{[17, 18].sort(identity.compare).map(id => <option key={id} value={id}>{identity.label(id)}</option>)}</select></>;
}

describe('shared Staff identity presentation', () => {
  const query = vi.fn<directory.StaffDirectoryClient['queryPage']>();
  beforeEach(() => {
    query.mockReset();
    vi.spyOn(directory, 'createStaffDirectoryClient').mockReturnValue({ queryPage: query, resetPagination: vi.fn() });
  });

  it('shares every bounded page across consumers, preserves same-name identity and sorts option labels', async () => {
    query.mockResolvedValueOnce({ items: [person(17, 'A10')], next_cursor: 17 })
      .mockResolvedValueOnce({ items: [person(18, 'A002')], next_cursor: null });
    render(<StrictMode><StaffIdentityProvider><IdentityConsumers /></StaffIdentityProvider></StrictMode>);
    await waitFor(() => expect(screen.getByRole('option', { name: 'A002 同名月嫂' })).toBeInTheDocument());
    const select = screen.getByLabelText('測試月嫂選單') as HTMLSelectElement;
    expect(Array.from(select.options).map(option => option.value)).toEqual(['18', '17']);
    expect(select).toHaveValue('17');
    fireEvent.change(select, { target: { value: '18' } });
    expect(select).toHaveValue('18');
    expect(query).toHaveBeenCalledTimes(2);
    expect(query).toHaveBeenLastCalledWith({ pageSize: 200, afterId: 17 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('does not claim a missing number while loading or after a read error, and recovers by explicit retry', async () => {
    query.mockRejectedValueOnce(new Error('unavailable')).mockResolvedValueOnce({ items: [person(17, null), person(18, '001')], next_cursor: null });
    render(<StaffIdentityProvider><IdentityConsumers /></StaffIdentityProvider>);
    expect(screen.queryByRole('option', { name: '未設定 姓名未設定' })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '重新讀取公會編號' }));
    await screen.findByRole('option', { name: '001 同名月嫂' });
    expect((screen.getByLabelText('測試月嫂選單') as HTMLSelectElement).options[1]).toHaveTextContent('未設定 同名月嫂');
  });

  it('clears old page identities immediately and ignores a late response after page replacement', async () => {
    let oldResolve!: (value: Awaited<ReturnType<directory.StaffDirectoryClient['queryPage']>>) => void;
    query.mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }))
      .mockResolvedValueOnce({ items: [person(17, '新001'), person(18, '新002')], next_cursor: null });
    const view = render(<StaffIdentityProvider key="old"><IdentityConsumers /></StaffIdentityProvider>);
    await waitFor(() => expect(query).toHaveBeenCalledOnce());
    view.rerender(<StaffIdentityProvider key="new"><IdentityConsumers /></StaffIdentityProvider>);
    await screen.findByRole('option', { name: '新001 同名月嫂' });
    await act(async () => { oldResolve({ items: [person(17, '舊001')], next_cursor: null }); });
    expect(screen.queryByText(/舊001/)).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: '新001 同名月嫂' })).toHaveValue('17');
  });
});
