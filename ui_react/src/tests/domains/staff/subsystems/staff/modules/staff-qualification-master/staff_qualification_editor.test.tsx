import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffQualificationEditor } from '../../../../../../../components/StaffQualificationEditor';
import { staffQualificationEditingClient, type QualificationSnapshot } from '../../../../../../../api/staff/qualification_editing_client';

const snapshot: QualificationSnapshot = { staff_id: 11, before: { special_skills: ['照護'], certifications: ['托育證照'], transportation: ['機車'], has_massage_cert: true, care_babies: 1 }, after: { special_skills: ['照護'], certifications: ['托育證照'], transportation: ['機車'], has_massage_cert: true, care_babies: 1 }, snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null };

describe('Staff transportation and care capacity editing', () => {
  beforeEach(() => {
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    vi.spyOn(staffQualificationEditingClient, 'query').mockResolvedValue(snapshot);
    vi.spyOn(staffQualificationEditingClient, 'preview').mockImplementation(async (_id, facts) => ({ ...snapshot, after: facts, preview_fingerprint: 'b'.repeat(64) }));
    vi.spyOn(staffQualificationEditingClient, 'apply').mockImplementation(async (_id, facts, preview, _reason, key) => ({ ...preview, after: facts, idempotency_key: key, replayed: false, correlation_id: 'test' }));
  });
  afterEach(() => vi.restoreAllMocks());

  it('saves only transportation and care capacity changes, preserving hidden qualification values', async () => {
    const onUpdated = vi.fn();
    render(<StaffQualificationEditor staffId={11} onUpdated={onUpdated} />);
    expect(await screen.findByRole('textbox', { name: '交通方式' })).toHaveValue('機車');
    expect(screen.getByRole('spinbutton', { name: '最多照顧寶寶數' })).toHaveValue(1);
    expect(screen.queryByLabelText(/專業技能|一般證照|按摩證書|備註/)).not.toBeInTheDocument();
    expect(screen.queryByText(/照護|托育證照/)).not.toBeInTheDocument();
    const save = screen.getByRole('button', { name: '儲存' });
    expect(save).toBeEnabled();
    expect(screen.queryByRole('button', { name: '重試讀取交通與照顧人數' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('交通方式'), { target: { value: '汽車' } });
    fireEvent.change(screen.getByLabelText('最多照顧寶寶數'), { target: { value: '2' } });
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
    const after = { ...snapshot.after, transportation: ['汽車'], care_babies: 2 };
    vi.mocked(staffQualificationEditingClient.query).mockResolvedValue({ ...snapshot, before: after, after });
    fireEvent.click(save);
    await screen.findByText('交通與照顧人數已儲存。');
    expect(staffQualificationEditingClient.preview).toHaveBeenCalledExactlyOnceWith(11, after, expect.any(AbortSignal));
    expect(staffQualificationEditingClient.apply).toHaveBeenCalledExactlyOnceWith(
      11, after, expect.objectContaining({ preview_fingerprint: 'b'.repeat(64) }), '', expect.any(String), expect.any(AbortSignal),
    );
    expect(screen.getByLabelText('交通方式')).toHaveValue('汽車');
    expect(screen.getByLabelText('最多照顧寶寶數')).toHaveValue(2);
    expect(window.alert).not.toHaveBeenCalled();
    expect(onUpdated).toHaveBeenCalledOnce();
  });

  it('cancels changes to both fields without saving', async () => {
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    fireEvent.change(await screen.findByLabelText('交通方式'), { target: { value: '汽車' } });
    fireEvent.change(screen.getByLabelText('最多照顧寶寶數'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '取消變更' }));
    expect(screen.getByLabelText('交通方式')).toHaveValue('機車');
    expect(screen.getByLabelText('最多照顧寶寶數')).toHaveValue(1);
    expect(staffQualificationEditingClient.preview).not.toHaveBeenCalled();
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
  });

  it('requires a fresh query when hidden qualification facts change before preview', async () => {
    const fresh = { ...snapshot.after, special_skills: ['新技能'], certifications: ['新證照'], has_massage_cert: false };
    const freshSnapshot = { ...snapshot, before: fresh, after: fresh, snapshot_fingerprint: 'd'.repeat(64) };
    vi.mocked(staffQualificationEditingClient.query).mockResolvedValueOnce(snapshot).mockResolvedValue(freshSnapshot);
    vi.mocked(staffQualificationEditingClient.preview).mockImplementation(async (_id, values) => ({
      ...freshSnapshot, after: values, preview_fingerprint: 'e'.repeat(64),
    }));
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    fireEvent.change(await screen.findByLabelText('交通方式'), { target: { value: '汽車' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('資料已有更新，請重新查詢後再儲存。');
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
    expect(screen.queryByText(/新技能|新證照/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重試讀取交通與照顧人數' }));
    fireEvent.change(await screen.findByLabelText('交通方式'), { target: { value: '汽車' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    await screen.findByText('交通與照顧人數已儲存。');
    expect(staffQualificationEditingClient.apply).toHaveBeenCalledExactlyOnceWith(
      11, { ...fresh, transportation: ['汽車'] }, expect.objectContaining({ snapshot_fingerprint: 'd'.repeat(64) }),
      '', expect.any(String), expect.any(AbortSignal),
    );
  });

  it('keeps the same intent key for an uncertain save retry and offers requery', async () => {
    vi.mocked(staffQualificationEditingClient.apply).mockRejectedValueOnce(new Error('儲存結果未確認'));
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    await screen.findByLabelText('交通方式');
    fireEvent.change(screen.getByLabelText('交通方式'), { target: { value: '汽車' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    await screen.findByText('儲存結果未確認');
    expect(screen.getByRole('button', { name: '重試讀取交通與照顧人數' })).toBeEnabled();
    expect(screen.getByText(/機車 → 汽車/)).toBeInTheDocument();
    expect(screen.queryByText(/照護|托育證照/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    await waitFor(() => expect(staffQualificationEditingClient.apply).toHaveBeenCalledTimes(2));
    expect(staffQualificationEditingClient.preview).toHaveBeenCalledOnce();
    const calls = vi.mocked(staffQualificationEditingClient.apply).mock.calls;
    expect(calls[0]).toEqual(calls[1]);
  });

  it('reports a committed save separately from a failed readback', async () => {
    const onUpdated = vi.fn();
    render(<StaffQualificationEditor staffId={11} onUpdated={onUpdated} />);
    await screen.findByLabelText('交通方式');
    fireEvent.change(screen.getByLabelText('交通方式'), { target: { value: '汽車' } });
    vi.mocked(staffQualificationEditingClient.query).mockRejectedValueOnce(new Error('查詢暫時失敗'));
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    await screen.findByText('資料已儲存，但重新查詢失敗，請重試查詢。');
    expect(staffQualificationEditingClient.apply).toHaveBeenCalledOnce();
    expect(onUpdated).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: '重試讀取交通與照顧人數' })).toBeEnabled();
  });

  it('offers query retry only after a failed load and removes it after recovery', async () => {
    vi.mocked(staffQualificationEditingClient.query).mockRejectedValueOnce(new Error('資格暫時無法讀取'));
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    await screen.findByText('資格暫時無法讀取');
    fireEvent.click(screen.getByRole('button', { name: '重試讀取交通與照顧人數' }));
    await screen.findByLabelText('交通方式');
    expect(screen.queryByRole('button', { name: '重試讀取交通與照顧人數' })).not.toBeInTheDocument();
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
  });
});
