/**
 * File: finance_import_correction_client.ts
 * Description: 以嚴格 typed contract 執行帳務異常的 Finance Import 更正 Preview、Apply 與 receipt 查詢。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { FinanceImportQueryError, mapFinanceImportQueryError } from './finance_import_query_errors';

const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const classificationType = z.enum([
  'client_receipt', 'client_refund', 'client_refund_return',
  'client_subsidy_return', 'government_subsidy', 'staff_payout',
]);
const selectionSchema = z.strictObject({
  row_identity: z.string().min(1).max(191),
  classification_type: classificationType,
  target_obligation_identities: z.array(z.string().min(1).max(191)).min(1),
  refund_ledger_entry_identity: z.string().min(1).max(191).nullable(),
  allow_partial_refund_recovery: z.boolean(),
  allow_refund_overage_recovery: z.boolean(),
  allow_client_receipt_overage: z.boolean(),
  reason: z.string().trim().max(500).default(''),
  evidence: z.array(z.string().min(1)).min(1),
});
const candidateSchema = z.strictObject({
  row_identity: z.string().min(1), batch_identity: z.string().min(1), classification_type: z.string().min(1),
  owning_domain: z.string().min(1), bank_amount_ntd: z.number().int().positive(),
  allocations: z.array(z.strictObject({ obligation_identity: z.string().min(1), amount_ntd: z.number().int().positive() })),
  reason: z.string(), evidence: z.array(z.string().min(1)), refund_ledger_entry_identity: z.string().min(1).nullable(),
  allow_partial_refund_recovery: z.boolean(), allow_refund_overage_recovery: z.boolean(), allow_client_receipt_overage: z.boolean(),
  candidate_fingerprint: sha256,
  refund_summary: z.strictObject({ transfer_fee_ntd: z.number().int().min(0).max(100), remaining_ntd: z.number().int().nonnegative() }).nullish(),
});
const previewSchema = z.strictObject({
  candidate: candidateSchema, batch_version: z.number().int().nonnegative(), canonical_fact_version: z.number().int().nonnegative(),
  alert_version: z.number().int().nonnegative(), preview_fingerprint: sha256,
});
const jobAcceptedSchema = z.strictObject({ job_id: z.string().min(1).max(191), status_url: z.string().min(1), replayed: z.boolean() });
const receiptSchema = z.strictObject({
  row_identity: z.string().min(1), batch_identity: z.string().min(1), resulting_batch_version: z.number().int().positive(),
  classification_event_count: z.number().int().positive(), ledger_entry_count: z.number().int().positive(), allocation_count: z.number().int().positive(),
  reconciliation_receipt_count: z.number().int().positive(), alert_resolved_event_count: z.number().int().nonnegative(), preview_fingerprint: sha256,
});
const outcomeSchema = z.strictObject({
  job_id: z.string().min(1).max(191), status: z.enum(['queued', 'running', 'succeeded', 'failed', 'cancelled']),
  attempt_count: z.number().int().nonnegative(), max_attempts: z.number().int().nonnegative(), result_reference: z.string().min(1).max(191).nullable(),
  receipt: receiptSchema.nullable(),
  failure_code: z.string().regex(/^[a-z0-9_]+$/).max(128).nullable().optional(),
});
const envelope = <T extends z.ZodType>(data: T) => z.strictObject({ success: z.literal(true), message: z.string(), data, error: z.null() });

export type FinanceImportCorrectionSelection = z.infer<typeof selectionSchema>;
export type FinanceImportCorrectionPreview = z.infer<typeof previewSchema>;
export type FinanceImportCorrectionJobAccepted = z.infer<typeof jobAcceptedSchema>;
export type FinanceImportCorrectionJobOutcome = z.infer<typeof outcomeSchema>;

export const REFUND_BLOCKERS: Readonly<Record<string, string>> = {
  client_refund_recipient_account_ambiguous: '待退款項缺少唯一的退款收款帳戶，請先查核本案退款帳戶資料。',
  client_refund_recipient_account_mismatch: '銀行出款的收款帳號缺少，或與待退款項的收款帳戶不符，請核對原流水與退款帳戶。',
  bank_transaction_date_missing: '原銀行流水缺少交易日，無法核銷退款／補助，請先查核來源資料。',
  bank_currency_not_twd: '原銀行流水幣別不是新臺幣，無法核銷退款／補助，請先查核來源資料。',
  subsidy_advance_not_due: '銀行出款日早於補助款到期日，且當時尚無政府撥款涵蓋，無法核銷工會代墊。',
  subsidy_advance_settlement_ambiguous: '補助款的服務結束日、到期日或政府入款／代墊資料不完整、不一致或不唯一，請查核本案補助資料。',
  due_date_missing: '待核銷款項缺少到期或預計付款日期，請查核本案補助資料。',
  client_subsidy_memo_recipient_unconfirmed: '銀行備註無法確認本案客戶補助對象，請核對原始備註六碼及月嫂姓名。',
  bank_fact_not_eligible: '原銀行流水未通過退款／補助核銷資格檢查，原操作未留存更細的拒絕原因，請查核原流水。',
  stale_preview: '資料已變更，請重新查詢並預覽後再確認核銷。',
  refund_requires_exact_settlement: '實付與待退款的差額超出手續費條件；請核對金額，若屬不足額退款，請明確選擇不足額核銷方式。',
  allocation_exceeds_obligation: '銀行實付金額超過所選待退款項，請核對原流水金額及選取款項。',
};
export const SINOPAC_REFUND_BLOCKERS: Readonly<Record<string, string>> = {
  bank_transaction_date_missing: '原銀行流水缺少交易日，無法核銷客戶退款。',
  bank_currency_not_twd: '原銀行流水幣別不是新臺幣，無法核銷客戶退款。',
  due_date_missing: '待退款項缺少預計退款日，無法完成月份配對；請查核本案退款資料。',
  outgoing_client_refund_no_open_obligation: '所選案件目前沒有可供核對的未清一般退款單，請重新查詢退款資料。',
  outgoing_client_refund_month_no_match: '交易日與預計退款日都有值，但找不到同年月的未清退款單；請人工選款核對。',
  outgoing_client_refund_amount_mismatch: '銀行實付與單筆或同案同月合併待退金額不符合足額或100元內手續費條件；請核對差額，少退或超退須選對應方式處理。',
  outgoing_client_refund_multiple_fee_matches: '同月有多個單筆或合併退款配對符合金額或手續費條件；請核對預計退款日及金額並人工選款。',
  client_refund_source_account_missing: '原銀行流水未能辨識收款帳號，無法與退款單收款帳戶比對；請查核原流水。',
  client_refund_recipient_account_ambiguous: '所選退款單的收款帳戶缺少或不一致，無法確認唯一收款帳戶；請查核退款單帳戶資料。',
  client_refund_recipient_account_mismatch: '原銀行流水的收款帳號與所選退款單收款帳戶不同，無法核銷；請核對原流水與退款單帳戶。',
  client_refund_memo_case_mismatch: '所選退款單與原流水備註或人工確認的案件不符，請核對案件。',
  refund_requires_exact_settlement: '實付少於待退金額超過100元；若為實際少退，請明確選擇部分退款，保留原退款單未退餘額。',
  allocation_exceeds_obligation: '銀行實付超過所選待退金額；請核對款項，確認超退時沿超退追償方式處理。',
};

export const TAISHIN_SUBSIDY_REFUND_BLOCKERS: Readonly<Record<string, string>> = {
  bank_transaction_date_missing: '原銀行流水缺少交易日，無法核銷客戶補助退款。',
  bank_currency_not_twd: '原銀行流水幣別不是新臺幣，無法核銷客戶補助退款。',
  outgoing_client_refund_no_open_obligation: '本案沒有可供本次核對的未清客戶補助退款單，請重新查詢款項。',
  due_date_missing: '客戶補助退款單缺少正式預計退款日，請查核原款項；不能用目前服務結束日補造日期。',
  outgoing_client_refund_month_no_match: '交易日與正式預計退款日都有值，但找不到同年月的客戶補助待退款；請人工選款核對。',
  outgoing_client_refund_amount_mismatch: '銀行實付與單筆或同案同月合併待退金額不符合足額或100元內手續費條件；請核對差額，少退可選部分退款，超退可另列待追回款。',
  outgoing_client_refund_multiple_fee_matches: '有多個單筆或合併補助退款配對符合金額條件，請核對預計退款日及金額並人工選款。',
  client_subsidy_memo_recipient_unconfirmed: '原銀行備註六碼無法經正式虛擬帳號對照唯一定位案件，無法確認客戶補助退款對象。',
  client_subsidy_memo_case_mismatch: '原銀行備註六碼定位的案件與所選案件不同，無法核銷本案補助退款。',
  client_subsidy_memo_staff_matched: '原銀行備註先命中月嫂姓名，應依月嫂款核對，不能改走客戶補助退款。',
  subsidy_advance_not_due: '出款當時尚無政府資金支應，且早於本筆正式到期日，未符合代墊核銷條件。',
  subsidy_advance_settlement_ambiguous: '補助退款的正式款項或政府整期資金來源缺漏、衝突或不唯一，無法確認本次出款的資金歸屬。',
  refund_requires_exact_settlement: '實付少於待退金額超過100元；若為實際少退，請明確選擇部分退款並保留原款項餘額。',
  allocation_exceeds_obligation: '實付超過所選待退金額；確認實際超退時，請選擇「退款超出，另列待追回款」。',
  bank_fact_not_eligible: '原銀行流水未通過補助退款核銷資格檢查，未留存更細的具體原因，請重新查核原流水。',
  stale_preview: '資料已更新，請重新查詢並預覽後確認核銷。',
  client_refund_overage_required: '實付沒有超過所選待退金額，請改選足額或部分退款方式。',
};

export function financeRefundBlockerMessage(code?: string | null, kind?: string): string {
  if (kind === 'client_subsidy_return') return (code && TAISHIN_SUBSIDY_REFUND_BLOCKERS[code]) || '客戶補助退款核銷未完成，未留存適用現行流程的具體阻擋原因，請重新查核。';
  if (kind === 'client_refund' && code && SINOPAC_REFUND_BLOCKERS[code]) return SINOPAC_REFUND_BLOCKERS[code];
  return (code && REFUND_BLOCKERS[code]) || '退款／補助核銷未完成，未留存可顯示的具體阻擋原因，請重新查詢帳務資料。';
}

function requestOptions(signal?: AbortSignal, headers: Record<string, string> = {}): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new FinanceImportQueryError('FINANCE_IMPORT_UNAUTHENTICATED', '請先登入。', false, 401);
  return { token, signal, timeoutMs: 30_000, headers };
}

function commandHeaders(idempotencyKey: string, correlationId: string): Record<string, string> {
  if (!idempotencyKey.trim() || !correlationId.trim()) throw new FinanceImportQueryError('FINANCE_IMPORT_COMMAND_IDENTITY_INVALID', '命令識別不得為空白。');
  return { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': correlationId };
}

function decode<T>(schema: z.ZodType<T>, raw: unknown, label: string): T {
  try { return decodePayload(envelope(schema), raw).data as T; }
  catch (error) { throw mapFinanceImportQueryError(error instanceof Error ? error : new Error(`${label}回應結構異常。`)); }
}

function validSelection(selection: FinanceImportCorrectionSelection): FinanceImportCorrectionSelection {
  const parsed = selectionSchema.safeParse(selection);
  if (!parsed.success) throw new FinanceImportQueryError('FINANCE_IMPORT_CORRECTION_INPUT_INVALID', '帳務更正輸入不完整或格式不正確。');
  return parsed.data;
}

export const financeImportCorrectionClient = {
  async preview(selection: FinanceImportCorrectionSelection, signal?: AbortSignal): Promise<FinanceImportCorrectionPreview> {
    const request = validSelection(selection);
    try {
      return decode(previewSchema, await transport.post('/api/v1/finance-import/corrections/preview', request, requestOptions(signal, { 'X-Correlation-ID': `finance-import-correction-preview-${crypto.randomUUID()}` })), '帳務更正 Preview');
    } catch (error) {
      const mapped = mapFinanceImportQueryError(error);
      if (['client_refund', 'client_subsidy_return'].includes(request.classification_type) && (REFUND_BLOCKERS[mapped.code] || (request.classification_type === 'client_refund' && SINOPAC_REFUND_BLOCKERS[mapped.code]) || (request.classification_type === 'client_subsidy_return' && TAISHIN_SUBSIDY_REFUND_BLOCKERS[mapped.code]))) {
        throw new FinanceImportQueryError(mapped.code, financeRefundBlockerMessage(mapped.code, request.classification_type), mapped.retryable, mapped.status);
      }
      throw mapped;
    }
  },
  async apply(preview: FinanceImportCorrectionPreview, selection: FinanceImportCorrectionSelection, command: { idempotencyKey: string; correlationId: string; signal?: AbortSignal }): Promise<FinanceImportCorrectionJobAccepted> {
    const request = validSelection(selection);
    try {
      return decode(jobAcceptedSchema, await transport.post('/api/v1/finance-import/corrections/apply', {
        ...request, expected_batch_version: preview.batch_version, expected_canonical_fact_version: preview.canonical_fact_version,
        expected_alert_version: preview.alert_version, preview_fingerprint: preview.preview_fingerprint,
      }, requestOptions(command.signal, commandHeaders(command.idempotencyKey, command.correlationId))), '帳務更正 Apply');
    } catch (error) {
      const mapped = mapFinanceImportQueryError(error);
      if (['client_refund', 'client_subsidy_return'].includes(request.classification_type) && (REFUND_BLOCKERS[mapped.code] || (request.classification_type === 'client_refund' && SINOPAC_REFUND_BLOCKERS[mapped.code]) || (request.classification_type === 'client_subsidy_return' && TAISHIN_SUBSIDY_REFUND_BLOCKERS[mapped.code]))) {
        throw new FinanceImportQueryError(mapped.code, financeRefundBlockerMessage(mapped.code, request.classification_type), mapped.retryable, mapped.status);
      }
      throw mapped;
    }
  },
  async queryOutcome(jobId: string, signal?: AbortSignal): Promise<FinanceImportCorrectionJobOutcome> {
    const normalized = jobId.trim();
    if (!normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_JOB_ID_INVALID', 'job id 不得為空白。');
    try {
      const outcome = decode(outcomeSchema, await transport.get(`/api/v1/finance-import/jobs/${encodeURIComponent(normalized)}/correction-outcome`, requestOptions(signal)), '帳務更正 terminal receipt');
      if (outcome.job_id !== normalized) throw new FinanceImportQueryError('FINANCE_IMPORT_JOB_IDENTITY_MISMATCH', 'job identity 與查詢不一致。');
      return outcome;
    } catch (error) { throw mapFinanceImportQueryError(error); }
  },
};
