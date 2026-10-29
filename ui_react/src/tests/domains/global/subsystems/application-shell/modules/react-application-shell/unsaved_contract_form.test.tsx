import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ContractSigningActions } from '../../../../../../../components/ContractSigningActions';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../../components/UnsavedChanges';
import type { ContractSigningStatus } from '../../../../../../../api/orders/contract_signing_client';

const mocks = vi.hoisted(() => ({ sendStaff: vi.fn(), previewManualStaffAttestation: vi.fn(), recordManualStaffAttestation: vi.fn() }));
vi.mock('../../../../../../../api/orders/contract_signing_mutation_client', () => ({ contractSigningMutationClient: mocks }));
const signing: ContractSigningStatus = { case_no: 'TEST', staff_segments: [{ segment_id: 1, staff_id: 11, sent: false, signed_received: false }],
  commitment_id: null, client_document_sent: false, client_signed_received: false, contract_identity: null, documents: [] };
function Probe({ leave }: { leave: () => void }) {
  const { requestLeave } = useUnsavedNavigation();
  return <button onClick={() => requestLeave(leave)}>離開契約表單</button>;
}
function mount() {
  const leave = vi.fn();
  render(<UnsavedChangesProvider><ContractSigningActions caseNo="TEST" signing={signing} onCommitted={vi.fn()} /><Probe leave={leave} /></UnsavedChangesProvider>);
  return leave;
}

describe('契約表單的未儲存基準', () => {
  it('檢查成功但正式寫入失敗時仍保留證據，不能把檢查結果當作已儲存', async () => {
    mocks.previewManualStaffAttestation.mockResolvedValue({ case_no: 'TEST', scope: 'staff_segment', matching_segment_id: 1, confirmation_method: 'phone', preview_fingerprint: 'a'.repeat(64), can_apply: true, line_delivery_task_id: null });
    mocks.recordManualStaffAttestation.mockRejectedValue(new Error('證據儲存失敗'));
    const leave = mount();
    const file = new File(['synthetic evidence'], 'evidence.pdf', { type: 'application/pdf' });
    const input = screen.getByLabelText('人工月嫂簽約證據檔');
    Object.defineProperty(input, 'files', { configurable: true, value: { 0: file, length: 1, item: () => file } });
    fireEvent.change(input);
    fireEvent.change(screen.getByLabelText('月嫂備註（選填）'), { target: { value: '已電話核對' } });
    fireEvent.click(screen.getByRole('button', { name: /確認記錄人工月嫂簽約/ }));
    await screen.findByRole('alert');
    expect(mocks.previewManualStaffAttestation).toHaveBeenCalledOnce();
    expect(mocks.recordManualStaffAttestation).toHaveBeenCalledOnce();
    expect(mocks.previewManualStaffAttestation.mock.invocationCallOrder[0]).toBeLessThan(mocks.recordManualStaffAttestation.mock.invocationCallOrder[0]);
    fireEvent.click(screen.getByRole('button', { name: '離開契約表單' }));
    const warning = screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    expect(warning).toHaveTextContent('evidence.pdf'); expect(warning).toHaveTextContent('已電話核對');
    expect(leave).not.toHaveBeenCalled();
  });

  it('寄送確認成功後清除該欄位的待儲存狀態，後續改網址仍會警告', async () => {
    mocks.sendStaff.mockResolvedValue({ document_version_id: 1, signing_event_id: 2, line_delivery_task_id: 3, commitment_id: null, contract_identity: null });
    const leave = mount();
    fireEvent.change(screen.getByLabelText('受控 HTTPS 文件下載網址'), { target: { value: 'https://example.test/document-one' } });
    fireEvent.click(screen.getByRole('button', { name: /確認建立月嫂契約寄送任務/ }));
    await waitFor(() => expect(mocks.sendStaff).toHaveBeenCalled());
    expect(await screen.findByRole('status')).toHaveTextContent('簽署紀錄已建立');
    fireEvent.click(screen.getByRole('button', { name: '離開契約表單' }));
    expect(leave).toHaveBeenCalledOnce(); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('受控 HTTPS 文件下載網址'), { target: { value: 'https://example.test/document-two' } });
    fireEvent.click(screen.getByRole('button', { name: '離開契約表單' }));
    const warning = screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    expect(warning).toHaveTextContent('已輸入或修改下載網址'); expect(warning).not.toHaveTextContent('https://example.test/');
  });
});
