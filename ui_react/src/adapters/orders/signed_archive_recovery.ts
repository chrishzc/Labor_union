import { z } from 'zod';

const SignedArchiveRecoverySchema = z.strictObject({
  caseNo: z.string().min(1).max(50),
  actorId: z.number().int().positive(),
  idempotencyKey: z.string().regex(/^contract-external\.signed-archive:[0-9a-f]{32}$/),
});

export type SignedArchiveRecovery = z.infer<typeof SignedArchiveRecoverySchema>;

function storageKey(caseNo: string): string {
  return `orders:signed-archive:${caseNo}`;
}

function read(caseNo: string): SignedArchiveRecovery | null {
  const value = window.sessionStorage.getItem(storageKey(caseNo));
  if (value === null) return null;
  const decoded: unknown = JSON.parse(value);
  const recovery = SignedArchiveRecoverySchema.parse(decoded);
  if (recovery.caseNo !== caseNo) throw new Error('Signed archive recovery case mismatch');
  return recovery;
}

export const signedArchiveRecovery = {
  load(caseNo: string, actorId: number | null): SignedArchiveRecovery | null {
    const recovery = read(caseNo);
    if (recovery !== null && recovery.actorId !== actorId) {
      throw new Error('Signed archive recovery belongs to a different actor');
    }
    return recovery;
  },
  start(recovery: SignedArchiveRecovery): void {
    if (read(recovery.caseNo) !== null) throw new Error('Signed archive recovery already exists');
    window.sessionStorage.setItem(storageKey(recovery.caseNo), JSON.stringify(recovery));
  },
  clear(recovery: SignedArchiveRecovery): boolean {
    try {
      const current = read(recovery.caseNo);
      if (current === null || current.actorId !== recovery.actorId || current.idempotencyKey !== recovery.idempotencyKey) {
        return false;
      }
      window.sessionStorage.removeItem(storageKey(recovery.caseNo));
      return true;
    } catch {
      return false;
    }
  },
};
