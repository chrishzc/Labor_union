import { useRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSaveValidation } from '../../../../../../../components/useSaveValidation';

function Form({ onSave }: { onSave: () => void }) {
  const first = useRef<HTMLInputElement>(null);
  const second = useRef<HTMLInputElement>(null);
  const { validate, feedback } = useSaveValidation();
  return <div>
    <label>名稱<input ref={first} /></label>
    <details><summary>其他資料</summary><label>原因<input ref={second} /></label></details>
    {feedback}
    <button onClick={() => {
      if (validate([
        { value: first.current?.value, label: '名稱', ref: first },
        { value: second.current?.value, label: '原因', ref: second },
      ])) onSave();
    }}>儲存</button>
  </div>;
}

describe('儲存前的必填提示', () => {
  beforeEach(() => { window.alert = vi.fn(); });

  it('儲存可點擊，空白與空白字元會警告、標紅並定位第一個缺漏，補填後沿用原儲存', () => {
    const onSave = vi.fn();
    render(<Form onSave={onSave} />);
    const name = screen.getByLabelText('名稱');
    const reason = screen.getByLabelText('原因');
    const scroll = vi.fn();
    name.scrollIntoView = scroll;
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    expect(window.alert).toHaveBeenCalledWith('請填寫或選擇「名稱」後再儲存。');
    expect(screen.getByRole('alert').getAttribute('style')).toContain('var(--md-sys-color-error)');
    expect(name).toHaveFocus();
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(scroll).toHaveBeenCalledWith({ block: 'center', behavior: 'auto' });
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.input(name, { target: { value: '測試名稱' } });
    expect(name).not.toHaveAttribute('aria-invalid');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    fireEvent.input(reason, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    expect(window.alert).toHaveBeenLastCalledWith('請填寫或選擇「原因」後再儲存。');
    expect(reason.closest('details')).toHaveAttribute('open');
    expect(reason).toHaveFocus();
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.input(reason, { target: { value: '補登原因' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存' }));
    expect(onSave).toHaveBeenCalledOnce();
    expect(window.alert).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
