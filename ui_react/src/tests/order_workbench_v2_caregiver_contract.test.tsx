import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderCaregiverContractPanel } from '../components/OrderCaregiverContractPanel';

const mocks = vi.hoisted(() => ({
  query: vi.fn(),
  sendStaff: vi.fn(),
  uploadStaffSignedReturn: vi.fn(),
}));

vi.mock('../api/orders/contract_signing_client', () => ({
  contractSigningClient: {
    query: mocks.query,
  },
}));

vi.mock('../api/orders/contract_signing_mutation_client', () => ({
  contractSigningMutationClient: {
    sendStaff: mocks.sendStaff,
    uploadStaffSignedReturn: mocks.uploadStaffSignedReturn,
  },
}));

function signingStatus(sent: boolean, signedReceived: boolean, withDocument: boolean) {
  return {
    case_no: 'CASE-CONTRACT',
    staff_segments: [{
      segment_id: 31,
      staff_id: 8892,
      sent,
      signed_received: signedReceived,
    }],
    commitment_id: 77,
    client_document_sent: false,
    client_signed_received: false,
    contract_identity: 'contract:CASE-CONTRACT',
    documents: withDocument ? [{
      document_version_id: 21,
      scope: 'staff_segment',
      role: 'template_generated',
      target_key: 'staff-segment:31',
      version_number: 1,
      template_key: null,
      template_sha256: null,
      mapping_sha256: null,
      archive_sha256: 'a'.repeat(64),
      mime_type: 'application/pdf',
      file_size: 128,
    }] : [],
  };
}

const receipt = {
  document_version_id: 21,
  signing_event_id: 91,
  line_delivery_task_id: 52,
  commitment_id: 77,
  contract_identity: 'contract:CASE-CONTRACT',
};

describe('待辦看板 Beta 第 6 階月嫂契約', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('只接入月嫂契約 owner facts，建立寄送工作後回讀正式狀態', async () => {
    mocks.query
      .mockResolvedValueOnce(signingStatus(false, false, false))
      .mockResolvedValueOnce(signingStatus(true, false, true));
    mocks.sendStaff.mockResolvedValue(receipt);

    render(<OrderCaregiverContractPanel caseNo="CASE-CONTRACT" />);
    fireEvent.click(screen.getByRole('button', { name: '讀取月嫂契約狀態' }));

    expect(await screen.findByText('寄送狀態：尚未寄送')).toBeInTheDocument();
    expect(screen.getByText('簽回狀態：尚未簽回')).toBeInTheDocument();
    expect(screen.getByText('契約文件：尚未產生')).toBeInTheDocument();
    expect(screen.queryByText('客戶正式服務契約')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('受控 HTTPS 文件下載網址'), {
      target: { value: 'https://contracts.example/CASE-CONTRACT/staff-31.pdf' },
    });
    fireEvent.click(screen.getByRole('button', { name: '建立月嫂契約寄送工作' }));

    await waitFor(() => expect(mocks.sendStaff).toHaveBeenCalledWith(
      'CASE-CONTRACT',
      31,
      'https://contracts.example/CASE-CONTRACT/staff-31.pdf',
      expect.objectContaining({
        idempotencyKey: expect.any(String),
        correlationId: expect.any(String),
      }),
    ));
    expect(await screen.findByText('寄送狀態：已建立寄送工作')).toBeInTheDocument();
    expect(screen.getByText('契約文件：版本 #21')).toBeInTheDocument();
    expect(screen.getByText(/寄送工作已建立，並已回讀最新狀態/)).toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledTimes(2);
  });

  it('只用目前 server 回讀的月嫂契約文件版本記錄簽回，再回讀已簽回狀態', async () => {
    mocks.query
      .mockResolvedValueOnce(signingStatus(true, false, true))
      .mockResolvedValueOnce(signingStatus(true, true, true));
    mocks.uploadStaffSignedReturn.mockResolvedValue({ ...receipt, line_delivery_task_id: null });

    render(<OrderCaregiverContractPanel caseNo="CASE-CONTRACT" />);
    fireEvent.click(screen.getByRole('button', { name: '讀取月嫂契約狀態' }));

    expect(await screen.findByText('契約文件：版本 #21')).toBeInTheDocument();
    const signedFile = new File(['signed'], 'staff-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('月嫂簽回檔'), {
      target: {
        files: {
          0: signedFile,
          length: 1,
          item: (index: number) => index === 0 ? signedFile : null,
        },
      },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄月嫂契約簽回' }));

    await waitFor(() => expect(mocks.uploadStaffSignedReturn).toHaveBeenCalledWith(
      'CASE-CONTRACT',
      31,
      signedFile,
      21,
      expect.objectContaining({
        idempotencyKey: expect.any(String),
        correlationId: expect.any(String),
      }),
    ));
    expect(await screen.findByText('簽回狀態：已簽回')).toBeInTheDocument();
    expect(screen.getByText(/簽回已記錄，並已回讀最新狀態/)).toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledTimes(2);
  });
});
