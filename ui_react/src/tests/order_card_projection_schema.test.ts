/**
 * File: order_card_projection_schema.test.ts
 * Description: 驗證案件卡片投影的 availability 與 value 必須一致，避免缺陷資料偽裝成可用內容。
 */
import { describe, expect, it } from 'vitest';
import { OrdersCardProjectionFieldSchema } from '../api/orders/order_card_projection_schemas';
import { z } from 'zod';

const field = {
  owner: 'Scheduling',
  source_identity: 'fixture:assignment-segments',
  source_version: '1',
  availability_reason: null,
};

describe('Orders card projection availability contract', () => {
  it('rejects unavailable projection containers that still carry visible values', () => {
    const result = OrdersCardProjectionFieldSchema(z.array(z.string())).safeParse({
      ...field,
      value: ['must-not-render'],
      availability: 'unavailable',
      availability_reason: 'formal_assignment_lineage_missing',
    });
    expect(result.success).toBe(false);
  });

  it('rejects available projection fields without a value', () => {
    const result = OrdersCardProjectionFieldSchema(z.string()).safeParse({
      ...field,
      value: null,
      availability: 'available',
    });
    expect(result.success).toBe(false);
  });
});
