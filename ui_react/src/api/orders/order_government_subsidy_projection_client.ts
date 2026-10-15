/**
 * Typed GET client for the Order Workbench Government Subsidy side lane.
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

export const GOVERNMENT_SUBSIDY_SUBSTATUS_CODES = [
  'claim_lineage_missing',
  'draft',
  'submitted',
  'approved',
  'partially_paid',
  'paid',
  'pending_review',
  'offset_reserved',
  'offset_applied',
] as const;

export type GovernmentSubsidySubstatusCode =
  typeof GOVERNMENT_SUBSIDY_SUBSTATUS_CODES[number];

const SubstatusSchema = z.enum(GOVERNMENT_SUBSIDY_SUBSTATUS_CODES);
const NonnegativeIntSchema = z.number().int().nonnegative();
const SourceSchema = z.strictObject({
  owner: z.string().min(1),
  identity: z.string().min(1).nullable(),
  version: NonnegativeIntSchema.nullable(),
});
const NoticeSchema = z.strictObject({
  code: z.string().min(1),
  message: z.string(),
});
const ReadActionSchema = z.strictObject({
  action_id: z.string().min(1),
  method: z.literal('GET'),
  path: z.string().min(1),
});

export const OrderGovernmentSubsidyProjectionSchema = z.strictObject({
  case_no: z.string().min(1),
  substatus_code: SubstatusSchema,
  identity_status: z.string().min(1).nullable(),
  source: SourceSchema,
  occurred_at: z.string().min(1).nullable(),
  service_end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
  claim_quarter: z.number().int().min(1).max(4).nullable(),
  claim_application_year: z.number().int().min(1912).nullable(),
  claim_application_month: z.number().int().min(1).max(12).nullable(),
  claim_submitted_at: z.string().min(1).nullable(),
  blockers: z.array(NoticeSchema),
  warnings: z.array(NoticeSchema),
  available_read_actions: z.array(ReadActionSchema),
  claim_batch_id: z.number().int().positive().nullable(),
  claim_item_count: NonnegativeIntSchema,
  claimed_hours: NonnegativeIntSchema,
  unit_price_ntd: NonnegativeIntSchema.nullable(),
  requested_amount_ntd: NonnegativeIntSchema,
  approved_amount_ntd: NonnegativeIntSchema,
  net_allocated_ntd: NonnegativeIntSchema,
  service_end_confirmed: z.boolean(),
  estimated_subsidy_amount_ntd: NonnegativeIntSchema.nullable(),
  estimate_unavailable_reason: z.enum(['eligibility_pending', 'service_volume_pending', 'rate_snapshot_missing', 'amount_not_integer']).nullable(),
  confirmed_approved_amount_ntd: NonnegativeIntSchema.nullable(),
  outstanding_amount_ntd: NonnegativeIntSchema.nullable(),
  overpayment_identity: z.string().min(1).nullable(),
  overpayment_remaining_ntd: NonnegativeIntSchema.nullable(),
});

const CountsSchema = z.strictObject({
  claim_lineage_missing: NonnegativeIntSchema,
  draft: NonnegativeIntSchema,
  submitted: NonnegativeIntSchema,
  approved: NonnegativeIntSchema,
  partially_paid: NonnegativeIntSchema,
  paid: NonnegativeIntSchema,
  pending_review: NonnegativeIntSchema,
  offset_reserved: NonnegativeIntSchema,
  offset_applied: NonnegativeIntSchema,
});

export const OrderGovernmentSubsidyProjectionPageSchema = z.strictObject({
  items: z.array(OrderGovernmentSubsidyProjectionSchema),
  substatus_counts: CountsSchema,
  next_cursor: z.string().min(1).nullable(),
  etag: z.string().regex(/^[0-9a-f]{64}$/),
});

export type OrderGovernmentSubsidyProjection =
  z.infer<typeof OrderGovernmentSubsidyProjectionSchema>;
export type OrderGovernmentSubsidyProjectionPage =
  z.infer<typeof OrderGovernmentSubsidyProjectionPageSchema>;

export interface OrderGovernmentSubsidyProjectionQueryParams {
  page_size?: number;
  after_case_no?: string;
  case_no_search?: string;
  substatus_code?: GovernmentSubsidySubstatusCode;
}

export interface OrderGovernmentSubsidyProjectionQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  headers?: Record<string, string>;
  timeoutMs?: number;
  baseUrl?: string;
}

const ParamsSchema = z.strictObject({
  page_size: z.number().int().min(1).max(200).optional(),
  after_case_no: z.string().trim().min(1).max(50).optional(),
  case_no_search: z.string().trim().min(1).max(50).optional(),
  substatus_code: SubstatusSchema.optional(),
});

function requestOptions(
  options?: OrderGovernmentSubsidyProjectionQueryOptions,
): RequestOptions {
  return {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    timeoutMs: options?.timeoutMs,
    baseUrl: options?.baseUrl,
    headers: options?.headers,
  };
}

function decodeEnvelope(raw: unknown): OrderGovernmentSubsidyProjectionPage {
  const envelope = decodePayload(
    z.strictObject({
      success: z.boolean(),
      message: z.string(),
      data: OrderGovernmentSubsidyProjectionPageSchema,
      error: z.string().nullable(),
    }),
    raw,
  );
  if (!envelope.success) {
    throw new ApiHttpError(
      400,
      'ORDER_GOVERNMENT_SUBSIDY_PROJECTION_BUSINESS_ERROR',
      envelope.error ?? envelope.message,
      false,
      raw,
    );
  }
  return envelope.data;
}

export async function getOrderGovernmentSubsidyProjections(
  params: OrderGovernmentSubsidyProjectionQueryParams = {},
  options?: OrderGovernmentSubsidyProjectionQueryOptions,
): Promise<OrderGovernmentSubsidyProjectionPage> {
  const parsed = ParamsSchema.parse(params);
  const query: NonNullable<RequestOptions['params']> = {};
  if (parsed.page_size !== undefined) query.page_size = parsed.page_size;
  if (parsed.after_case_no !== undefined) query.after_case_no = parsed.after_case_no;
  if (parsed.case_no_search !== undefined) query.case_no_search = parsed.case_no_search;
  if (parsed.substatus_code !== undefined) query.substatus_code = parsed.substatus_code;

  const raw = await transport.get('/api/orders/government-subsidy-projections', {
    ...requestOptions(options),
    params: query,
  });
  return decodeEnvelope(raw);
}

export const orderGovernmentSubsidyProjectionClient = {
  getProjections: getOrderGovernmentSubsidyProjections,
  async queryAll(params: Omit<OrderGovernmentSubsidyProjectionQueryParams, 'after_case_no' | 'page_size'> = {}, options?: OrderGovernmentSubsidyProjectionQueryOptions): Promise<OrderGovernmentSubsidyProjection[]> {
    const items: OrderGovernmentSubsidyProjection[] = [];
    const identities = new Set<string>();
    let cursor: string | undefined;
    do {
      options?.signal?.throwIfAborted();
      const page = await getOrderGovernmentSubsidyProjections({ ...params, page_size: 200, after_case_no: cursor }, options);
      for (const row of page.items) {
        if (identities.has(row.case_no) || (cursor && row.case_no <= cursor)) throw new Error('補助查詢案件重複或順序異常。');
        identities.add(row.case_no); items.push(row);
      }
      if (page.next_cursor && ((cursor && page.next_cursor <= cursor) || page.items.length === 0 || page.items.some(row => row.case_no > page.next_cursor!))) throw new Error('補助查詢游標異常。');
      cursor = page.next_cursor ?? undefined;
    } while (cursor);
    options?.signal?.throwIfAborted();
    return items;
  },
};
