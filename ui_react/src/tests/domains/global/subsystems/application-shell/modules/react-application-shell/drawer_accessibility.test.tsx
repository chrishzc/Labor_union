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

    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(document.body).not.toHaveClass('modal-open');
    expect(trigger).toHaveFocus();
  });
});
