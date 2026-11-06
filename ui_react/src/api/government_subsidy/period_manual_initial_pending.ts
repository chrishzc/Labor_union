/** Same-tab journal for one unresolved first government receipt; never stores credentials. */
import {z} from 'zod';
import {governmentManualInitialCommandSchema} from './period_reconciliation_client';

export const governmentManualInitialStorageKey='government-period:manual-initial-receipt';
const pendingSchema=z.strictObject({version:z.literal(1),actorId:z.number().int().positive().safe(),command:governmentManualInitialCommandSchema});
export type PendingGovernmentManualInitial=z.infer<typeof pendingSchema>;
export class GovernmentManualInitialStorageError extends Error {
  constructor(message='無法安全讀取或保留原首次政府實收，請重新讀取補登狀態，勿另建一筆。'){super(message);}
}
const same=(a:PendingGovernmentManualInitial,b:PendingGovernmentManualInitial)=>JSON.stringify(a)===JSON.stringify(b);
export function readPendingGovernmentManualInitial():PendingGovernmentManualInitial|null{
  try{
    const raw=window.sessionStorage.getItem(governmentManualInitialStorageKey);
    return raw===null?null:pendingSchema.parse(JSON.parse(raw));
  }catch{throw new GovernmentManualInitialStorageError();}
}
export function savePendingGovernmentManualInitial(next:PendingGovernmentManualInitial,expected:PendingGovernmentManualInitial|null):void{
  try{
    const parsed=pendingSchema.parse(next),current=readPendingGovernmentManualInitial();
    if(current&&(!expected||!same(current,pendingSchema.parse(expected))))throw new GovernmentManualInitialStorageError();
    const raw=JSON.stringify(parsed);
    window.sessionStorage.setItem(governmentManualInitialStorageKey,raw);
    if(window.sessionStorage.getItem(governmentManualInitialStorageKey)!==raw)throw new GovernmentManualInitialStorageError();
  }catch{throw new GovernmentManualInitialStorageError();}
}
export function clearPendingGovernmentManualInitial(expected:PendingGovernmentManualInitial):void{
  try{
    const current=readPendingGovernmentManualInitial();
    if(current&&!same(current,pendingSchema.parse(expected)))throw new GovernmentManualInitialStorageError();
    window.sessionStorage.removeItem(governmentManualInitialStorageKey);
    if(window.sessionStorage.getItem(governmentManualInitialStorageKey)!==null)throw new GovernmentManualInitialStorageError();
  }catch{throw new GovernmentManualInitialStorageError('首次政府實收已回覆，但無法清理原操作；請重新讀取原結果，勿另建一筆。');}
}
