import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { Drawer } from '../../../../../../../components/Drawer';

function DrawerHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>開啟抽屜</button>
      <Drawer
        isOpen={open}
        onClose={() => setOpen(false)}
        title="測試抽屜"
        closeLabel="關閉測試抽屜"
        footer={<button type="button">最後操作</button>}
      >
        <input aria-label="抽屜欄位" />
      </Drawer>
    </>
  );
}

afterEach(() => {
  document.body.classList.remove('modal-open');
});

describe('Drawer 無障礙互動', () => {
  it('開啟時鎖定背景與移入焦點，Escape 關閉後把焦點還給觸發按鈕', async () => {
    render(<DrawerHarness />);
    const trigger = screen.getByRole('button', { name: '開啟抽屜' });
    trigger.focus();
    fireEvent.click(trigger);

    expect(screen.getByRole('dialog', { name: '測試抽屜' })).toBeInTheDocument();
    expect(document.body).toHaveClass('modal-open');
    await waitFor(() => expect(screen.getByRole('button', { name: '關閉測試抽屜' })).toHaveFocus());

    const escape = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true, bubbles: true });
    fireEvent(window, escape);
    expect(escape.defaultPrevented).toBe(true);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(document.body).not.toHaveClass('modal-open');
    expect(trigger).toHaveFocus();
  });

  it('closeDisabled 切換時不會重設焦點或跳到底部可聚焦元素，且仍依最新狀態控制 Escape', async () => {
    function BusyDrawerHarness() {
      const [open, setOpen] = useState(true);
      const [busy, setBusy] = useState(false);
      return (
        <Drawer
          isOpen={open}
          onClose={() => setOpen(false)}
          title="忙碌狀態抽屜"
          closeLabel="關閉忙碌狀態抽屜"
          closeDisabled={busy}
        >
          <input aria-label="抽屜欄位" disabled={busy} />
          <button type="button" disabled={busy} onClick={() => setBusy(true)}>模擬儲存</button>
          <button type="button" onClick={() => setBusy(false)}>模擬完成</button>
          <details>
            <summary tabIndex={0}>底部變更歷程</summary>
          </details>
        </Drawer>
      );
    }

    render(<BusyDrawerHarness />);
    const closeBtn = screen.getByRole('button', { name: '關閉忙碌狀態抽屜' });
    await waitFor(() => expect(closeBtn).toHaveFocus());

    const input = screen.getByLabelText('抽屜欄位');
    input.focus();
    expect(input).toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: '模擬儲存' }));
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));
    expect(screen.getByText('底部變更歷程')).not.toHaveFocus();

    const blockedEscape = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true, bubbles: true });
    fireEvent(window, blockedEscape);
    expect(blockedEscape.defaultPrevented).toBe(false);
    expect(screen.getByRole('dialog', { name: '忙碌狀態抽屜' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '模擬完成' }));
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));
    expect(closeBtn).not.toHaveFocus();
    expect(screen.getByText('底部變更歷程')).not.toHaveFocus();

    const allowedEscape = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true, bubbles: true });
    fireEvent(window, allowedEscape);
    expect(allowedEscape.defaultPrevented).toBe(true);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});
