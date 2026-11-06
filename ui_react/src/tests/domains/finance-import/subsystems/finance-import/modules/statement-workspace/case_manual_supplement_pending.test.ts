/** Same-tab journal validation and compare-before-overwrite; no HTTP or SQL. */
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import {
  ManualSupplementStorageError, manualSupplementStorageKey, readPendingManualSupplement,
  savePendingManualSupplement, manualSupplementSignature, type PendingManualSupplement,
} from '../../../../../../../api/finance_import/case_manual_supplement_pending';

const record = (): PendingManualSupplement => ({ version: 1, actorId: 1, caseNo: 'CASE', key: 'original-key',
  command: { bank: 'sinopac', direction: 'client_receipt', target_item: 'deposit:CASE', amount_ntd: 1000,
    transaction_date: '2026-11-06', reason: null, allow_overage_disposition: false } });
beforeEach(() => window.sessionStorage.clear());
afterEach(() => vi.restoreAllMocks());

it.each(['wrong-case', 'invalid-date', 'invalid-intent', 'unknown-field'])('refuses an invalid stored command without erasing it (%s)', corruption => {
  const value = record();
  const raw = JSON.stringify(corruption === 'wrong-case' ? { ...value, caseNo: 'OTHER' }
    : corruption === 'invalid-date' ? { ...value, command: { ...value.command, transaction_date: '2026-02-30' } }
    : corruption === 'invalid-intent' ? { ...value, command: { ...value.command, direction: 'staff_salary', allow_overage_disposition: true } }
    : { ...value, unexpected: 'invalid' });
  window.sessionStorage.setItem(manualSupplementStorageKey('CASE'), raw);
  expect(() => readPendingManualSupplement('CASE')).toThrow(ManualSupplementStorageError);
  expect(window.sessionStorage.getItem(manualSupplementStorageKey('CASE'))).toBe(raw);
});

it('does not overwrite a concurrently retained command or a different actor', () => {
  const original = record();
  savePendingManualSupplement(original, null);
  const foreign = { ...original, key: 'other-key', actorId: 2 };
  expect(() => savePendingManualSupplement(foreign, null)).toThrow(ManualSupplementStorageError);
  expect(readPendingManualSupplement('CASE')).toEqual(original);
});

it('requires write readback and fails when storage silently drops the write', () => {
  const originalStorage = window.sessionStorage;
  const write = vi.fn();
  vi.spyOn(window, 'sessionStorage', 'get').mockReturnValue({
    getItem: (key: string) => originalStorage.getItem(key), setItem: write,
  } as unknown as Storage);
  expect(() => savePendingManualSupplement(record(), null)).toThrow(ManualSupplementStorageError);
  expect(write).toHaveBeenCalledOnce();
  expect(originalStorage.getItem(manualSupplementStorageKey('CASE'))).toBeNull();
});

it('accepts an explicit refund recovery intent while keeping receipt and refund pending commands distinct', () => {
  const receipt = record();
  const refund: PendingManualSupplement = { ...receipt, command: { ...receipt.command,
    direction: 'client_refund', target_item: 'refund:CASE', allow_overage_disposition: true } };
  savePendingManualSupplement(refund, null);
  expect(readPendingManualSupplement('CASE')).toEqual(refund);
  expect(manualSupplementSignature('CASE', refund.command)).not.toBe(manualSupplementSignature('CASE', receipt.command));
  expect(() => savePendingManualSupplement(receipt, null)).toThrow(ManualSupplementStorageError);
  expect(readPendingManualSupplement('CASE')).toEqual(refund);
});
