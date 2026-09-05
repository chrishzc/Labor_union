import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const ordersPageSource = readFileSync(
  resolve(process.cwd(), 'src/pages/OrdersPage.tsx'),
  'utf8',
);

describe('Orders contract document source', () => {
  it('keeps the formal Contract Signing document path and removes the handcrafted draft surface', () => {
    expect(ordersPageSource).toContain('<ContractExternalSigningActions');
    expect(ordersPageSource).not.toContain('契約草稿預覽（非正式）');
    expect(ordersPageSource).not.toContain('訂單規格摘要');
    expect(ordersPageSource).not.toContain('列印草稿');
    expect(ordersPageSource).not.toContain('contractDocView');
    expect(ordersPageSource).not.toContain('contractDocFullscreen');
  });
});
