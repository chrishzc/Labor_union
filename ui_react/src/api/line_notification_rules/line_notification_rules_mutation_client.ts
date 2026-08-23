/**
 * File: line_notification_rules_mutation_client.ts
 * Description: 以 fresh Session 呼叫通知規則 Preview、Save、Delete，並嚴格驗證雙階段 mutation 契約。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  LineNotificationRulesMutationRequestError,
  LineNotificationRulesMutationUnauthenticatedError,
  mapLineNotificationRulesMutationError,
} from './line_notification_rules_mutation_errors';
import {
  DeleteLineNotificationRuleRequestSchema,
  DeleteLineNotificationRuleResponseSchema,
  PreviewLineNotificationRulesRequestSchema,
  PreviewLineNotificationRulesResponseSchema,
  SaveLineNotificationRulesRequestSchema,
  SaveLineNotificationRulesResponseSchema,
  type DeleteLineNotificationRuleReceipt,
  type DeleteLineNotificationRuleRequest,
  type PreviewLineNotificationRules,
  type PreviewLineNotificationRulesRequest,
  type SaveLineNotificationRulesReceipt,
  type SaveLineNotificationRulesRequest,
} from './line_notification_rules_mutation_schemas';

export interface LineNotificationRulesMutationRequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export interface LineNotificationRulesMutationClient {
  preview(
    payload: PreviewLineNotificationRulesRequest,
    options?: LineNotificationRulesMutationRequestOptions
  ): Promise<PreviewLineNotificationRules>;
  save(
    payload: SaveLineNotificationRulesRequest,
    options?: LineNotificationRulesMutationRequestOptions
  ): Promise<SaveLineNotificationRulesReceipt>;
  deleteRule(
    ruleId: string,
    payload: DeleteLineNotificationRuleRequest,
    options?: LineNotificationRulesMutationRequestOptions
  ): Promise<DeleteLineNotificationRuleReceipt>;
}

function requestOptions(
  options?: LineNotificationRulesMutationRequestOptions
): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LineNotificationRulesMutationUnauthenticatedError();
  return {
    token,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
  };
}

function parseRequest<TData>(schema: z.ZodType<TData>, payload: unknown): TData {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new LineNotificationRulesMutationRequestError(
      parsed.error.issues.map((issue) => issue.message).join('; ')
    );
  }
  return parsed.data;
}

function rulePath(ruleId: string): string {
  const parsed = z.string().regex(/^[a-z][a-z0-9_]{0,63}$/).safeParse(ruleId);
  if (!parsed.success) {
    throw new LineNotificationRulesMutationRequestError(
      '通知規則 id 必須符合小寫識別值格式。'
    );
  }
  return `/api/v1/line/notification-rules/${encodeURIComponent(parsed.data)}`;
}

async function call<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw mapLineNotificationRulesMutationError(error);
  }
}

export function previewLineNotificationRules(
  payload: PreviewLineNotificationRulesRequest,
  options?: LineNotificationRulesMutationRequestOptions
): Promise<PreviewLineNotificationRules> {
  return call(async () => {
    const validPayload = parseRequest(PreviewLineNotificationRulesRequestSchema, payload);
    const raw = await transport.post<object>(
      '/api/v1/line/notification-rules/preview',
      validPayload,
      requestOptions(options)
    );
    return decodePayload(PreviewLineNotificationRulesResponseSchema, raw).data;
  });
}

export function saveLineNotificationRules(
  payload: SaveLineNotificationRulesRequest,
  options?: LineNotificationRulesMutationRequestOptions
): Promise<SaveLineNotificationRulesReceipt> {
  return call(async () => {
    const validPayload = parseRequest(SaveLineNotificationRulesRequestSchema, {
      ...payload,
      reason: typeof payload.reason === 'string' ? payload.reason.trim() : payload.reason,
    });
    const raw = await transport.put<object>(
      '/api/v1/line/notification-rules',
      validPayload,
      requestOptions(options)
    );
    return decodePayload(SaveLineNotificationRulesResponseSchema, raw).data;
  });
}

export function deleteLineNotificationRule(
  ruleId: string,
  payload: DeleteLineNotificationRuleRequest,
  options?: LineNotificationRulesMutationRequestOptions
): Promise<DeleteLineNotificationRuleReceipt> {
  return call(async () => {
    const path = rulePath(ruleId);
    const validPayload = parseRequest(DeleteLineNotificationRuleRequestSchema, {
      ...payload,
      reason: typeof payload.reason === 'string' ? payload.reason.trim() : payload.reason,
    });
    const raw = await transport.request<object>(path, {
      ...requestOptions(options),
      method: 'DELETE',
      body: validPayload,
    });
    return decodePayload(DeleteLineNotificationRuleResponseSchema, raw).data;
  });
}

export const lineNotificationRulesMutationClient: LineNotificationRulesMutationClient = {
  preview: previewLineNotificationRules,
  save: saveLineNotificationRules,
  deleteRule: deleteLineNotificationRule,
};
