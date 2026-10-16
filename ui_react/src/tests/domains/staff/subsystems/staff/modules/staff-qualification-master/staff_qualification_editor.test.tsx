import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffQualificationEditor } from '../../../../../../../components/StaffQualificationEditor';
import { staffQualificationEditingClient, type QualificationSnapshot } from '../../../../../../../api/staff/qualification_editing_client';

const snapshot: QualificationSnapshot = { staff_id: 11, before: { special_skills: ['照護'], certifications: ['托育證照'], transportation: ['機車'], has_massage_cert: null, care_babies: 1 }, after: { special_skills: ['照護'], certifications: ['托育證照'], transportation: ['機車'], has_massage_cert: null, care_babies: 1 }, snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null };

describe('Staff professional qualification editing', () => {
  beforeEach(() => {
    vi.spyOn(staffQualificationEditingClient, 'query').mockResolvedValue(snapshot);
    vi.spyOn(staffQualificationEditingClient, 'preview').mockImplementation(async (_id, facts) => ({ ...snapshot, after: facts, preview_fingerprint: 'b'.repeat(64) }));
    vi.spyOn(staffQualificationEditingClient, 'apply').mockImplementation(async (_id, facts, preview, _reason, key) => ({ ...preview, after: facts, idempotency_key: key, replayed: false, correlation_id: 'test' }));
  });
  afterEach(() => vi.restoreAllMocks());

  it('edits all five facts, previews then saves and reads the persisted values', async () => {
    const onUpdated = vi.fn();
    render(<StaffQualificationEditor staffId={11} onUpdated={onUpdated} />);
    const skills = await screen.findByLabelText('專業技能');
    const save = screen.getByRole('button', { name: '確認儲存' });
    expect(save).toBeDisabled();
    expect(save).toHaveAccessibleDescription('尚未預覽：請先按「預覽變更」。');
    expect(screen.queryByRole('button', { name: '重試讀取專業資格' })).not.toBeInTheDocument();
    fireEvent.change(skills, { target: { value: '照護\n哺乳協助' } });
    fireEvent.change(screen.getByLabelText('一般證照'), { target: { value: '急救證書' } });
    fireEvent.change(screen.getByLabelText('交通方式'), { target: { value: '汽車' } });
    fireEvent.change(screen.getByLabelText('按摩證書'), { target: { value: 'true' } });
    fireEvent.change(screen.getByLabelText('最多照顧寶寶數'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽完成，請核對變更後確認儲存。');
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(save).toHaveAccessibleDescription('預覽完成：請填寫「專業資格異動原因」後確認儲存。');
    fireEvent.change(screen.getByLabelText('專業資格異動原因'), { target: { value: '核對證明' } });
    expect(save).toBeEnabled();
    expect(save).toHaveAccessibleDescription('預覽與異動原因已完成，可以按「確認儲存」。');
    const after = { special_skills: ['照護', '哺乳協助'], certifications: ['急救證書'], transportation: ['汽車'], has_massage_cert: true, care_babies: 2 };
    vi.mocked(staffQualificationEditingClient.query).mockResolvedValue({ ...snapshot, before: after, after });
    fireEvent.click(screen.getByRole('button', { name: '確認儲存' }));
    await screen.findByText('專業資格與服務資料已儲存並重新查詢。');
    expect(staffQualificationEditingClient.apply).toHaveBeenCalledWith(11, after, expect.objectContaining({ preview_fingerprint: 'b'.repeat(64) }), '核對證明', expect.any(String), expect.any(AbortSignal));
    expect(screen.getByLabelText('一般證照')).toHaveValue('急救證書');
    expect(onUpdated).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: '重試讀取專業資格' })).not.toBeInTheDocument();
  });

  it('cancels edits without saving and invalidates preview after another change', async () => {
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    fireEvent.change(await screen.findByLabelText('專業技能'), { target: { value: '新技能' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽完成，請核對變更後確認儲存。');
    fireEvent.change(screen.getByLabelText('專業資格異動原因'), { target: { value: '測試' } });
    fireEvent.change(screen.getByLabelText('按摩證書'), { target: { value: 'false' } });
    expect(screen.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '確認儲存' })).toHaveAccessibleDescription('尚未預覽：請先按「預覽變更」。');
    fireEvent.click(screen.getByRole('button', { name: '取消變更' }));
    expect(screen.getByLabelText('專業技能')).toHaveValue('照護');
    expect(screen.getByLabelText('按摩證書')).toHaveValue('');
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
  });

  it('keeps the same intent key for an uncertain save retry and offers requery', async () => {
    vi.mocked(staffQualificationEditingClient.apply).mockRejectedValueOnce(new Error('儲存結果未確認'));
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    await screen.findByLabelText('一般證照');
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽完成，請核對變更後確認儲存。');
    fireEvent.change(screen.getByLabelText('專業資格異動原因'), { target: { value: '核對' } });
    fireEvent.click(screen.getByRole('button', { name: '確認儲存' }));
    await screen.findByText('儲存結果未確認');
    expect(screen.getByRole('button', { name: '重試讀取專業資格' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '確認儲存' }));
    await waitFor(() => expect(staffQualificationEditingClient.apply).toHaveBeenCalledTimes(2));
    expect(vi.mocked(staffQualificationEditingClient.apply).mock.calls[0][4]).toBe(vi.mocked(staffQualificationEditingClient.apply).mock.calls[1][4]);
  });

  it('reports a committed save separately from a failed readback', async () => {
    const onUpdated = vi.fn();
    render(<StaffQualificationEditor staffId={11} onUpdated={onUpdated} />);
    await screen.findByLabelText('一般證照');
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽完成，請核對變更後確認儲存。');
    fireEvent.change(screen.getByLabelText('專業資格異動原因'), { target: { value: '核對' } });
    vi.mocked(staffQualificationEditingClient.query).mockRejectedValueOnce(new Error('查詢暫時失敗'));
    fireEvent.click(screen.getByRole('button', { name: '確認儲存' }));
    await screen.findByText('資料已儲存，但重新查詢失敗，請重試查詢。');
    expect(staffQualificationEditingClient.apply).toHaveBeenCalledOnce();
    expect(onUpdated).toHaveBeenCalledOnce();
    expect(screen.getByRole('button', { name: '重試讀取專業資格' })).toBeEnabled();
  });

  it('offers query retry only after a failed load and removes it after recovery', async () => {
    vi.mocked(staffQualificationEditingClient.query).mockRejectedValueOnce(new Error('資格暫時無法讀取'));
    render(<StaffQualificationEditor staffId={11} onUpdated={() => undefined} />);
    await screen.findByText('資格暫時無法讀取');
    fireEvent.click(screen.getByRole('button', { name: '重試讀取專業資格' }));
    await screen.findByLabelText('一般證照');
    expect(screen.queryByRole('button', { name: '重試讀取專業資格' })).not.toBeInTheDocument();
    expect(staffQualificationEditingClient.apply).not.toHaveBeenCalled();
  });
});
