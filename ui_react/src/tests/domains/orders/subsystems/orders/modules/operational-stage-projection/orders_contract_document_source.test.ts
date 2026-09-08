import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const workbenchSource = readFileSync(
  resolve(process.cwd(), 'src/pages/OrderWorkbenchV2Page.tsx'),
  'utf8',
);

describe('Order Workbench contract document source', () => {
  it('keeps the formal Contract Signing document path and removes the handcrafted draft surface', () => {
    expect(workbenchSource).toContain('<ContractExternalSigningActions');
    expect(workbenchSource).not.toContain('<OrderCaregiverContractPanel');
    expect(workbenchSource).not.toContain('<OrderClientContractPanel');
    expect(workbenchSource).not.toContain('契約草稿預覽（非正式）');
    expect(workbenchSource).not.toContain('訂單規格摘要');
    expect(workbenchSource).not.toContain('列印草稿');
    expect(workbenchSource).not.toContain('contractDocView');
    expect(workbenchSource).not.toContain('contractDocFullscreen');
  });
});
