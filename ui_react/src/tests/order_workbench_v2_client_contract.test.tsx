import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderClientContractPanel } from '../components/OrderClientContractPanel';

const mocks = vi.hoisted(() => ({
  query: vi.fn(),
  sendClient: vi.fn(),
  uploadClientSignedReturn: vi.fn(),
}));

vi.mock('../api/orders/contract_signing_client', () => ({
  contractSigningClient: {
    query: mocks.query,
  },
}));

vi.mock('../api/orders/contract_signing_mutation_client', () => ({
  contractSigningMutationClient: {
    sendClient: mocks.sendClient,
    uploadClientSignedReturn: mocks.uploadClientSignedReturn,
  },
}));

function signingStatus(sent: boolean, signedReceived: boolean, withDocument: boolean) {
  return {
    case_no: 'CASE-CLIENT-CONTRACT',
    staff_segments: [{
      segment_id: 31,
      staff_id: 8892,
      sent: true,
      signed_received: true,
    }],
    commitment_id: 77,
    client_document_sent: sent,
    client_signed_received: signedReceived,
    contract_identity: 'contract:CASE-CLIENT-CONTRACT',
    documents: withDocument ? [{
      document_version_id: 41,
      scope: 'client_contract',
      role: 'template_generated',
      target_key: 'client-contract',
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
  document_version_id: 41,
  signing_event_id: 92,
  line_delivery_task_id: 53,
  commitment_id: 77,
  contract_identity: 'contract:CASE-CLIENT-CONTRACT',
};

describe('待辦看板 Beta 第 8 階客戶契約', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('只接入客戶契約 owner facts，建立寄送工作後回讀正式狀態', async () => {
    mocks.query
      .mockResolvedValueOnce(signingStatus(false, false, false))
      .mockResolvedValueOnce(signingStatus(true, false, true));
    mocks.sendClient.mockResolvedValue(receipt);

    render(<OrderClientContractPanel caseNo="CASE-CLIENT-CONTRACT" />);
    fireEvent.click(screen.getByRole('button', { name: '讀取客戶契約狀態' }));

    expect(await screen.findByText('寄送狀態')).toBeInTheDocument();
    expect(screen.getByText('尚未寄送')).toBeInTheDocument();
    expect(screen.getByText('尚未簽回')).toBeInTheDocument();
    expect(screen.getByText('尚未產生')).toBeInTheDocument();
    expect(screen.queryByText(/月嫂 #/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('客戶契約受控 HTTPS 文件下載網址'), {
      target: { value: 'https://contracts.example/CASE-CLIENT-CONTRACT/client.pdf' },
    });
    fireEvent.click(screen.getByRole('button', { name: '建立客戶契約寄送工作' }));

    await waitFor(() => expect(mocks.sendClient).toHaveBeenCalledWith(
      'CASE-CLIENT-CONTRACT',
      'https://contracts.example/CASE-CLIENT-CONTRACT/client.pdf',
      expect.objectContaining({
        idempotencyKey: expect.any(String),
        correlationId: expect.any(String),
      }),
    ));
    expect(await screen.findByText('已建立寄送工作')).toBeInTheDocument();
    expect(screen.getByText('版本 #41')).toBeInTheDocument();
    expect(screen.getByText(/寄送工作已建立，並已回讀最新狀態/)).toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledTimes(2);
  });

  it('只用目前 server 回讀的客戶契約文件版本記錄簽回，再回讀已簽回狀態', async () => {
    mocks.query
      .mockResolvedValueOnce(signingStatus(true, false, true))
      .mockResolvedValueOnce(signingStatus(true, true, true));
    mocks.uploadClientSignedReturn.mockResolvedValue({ ...receipt, line_delivery_task_id: null });

    render(<OrderClientContractPanel caseNo="CASE-CLIENT-CONTRACT" />);
    fireEvent.click(screen.getByRole('button', { name: '讀取客戶契約狀態' }));

    expect(await screen.findByText('版本 #41')).toBeInTheDocument();
    const signedFile = new File(['signed'], 'client-signed.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('客戶簽回檔'), {
      target: {
        files: {
          0: signedFile,
          length: 1,
          item: (index: number) => index === 0 ? signedFile : null,
        },
      },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄客戶契約簽回' }));

    await waitFor(() => expect(mocks.uploadClientSignedReturn).toHaveBeenCalledWith(
      'CASE-CLIENT-CONTRACT',
      signedFile,
      41,
      expect.objectContaining({
        idempotencyKey: expect.any(String),
        correlationId: expect.any(String),
      }),
    ));
    expect(await screen.findByText('已簽回')).toBeInTheDocument();
    expect(screen.getByText(/簽回已記錄，並已回讀最新狀態/)).toBeInTheDocument();
    expect(mocks.query).toHaveBeenCalledTimes(2);
  });
});
