/**
 * File: order_core_stage_projection_client.ts
 * Description: 以 typed GET query 取得待辦看板 Beta 十三核心階段投影。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import {
  CORE_STAGE_BRANCH_TYPES,
  CORE_STAGE_CODES,
  CORE_STAGE_SUBSTATUS_CODES,
  HISTORICAL_LIFECYCLE_FACETS,
  OrderCoreStageTimelinePageSchema,
  substatusBelongsToStage,
  type CoreStageBranchType,
  type CoreStageCode,
  type CoreStageSubstatusCode,
  type HistoricalLifecycleFacet,
  type OrderCoreStageTimelinePage,
} from './order_core_stage_projection_schemas';

export interface OrderCoreStageProjectionQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  ifNoneMatch?: string;
  baseUrl?: string;
}

export interface OrderCoreStageProjectionQueryParams {
  page_size?: number;
  after_case_no?: string;
  lifecycle_scope?: 'all' | 'unfinished';
  stage?: CoreStageCode;
  substatus_code?: CoreStageSubstatusCode;
  case_no_search?: string;
  blocker_only?: boolean;
  warning_only?: boolean;
  branch_type?: CoreStageBranchType;
  historical_lifecycle?: HistoricalLifecycleFacet;
}

export interface OrderCoreStageProjectionClient {
  getCoreStageTimelines(
    params?: OrderCoreStageProjectionQueryParams,
    options?: OrderCoreStageProjectionQueryOptions,
  ): Promise<OrderCoreStageTimelinePage>;
}

const ParamsSchema = z.strictObject({
  page_size: z.number().int().min(1).max(200).optional(),
  after_case_no: z.string().trim().min(1).max(50).optional(),
  lifecycle_scope: z.enum(['all', 'unfinished']).optional(),
  stage: z.enum(CORE_STAGE_CODES).optional(),
  substatus_code: z.enum(CORE_STAGE_SUBSTATUS_CODES).optional(),
  case_no_search: z.string().trim().min(1).max(50).optional(),
  blocker_only: z.boolean().optional(),
  warning_only: z.boolean().optional(),
  branch_type: z.enum(CORE_STAGE_BRANCH_TYPES).optional(),
  historical_lifecycle: z.enum(HISTORICAL_LIFECYCLE_FACETS).optional(),
}).superRefine((params, context) => {
  if (params.substatus_code !== undefined && params.stage === undefined) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['stage'],
      message: '指定 substatus_code 時必須同時指定 stage',
    });
  } else if (
    params.stage !== undefined
    && params.substatus_code !== undefined
    && !substatusBelongsToStage(params.stage, params.substatus_code)
  ) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['substatus_code'],
      message: 'substatus_code 不屬於指定 stage',
    });
  }
  if (params.historical_lifecycle !== undefined && params.branch_type !== 'historical') {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['historical_lifecycle'],
      message: 'historical_lifecycle 只允許 historical branch',
    });
  }
});

function requestOptions(options?: OrderCoreStageProjectionQueryOptions): RequestOptions {
  const headers = { ...(options?.headers ?? {}) };
  if (options?.ifNoneMatch) headers['If-None-Match'] = options.ifNoneMatch;
  return {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers,
  };
}

function decodeCoreStageEnvelope(raw: unknown): OrderCoreStageTimelinePage {
  const envelope = decodePayload(
    z.strictObject({
      success: z.boolean(),
      message: z.string(),
      data: OrderCoreStageTimelinePageSchema,
      error: z.string().nullable(),
    }),
    raw,
  );
  if (!envelope.success) {
    throw new ApiHttpError(
      400,
      'ORDERS_CORE_STAGE_PROJECTION_BUSINESS_ERROR',
      envelope.error ?? envelope.message,
      false,
      raw,
    );
  }
  return envelope.data;
}

export async function getOrderCoreStageTimelines(
  params: OrderCoreStageProjectionQueryParams = {},
  options?: OrderCoreStageProjectionQueryOptions,
): Promise<OrderCoreStageTimelinePage> {
  const parsed = ParamsSchema.parse(params);
  const query: NonNullable<RequestOptions['params']> = {};
  if (parsed.page_size !== undefined) query.page_size = parsed.page_size;
  if (parsed.after_case_no !== undefined) query.after_case_no = parsed.after_case_no;
  if (parsed.lifecycle_scope !== undefined) query.lifecycle_scope = parsed.lifecycle_scope;
  if (parsed.stage !== undefined) query.stage = parsed.stage;
  if (parsed.substatus_code !== undefined) query.substatus_code = parsed.substatus_code;
  if (parsed.case_no_search !== undefined) query.case_no_search = parsed.case_no_search;
  if (parsed.blocker_only !== undefined) query.blocker_only = parsed.blocker_only;
  if (parsed.warning_only !== undefined) query.warning_only = parsed.warning_only;
  if (parsed.branch_type !== undefined) query.branch_type = parsed.branch_type;
  if (parsed.historical_lifecycle !== undefined) query.historical_lifecycle = parsed.historical_lifecycle;

  const raw = await transport.get('/api/orders/core-stage-timelines', {
    ...requestOptions(options),
    params: query,
  });
  return decodeCoreStageEnvelope(raw);
}

class DefaultOrderCoreStageProjectionClient implements OrderCoreStageProjectionClient {
  private readonly defaults?: OrderCoreStageProjectionQueryOptions;

  constructor(defaults?: OrderCoreStageProjectionQueryOptions) {
    this.defaults = defaults;
  }

  getCoreStageTimelines(
    params?: OrderCoreStageProjectionQueryParams,
    options?: OrderCoreStageProjectionQueryOptions,
  ) {
    return getOrderCoreStageTimelines(params, {
      ...this.defaults,
      ...options,
      headers: { ...(this.defaults?.headers ?? {}), ...(options?.headers ?? {}) },
    });
  }
}

export function createOrderCoreStageProjectionClient(
  defaults?: OrderCoreStageProjectionQueryOptions,
): OrderCoreStageProjectionClient {
  return new DefaultOrderCoreStageProjectionClient(defaults);
}

export const orderCoreStageProjectionClient: OrderCoreStageProjectionClient =
  createOrderCoreStageProjectionClient();
