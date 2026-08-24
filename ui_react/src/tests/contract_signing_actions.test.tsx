/**
 * File: contract_signing_actions.test.tsx
 * Description: 驗證契約簽署介面會以既有 typed 命令實際建立寄送與簽回紀錄。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ContractSigningActions } from '../components/ContractSigningActions';
import { contractSigningMutationClient } from '../api/orders/contract_signing_mutation_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';

const receipt = {
  document_version_id: 7,
  signing_event_id: 8,
  line_delivery_task_id: 9,
  commitment_id: 3,
  contract_identity: 'contract:case-1',
};

const waitingForStaffReturn = {
  case_no: 'CASE-1',
  staff_segments: [{ segment_id: 3, staff_id: 9, sent: true, signed_received: false }],
  commitment_id: 3,
  client_document_sent: false,
  client_signed_received: false,
  contract_identity: null,
  documents: [{
    document_version_id: 7,
    scope: 'staff_segment',
    role: 'template_generated',
    target_key: 'staff-segment:3',
    version_number: 1,
    template_key: null,
    template_sha256: null,
    mapping_sha256: null,
    archive_sha256: 'a'.repeat(64),
    mime_type: 'application/pdf',
    file_size: 12,
  }],
};

describe('ContractSigningActions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('以 HTTPS 文件網址建立月嫂寄送任務並顯示 server receipt', async () => {
    const sendStaff = vi.spyOn(contractSigningMutationClient, 'sendStaff').mockResolvedValue(receipt);
    render(<ContractSigningActions
      caseNo="CASE-1"
      signing={{ ...waitingForStaffReturn, staff_segments: [{ segment_id: 3, staff_id: 9, sent: false, signed_received: false }] }}
      onCommitted={vi.fn()}
    />);

    fireEvent.change(screen.getByLabelText('受控 HTTPS 文件下載網址'), { target: { value: 'https://contracts.example/file.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: '確認建立月嫂契約寄送任務' }));

    await waitFor(() => expect(sendStaff).toHaveBeenCalledWith(
      'CASE-1', 3, 'https://contracts.example/file.pdf', expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
    expect(await screen.findByText(/已建立 durable LINE 寄送任務 #9/)).toBeInTheDocument();
  });

  it('只以目前已寄送的文件版本記錄月嫂簽回檔', async () => {
    const uploadStaffSignedReturn = vi.spyOn(contractSigningMutationClient, 'uploadStaffSignedReturn').mockResolvedValue(receipt);
    render(<ContractSigningActions caseNo="CASE-1" signing={waitingForStaffReturn} onCommitted={vi.fn()} />);

    const signedFile = new File(['signed'], 'signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('月嫂簽回檔'), {
      target: { files: { 0: signedFile, length: 1, item: (index: number) => index === 0 ? signedFile : null } },
    });
    fireEvent.click(screen.getByRole('button', { name: '確認記錄月嫂簽回' }));

    await waitFor(() => expect(uploadStaffSignedReturn).toHaveBeenCalledWith(
      'CASE-1', 3, signedFile, 7, expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
  });

  it('從版本化文件清單下載既有 PDF，不以瀏覽器重新轉檔', async () => {
    const download = vi.spyOn(contractSigningClient, 'downloadDocument').mockResolvedValue({
      blob: new Blob(['pdf'], { type: 'application/pdf' }),
      filename: 'signed-contract.pdf',
      mimeType: 'application/pdf',
    });
    const createObjectURL = vi.fn().mockReturnValue('blob:contract-test');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    render(<ContractSigningActions caseNo="CASE-1" signing={waitingForStaffReturn} onCommitted={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: '下載／匯出此文件' }));

    await waitFor(() => expect(download).toHaveBeenCalledWith('CASE-1', 7));
    expect(click).toHaveBeenCalledOnce();
    expect(await screen.findByText(/已下載不可變契約文件版本 #7/)).toBeInTheDocument();
  });
});
