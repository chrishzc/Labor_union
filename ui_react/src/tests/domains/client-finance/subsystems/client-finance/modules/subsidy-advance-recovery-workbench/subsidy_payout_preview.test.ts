/** The customer-refund preview must preserve an owner-classified advance. */
import { expect, it } from 'vitest';
import { ClientPayablePreviewSchema } from '../../../../../../../api/client_finance/client_settlement_remediation_schemas';

it('accepts a subsidy advance through the existing customer payable preview contract', () => {
  const preview = ClientPayablePreviewSchema.parse({
    account_version: 3, preview_fingerprint: 'a'.repeat(64),
    candidate: {
      correction_type: 'refund', case_no: 'TEST-001', amount: { amount: 12000 },
      entries: [{ identity: 'refund-bank:1', entry_type: 'subsidy_advance', amount: { amount: 12000 },
        occurred_on: '2026-03-15', reversal_of_entry_identity: null, finance_import_row_identity: '1' }],
      allocations: [{ entry_identity: 'refund-bank:1', obligation_identity: 'test:subsidy', amount: { amount: 12000 } }],
      affected_obligations: ['test:subsidy'], reversal_entry_type: null, recovery_amount: { amount: 0 }, fingerprint: 'b'.repeat(64),
    },
  });
  expect(preview.candidate.entries[0].entry_type).toBe('subsidy_advance');
});
