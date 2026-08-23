/**
 * File: account_center_client.ts
 * Description: Root Account Center mutation client，使用 fresh Bearer 與 strict typed receipt。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  AccountCreateCommandSchema,
  AccountEnabledCommandSchema,
  AccountMutationResponseSchema,
  AccountPasswordResetCommandSchema,
  AccountSecurityCommandSchema,
  type AccountCreateCommand,
  type AccountEnabledCommand,
  type AccountMutationReceipt,
  type AccountPasswordResetCommand,
  type AccountSecurityCommand,
} from './account_center_schemas';

type CommandOptions = Omit<RequestOptions, 'method' | 'body' | 'token' | 'params'>;

function options(value?: CommandOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new Error('ACCOUNT_CENTER_UNAUTHENTICATED');
  return { ...value, token };
}

async function command(
  method: 'POST' | 'PATCH',
  path: string,
  body: unknown,
  requestOptions?: CommandOptions,
): Promise<AccountMutationReceipt> {
  const raw = await transport.request<unknown>(path, { ...options(requestOptions), method, body });
  const decoded = AccountMutationResponseSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiDecodeError(
      'Account Center receipt 不符 strict contract。',
      decoded.error.issues.map((issue) => ({
        path: issue.path.join('.') || '(root)', message: issue.message, code: issue.code,
      })),
      raw,
    );
  }
  return decoded.data.data;
}

export const accountCenterClient = {
  create(input: AccountCreateCommand, requestOptions?: CommandOptions) {
    return command('POST', '/api/v1/admin/accounts', AccountCreateCommandSchema.parse(input), requestOptions);
  },
  setEnabled(accountId: number, input: AccountEnabledCommand, requestOptions?: CommandOptions) {
    return command('PATCH', `/api/v1/admin/accounts/${accountId}/enabled`, AccountEnabledCommandSchema.parse(input), requestOptions);
  },
  resetPassword(accountId: number, input: AccountPasswordResetCommand, requestOptions?: CommandOptions) {
    return command('POST', `/api/v1/admin/accounts/${accountId}/password-reset`, AccountPasswordResetCommandSchema.parse(input), requestOptions);
  },
  resetMfa(accountId: number, input: AccountSecurityCommand, requestOptions?: CommandOptions) {
    return command('POST', `/api/v1/admin/accounts/${accountId}/mfa-reset`, AccountSecurityCommandSchema.parse(input), requestOptions);
  },
  revokeSessions(accountId: number, input: AccountSecurityCommand, requestOptions?: CommandOptions) {
    return command('POST', `/api/v1/admin/accounts/${accountId}/sessions/revoke`, AccountSecurityCommandSchema.parse(input), requestOptions);
  },
};
