/**
 * File: account_directory_client.ts
 * Description: 以每次最新記憶體 Bearer 查詢 root-only 帳號清冊。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import {
  AccountDirectoryResponseSchema,
  type AccountDirectoryItem,
} from './account_directory_schemas';
import {
  AccountDirectoryError,
  AccountDirectoryUnauthenticatedError,
  mapAccountDirectoryError,
} from './account_directory_errors';

export type AccountDirectoryQueryOptions = Omit<
  RequestOptions,
  'method' | 'body' | 'token' | 'params'
>;

export interface AccountDirectoryClient {
  query(options?: AccountDirectoryQueryOptions): Promise<AccountDirectoryItem[]>;
}

function requestOptions(options?: AccountDirectoryQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new AccountDirectoryUnauthenticatedError();
  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }
  return { ...options, headers, token };
}

export async function queryAccountDirectory(
  options?: AccountDirectoryQueryOptions,
): Promise<AccountDirectoryItem[]> {
  try {
    const raw = await transport.get<unknown>(
      '/api/v1/admin/accounts',
      requestOptions(options),
    );
    const decoded = AccountDirectoryResponseSchema.safeParse(raw);
    if (!decoded.success) {
      throw new ApiDecodeError(
        '帳號清冊回應結構不符 strict contract。',
        decoded.error.issues.map((issue) => ({
          path: issue.path.join('.') || '(root)',
          message: issue.message,
          code: issue.code,
        })),
        raw,
      );
    }
    if (!decoded.data.success) {
      throw new AccountDirectoryError(
        'ACCOUNT_DIRECTORY_INVALID',
        decoded.data.error ?? decoded.data.message,
      );
    }
    return decoded.data.data;
  } catch (error) {
    throw mapAccountDirectoryError(error);
  }
}

export function createAccountDirectoryClient(): AccountDirectoryClient {
  return { query: queryAccountDirectory };
}

export const accountDirectoryClient = createAccountDirectoryClient();
