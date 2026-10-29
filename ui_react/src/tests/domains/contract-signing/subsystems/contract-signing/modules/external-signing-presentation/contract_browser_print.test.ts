import { afterEach, describe, expect, it, vi } from 'vitest';
import { openContractPrintView } from '../../../../../../../api/orders/contract_full_preview_client';
import { transport } from '../../../../../../../api/shared/transport';

afterEach(() => vi.restoreAllMocks());

function popup() {
  const button = new EventTarget();
  const document = {
    title: '', body: { textContent: '' },
    open: vi.fn(), write: vi.fn(), close: vi.fn(),
    getElementById: vi.fn(() => button), fonts: { ready: Promise.resolve() },
    adoptedStyleSheets: [] as CSSStyleSheet[],
  };
  class PrintStylesheet {
    replaceSync = vi.fn();
  }
  const view = { document, CSSStyleSheet: PrintStylesheet, opener: window, closed: false, close: vi.fn(), focus: vi.fn(), print: vi.fn() };
  vi.spyOn(window, 'open').mockReturnValue(view as unknown as Window);
  return { view, button };
}

describe('contract browser printing', () => {
  it('opens within the click gesture and waits for fonts before printing the authenticated HTML', async () => {
    const { view, button } = popup();
    let fontsReady!: () => void;
    view.document.fonts.ready = new Promise<void>(resolve => { fontsReady = resolve; });
    const get = vi.spyOn(transport, 'get').mockResolvedValue(new Blob(['<html>完整契約</html>'], { type: 'text/html;charset=utf-8' }));
    const controller = new AbortController();
    const pending = openContractPrintView('CASE-001', 'staff', 41, controller.signal);
    expect(window.open).toHaveBeenCalledWith('', '_blank');
    await vi.waitFor(() => expect(view.document.write).toHaveBeenCalledWith(expect.stringContaining('完整契約')));
    expect(view.print).not.toHaveBeenCalled();
    fontsReady();
    await pending;
    expect(get).toHaveBeenCalledWith('/api/v1/orders/CASE-001/contract-signing/staff-segments/41/print', expect.objectContaining({ signal: controller.signal, responseType: 'blob', cache: 'no-store' }));
    expect(view.print).toHaveBeenCalledOnce();
    button.dispatchEvent(new Event('click'));
    expect(view.print).toHaveBeenCalledTimes(2);
    expect(view.opener).toBeNull();
  });

  it('applies print rules and cell formatting without inline styles in the inherited CSP document', async () => {
    const { view } = popup();
    const html = '<html><head><style>@page{size:A4;margin:8mm}@media print{.print-controls{display:none}}</style></head><body><aside class="print-controls">列印提示</aside><table><tr><td style="background:#FCDCE9;font-size:14pt">示範客戶 &lt;td style=&quot;literal&quot;&gt; style=文字</td></tr></table></body></html>';
    vi.spyOn(transport, 'get').mockResolvedValue(new Blob([html], { type: 'text/html' }));

    await openContractPrintView('CASE-001', 'client', null, new AbortController().signal);

    const written = view.document.write.mock.calls[0][0] as string;
    const parsed = new DOMParser().parseFromString(written, 'text/html');
    expect(written).not.toContain('<style');
    expect(parsed.querySelectorAll('[style]')).toHaveLength(0);
    expect(written).toContain('data-contract-style="0"');
    expect(written).toContain('示範客戶');
    expect(parsed.body.textContent).toContain('<td style="literal"> style=文字');
    expect(view.document.adoptedStyleSheets).toHaveLength(1);
    expect(view.document.adoptedStyleSheets[0].replaceSync).toHaveBeenCalledWith(expect.stringContaining('@media print{.print-controls{display:none}}'));
    expect(view.document.adoptedStyleSheets[0].replaceSync).toHaveBeenCalledWith(expect.stringContaining('[data-contract-style="0"]{background:#FCDCE9;font-size:14pt}'));
  });

  it('reports popup blocking before making a request', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const get = vi.spyOn(transport, 'get');
    await expect(openContractPrintView('CASE-001', 'client', null, new AbortController().signal)).rejects.toThrow('封鎖列印視窗');
    expect(get).not.toHaveBeenCalled();
  });

  it('closes a failed or cancelled print window without printing stale case data', async () => {
    const { view } = popup();
    const get = vi.spyOn(transport, 'get').mockRejectedValue(new Error('讀取失敗'));
    await expect(openContractPrintView('CASE-001', 'client', null, new AbortController().signal)).rejects.toThrow('讀取失敗');
    expect(view.close).toHaveBeenCalledOnce();
    expect(view.print).not.toHaveBeenCalled();
    get.mockResolvedValue(new Blob(['完整契約'], { type: 'text/html' }));
    const controller = new AbortController();
    const pending = openContractPrintView('CASE-002', 'client', null, controller.signal);
    controller.abort();
    await pending;
    expect(view.print).not.toHaveBeenCalled();
    expect(view.document.write).not.toHaveBeenCalled();
  });
});
