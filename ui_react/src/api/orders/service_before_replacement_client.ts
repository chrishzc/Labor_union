/**
 * File: service_before_replacement_client.ts
 * Description: 嚴格解碼服務前換人 Query／Preview／Apply，並保留結果未明時的同鍵對帳命令。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../shared/typed_errors';

export const ServiceBeforeReplacementScenarioSchema = z.enum(['R-01', 'R-02', 'R-03', 'R-04', 'R-07']);
export const ServiceBeforeReplacementErrorCodeSchema = z.enum([
  'replacement_blocked', 'replacement_actual_service_exists', 'replacement_version_conflict',
  'replacement_identity_drift', 'replacement_reason_evidence_drift', 'replacement_preview_stale',
  'replacement_idempotency_mismatch', 'replacement_request_invalid', 'replacement_scenario_invalid',
  'replacement_scenario_required', 'replacement_service_proof_unavailable', 'replacement_facts_not_found',
  'replacement_source_unavailable', 'replacement_outcome_unknown', 'replacement_internal_error',
]);
const OutcomeSchema = z.enum(['ready', 'blocked', 'substitution_referral']);
const ResumeStepSchema = z.enum(['step_2', 'step_3', 'step_4']);
const ProjectionKindSchema = z.enum(['successor_matching', 'matching_only_zero_service']);
const FingerprintSchema = z.string().regex(/^[0-9a-f]{64}$/);
const RootKindSchema = z.enum([
  'candidate_binding', 'willingness', 'matching_plan', 'matching_segment',
  'matching_reply', 'recipient_confirmation', 'waiting_lock', 'commitment',
  'signback', 'recipient_binding', 'effective_generation', 'assignment',
  'official_schedule', 'successor_round',
]);

const ReplacementRootSchema = z.strictObject({
  kind: RootKindSchema,
  root_id: z.string().min(1).max(191),
  case_no: z.string().min(1).max(50),
  current: z.boolean(),
  caregiver_bound: z.boolean(),
});

const RootDeltaSchema = z.strictObject({
  retained: z.array(ReplacementRootSchema),
  superseded: z.array(ReplacementRootSchema),
  created: z.array(ReplacementRootSchema),
});

const ActualServiceProofSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  service_dates: z.array(z.string().date()),
  source_identity: z.string().min(1).max(191),
  source_version: z.number().int().nonnegative(),
  fingerprint: FingerprintSchema,
});

const CandidatePoolReuseProofSchema = z.strictObject({
  pool_identity: z.string().min(1).max(191),
  round_identity: z.string().min(1).max(191),
  coverage_version: z.number().int().nonnegative(),
  availability_version: z.number().int().nonnegative(),
  willingness_version: z.number().int().nonnegative(),
  fingerprint: FingerprintSchema,
  same_round: z.boolean(),
  coverage_valid: z.boolean(),
  availability_valid: z.boolean(),
  willingness_valid: z.boolean(),
  fresh: z.boolean(),
  accepted_candidate: z.boolean(),
  case_no: z.string().min(1).max(50),
  successor_round_identity: z.string().min(1).max(191),
  generation_version: z.number().int().nonnegative(),
  event_version: z.number().int().nonnegative(),
  candidate_identity: z.string().min(1).max(191),
});

const SuccessorRoundSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  round_identity: z.string().min(1).max(191),
  generation_identity: z.string().min(1).max(191),
  event_identity: z.string().min(1).max(191),
  generation_version: z.number().int().nonnegative(),
  event_version: z.number().int().nonnegative(),
  candidate_count: z.number().int().nonnegative(),
  zero_candidate_disposition: z.string().max(500).nullable(),
  fingerprint: FingerprintSchema,
}).superRefine((value, context) => {
  if ((value.candidate_count === 0) !== (value.zero_candidate_disposition !== null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['zero_candidate_disposition'], message: 'zero-candidate disposition mismatch' });
  }
});

const BaseFactsSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  scenario: ServiceBeforeReplacementScenarioSchema,
  outcome: OutcomeSchema,
  actual_service_day_count: z.number().int().nonnegative(),
  actual_service_dates: z.array(z.string().date()),
  actual_service_proof: ActualServiceProofSchema.nullable(),
  prior_generation_identity: z.string().max(191).nullable(),
  prior_event_identity: z.string().max(191).nullable(),
  prior_aggregate_identity: z.string().max(191).nullable(),
  generation_version: z.number().int().nonnegative(),
  event_version: z.number().int().nonnegative(),
  aggregate_version: z.number().int().nonnegative(),
  impacted_roots: z.array(ReplacementRootSchema),
  retained_roots: z.array(ReplacementRootSchema),
  root_delta: RootDeltaSchema.nullable(),
  candidate_pool_reuse_proof: CandidatePoolReuseProofSchema.nullable(),
  successor_round: SuccessorRoundSchema.nullable(),
  resume_step: ResumeStepSchema,
  blockers: z.array(z.string()),
});

type BaseFacts = z.infer<typeof BaseFactsSchema>;

function rootIds(values: readonly z.infer<typeof ReplacementRootSchema>[]): string[] {
  return values.map((value) => value.root_id);
}

function addBaseFactsIssues(value: BaseFacts, context: z.RefinementCtx): void {
  const canonicalDates = [...new Set(value.actual_service_dates)].sort();
  if (canonicalDates.join('\n') !== value.actual_service_dates.join('\n') || canonicalDates.length !== value.actual_service_day_count) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['actual_service_dates'], message: 'actual service dates/count mismatch' });
  }
  const rootGroups = [value.impacted_roots, value.retained_roots];
  if (rootGroups.some((group) => rootIds(group).join('\n') !== [...new Set(rootIds(group))].sort().join('\n'))) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['impacted_roots'], message: 'root set is not canonical' });
  }
  if (rootGroups.flat().some((root) => root.case_no !== value.case_no)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['impacted_roots'], message: 'cross-case root rejected' });
  }
  const impacted = new Set(rootIds(value.impacted_roots));
  if (rootIds(value.retained_roots).some((identity) => impacted.has(identity))) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['retained_roots'], message: 'root sets overlap' });
  }
  if (value.root_delta) {
    const deltaGroups = [value.root_delta.retained, value.root_delta.superseded, value.root_delta.created];
    const allDeltaIds = deltaGroups.flatMap(rootIds);
    if (deltaGroups.some((group) => rootIds(group).join('\n') !== [...new Set(rootIds(group))].sort().join('\n'))
      || new Set(allDeltaIds).size !== allDeltaIds.length) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['root_delta'], message: 'root delta is not canonical and disjoint' });
    }
    if (deltaGroups.flat().some((root) => root.case_no !== value.case_no)
      || rootIds(value.root_delta.superseded).join('\n') !== rootIds(value.impacted_roots).join('\n')
      || rootIds(value.root_delta.retained).join('\n') !== rootIds(value.retained_roots).join('\n')) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['root_delta'], message: 'root delta does not match owner facts' });
    }
  }
  if (value.actual_service_proof && (value.actual_service_proof.case_no !== value.case_no
    || value.actual_service_proof.service_dates.join('\n') !== value.actual_service_dates.join('\n'))) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['actual_service_proof'], message: 'service proof identity mismatch' });
  }
  if (value.actual_service_day_count > 0 && value.actual_service_proof === null) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['actual_service_proof'], message: 'actual service referral requires proof' });
  }
  if (value.successor_round && (
    value.successor_round.case_no !== value.case_no
    || value.successor_round.generation_version <= value.generation_version
    || value.successor_round.event_version <= value.event_version
  )) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['successor_round'], message: 'successor identity/version mismatch' });
  }
  if (value.candidate_pool_reuse_proof && (
    value.candidate_pool_reuse_proof.case_no !== value.case_no
    || value.candidate_pool_reuse_proof.generation_version !== value.generation_version
    || value.candidate_pool_reuse_proof.event_version !== value.event_version
    || (value.successor_round !== null
      && value.candidate_pool_reuse_proof.successor_round_identity !== value.successor_round.round_identity)
  )) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['candidate_pool_reuse_proof'], message: 'candidate reuse identity/version mismatch' });
  }
  if (value.outcome === 'ready' && (value.blockers.length > 0 || value.root_delta === null || value.actual_service_proof === null)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['outcome'], message: 'ready facts are incomplete' });
  }
  if (value.outcome === 'substitution_referral' && (
    value.actual_service_day_count === 0 || value.root_delta !== null || value.impacted_roots.length > 0
    || value.retained_roots.length > 0 || value.candidate_pool_reuse_proof !== null || value.successor_round !== null
  )) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['outcome'], message: 'referral contains replacement facts' });
  }
}

export const ServiceBeforeReplacementQuerySchema = BaseFactsSchema.superRefine((value, context) => {
  addBaseFactsIssues(value, context);
  if (value.root_delta?.created.length) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['root_delta', 'created'], message: 'query cannot contain created roots' });
  }
});

export const ServiceBeforeReplacementPreviewSchema = BaseFactsSchema.extend({
  replacement_generation_identity: z.string().max(191).nullable(),
  replacement_event_identity: z.string().max(191).nullable(),
  successor_round_identity: z.string().max(191).nullable(),
  expected_generation_version: z.number().int().nonnegative(),
  resulting_generation_version: z.number().int().nonnegative().nullable(),
  expected_event_version: z.number().int().nonnegative(),
  resulting_event_version: z.number().int().nonnegative().nullable(),
  expected_aggregate_version: z.number().int().nonnegative(),
  resulting_aggregate_version: z.number().int().nonnegative().nullable(),
  superseded_roots: z.array(ReplacementRootSchema),
  created_roots: z.array(ReplacementRootSchema),
  preview_fingerprint: FingerprintSchema,
  reason: z.string().min(1).max(500),
  evidence: z.array(z.string().min(1)).min(1).max(20),
  projection_kind: ProjectionKindSchema,
}).superRefine((value, context) => {
  addBaseFactsIssues(value, context);
  if (value.outcome === 'ready') {
    const required = [
      value.prior_generation_identity, value.prior_event_identity, value.prior_aggregate_identity,
      value.replacement_generation_identity, value.replacement_event_identity, value.successor_round_identity,
      value.resulting_generation_version, value.resulting_event_version, value.resulting_aggregate_version,
    ];
    if (required.some((item) => item === null) || value.superseded_roots.length === 0 || value.created_roots.length === 0) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['outcome'], message: 'ready preview lacks replacement identities' });
    }
    if (value.root_delta === null
      || rootIds(value.root_delta.superseded).join('\n') !== rootIds(value.superseded_roots).join('\n')
      || rootIds(value.root_delta.created).join('\n') !== rootIds(value.created_roots).join('\n')) {
      context.addIssue({ code: z.ZodIssueCode.custom, path: ['root_delta'], message: 'preview root delta mismatch' });
    }
  }
  if (value.outcome === 'substitution_referral' && (
    value.replacement_generation_identity !== null || value.replacement_event_identity !== null
    || value.successor_round_identity !== null || value.resulting_generation_version !== null
    || value.resulting_event_version !== null || value.resulting_aggregate_version !== null
    || value.superseded_roots.length > 0 || value.created_roots.length > 0
  )) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['outcome'], message: 'referral contains replacement result' });
  }
});

const ReceiptSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  receipt_identity: z.string().min(1).max(191),
  idempotency_key: z.string().min(1).max(191),
  command_fingerprint: FingerprintSchema,
  preview_fingerprint: FingerprintSchema,
  replacement_generation_identity: z.string().min(1).max(191),
  replacement_event_identity: z.string().min(1).max(191),
  successor_round_identity: z.string().min(1).max(191),
  resulting_generation_version: z.number().int().nonnegative(),
  resulting_event_version: z.number().int().nonnegative(),
  resulting_aggregate_version: z.number().int().nonnegative(),
  outbox_identity: z.string().min(1).max(191),
  retained_root_ids: z.array(z.string().min(1)),
  superseded_root_ids: z.array(z.string().min(1)),
  created_root_ids: z.array(z.string().min(1)),
  retained_root_set_digest: FingerprintSchema,
  retained_root_count: z.number().int().nonnegative(),
  superseded_root_set_digest: FingerprintSchema,
  superseded_root_count: z.number().int().nonnegative(),
  created_root_set_digest: FingerprintSchema,
  created_root_count: z.number().int().nonnegative(),
  matching_package_lineage_id: z.number().int().positive().nullable(),
  matching_event_id: z.number().int().positive().nullable(),
});

const ReadbackSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  generation_identity: z.string().min(1).max(191),
  event_identity: z.string().min(1).max(191),
  successor_round_identity: z.string().min(1).max(191),
  generation_version: z.number().int().nonnegative(),
  event_version: z.number().int().nonnegative(),
  aggregate_version: z.number().int().nonnegative(),
  retained_root_ids: z.array(z.string().min(1)),
  superseded_root_ids: z.array(z.string().min(1)),
  created_root_ids: z.array(z.string().min(1)),
  root_set_digests: z.tuple([FingerprintSchema, FingerprintSchema, FingerprintSchema]),
  root_set_counts: z.tuple([z.number().int().nonnegative(), z.number().int().nonnegative(), z.number().int().nonnegative()]),
  outbox_identity: z.string().min(1).max(191),
  matching_package_lineage_id: z.number().int().positive().nullable(),
  matching_event_id: z.number().int().positive().nullable(),
  complete: z.literal(true),
});

export const ServiceBeforeReplacementApplySchema = z.strictObject({
  status: z.enum(['applied', 'replayed']),
  receipt: ReceiptSchema,
  readback: ReadbackSchema,
}).superRefine((value, context) => {
  const receipt = value.receipt;
  const readback = value.readback;
  const receiptGroups = [receipt.retained_root_ids, receipt.superseded_root_ids, receipt.created_root_ids];
  const readbackGroups = [readback.retained_root_ids, readback.superseded_root_ids, readback.created_root_ids];
  const receiptCounts = [receipt.retained_root_count, receipt.superseded_root_count, receipt.created_root_count];
  if (receiptGroups.some((group) => group.join('\n') !== [...new Set(group)].sort().join('\n'))
    || new Set(receiptGroups.flat()).size !== receiptGroups.flat().length
    || receiptCounts.some((count, index) => count !== receiptGroups[index].length)
    || readback.root_set_counts.some((count, index) => count !== readbackGroups[index].length)
    || JSON.stringify(receiptGroups) !== JSON.stringify(readbackGroups)) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['readback'], message: 'receipt/readback root sets mismatch' });
  }
  if (receipt.case_no !== readback.case_no
    || receipt.replacement_generation_identity !== readback.generation_identity
    || receipt.replacement_event_identity !== readback.event_identity
    || receipt.successor_round_identity !== readback.successor_round_identity
    || receipt.resulting_generation_version !== readback.generation_version
    || receipt.resulting_event_version !== readback.event_version
    || receipt.resulting_aggregate_version !== readback.aggregate_version
    || receipt.outbox_identity !== readback.outbox_identity
    || receipt.matching_package_lineage_id !== readback.matching_package_lineage_id
    || receipt.matching_event_id !== readback.matching_event_id) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['readback'], message: 'receipt/readback mismatch' });
  }
});

const PreviewRequestSchema = z.strictObject({
  scenario: ServiceBeforeReplacementScenarioSchema,
  reason: z.string().min(1).max(500).refine((value) => value === value.trim()),
  evidence: z.array(z.string().min(1)).min(1).max(20),
}).superRefine((value, context) => {
  if (value.evidence.join('\n') !== [...new Set(value.evidence.map((item) => item.trim()).filter(Boolean))].sort().join('\n')) {
    context.addIssue({ code: z.ZodIssueCode.custom, path: ['evidence'], message: 'evidence must be canonical' });
  }
});

const ApplyRequestSchema = PreviewRequestSchema.and(z.strictObject({
  expected_generation_version: z.number().int().nonnegative(),
  expected_event_version: z.number().int().nonnegative(),
  expected_aggregate_version: z.number().int().nonnegative(),
  prior_generation_identity: z.string().min(1).max(191),
  prior_event_identity: z.string().min(1).max(191),
  prior_aggregate_identity: z.string().min(1).max(191),
  preview_fingerprint: FingerprintSchema,
}));

function envelope<T extends z.ZodTypeAny>(data: T) {
  return z.strictObject({ success: z.literal(true), message: z.string().min(1), data, error: z.null() });
}

export type ServiceBeforeReplacementScenario = z.infer<typeof ServiceBeforeReplacementScenarioSchema>;
export type ServiceBeforeReplacementErrorCode = z.infer<typeof ServiceBeforeReplacementErrorCodeSchema>;
export type ServiceBeforeReplacementQuery = z.infer<typeof ServiceBeforeReplacementQuerySchema>;
export type ServiceBeforeReplacementPreview = z.infer<typeof ServiceBeforeReplacementPreviewSchema>;
export type ServiceBeforeReplacementApplyResult = z.infer<typeof ServiceBeforeReplacementApplySchema>;
export type ServiceBeforeReplacementPreviewRequest = z.infer<typeof PreviewRequestSchema>;
export type ServiceBeforeReplacementApplyRequest = z.infer<typeof ApplyRequestSchema>;

export interface ServiceBeforeReplacementCommandIdentity {
  readonly idempotencyKey: string;
  readonly correlationId: string;
}

export interface ServiceBeforeReplacementActorBinding {
  readonly actor: string;
  readonly capabilities: readonly ['orders.historical_review.remediate'];
}

type CanonicalValue = null | boolean | number | string | readonly CanonicalValue[] | { readonly [key: string]: CanonicalValue };

function canonicalJson(value: CanonicalValue): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'number' || typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  const mapping = value as { readonly [key: string]: CanonicalValue };
  return `{${Object.keys(mapping).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(mapping[key])}`).join(',')}}`;
}

async function sha256Text(value: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error('瀏覽器缺少 SHA-256 驗證能力。');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, '0')).join('');
}

async function fingerprintPayload(value: { readonly [key: string]: CanonicalValue }): Promise<string> {
  return sha256Text(canonicalJson(value));
}

async function assertFingerprint(actual: string, payload: { readonly [key: string]: CanonicalValue }, label: string): Promise<void> {
  if (actual !== await fingerprintPayload(payload)) throw new Error(`${label} fingerprint mismatch`);
}

async function verifyNestedFingerprints(value: BaseFacts): Promise<void> {
  const proof = value.actual_service_proof;
  if (proof) {
    await assertFingerprint(proof.fingerprint, {
      kind: 'authoritative-actual-service-proof',
      case_no: proof.case_no,
      service_dates: proof.service_dates,
      source_identity: proof.source_identity,
      source_version: proof.source_version,
    }, 'actual service proof');
  }
  const reuse = value.candidate_pool_reuse_proof;
  if (reuse) {
    await assertFingerprint(reuse.fingerprint, {
      pool_identity: reuse.pool_identity,
      round_identity: reuse.round_identity,
      coverage_version: reuse.coverage_version,
      availability_version: reuse.availability_version,
      willingness_version: reuse.willingness_version,
      same_round: reuse.same_round,
      coverage_valid: reuse.coverage_valid,
      availability_valid: reuse.availability_valid,
      willingness_valid: reuse.willingness_valid,
      fresh: reuse.fresh,
      accepted_candidate: reuse.accepted_candidate,
      case_no: reuse.case_no,
      successor_round_identity: reuse.successor_round_identity,
      generation_version: reuse.generation_version,
      event_version: reuse.event_version,
      candidate_identity: reuse.candidate_identity,
    }, 'candidate pool reuse proof');
  }
  const successor = value.successor_round;
  if (successor) {
    await assertFingerprint(successor.fingerprint, {
      kind: 'successor-round',
      case_no: successor.case_no,
      round_identity: successor.round_identity,
      generation_identity: successor.generation_identity,
      event_identity: successor.event_identity,
      generation_version: successor.generation_version,
      event_version: successor.event_version,
      candidate_count: successor.candidate_count,
      zero_candidate_disposition: successor.zero_candidate_disposition,
    }, 'successor round');
  }
}

function rootCanonicalTuple(root: z.infer<typeof ReplacementRootSchema>): CanonicalValue {
  return [root.kind, root.root_id, root.case_no, root.current, root.caregiver_bound];
}

function actualServiceCanonicalTuple(proof: z.infer<typeof ActualServiceProofSchema> | null): CanonicalValue {
  return proof === null ? null : [proof.case_no, proof.service_dates, proof.source_identity, proof.source_version, proof.fingerprint];
}

function reuseCanonicalTuple(proof: z.infer<typeof CandidatePoolReuseProofSchema> | null): CanonicalValue {
  return proof === null ? null : [
    proof.pool_identity, proof.round_identity, proof.coverage_version, proof.availability_version,
    proof.willingness_version, proof.fingerprint, proof.same_round, proof.coverage_valid,
    proof.availability_valid, proof.willingness_valid, proof.fresh, proof.accepted_candidate,
    proof.case_no, proof.successor_round_identity, proof.generation_version, proof.event_version,
    proof.candidate_identity,
  ];
}

function successorCanonicalTuple(successor: z.infer<typeof SuccessorRoundSchema> | null): CanonicalValue {
  return successor === null ? null : [
    successor.case_no, successor.round_identity, successor.generation_identity, successor.event_identity,
    successor.generation_version, successor.event_version, successor.candidate_count,
    successor.zero_candidate_disposition,
  ];
}

export async function verifyServiceBeforeReplacementQuery(
  value: ServiceBeforeReplacementQuery,
  caseNo: string,
  scenario: ServiceBeforeReplacementScenario,
): Promise<ServiceBeforeReplacementQuery> {
  if (value.case_no !== caseNo || value.scenario !== scenario) throw new Error('replacement query request/response identity mismatch');
  await verifyNestedFingerprints(value);
  return value;
}

export async function verifyServiceBeforeReplacementPreview(
  value: ServiceBeforeReplacementPreview,
  caseNo: string,
  request: ServiceBeforeReplacementPreviewRequest,
): Promise<ServiceBeforeReplacementPreview> {
  if (value.case_no !== caseNo || value.scenario !== request.scenario
    || value.reason !== request.reason || value.evidence.join('\n') !== request.evidence.join('\n')) {
    throw new Error('replacement preview request/response identity mismatch');
  }
  await verifyNestedFingerprints(value);
  await assertFingerprint(value.preview_fingerprint, {
    family: 'service-before-replacement',
    case_no: value.case_no,
    prior_case_no: value.case_no,
    scenario: value.scenario,
    prior_aggregate_identity: value.prior_aggregate_identity,
    expected_aggregate_version: value.expected_aggregate_version,
    resulting_aggregate_version: value.resulting_aggregate_version,
    prior_generation_identity: value.prior_generation_identity,
    prior_event_identity: value.prior_event_identity,
    expected_generation_version: value.expected_generation_version,
    expected_event_version: value.expected_event_version,
    generation_identity: value.replacement_generation_identity,
    event_identity: value.replacement_event_identity,
    round_identity: value.successor_round_identity,
    actual_service_proof: actualServiceCanonicalTuple(value.actual_service_proof),
    actual_service_dates: value.actual_service_dates,
    candidate_pool_reuse: reuseCanonicalTuple(value.candidate_pool_reuse_proof),
    candidate_identity: value.candidate_pool_reuse_proof?.candidate_identity ?? null,
    retained: value.retained_roots.map(rootCanonicalTuple),
    superseded: value.superseded_roots.map(rootCanonicalTuple),
    created: value.created_roots.map(rootCanonicalTuple),
    resume_step: value.resume_step,
    projection_kind: value.projection_kind,
    reason_evidence: [value.reason, value.evidence],
    blockers: value.blockers,
    successor_round: successorCanonicalTuple(value.successor_round),
  }, 'replacement preview');
  return value;
}

async function rootSetDigest(values: readonly string[]): Promise<string> {
  return sha256Text([...values].sort().join('\n'));
}

export async function verifyServiceBeforeReplacementApply(
  value: ServiceBeforeReplacementApplyResult,
  caseNo: string,
  request: ServiceBeforeReplacementApplyRequest,
  identity: ServiceBeforeReplacementCommandIdentity,
  actorBinding: ServiceBeforeReplacementActorBinding,
): Promise<ServiceBeforeReplacementApplyResult> {
  const receipt = value.receipt;
  const readback = value.readback;
  if (receipt.case_no !== caseNo || readback.case_no !== caseNo
    || receipt.idempotency_key !== identity.idempotencyKey
    || receipt.preview_fingerprint !== request.preview_fingerprint) {
    throw new Error('replacement apply request/response identity mismatch');
  }
  await assertFingerprint(receipt.command_fingerprint, {
    command_type: 'scheduling.service_before_replacement.apply',
    command_version: 1,
    case_no: caseNo,
    scenario: request.scenario,
    expected_generation_version: request.expected_generation_version,
    expected_event_version: request.expected_event_version,
    expected_aggregate_version: request.expected_aggregate_version,
    prior_generation_identity: request.prior_generation_identity,
    prior_event_identity: request.prior_event_identity,
    prior_aggregate_identity: request.prior_aggregate_identity,
    preview_fingerprint: request.preview_fingerprint,
    actor: actorBinding.actor,
    capabilities: actorBinding.capabilities,
    reason: request.reason,
    evidence: request.evidence,
  }, 'replacement command');
  const groups = [receipt.retained_root_ids, receipt.superseded_root_ids, receipt.created_root_ids] as const;
  const expectedDigests = await Promise.all(groups.map(rootSetDigest));
  const receiptDigests = [receipt.retained_root_set_digest, receipt.superseded_root_set_digest, receipt.created_root_set_digest];
  if (expectedDigests.some((digest, index) => digest !== receiptDigests[index] || digest !== readback.root_set_digests[index])) {
    throw new Error('replacement root set digest mismatch');
  }
  return value;
}

export async function decodeAndVerifyServiceBeforeReplacementApplyResponse(
  raw: unknown,
  caseNo: string,
  request: ServiceBeforeReplacementApplyRequest,
  identity: ServiceBeforeReplacementCommandIdentity,
  commandActor: ServiceBeforeReplacementActorBinding,
): Promise<ServiceBeforeReplacementApplyResult> {
  try {
    const data = decodePayload(envelope(ServiceBeforeReplacementApplySchema), raw).data;
    return await verifyServiceBeforeReplacementApply(data, caseNo, request, identity, commandActor);
  } catch (error) {
    throw new ApiHttpError(
      503,
      'replacement_outcome_unknown',
      'Apply 已送達，但 receipt／readback 無法完成嚴格對帳；只能用原命令與原 Idempotency-Key 重查。',
      true,
      error,
    );
  }
}

export function serviceBeforeReplacementErrorCode(error: unknown): ServiceBeforeReplacementErrorCode | null {
  if (!(error instanceof ApiHttpError)) return null;
  const result = ServiceBeforeReplacementErrorCodeSchema.safeParse(error.code);
  return result.success ? result.data : null;
}

export function isServiceBeforeReplacementOutcomeUnknown(error: unknown): boolean {
  return error instanceof ApiTimeoutError
    || error instanceof ApiNetworkError
    || serviceBeforeReplacementErrorCode(error) === 'replacement_outcome_unknown';
}

function canonicalCaseNo(caseNo: string): string {
  const value = caseNo.trim();
  if (!value || value.length > 50) throw new Error('案件編號無效。');
  return value;
}

function authToken(): string {
  const token = sessionClient.getToken();
  if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入或啟用本機 no-auth 開發模式。');
  return token;
}

function actorBinding(): ServiceBeforeReplacementActorBinding {
  const user = sessionClient.getUser();
  if (!user) throw new ApiHttpError(401, 'UNAUTHENTICATED', '無法確認服務前換人的操作人員。');
  return {
    actor: user.id === null ? 'admin:development' : `admin:${user.id}`,
    capabilities: ['orders.historical_review.remediate'],
  };
}

function uuidHex(): string {
  if (!globalThis.crypto?.randomUUID) throw new Error('瀏覽器無法建立安全命令識別。');
  return globalThis.crypto.randomUUID().replaceAll('-', '').toLowerCase();
}

export function createServiceBeforeReplacementCommandIdentity(): ServiceBeforeReplacementCommandIdentity {
  return {
    idempotencyKey: `service-before-replacement:${uuidHex()}`,
    correlationId: `service-before-replacement-${uuidHex()}`,
  };
}

function requestOptions(identity?: ServiceBeforeReplacementCommandIdentity, signal?: AbortSignal): RequestOptions {
  return {
    token: authToken(),
    signal,
    headers: {
      'X-Correlation-ID': identity?.correlationId ?? `service-before-replacement-${uuidHex()}`,
      ...(identity ? { 'Idempotency-Key': identity.idempotencyKey } : {}),
    },
  };
}

function basePath(caseNo: string): string {
  return `/api/v1/orders/${encodeURIComponent(canonicalCaseNo(caseNo))}/service-before-replacement`;
}

export const serviceBeforeReplacementClient = {
  async query(caseNo: string, scenario: ServiceBeforeReplacementScenario, signal?: AbortSignal): Promise<ServiceBeforeReplacementQuery> {
    const canonicalCase = canonicalCaseNo(caseNo);
    const data = decodePayload(
      envelope(ServiceBeforeReplacementQuerySchema),
      await transport.get(basePath(canonicalCase), { ...requestOptions(undefined, signal), params: { scenario } }),
    ).data;
    return verifyServiceBeforeReplacementQuery(data, canonicalCase, scenario);
  },

  async preview(caseNo: string, request: ServiceBeforeReplacementPreviewRequest, signal?: AbortSignal): Promise<ServiceBeforeReplacementPreview> {
    const canonicalCase = canonicalCaseNo(caseNo);
    const body = PreviewRequestSchema.parse(request);
    const data = decodePayload(
      envelope(ServiceBeforeReplacementPreviewSchema),
      await transport.post(`${basePath(canonicalCase)}/preview`, body, requestOptions(undefined, signal)),
    ).data;
    return verifyServiceBeforeReplacementPreview(data, canonicalCase, body);
  },

  async apply(
    caseNo: string,
    request: ServiceBeforeReplacementApplyRequest,
    identity: ServiceBeforeReplacementCommandIdentity,
    signal?: AbortSignal,
  ): Promise<ServiceBeforeReplacementApplyResult> {
    const canonicalCase = canonicalCaseNo(caseNo);
    const body = ApplyRequestSchema.parse(request);
    const commandActor = actorBinding();
    const raw = await transport.post(`${basePath(canonicalCase)}/apply`, body, requestOptions(identity, signal));
    return decodeAndVerifyServiceBeforeReplacementApplyResponse(raw, canonicalCase, body, identity, commandActor);
  },
};
