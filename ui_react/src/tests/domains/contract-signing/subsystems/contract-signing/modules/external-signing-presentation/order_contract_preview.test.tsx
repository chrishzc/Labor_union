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
  field_states: {},
  warnings: [],
  blockers: [],
  preview_fingerprint: 'b'.repeat(64),
  ready_to_print: true,
};

describe('OrderContractPreview', () => {
  beforeEach(() => vi.resetAllMocks());

  it('automatically reads the client projection', async () => {
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview,
      scope: 'client',
      template_key: 'contract_client_copy',
      field_values: { F1: 'CASE-001', D36: '99781699115157', 'projected.projected_subsidy_amount': 12000 },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);

    await waitFor(() => expect(previewContractFields).toHaveBeenCalledWith(
      'CASE-001', 'client', null, expect.any(AbortSignal),
    ));
    expect(await screen.findByText('預估市府補助金額')).toBeInTheDocument();
    expect(screen.getByText('12000')).toBeInTheDocument();
    expect(screen.getByText('本案專屬虛擬帳號')).toBeInTheDocument();
    expect(screen.getByText('99781699115157')).toBeInTheDocument();
    expect(screen.getByText(/契約顯示預計繳款日/)).toBeInTheDocument();
  });

  it('marks absent planned payment stages and notes as optional', async () => {
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview,
      scope: 'client',
      template_key: 'contract_client_copy',
      field_states: {
        'projected.deposit_due_date': 'optional_empty',
        'projected.first_payment_due_date': 'optional_empty',
        'projected.second_payment_due_date': 'optional_empty',
        F41: 'optional_empty',
      },
      field_values: {
        F1: 'CASE-001',
        'projected.second_payment_due_date': null,
        F41: '',
      },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);

    expect(await screen.findAllByText('未填（可留白）')).toHaveLength(4);
    expect(screen.queryByText('契約尚有未完成條件，請核對資料後再準備文件。')).not.toBeInTheDocument();
  });

  it('keeps one optional field optional when another field is missing', async () => {
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview,
      ready_to_print: false,
      warnings: ['contract_pdf_field_missing:B43'],
      blockers: ['contract_pdf_external_reference_unresolved'],
      scope: 'client',
      template_key: 'contract_client_copy',
      field_states: {
        B43: 'missing',
        F41: 'optional_empty',
        'projected.deposit_due_date': 'optional_empty',
        'projected.first_payment_due_date': 'optional_empty',
        'projected.second_payment_due_date': 'optional_empty',
      },
      field_values: { F1: 'CASE-001', B43: null, F41: '', 'projected.deposit_due_date': null },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);

    expect(await screen.findByText(/目前資料仍有缺漏/)).toBeInTheDocument();
    expect(screen.getByText(/契約模板或文件產生發生技術問題/)).toBeInTheDocument();
    expect(screen.getAllByText('未填（可留白）')).toHaveLength(4);
    expect(screen.getByText('服務地址').nextElementSibling).toHaveTextContent('尚未提供／待核對');
  });

  it('shows the staff projection as one whole payable with a projected payday', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({
      state: 'preparing',
      case_no: 'CASE-001',
      staff_segments: [{ segment_id: 97, staff_id: 7, sent: false, signed_received: false }],
      commitment_id: null, documents: [],
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

  it('requires an exact choice when unsigned current data has multiple staff segments', async () => {
    vi.mocked(contractExternalSigningClient.query).mockResolvedValue({
      state: 'preparing',
      case_no: 'CASE-001', commitment_id: null, documents: [],
      staff_segments: [
        { segment_id: 97, staff_id: 7, sent: false, signed_received: false },
        { segment_id: 98, staff_id: 8, sent: false, signed_received: false },
      ],
    } as never);
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview, scope: 'staff', template_key: 'contract_staff_service', field_values: { C4: '第二位服務人員' },
    });

    render(<OrderContractPreview caseNo="CASE-001" />);
    fireEvent.click(screen.getByRole('button', { name: /服務人員委任契約/ }));
    const choice = await screen.findByRole('combobox', { name: '選擇月嫂契約' });
    expect(vi.mocked(previewContractFields).mock.calls.some((call) => call[1] === 'staff')).toBe(false);
    fireEvent.change(choice, { target: { value: '98' } });
    await waitFor(() => expect(previewContractFields).toHaveBeenCalledWith(
      'CASE-001', 'staff', 98, expect.any(AbortSignal),
    ));
    expect(await screen.findByText('第二位服務人員')).toBeInTheDocument();
  });

  it('resolves the new case target instead of reusing the previous case segment', async () => {
    vi.mocked(contractExternalSigningClient.query)
      .mockResolvedValueOnce({ state: 'preparing', case_no: 'CASE-001', staff_segments: [{ segment_id: 97, staff_id: 7 }] } as never)
      .mockResolvedValueOnce({ state: 'preparing', case_no: 'CASE-002', staff_segments: [{ segment_id: 98, staff_id: 8 }] } as never);
    vi.mocked(previewContractFields).mockResolvedValue({
      ...basePreview, scope: 'staff', template_key: 'contract_staff_service', field_values: {},
    });
    const { rerender } = render(<OrderContractPreview caseNo="CASE-001" />);
    fireEvent.click(screen.getByRole('button', { name: /服務人員委任契約/ }));
    await waitFor(() => expect(previewContractFields).toHaveBeenCalledWith(
      'CASE-001', 'staff', 97, expect.any(AbortSignal),
    ));
    rerender(<OrderContractPreview caseNo="CASE-002" />);
    await waitFor(() => expect(previewContractFields).toHaveBeenCalledWith(
      'CASE-002', 'staff', 98, expect.any(AbortSignal),
    ));
    expect(previewContractFields).not.toHaveBeenCalledWith('CASE-002', 'staff', 97, expect.any(AbortSignal));
  });
});
