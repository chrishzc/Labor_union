/**
 * File: challenger_g2_orders_client.test.ts
 * Description: 反向挑戰 Orders allowlist 與 Pydantic-to-Zod required、nullable、extra 契約。
 */
import { describe, expect, it } from 'vitest';
import * as clientModule from '../api/orders/order_query_client';
import * as schemaModule from '../api/orders/order_query_schemas';
import {
  ActualStartSchema,
  AssignmentPlanSchema,
  ContractCompletionSchema,
  FormManagementContextSchema,
  OrderCalendarDetailSchema,
  OrderDetailSchema,
  OrderSummaryPageSchema,
  OrderTermsSchema,
} from '../api/orders/order_query_schemas';
import {
  realisticActualStart,
  realisticAssignmentPlan,
  realisticContractCompletion,
  realisticFormManagementContext,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
} from './fixtures/orders_real_data_fixtures';

describe('G2 Orders contract challenger', () => {
  it('exports no removed query functions or response schemas', () => {
    const forbidden = [
      'getCandidateContactPool', 'recommendStaff', 'getActiveMatchingPlan',
      'getMatchingPlanContactState', 'getLifecycleControlState',
      'getContractSigning', 'getServiceDates', 'getScheduleConfirmation',
      'getOrderCancellation', 'getFormManagementStatistics',
    ];
    for (const name of forbidden) expect(name in clientModule).toBe(false);
    const forbiddenSchemas = [
      'CandidateContactPoolSchema', 'StaffRecommendationSchema',
      'ActiveMatchingPlanSchema', 'MatchingPlanContactStateSchema',
      'LifecycleControlStateSchema', 'ContractSigningSchema',
      'ServiceDateConfirmationSchema', 'ScheduleConfirmationSchema',
      'OrderCancellationSchema', 'FormManagementStatisticsSchema',
    ];
    for (const name of forbiddenSchemas) expect(name in schemaModule).toBe(false);
  });

  it.each([
    ['summary', OrderSummaryPageSchema, realisticOrderSummaryPage],
    ['detail', OrderDetailSchema, realisticOrderDetail],
    ['calendar', OrderCalendarDetailSchema, realisticOrderCalendarDetail],
    ['terms', OrderTermsSchema, realisticOrderTerms],
    ['form context', FormManagementContextSchema, realisticFormManagementContext],
    ['actual start', ActualStartSchema, realisticActualStart],
    ['completion', ContractCompletionSchema, realisticContractCompletion],
    ['assignment', AssignmentPlanSchema, realisticAssignmentPlan],
  ] as const)('%s accepts the live Pydantic-aligned fixture', (_name, schema, fixture) => {
    expect(schema.parse(fixture)).toEqual(fixture);
  });

  it('does not default missing nullable summary fields', () => {
    const item = { ...realisticOrderSummaryPage.items[0] };
    Reflect.deleteProperty(item, 'staff_name');
    expect(() => OrderSummaryPageSchema.parse({ ...realisticOrderSummaryPage, items: [item] })).toThrow();
  });

  it('rejects extra nested keys rather than silently stripping drift', () => {
    const assignment = {
      ...realisticAssignmentPlan,
      assignments: [{ ...realisticAssignmentPlan.assignments[0], formal_recommendation: true }],
    };
    expect(() => AssignmentPlanSchema.parse(assignment)).toThrow();
  });

  it('distinguishes required nullable from optional', () => {
    expect(OrderDetailSchema.parse({ ...realisticOrderDetail, staff_id: null }).staff_id).toBeNull();
    const missing = { ...realisticOrderDetail };
    Reflect.deleteProperty(missing, 'staff_id');
    expect(() => OrderDetailSchema.parse(missing)).toThrow();
  });

  it('rejects dates and time strings outside the server serialization shape', () => {
    expect(() => OrderSummaryPageSchema.parse({
      ...realisticOrderSummaryPage,
      items: [{ ...realisticOrderSummaryPage.items[0], start_date: '09/01/2026' }],
    })).toThrow();
    expect(() => OrderTermsSchema.parse({
      ...realisticOrderTerms,
      terms: {
        ...realisticOrderTerms.terms,
        service_time: { ...realisticOrderTerms.terms.service_time, start_time: '08:30' },
      },
    })).toThrow();
  });

  it('rejects permissive envelope omissions and additions', () => {
    const schema = schemaModule.createOrderQueryEnvelopeSchema(OrderDetailSchema);
    expect(() => schema.parse({ success: true, message: 'ok', data: realisticOrderDetail })).toThrow();
    expect(() => schema.parse({
      success: true, message: 'ok', data: realisticOrderDetail, error: null, guessed: true,
    })).toThrow();
  });
});
