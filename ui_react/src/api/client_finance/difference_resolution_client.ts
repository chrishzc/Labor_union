import {z} from 'zod';
import {transport} from '../shared/transport';
import {sessionClient} from '../auth/session_client';
const integer=z.number().int();
const clientItem=z.strictObject({identity:z.string(),label:z.string(),kind:z.string(),direction:z.string(),expected_ntd:integer,actual_ntd:integer,remaining_ntd:integer,noncash_ntd:integer,mode:z.enum(['automatic','manual']),computed_ntd:integer,effective_ntd:integer,status:z.string(),options:z.array(z.string()),service_reduction_ntd:integer.optional(),effective_charge_ntd:integer.nullable().optional()});
const event=z.strictObject({identity:z.string(),target_identity:z.string(),action:z.string(),amount_ntd:integer,reason:z.string(),actor:z.string(),confirmed_on:z.string(),before_ntd:integer.nullable().optional(),after_ntd:integer.nullable().optional(),computed_ntd:integer.nullable().optional()});
const clientView=z.strictObject({case_no:z.string(),version:integer,items:z.array(clientItem),events:z.array(event)});
const payrollView=z.strictObject({case_no:z.string(),version:integer,items:z.array(z.strictObject({identity:z.string(),party:z.string(),mode:z.enum(['automatic','manual']),computed_ntd:integer,effective_ntd:integer,actual_ntd:integer,remaining_ntd:integer})),events:z.array(z.strictObject({identity:z.string(),target_identity:z.string(),action:z.string(),before_ntd:integer,after_ntd:integer,computed_ntd:integer,reason:z.string(),actor:z.string(),confirmed_on:z.string()}))});
const staffView=z.strictObject({case_no:z.string(),items:z.array(z.strictObject({identity:z.string(),staff_id:integer,party:z.string(),original_ntd:integer,remaining_ntd:integer,noncash_ntd:integer,version:integer,status:z.string(),related_cases:z.array(z.string())})),events:z.array(event)});
export type ClientDifferenceView=z.infer<typeof clientView>;
export type PayrollAmountView=z.infer<typeof payrollView>;
export type StaffRecoveryView=z.infer<typeof staffView>;
export type DifferenceCommand={identity:string;action:string;amount_ntd:number|null;reason:string;expected_version:number;key:string};
function options(signal?:AbortSignal){return {token:sessionClient.getToken(),signal};}
const path=(caseNo:string,owner:'client'|'payroll'|'staff')=>`/api/v1/orders/${encodeURIComponent(caseNo)}/${{client:'client-finance/differences',payroll:'payroll/amount-corrections',staff:'staff-payables/recovery-dispositions'}[owner]}`;
export const differenceResolutionClient={
  async client(caseNo:string,signal?:AbortSignal){return clientView.parse((await transport.get<{data:unknown}>(path(caseNo,'client'),options(signal))).data);},
  async payroll(caseNo:string,signal?:AbortSignal){return payrollView.parse((await transport.get<{data:unknown}>(path(caseNo,'payroll'),options(signal))).data);},
  async staff(caseNo:string,signal?:AbortSignal){return staffView.parse((await transport.get<{data:unknown}>(path(caseNo,'staff'),options(signal))).data);},
  async apply(caseNo:string,owner:'client'|'payroll'|'staff',command:DifferenceCommand){
    const data=(await transport.post<{data:unknown}>(path(caseNo,owner),command,options())).data;
    return owner==='client'?clientView.parse(data):owner==='payroll'?payrollView.parse(data):staffView.parse(data);
  },
};
