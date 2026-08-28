/**
 * File: anomaly_detail_adapter.test.ts
 * Description: 驗證異常詳情 adapter 的 typed 投影、身份一致性與零推導契約。
 */

import { describe, expect, it } from 'vitest';
import { adaptAnomalyDetailBundle, visibleEvidenceItems } from '../adapters/anomalies/anomaly_detail_adapter';
import type {
  AnomalyDetailView,
  AnomalyRecoveryContextView,
} from '../api/anomalies/anomaly_detail_schemas';
import {
  VALID_ANOMALY_DETAIL_VIEW,
  VALID_ANOMALY_RECOVERY_CONTEXT_VIEW,
} from './fixtures/anomalies/anomaly_detail_contract_fixtures';

function alignedDetail(): AnomalyDetailView {
  const definitionCode = VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.definition_code;
  return {
    ...VALID_ANOMALY_DETAIL_VIEW,
    summary: {
      ...VALID_ANOMALY_DETAIL_VIEW.summary,
      definition_code: definitionCode,
      display_snapshot: {
        ...VALID_ANOMALY_DETAIL_VIEW.summary.display_snapshot,
        definition_code: definitionCode,
      },
    },
  };
}

function alignedRecovery(): AnomalyRecoveryContextView {
  return VALID_ANOMALY_RECOVERY_CONTEXT_VIEW;
}

describe('Anomaly detail adapter', () => {
  it('投影 typed evidence 的業務標籤、兩條 timeline、root facts、occurrences 與 action metadata', () => {
    const view = adaptAnomalyDetailBundle(alignedDetail(), alignedRecovery());

    expect(view.fingerprint).toBe(VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.fingerprint);
    expect(view.definitionCode).toBe(VALID_ANOMALY_RECOVERY_CONTEXT_VIEW.definition_code);
    expect(view.evidence).toContainEqual({
      key: 'case_no',
      kind: 'identity',
      label: '案件',
      value: 'CASE-SYNTH-042',
    });
    expect(view.evidence).toContainEqual({
      key: 'overdue_obligations',
      kind: 'identity_list',
      label: '具體逾期義務',
      value: 'obligation:SYNTH-19',
    });

    expect(view.detailTimeline).toEqual([
      {
        action: '已進入人工確認',
        actor: 'O***',
        reason: '異常已進入人工確認流程。',
        correlationId: 'anomaly-detail:SYNTH-42',
        expectedVersion: 2,
        resultingVersion: 3,
        createdAt: '2026-08-22T09:30:00+00:00',
      },
      {
        action: '已記錄處理進度',
        actor: 'S***',
        reason: '人工處理進度已更新；不代表根事實已修正。',
        correlationId: 'anomaly-detail:SYNTH-43',
        expectedVersion: 3,
        resultingVersion: 4,
        createdAt: '2026-08-22T10:00:00+00:00',
      },
    ]);
    expect(view.recoveryTimeline).toEqual([
      {
        action: '已記錄處理進度',
        actor: 'O***',
        reason: '人工處理進度已更新；不代表根事實已修正。',
        correlationId: 'anomaly-recovery:SYNTH-42',
        expectedVersion: 2,
        resultingVersion: 3,
        createdAt: '2026-08-22T10:00:00+00:00',
      },
    ]);

    expect(view.rootFacts).toContainEqual({
      key: 'amount_delta_ntd',
      kind: 'money_ntd',
      label: '金額差異',
      value: 'NT$ 1,200',
    });
    expect(view.rootFacts).toContainEqual({
      key: 'domain_blockers',
      kind: 'code_list',
      label: '阻擋原因',
      value: 'manual_review',
    });
    expect(view.occurrences).toEqual([
      expect.objectContaining({
        fingerprint: 'b'.repeat(64),
        occurredAt: '2026-08-22T09:30:00+00:00',
      }),
    ]);
    expect(view.occurrences[0]?.evidence).toContainEqual({
      key: 'integrity_blocker_active',
      kind: 'boolean',
      label: '目前阻擋作業',
      value: '否',
    });
    expect(view.actions).toEqual([
      {
        key: 'repair_finance_projection',
        label: '預覽財務投影修復',
        owner: 'finance_import',
        bindings: [
          'finance_import_row_identity=row:SYNTH-42',
          'source_version=7',
        ],
        requiredInputs: ['evidence', 'reason'],
        previewOperation: 'PreviewFinanceProjectionRepair',
        applyOperation: 'ApplyFinanceProjectionRepair',
        completionPredicate: 'root_condition_cleared',
        contractVersion: 1,
      },
    ]);
    expect(view.projectionFreshness).toBe('fresh');
    expect(view.domainBlockerActive).toBe(true);
  });

  it('identity mismatch 會 fail closed，且分別涵蓋 fingerprint、definition 與 source', () => {
    const detail = alignedDetail();
    const recovery = alignedRecovery();

    expect(() => adaptAnomalyDetailBundle(
      {
        ...detail,
        summary: { ...detail.summary, fingerprint: 'c'.repeat(64) },
      },
      recovery,
    )).toThrow('detail 與 recovery identity 不一致');

    expect(() => adaptAnomalyDetailBundle(
      detail,
      { ...recovery, definition_code: 'other-definition' },
    )).toThrow('detail 與 recovery identity 不一致');

    expect(() => adaptAnomalyDetailBundle(
      detail,
      { ...recovery, source_identity: 'different-source:17' },
    )).toThrow('detail 與 recovery identity 不一致');
  });

  it('不產生已修復結論或領域推導，只保留 server typed values', () => {
    const view = adaptAnomalyDetailBundle(alignedDetail(), alignedRecovery());
    const serialized = JSON.stringify(view);

    expect(serialized).not.toContain('已修復');
    expect(view).not.toHaveProperty('severityLabel');
    expect(view).not.toHaveProperty('statusLabel');
    expect(view).not.toHaveProperty('domainLabel');
    expect(view.rootFacts.find((item) => item.key === 'domain_blockers')?.value).toBe('manual_review');
  });

  it('顯示 CLIENTREFUND 的 typed row／batch／refund／case-obligation 與原因阻擋欄位，但隱藏 private/raw 欄位', () => {
    const fields = [
      { key: 'finance_import_row_id', kind: 'identity', value: 'row:SYNTH-42' },
      { key: 'finance_import_batch_id', kind: 'identity', value: 'batch:SYNTH-09' },
      { key: 'original_refund_ledger_entry_id', kind: 'identity', value: 'ledger-refund:SYNTH-42' },
      { key: 'affected_order_identities', kind: 'identity_list', value: ['order:SYNTH-17'] },
      { key: 'affected_obligation_identities', kind: 'identity_list', value: ['obligation:SYNTH-19'] },
      { key: 'domain_blockers', kind: 'code_list', value: ['refund_return_requires_confirmed_reversal'] },
      { key: 'reason_codes', kind: 'code_list', value: ['refund_return_review_recorded'] },
      { key: 'source_identity', kind: 'identity', value: 'event:private' },
      { key: 'raw_payload', kind: 'masked_text', value: 'private' },
      { key: 'fingerprint', kind: 'identity', value: 'private' },
    ] as const;

    expect(visibleEvidenceItems(fields)).toEqual(fields.slice(0, 7));
  });

  it('recovery action 為空時使用已綁定的 detail owner action，不顯示無處理方式', () => {
    const detail = alignedDetail();
    const boundAction = {
      ...detail.available_actions[0],
      source_bindings: [{ kind: 'version' as const, key: 'source_version', value: 7 }],
    };
    const recovery = { ...alignedRecovery(), available_actions: [] };

    const view = adaptAnomalyDetailBundle(
      { ...detail, available_actions: [boundAction] },
      recovery,
    );

    expect(view.recoveryAvailable).toBe(true);
    expect(view.actions).toEqual([
      expect.objectContaining({
        key: boundAction.action_key,
        bindings: ['source_version=7'],
      }),
    ]);
  });
});
