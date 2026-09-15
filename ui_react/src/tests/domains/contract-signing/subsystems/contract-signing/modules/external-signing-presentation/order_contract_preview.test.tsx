import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { previewContractFields } from '../../../../../../../api/orders/contract_full_preview_client';
import { contractExternalSigningClient } from '../../../../../../../api/orders/contract_external_signing_client';
import { OrderContractPreview } from '../../../../../../../components/OrderContractPreview';

vi.mock('../../../../../../../api/orders/contract_full_preview_client', () => ({
  previewContractFields: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/contract_external_signing_client', () => ({
  contractExternalSigningClient: { query: vi.fn() },
}));

const basePreview = {
  case_no: 'CASE-001',
  assignment_id: null,
  template_version: 'a'.repeat(64),
  owner_fingerprints: {},
  blockers: [],
  preview_fingerprint: 'b'.repeat(64),
  ready_to_print: true,
};

describe('OrderContractPreview', () => {
  beforeEach(() => vi.clearAllMocks());

  it('automatically reads the client projection', async () => {
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview,
      scope: 'client',
      template_key: 'contract_client_copy',
      field_values: { F1: 'CASE-001', 'projected.projected_subsidy_amount': 12000 },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);

    await waitFor(() => expect(previewContractFields).toHaveBeenCalledWith(
      'CASE-001', 'client', null, expect.any(AbortSignal),
    ));
    expect(await screen.findByText('預估市府補助金額')).toBeInTheDocument();
    expect(screen.getByText('12000')).toBeInTheDocument();
  });

  it('marks the second payment due date and notes as optional when blank', async () => {
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview,
      scope: 'client',
      template_key: 'contract_client_copy',
      field_values: {
        F1: 'CASE-001',
        'projected.second_payment_due_date': null,
        F41: '',
      },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);

    expect(await screen.findAllByText('未填（可留白）')).toHaveLength(2);
    expect(screen.queryByText('契約尚有未完成條件，請核對資料後再準備文件。')).not.toBeInTheDocument();
  });

  it('shows the staff projection as one whole payable with a projected payday', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({
      staff_targets: [{ matching_segment_id: 97 }],
    } as never);
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview,
      scope: 'staff',
      assignment_id: 97,
      template_key: 'contract_staff_service',
      field_values: {
        'projected.service_unit_price': 300,
        'projected.staff_payable_total': 48000,
        'projected.staff_payable_due_date': '2027-02-15',
      },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);
    fireEvent.click(screen.getByRole('button', { name: /服務人員委任契約/ }));

    await waitFor(() => expect(previewContractFields).toHaveBeenCalledWith(
      'CASE-001', 'staff', 97, expect.any(AbortSignal),
    ));
    expect(await screen.findByText('預估服務單價')).toBeInTheDocument();
    expect(screen.getByText('預估整筆應付報酬')).toBeInTheDocument();
    expect(screen.getByText('預估發薪日')).toBeInTheDocument();
    expect(screen.getByText('48000')).toBeInTheDocument();
    expect(screen.getByText('2027-02-15')).toBeInTheDocument();
  });
});
