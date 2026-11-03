import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';
const amount=z.strictObject({amount:z.number().int().nonnegative()});
const candidate=z.strictObject({status:z.enum(['exact','overage','partial','review_required']),payment_stage:z.enum(['deposit','first','second','adjustment']).nullable(),bank_total:amount,obligation_total:amount,overage_amount:amount,allocations:z.array(z.strictObject({bank_fact_identity:z.string(),obligation_identity:z.string(),amount})),blockers:z.array(z.string()),settlement_identity:z.string().regex(/^[a-f0-9]{64}$/)});
const preview=z.strictObject({account_version:z.number().int().nonnegative(),candidate,preview_fingerprint:z.string().regex(/^[a-f0-9]{64}$/)});
const receipt=z.strictObject({case_no:z.string(),account_version:z.number().int().nonnegative(),status:z.enum(['exact','partial','overage']),settlement_identity:z.string().regex(/^[a-f0-9]{64}$/),ledger_entry_count:z.number().int().nonnegative(),allocation_count:z.number().int().nonnegative(),blockers:z.array(z.string())});
const envelope=<T extends z.ZodTypeAny>(data:T)=>z.strictObject({success:z.literal(true),message:z.string(),data,error:z.string().nullable().optional()});
export type ReceiptSelection={payment_stage:null;finance_import_row_ids:number[];obligation_identities:string[]};
export type ReceiptAction='exact'|'partial'|'overage';
export type ReceiptPreview=z.infer<typeof preview>;
export type ReceiptCommand={selection:ReceiptSelection;expected_account_version:number;preview_fingerprint:string;reason:string;key:string;action:ReceiptAction};
function options(signal?:AbortSignal){const token=sessionClient.getToken();if(!token)throw new ApiHttpError(401,'UNAUTHENTICATED','請先登入。');return{token,signal};}
const base=(caseNo:string)=>`/api/v1/orders/${encodeURIComponent(caseNo)}/client-finance/receipt-reconciliation`;
const prefix=(action:ReceiptAction)=>action==='exact'?'':`/${action}`;
export const clientReceiptReconciliationClient={
  async preview(caseNo:string,selection:ReceiptSelection,action:ReceiptAction,signal?:AbortSignal){return decodePayload(envelope(preview),await transport.post(base(caseNo)+prefix(action)+'/preview',selection,options(signal))).data;},
  async apply(caseNo:string,command:ReceiptCommand){const {selection,expected_account_version,preview_fingerprint,reason,key,action}=command;const result=decodePayload(envelope(receipt),await transport.post(base(caseNo)+prefix(action)+'/apply',{...selection,expected_account_version,preview_fingerprint,reason},{...options(),headers:{'Idempotency-Key':key,'X-Correlation-ID':key}})).data;if(result.case_no!==caseNo)throw new ApiDecodeError('核銷結果案件不符。');return result;},
};
