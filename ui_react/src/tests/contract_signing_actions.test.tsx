/**
 * File: contract_signing_actions.test.tsx
 * Description: 驗證契約簽署操作、人工 Preview/Apply、文件下載及 receipt/readback 失敗邊界。
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

const manualPreview = {
  case_no: 'CASE-1',
  scope: 'staff_segment' as const,
  matching_segment_id: 3,
  confirmation_method: 'paper' as const,
  preview_fingerprint: 'b'.repeat(64),
  can_apply: true as const,
  line_delivery_task_id: null,
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
    vi.unstubAllGlobals();
  });

  it('以 HTTPS 文件網址建立月嫂寄送任務並顯示 server receipt', async () => {
    const sendStaff = vi.spyOn(contractSigningMutationClient, 'sendStaff').mockResolvedValue(receipt);
    render(<ContractSigningActions
      caseNo="CASE-1"
      signing={{ ...waitingForStaffReturn, staff_segments: [{ segment_id: 3, staff_id: 9, sent: false, signed_received: false }] }}
      onCommitted={vi.fn()}
    />);

    fireEvent.change(screen.getByLabelText('受控 HTTPS 文件下載網址'), { target: { value: 'https://contracts.example/file.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: /確認建立月嫂契約寄送任務/ }));

    await waitFor(() => expect(sendStaff).toHaveBeenCalledWith(
      'CASE-1', 3, 'https://contracts.example/file.pdf', expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
    expect(await screen.findByText(/已排入 LINE 寄送佇列，尚未代表對方已收到/)).toBeInTheDocument();
  });

  it('只以目前已寄送的文件版本記錄月嫂簽回檔', async () => {
    const uploadStaffSignedReturn = vi.spyOn(contractSigningMutationClient, 'uploadStaffSignedReturn').mockResolvedValue(receipt);
    render(<ContractSigningActions caseNo="CASE-1" signing={waitingForStaffReturn} onCommitted={vi.fn()} />);

    const signedFile = new File(['signed'], 'signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('月嫂簽回檔'), {
      target: { files: { 0: signedFile, length: 1, item: (index: number) => index === 0 ? signedFile : null } },
    });
    fireEvent.click(screen.getByRole('button', { name: /確認記錄月嫂簽回/ }));

    await waitFor(() => expect(uploadStaffSignedReturn).toHaveBeenCalledWith(
      'CASE-1', 3, signedFile, 7, expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
  });

  it('以實際月嫂證據完成 Preview 後才允許人工簽約套用，且不建立 LINE 任務', async () => {
    const previewManualStaffAttestation = vi.spyOn(contractSigningMutationClient, 'previewManualStaffAttestation').mockResolvedValue(manualPreview);
    const recordManualStaffAttestation = vi.spyOn(contractSigningMutationClient, 'recordManualStaffAttestation').mockResolvedValue({ ...receipt, line_delivery_task_id: null });
    render(<ContractSigningActions
      caseNo="CASE-1"
      signing={{ ...waitingForStaffReturn, staff_segments: [{ segment_id: 3, staff_id: 9, sent: false, signed_received: false }] }}
      onCommitted={vi.fn()}
    />);

    const evidence = new File(['signed-evidence'], 'manual-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('人工月嫂簽約證據檔'), {
      target: { files: { 0: evidence, length: 1, item: (index: number) => index === 0 ? evidence : null } },
    });
    fireEvent.change(screen.getByLabelText('月嫂人工確認方式'), { target: { value: 'paper' } });
    fireEvent.change(screen.getByLabelText('月嫂人工確認依據'), { target: { value: '已核對紙本簽署頁與月嫂身分。' } });
    expect(screen.getByRole('button', { name: /確認記錄人工月嫂簽約/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /預覽人工月嫂簽約證據/ }));

    await waitFor(() => expect(previewManualStaffAttestation).toHaveBeenCalledWith(
      'CASE-1', 3, 'paper', '已核對紙本簽署頁與月嫂身分。', expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
    expect(await screen.findByText(/未建立 LINE 寄送/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /確認記錄人工月嫂簽約/ }));
    await waitFor(() => expect(recordManualStaffAttestation).toHaveBeenCalledWith(
      'CASE-1', 3, evidence, 'paper', '已核對紙本簽署頁與月嫂身分。', manualPreview.preview_fingerprint,
      expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
    expect(await screen.findByText(/未建立 LINE 寄送/)).toBeInTheDocument();
  });

  it('客戶可在有效服務承諾下用人工證據完成 Preview→Apply，不假造 LINE 寄送', async () => {
    const previewManualClientAttestation = vi.spyOn(contractSigningMutationClient, 'previewManualClientAttestation').mockResolvedValue({ ...manualPreview, scope: 'client_contract', matching_segment_id: null, confirmation_method: 'phone' });
    const recordManualClientAttestation = vi.spyOn(contractSigningMutationClient, 'recordManualClientAttestation').mockResolvedValue({ ...receipt, line_delivery_task_id: null });
    render(<ContractSigningActions
      caseNo="CASE-1"
      signing={{ ...waitingForStaffReturn, staff_segments: [], client_document_sent: false, client_signed_received: false }}
      onCommitted={vi.fn()}
    />);

    const evidence = new File(['client-evidence'], 'client-manual.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('人工客戶簽約證據檔'), {
      target: { files: { 0: evidence, length: 1, item: (index: number) => index === 0 ? evidence : null } },
    });
    fireEvent.change(screen.getByLabelText('客戶人工確認依據'), { target: { value: '已由客戶電話確認並核對簽署文件。' } });
    fireEvent.click(screen.getByRole('button', { name: /預覽人工客戶簽約證據/ }));
    await waitFor(() => expect(previewManualClientAttestation).toHaveBeenCalledWith(
      'CASE-1', 'phone', '已由客戶電話確認並核對簽署文件。', expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
    ));
    fireEvent.click(screen.getByRole('button', { name: /確認記錄人工客戶簽約並完成契約/ }));
    await waitFor(() => expect(recordManualClientAttestation).toHaveBeenCalledWith(
      'CASE-1', evidence, 'phone', '已由客戶電話確認並核對簽署文件。', manualPreview.preview_fingerprint,
      expect.objectContaining({ idempotencyKey: expect.any(String), correlationId: expect.any(String) }),
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

    fireEvent.click(screen.getByRole('button', { name: /下載／匯出此文件/ }));

    await waitFor(() => expect(download).toHaveBeenCalledWith('CASE-1', 7));
    expect(click).toHaveBeenCalledOnce();
    expect(await screen.findByText(/已下載不可變契約文件版本 #7/)).toBeInTheDocument();
  });

  it('Apply receipt 已提交但 fresh readback 失敗時保留 receipt 並提示可重試觀察', async () => {
    vi.spyOn(contractSigningMutationClient, 'sendStaff').mockResolvedValue(receipt);
    const onCommitted = vi.fn().mockRejectedValue(new Error('重新查詢失敗'));
    render(<ContractSigningActions
      caseNo="CASE-1"
      signing={{ ...waitingForStaffReturn, staff_segments: [{ segment_id: 3, staff_id: 9, sent: false, signed_received: false }] }}
      onCommitted={onCommitted}
    />);

    fireEvent.change(screen.getByLabelText('受控 HTTPS 文件下載網址'), { target: { value: 'https://contracts.example/file.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: /確認建立月嫂契約寄送任務/ }));

    await waitFor(() => expect(onCommitted).toHaveBeenCalledOnce());
    expect(screen.getByRole('status')).toHaveTextContent('簽署紀錄已建立');
    expect(screen.getByRole('status')).toHaveTextContent('重新載入結果失敗，可再按查詢確認；不需重複送出');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
