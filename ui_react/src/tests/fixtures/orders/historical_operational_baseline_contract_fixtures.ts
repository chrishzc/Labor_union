/**
 * File: historical_operational_baseline_contract_fixtures.ts
 * Description: Orders owned Historical Operational Baseline Query fixtures。
 */
import type { HistoricalOperationalBaseline } from '../../../api/orders/historical_operational_baseline_schemas';

const fingerprint = (character: string): string => character.repeat(64);

export const HISTORICAL_BASELINE_CASE_NO = 'CASE-HOB-1';

export const HISTORICAL_OPERATIONAL_BASELINE_VIEW: HistoricalOperationalBaseline = {
  order_identity: 'order:CASE-HOB-1',
  case_no: HISTORICAL_BASELINE_CASE_NO,
  historical_provenance: {
    source_event_identity: 'historical-orders:source:1',
    source_version: 3,
  },
  current_orders_version: 4,
  baseline_binding_fingerprint: fingerprint('a'),
  current_baseline: {
    baseline_event_identity: 'historical-operational-baseline-event:1',
    selected_step: 3,
    resulting_orders_version: 4,
    resulting_owner_binding_fingerprint: fingerprint('a'),
    step_projection: [
      { step: 1, state: 'historical_baseline_completed' },
      { step: 2, state: 'historical_baseline_completed' },
      { step: 3, state: 'in_progress' },
    ],
  },
  allowed_steps: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
  evidence_modes: ['retained', 'historical_evidence_unavailable_accepted'],
};

export const HISTORICAL_OPERATIONAL_BASELINE_RESPONSE = {
  success: true as const,
  message: '成功載入歷史案件作業基準',
  data: HISTORICAL_OPERATIONAL_BASELINE_VIEW,
  error: null,
};
