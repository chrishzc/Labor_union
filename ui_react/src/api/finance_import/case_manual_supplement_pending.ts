/** Same-tab recovery journal for this existing manual-supplement command only. */
import { z } from 'zod';
import type { CaseManualSupplementCommand } from './finance_accounting_client';

const commandSchema = z.strictObject({
  bank: z.enum(['sinopac', 'taishin']),
  direction: z.enum(['client_receipt', 'staff_salary', 'client_refund', 'government_subsidy']),
  target_item: z.string().min(1).max(191).refine(value => value.trim() === value),
  amount_ntd: z.union([z.number().int().positive().safe(), z.string().regex(/^[1-9][0-9]*$/)]),
  transaction_date: z.string().regex(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/).refine(value => {
    const time = Date.parse(`${value}T00:00:00Z`);
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
  }),
  reason: z.string().max(500).nullable().optional(),
  allow_overage_disposition: z.boolean(),
}).refine(value => !value.allow_overage_disposition
  || value.direction === 'client_receipt' || value.direction === 'client_refund');
const pendingSchema = z.strictObject({
  version: z.literal(1), actorId: z.number().int().positive().safe(),
  caseNo: z.string().min(1).max(191), key: z.string().min(1).max(191), command: commandSchema,
});
export type PendingManualSupplement = z.infer<typeof pendingSchema>;
export const manualSupplementStorageKey = (caseNo: string) => `finance-manual-supplement:${caseNo}`;

export class ManualSupplementStorageError extends Error {
  constructor(message = '無法安全讀取或保留原補登操作，請重新讀取補登狀態，勿另建一筆。') { super(message); }
}

export function manualSupplementSignature(caseNo: string, command: CaseManualSupplementCommand): string {
  return JSON.stringify({ case_no: caseNo, ...commandSchema.parse(command) });
}

export function readPendingManualSupplement(caseNo: string): PendingManualSupplement | null {
  try {
    const raw = window.sessionStorage.getItem(manualSupplementStorageKey(caseNo));
    if (raw === null) return null;
    const value = pendingSchema.parse(JSON.parse(raw));
    if (value.caseNo !== caseNo) throw new Error('scope mismatch');
    return value;
  } catch { throw new ManualSupplementStorageError(); }
}

function same(left: PendingManualSupplement, right: PendingManualSupplement): boolean {
  return left.actorId === right.actorId && left.caseNo === right.caseNo && left.key === right.key
    && manualSupplementSignature(left.caseNo, left.command) === manualSupplementSignature(right.caseNo, right.command);
}

export function savePendingManualSupplement(next: PendingManualSupplement, expected: PendingManualSupplement | null): void {
  try {
    const value = pendingSchema.parse(next);
    const current = readPendingManualSupplement(value.caseNo);
    if (current && (!expected || !same(current, expected))) throw new ManualSupplementStorageError();
    const raw = JSON.stringify(value);
    window.sessionStorage.setItem(manualSupplementStorageKey(value.caseNo), raw);
    if (window.sessionStorage.getItem(manualSupplementStorageKey(value.caseNo)) !== raw) throw new ManualSupplementStorageError();
  } catch { throw new ManualSupplementStorageError(); }
}

export function clearPendingManualSupplement(expected: PendingManualSupplement): void {
  try {
    const current = readPendingManualSupplement(expected.caseNo);
    if (current && !same(current, expected)) throw new ManualSupplementStorageError();
    window.sessionStorage.removeItem(manualSupplementStorageKey(expected.caseNo));
    if (window.sessionStorage.getItem(manualSupplementStorageKey(expected.caseNo)) !== null) throw new ManualSupplementStorageError();
  } catch { throw new ManualSupplementStorageError('補登已完成，但無法清理原操作紀錄。請重新讀取補登狀態，勿重建補登。'); }
}
