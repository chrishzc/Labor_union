import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const account = z.string().regex(/^99781699[0-9]{6}$/);
const viewSchema = z.strictObject({ case_no: z.string(), imported_virtual_accounts: z.array(account), built_in_virtual_account: account.nullable(), mapping_ids: z.array(z.number().int().positive()) });
const receiptSchema = z.strictObject({ case_no: z.string(), before: z.array(account), virtual_account: account });
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.null() });
export type CaseVirtualAccountView = z.infer<typeof viewSchema>;
export interface CaseVirtualAccountCommand { case_no: string; virtual_account: string; expected_mapping_ids: number[] }
const token = () => {
  const value = sessionClient.getToken();
  if (!value) throw new Error('請先登入管理後台。');
  return value;
};
const path = (caseNo: string) => `/api/v1/admin/client-finance/cases/${encodeURIComponent(caseNo)}/virtual-account`;
const forCase = <T extends { case_no: string }>(value: T, caseNo: string): T => {
  if (value.case_no !== caseNo) throw new Error('虛擬帳號回應的案件不一致。');
  return value;
};

export const caseVirtualAccountClient = {
  async query(caseNo: string): Promise<CaseVirtualAccountView> {
    return forCase(decodePayload(envelope(viewSchema), await transport.get(path(caseNo), { token: token() })).data, caseNo);
  },
  async apply(command: CaseVirtualAccountCommand, key: string) {
    const raw = await transport.post(`${path(command.case_no)}/apply`, {
      virtual_account: command.virtual_account, expected_mapping_ids: command.expected_mapping_ids,
    }, { token: token(), headers: { 'Idempotency-Key': key } });
    const receipt = forCase(decodePayload(envelope(receiptSchema), raw).data, command.case_no);
    if (receipt.virtual_account !== command.virtual_account) throw new Error('儲存收據與送出內容不一致。');
    return receipt;
  },
};
